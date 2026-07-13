"""M4 补充测试：本机 Agent、训练取消、模型构建与数据集配置。

现有 test_training_metrics.py 已覆盖训练配置校验、设备选择、训练执行/状态/
结果、训练失败、Validate 门禁与云端 /train 中转。本文件补齐人员 4 职责范围内
此前未覆盖的部分：

    local_agent/main.py          —— 本机 Agent HTTP 接口（/health、/devices、/validate）
    local_agent/agent_client.py  —— 云端指令处理（start/cancel/ping/请求-响应）
    local_agent/runtime/trainer.py       —— 训练取消（stop_training_job 与取消流程）
    local_agent/runtime/model_builder.py —— 由模型图构建可执行 PyTorch 模型的正确性
    local_agent/runtime/trainer.py（数据集部分）—— MNIST/FashionMNIST/CIFAR 配置与别名解析
    backend/cloud_training.py    —— 取消中转、Agent 在线状态查询、任务下发

说明：
- 与现有用例一致，不下载真实数据集、不依赖 GPU；训练相关用例用合成数据或打桩。
- Agent HTTP 接口用例直接调用路由处理函数（不依赖 TestClient/httpx）。
- Agent 客户端用例把后台训练线程打桩为 no-op，只验证指令分发与回执，不跑真实训练。
- 运行方式（在 softwareProject 目录下）：
      python -m unittest tests.M4_training_metrics.test_code.test_agent_training_extra -v
"""

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import torch
import torch.nn as nn

# 保证无论从哪个目录运行，都能 import 到 local_agent 和 backend 包
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# —————————————————————————————————————————————
# 公共测试夹具：模型图
# —————————————————————————————————————————————

def layer(layer_id, layer_type, params=None):
    return {"id": layer_id, "type": layer_type, "params": params or {}}


def connection(source, target):
    return {"source": source, "target": target}


def valid_cnn_graph():
    """能通过校验、可训练的最小 CNN（输入 [1,28,28]，输出 10 类）。"""
    return {
        "layers": [
            layer("input", "Input", {"shape": [1, 28, 28]}),
            layer("conv", "Conv2D", {"out_channels": 4, "kernel_size": 3, "stride": 1, "padding": 1}),
            layer("relu", "ReLU"),
            layer("pool", "Pooling", {"kernel_size": 2, "stride": 2, "padding": 0}),
            layer("flatten", "Flatten"),
            layer("linear", "Linear", {"out_features": 10}),
            layer("output", "Output"),
        ],
        "connections": [
            connection("input", "conv"),
            connection("conv", "relu"),
            connection("relu", "pool"),
            connection("pool", "flatten"),
            connection("flatten", "linear"),
            connection("linear", "output"),
        ],
    }


def mlp_graph():
    """输入 [784]、两层全连接、输出 10 类的 MLP。"""
    return {
        "layers": [
            layer("input", "Input", {"shape": [784]}),
            layer("fc1", "Linear", {"out_features": 64}),
            layer("relu", "ReLU"),
            layer("dropout", "Dropout", {"p": 0.25}),
            layer("fc2", "Linear", {"out_features": 10}),
            layer("output", "Output"),
        ],
        "connections": [
            connection("input", "fc1"),
            connection("fc1", "relu"),
            connection("relu", "dropout"),
            connection("dropout", "fc2"),
            connection("fc2", "output"),
        ],
    }


def lstm_graph():
    """序列输入 [12,8]、双向 LSTM、输出 4 类的序列模型。"""
    return {
        "layers": [
            layer("input", "Input", {"shape": [12, 8]}),
            layer("lstm", "LSTM", {"hidden_size": 16, "num_layers": 1, "return_sequences": False, "bidirectional": True}),
            layer("fc", "Linear", {"out_features": 4}),
            layer("output", "Output"),
        ],
        "connections": [
            connection("input", "lstm"),
            connection("lstm", "fc"),
            connection("fc", "output"),
        ],
    }


def add_branch_graph():
    """两分支逐元素相加合并（add）。"""
    return {
        "layers": [
            layer("input", "Input", {"shape": [4]}),
            layer("left", "Linear", {"out_features": 4}),
            layer("right", "Linear", {"out_features": 4}),
            layer("merge_relu", "ReLU", {"merge": "add"}),
            layer("output", "Output"),
        ],
        "connections": [
            connection("input", "left"),
            connection("input", "right"),
            connection("left", "merge_relu"),
            connection("right", "merge_relu"),
            connection("merge_relu", "output"),
        ],
    }


def concat_branch_graph():
    """两分支按维度拼接合并（concat，3+5=8），再接分类层输出 2 类。"""
    return {
        "layers": [
            layer("input", "Input", {"shape": [4]}),
            layer("left", "Linear", {"out_features": 3}),
            layer("right", "Linear", {"out_features": 5}),
            layer("merge_relu", "ReLU", {"merge": "concat", "dim": 1}),
            layer("classifier", "Linear", {"out_features": 2}),
            layer("output", "Output"),
        ],
        "connections": [
            connection("input", "left"),
            connection("input", "right"),
            connection("left", "merge_relu"),
            connection("right", "merge_relu"),
            connection("merge_relu", "classifier"),
            connection("classifier", "output"),
        ],
    }


def invalid_graph_missing_output():
    """缺少 Output 节点，无法通过结构校验。"""
    return {
        "layers": [
            layer("input", "Input", {"shape": [1, 28, 28]}),
            layer("flatten", "Flatten"),
        ],
        "connections": [connection("input", "flatten")],
    }


# —————————————————————————————————————————————
# 1. 本机 Agent HTTP 接口（local_agent/main.py）
# —————————————————————————————————————————————

class AgentHttpEndpointTests(unittest.TestCase):
    """直接调用 local_agent/main.py 的路由处理函数（不依赖 TestClient/httpx）。"""

    @classmethod
    def setUpClass(cls):
        from local_agent import main as agent_main
        from local_agent.runtime.schemas import ModelRequest
        cls.agent_main = agent_main
        cls.ModelRequest = ModelRequest

    def test_health_check_reports_ok_and_devices(self):
        """M4-024 /health 返回 status=ok、服务名与本机设备摘要。"""
        body = self.agent_main.health_check()
        self.assertEqual("ok", body["status"])
        self.assertEqual("VisualDL Local Training Agent", body["service"])
        # 设备摘要必含 cpu，且默认设备无 GPU 时为 cpu
        self.assertIn("cpu", body["devices"]["available_devices"])
        if not body["devices"]["cuda_available"]:
            self.assertEqual("cpu", body["devices"]["default_device"])

    def test_list_devices_returns_summary_with_cpu(self):
        """M4-025 /devices 返回 status=ok 并展开设备摘要（含 cpu、cuda 标志）。"""
        body = self.agent_main.list_devices()
        self.assertEqual("ok", body["status"])
        self.assertIn("cpu", body["available_devices"])
        self.assertIn("cuda_available", body)
        self.assertIsInstance(body["cuda_available"], bool)

    def test_validate_endpoint_accepts_valid_graph(self):
        """M4-026 /validate 对合法 CNN 图返回 valid=True。"""
        request = self.ModelRequest(model=valid_cnn_graph())
        report = self.agent_main.validate_model(request)
        self.assertTrue(report["valid"])
        self.assertEqual([], report["errors"])

    def test_validate_endpoint_rejects_invalid_graph(self):
        """M4-027 /validate 对缺少 Output 的图返回 valid=False 并带错误。"""
        request = self.ModelRequest(model=invalid_graph_missing_output())
        report = self.agent_main.validate_model(request)
        self.assertFalse(report["valid"])
        self.assertTrue(report["errors"])


# —————————————————————————————————————————————
# 2. Agent 客户端指令处理（local_agent/agent_client.py）
# —————————————————————————————————————————————

class AgentClientCommandTests(unittest.TestCase):
    """验证 handle_cloud_command 对云端各类指令的分发与回执。

    后台训练线程被打桩为不启动真实线程，只验证指令处理逻辑与状态机，
    不依赖 WebSocket 连接与真实训练。
    """

    @classmethod
    def setUpClass(cls):
        from local_agent import agent_client
        cls.agent_client = agent_client

    def setUp(self):
        # 每个用例前重置 Agent 运行态，避免任务映射互相污染
        self.agent_client.state.job_map.clear()
        self.agent_client.state.cancelled.clear()

    def tearDown(self):
        self.agent_client.state.job_map.clear()
        self.agent_client.state.cancelled.clear()

    def test_ping_command_returns_pong(self):
        """M4-028 收到 ping 指令返回 pong。"""
        response = self.agent_client.handle_cloud_command({"type": "ping"})
        self.assertEqual("pong", response["type"])

    def test_unknown_command_is_rejected(self):
        """M4-029 未知指令返回 accepted=False 的回执。"""
        response = self.agent_client.handle_cloud_command({"type": "no_such_command"})
        self.assertEqual("command_ack", response["type"])
        self.assertFalse(response["accepted"])

    def test_start_training_dispatches_and_acks(self):
        """M4-030 start_training 指令创建本机任务并返回 accepted=True 回执。"""
        # 打桩后台线程：只记录被启动，不真正跑训练
        with mock.patch.object(self.agent_client, "threading") as threading_mock:
            response = self.agent_client.handle_cloud_command({
                "type": "start_training",
                "job_id": "cloud_job_1",
                "model": valid_cnn_graph(),
                "train_config": {"epochs": 1, "batch_size": 10, "rate": 0.01, "device": "cpu"},
            })
            # 后台流式线程被创建并启动
            self.assertTrue(threading_mock.Thread.called)
            threading_mock.Thread.return_value.start.assert_called_once()

        self.assertEqual("command_ack", response["type"])
        self.assertEqual("start_training", response["command"])
        self.assertTrue(response["accepted"])
        # 云端 job_id 已映射到本机 runtime job_id
        self.assertIn("cloud_job_1", self.agent_client.state.job_map)
        self.assertEqual(response["local_job_id"], self.agent_client.state.job_map["cloud_job_1"])

    def test_start_training_with_invalid_config_returns_failure_ack(self):
        """M4-031 create_training_job 抛错时 start_training 返回 accepted=False。"""
        # train_config 缺少 epochs 会在 create_training_job 中 KeyError
        with mock.patch.object(self.agent_client, "send_training_update") as send_mock:
            response = self.agent_client.handle_cloud_command({
                "type": "start_training",
                "job_id": "cloud_job_bad",
                "model": valid_cnn_graph(),
                "train_config": {},  # 缺 epochs
            })
        self.assertEqual("command_ack", response["type"])
        self.assertFalse(response["accepted"])
        # 失败时向云端回传了 failed 结果
        self.assertTrue(send_mock.called)
        self.assertEqual("failed", send_mock.call_args[0][1])

    def test_cancel_training_acks_and_marks_cancelled(self):
        """M4-032 cancel_training 指令记录取消并调用 stop_training_job。"""
        self.agent_client.state.job_map["cloud_job_2"] = "local_job_2"
        with mock.patch.object(self.agent_client.runtime_trainer, "stop_training_job") as stop_mock:
            response = self.agent_client.handle_cloud_command({
                "type": "cancel_training",
                "job_id": "cloud_job_2",
            })
            stop_mock.assert_called_once_with("local_job_2")

        self.assertEqual("command_ack", response["type"])
        self.assertEqual("cancel_training", response["command"])
        self.assertTrue(response["accepted"])
        self.assertIn("cloud_job_2", self.agent_client.state.cancelled)

    def test_agent_request_devices_returns_summary(self):
        """M4-033 agent_request(devices) 返回本机设备摘要。"""
        response = self.agent_client.handle_cloud_command({
            "type": "agent_request",
            "request_id": "req_1",
            "action": "devices",
        })
        self.assertEqual("agent_response", response["type"])
        self.assertEqual("req_1", response["request_id"])
        self.assertTrue(response["ok"])
        self.assertIn("cpu", response["data"]["available_devices"])

    def test_agent_request_validate_returns_report(self):
        """M4-034 agent_request(validate) 返回结构校验结果。"""
        response = self.agent_client.handle_cloud_command({
            "type": "agent_request",
            "request_id": "req_2",
            "action": "validate",
            "payload": {"model": valid_cnn_graph()},
        })
        self.assertTrue(response["ok"])
        self.assertTrue(response["data"]["valid"])

    def test_agent_request_unknown_action_fails(self):
        """M4-035 agent_request 未知 action 返回 ok=False。"""
        response = self.agent_client.handle_cloud_command({
            "type": "agent_request",
            "request_id": "req_3",
            "action": "no_such_action",
        })
        self.assertEqual("agent_response", response["type"])
        self.assertFalse(response["ok"])
        self.assertIn("error", response)

    def test_build_hello_message_carries_agent_and_device_info(self):
        """M4-036 hello 注册消息包含 agent_id、运行时版本与设备摘要，且不含 token。"""
        message = self.agent_client.build_agent_hello_message(
            agent_id="agent_test",
            auth_token="secret-token",
            runtime_version="1.0.0",
            device_summary={"available_devices": ["cpu"]},
        )
        self.assertEqual("hello", message["type"])
        self.assertEqual("agent_test", message["agent_id"])
        self.assertEqual("1.0.0", message["runtime_version"])
        self.assertIn("device_summary", message)
        # 敏感 token 不应出现在 hello 消息体中
        self.assertNotIn("secret-token", str(message))

    def test_send_training_update_without_loop_is_noop(self):
        """M4-037 事件循环未就绪时 send_training_update 安全返回、不抛异常。"""
        saved_loop = self.agent_client.state.loop
        self.agent_client.state.loop = None
        try:
            # 不应抛异常
            self.agent_client.send_training_update("job", "running", {"type": "training_update"})
        finally:
            self.agent_client.state.loop = saved_loop


# —————————————————————————————————————————————
# 3. 训练取消链路（local_agent/runtime/trainer.py）
# —————————————————————————————————————————————

class TrainingCancellationTests(unittest.TestCase):
    """验证 stop_training_job 状态机与取消后训练流程的收尾。"""

    @classmethod
    def setUpClass(cls):
        from local_agent.runtime import trainer
        cls.trainer = trainer

    def setUp(self):
        self.trainer.TRANING_JOBS.clear()

    def tearDown(self):
        self.trainer.TRANING_JOBS.clear()

    def _create_job(self, epochs=2):
        return self.trainer.create_training_job(
            valid_cnn_graph(),
            {"epochs": epochs, "batch_size": 10, "rate": 0.01, "device": "cpu"},
        )["job_id"]

    def test_stop_pending_job_requests_cancel(self):
        """M4-038 取消一个 pending 任务：置 cancel_requested 并转入 cancelling。"""
        job_id = self._create_job()
        result = self.trainer.stop_training_job(job_id)

        self.assertTrue(result["cancelled"])
        self.assertEqual("cancelling", result["status"])
        self.assertTrue(self.trainer.TRANING_JOBS[job_id]["cancel_requested"])
        self.assertEqual("cancelling", self.trainer.TRANING_JOBS[job_id]["status"])

    def test_stop_finished_job_is_noop(self):
        """M4-039 取消一个已结束（completed）任务：不再取消，返回原状态。"""
        job_id = self._create_job()
        self.trainer.TRANING_JOBS[job_id]["status"] = "completed"
        result = self.trainer.stop_training_job(job_id)

        self.assertFalse(result["cancelled"])
        self.assertEqual("completed", result["status"])

    def test_stop_unknown_job_raises(self):
        """M4-040 取消不存在的任务应抛出 ValueError。"""
        with self.assertRaises(ValueError):
            self.trainer.stop_training_job("does_not_exist")

    def test_cancel_before_training_yields_cancelled_status(self):
        """M4-041 数据集准备阶段已请求取消：run_training_job 收尾为 cancelled，无指标。"""
        job_id = self._create_job(epochs=2)
        # 先请求取消，训练进入数据准备后立即命中取消检查
        self.trainer.stop_training_job(job_id)

        images = torch.randn(20, 1, 28, 28)
        labels = torch.randint(0, 10, (20,))
        dataset = torch.utils.data.TensorDataset(images, labels)
        loader = torch.utils.data.DataLoader(dataset, batch_size=10)

        with mock.patch.object(self.trainer, "prepare_dataset", return_value=(loader, loader)):
            result = self.trainer.run_training_job(job_id)

        self.assertEqual("cancelled", result["status"])
        self.assertEqual("cancelled", self.trainer.TRANING_JOBS[job_id]["status"])
        self.assertEqual([], self.trainer.TRANING_JOBS[job_id]["metrics"])


# —————————————————————————————————————————————
# 4. 模型构建正确性（local_agent/runtime/model_builder.py）
# —————————————————————————————————————————————

class ModelBuilderTests(unittest.TestCase):
    """验证由模型图构建的 PyTorch 模型层类型正确、前向输出维度符合预期。"""

    @classmethod
    def setUpClass(cls):
        from local_agent.runtime import model_builder
        cls.model_builder = model_builder

    def test_build_cnn_forward_output_shape(self):
        """M4-042 CNN 图构建后前向输出应为 [N, 10]。"""
        model = self.model_builder.build_model(valid_cnn_graph())
        output = model(torch.randn(2, 1, 28, 28))
        self.assertEqual((2, 10), tuple(output.shape))

    def test_build_mlp_forward_output_shape(self):
        """M4-043 MLP 图构建后前向输出应为 [N, 10]。"""
        model = self.model_builder.build_model(mlp_graph())
        output = model(torch.randn(4, 784))
        self.assertEqual((4, 10), tuple(output.shape))

    def test_build_lstm_forward_output_shape(self):
        """M4-044 双向 LSTM 图（输入 [12,8]）前向输出应为 [N, 4]。"""
        model = self.model_builder.build_model(lstm_graph())
        output = model(torch.randn(3, 12, 8))
        self.assertEqual((3, 4), tuple(output.shape))

    def test_build_add_branch_forward_output_shape(self):
        """M4-045 add 分支合并模型前向输出应为 [N, 4]（逐元素相加不改变维度）。"""
        model = self.model_builder.build_model(add_branch_graph())
        output = model(torch.randn(5, 4))
        self.assertEqual((5, 4), tuple(output.shape))

    def test_build_concat_branch_forward_output_shape(self):
        """M4-046 concat 分支合并（3+5=8）再分类，前向输出应为 [N, 2]。"""
        model = self.model_builder.build_model(concat_branch_graph())
        output = model(torch.randn(6, 4))
        self.assertEqual((6, 2), tuple(output.shape))

    def test_create_layer_builds_correct_torch_modules(self):
        """M4-047 create_layer 按层类型创建对应的 PyTorch 层并带正确参数。"""
        conv = self.model_builder.create_layer(
            layer("c", "Conv2D", {"out_channels": 8, "kernel_size": 3, "stride": 1, "padding": 1}),
            input_shape=[1, 28, 28],
        )
        self.assertIsInstance(conv, nn.Conv2d)
        self.assertEqual(1, conv.in_channels)
        self.assertEqual(8, conv.out_channels)

        linear = self.model_builder.create_layer(
            layer("l", "Linear", {"out_features": 10}), input_shape=[64]
        )
        self.assertIsInstance(linear, nn.Linear)
        self.assertEqual(64, linear.in_features)
        self.assertEqual(10, linear.out_features)

        pool = self.model_builder.create_layer(
            layer("p", "Pooling", {"kernel_size": 2, "stride": 2}), input_shape=[8, 28, 28]
        )
        self.assertIsInstance(pool, nn.MaxPool2d)

        dropout = self.model_builder.create_layer(
            layer("d", "Dropout", {"p": 0.3}), input_shape=[10]
        )
        self.assertIsInstance(dropout, nn.Dropout)
        self.assertAlmostEqual(0.3, dropout.p)

    def test_input_and_output_layers_have_no_module(self):
        """M4-048 Input/Output 端口层不产生 PyTorch 模块（返回 None）。"""
        self.assertIsNone(self.model_builder.create_layer(layer("i", "Input", {"shape": [1, 28, 28]})))
        self.assertIsNone(self.model_builder.create_layer(layer("o", "Output")))

    def test_extract_model_summary_counts_parameters(self):
        """M4-049 模型结构摘要应逐层列出并统计可训练参数量（>0）。"""
        model = self.model_builder.build_model(mlp_graph())
        summary = self.model_builder.extract_model_summary(model)

        self.assertGreater(summary["total_parameters"], 0)
        self.assertEqual(summary["total_parameters"], summary["trainable_parameters"])
        layer_types = [item["type"] for item in summary["layers"]]
        self.assertIn("Linear", layer_types)


# —————————————————————————————————————————————
# 5. 数据集配置与输入维度匹配（local_agent/runtime/trainer.py）
# —————————————————————————————————————————————

class DatasetConfigTests(unittest.TestCase):
    """验证内置数据集配置、别名解析、转换以及与模型输入维度的匹配。"""

    @classmethod
    def setUpClass(cls):
        from local_agent.runtime import trainer
        from local_agent.runtime import model_builder
        cls.trainer = trainer
        cls.model_builder = model_builder

    def test_builtin_datasets_registered(self):
        """M4-050 内置数据集规格应包含 MNIST/FashionMNIST/CIFAR10 等及其数据集类。"""
        specs = self.trainer.DATASET_SPECS
        for name in ("MNIST", "FashionMNIST", "CIFAR10"):
            self.assertIn(name, specs)
            self.assertIn("class", specs[name])

    def test_resolve_dataset_key_accepts_names_and_aliases(self):
        """M4-051 数据集名称与别名（大小写/连字符/下划线）都能解析到标准 key。"""
        resolve = self.trainer._resolve_dataset_key
        self.assertEqual("MNIST", resolve("MNIST"))
        self.assertEqual("MNIST", resolve("mnist"))
        self.assertEqual("FashionMNIST", resolve("fashion-mnist"))
        self.assertEqual("FashionMNIST", resolve("fashion_mnist"))
        self.assertEqual("CIFAR10", resolve("cifar-10"))
        self.assertEqual("CIFAR100", resolve("cifar100"))

    def test_resolve_unknown_dataset_raises(self):
        """M4-052 未知数据集名称应抛出 ValueError 并提示支持列表。"""
        with self.assertRaises(ValueError):
            self.trainer._resolve_dataset_key("ImageNet")

    def test_resolve_empty_dataset_name_raises(self):
        """M4-053 空数据集名称应抛出 ValueError。"""
        with self.assertRaises(ValueError):
            self.trainer._resolve_dataset_key("  ")

    def test_cifar_transform_normalizes_three_channels(self):
        """M4-054 CIFAR 使用含三通道 Normalize 的转换，灰度数据集使用 ToTensor。"""
        import torchvision

        cifar_transform = self.trainer._build_dataset_transform("CIFAR10")
        self.assertIsInstance(cifar_transform, torchvision.transforms.Compose)
        has_normalize = any(
            isinstance(t, torchvision.transforms.Normalize) for t in cifar_transform.transforms
        )
        self.assertTrue(has_normalize)

        mnist_transform = self.trainer._build_dataset_transform("MNIST")
        self.assertIsInstance(mnist_transform, torchvision.transforms.ToTensor)

    def test_mnist_input_dims_match_cnn_model(self):
        """M4-055 MNIST 输入 [1,28,28] 与 CNN 模型输入维度匹配（前向可跑通）。"""
        model = self.model_builder.build_model(valid_cnn_graph())
        # 模拟一个 batch 的 MNIST 数据（单通道 28x28）
        output = model(torch.randn(8, 1, 28, 28))
        self.assertEqual((8, 10), tuple(output.shape))

    def test_cifar_input_dims_match_cnn_model(self):
        """M4-056 CIFAR10 输入 [3,32,32] 与对应 CNN 模型输入维度匹配（前向可跑通）。"""
        cifar_cnn = {
            "layers": [
                layer("input", "Input", {"shape": [3, 32, 32]}),
                layer("conv", "Conv2D", {"out_channels": 6, "kernel_size": 3, "stride": 1, "padding": 1}),
                layer("relu", "ReLU"),
                layer("pool", "Pooling", {"kernel_size": 2, "stride": 2, "padding": 0}),
                layer("flatten", "Flatten"),
                layer("linear", "Linear", {"out_features": 10}),
                layer("output", "Output"),
            ],
            "connections": [
                connection("input", "conv"),
                connection("conv", "relu"),
                connection("relu", "pool"),
                connection("pool", "flatten"),
                connection("flatten", "linear"),
                connection("linear", "output"),
            ],
        }
        model = self.model_builder.build_model(cifar_cnn)
        output = model(torch.randn(4, 3, 32, 32))
        self.assertEqual((4, 10), tuple(output.shape))


# —————————————————————————————————————————————
# 6. 云端取消中转与 Agent 在线状态（backend/cloud_training.py）
# —————————————————————————————————————————————

class CloudCancelAndAgentStatusTests(unittest.TestCase):
    """直接调用 backend.cloud_training 的接口函数验证取消中转与在线状态查询。"""

    @classmethod
    def setUpClass(cls):
        from backend import cloud_training as ct
        from backend.schemas import CloudModelGraph, CloudTrainRequest
        cls.ct = ct
        cls.CloudModelGraph = CloudModelGraph
        cls.CloudTrainRequest = CloudTrainRequest

    def setUp(self):
        self.ct.registry.jobs.clear()
        self.ct.registry.agents.clear()
        self.ct.registry.clients.clear()
        self.ct.registry.agent_requests.clear()

    def tearDown(self):
        self.ct.registry.jobs.clear()
        self.ct.registry.agents.clear()
        self.ct.registry.clients.clear()
        self.ct.registry.agent_requests.clear()

    def _make_request(self):
        graph = valid_cnn_graph()
        model = self.CloudModelGraph(layers=graph["layers"], connections=graph["connections"])
        return self.CloudTrainRequest(
            model=model,
            train_config={"epochs": 2, "batch_size": 16, "rate": 0.01, "device": "cpu"},
        )

    def _create_job(self, user_id="user_1"):
        created = asyncio.run(self.ct.create_cloud_training_job(self._make_request(), user_id=user_id))
        return created["job_id"]

    def test_cancel_without_agent_marks_cancelled(self):
        """M4-057 无在线 Agent 时取消任务：云端直接标记 cancelled。"""
        job_id = self._create_job()
        result = asyncio.run(self.ct.cancel_cloud_training_job(job_id, user_id="user_1"))

        self.assertTrue(result["cancelled"])
        self.assertEqual("cancelled", result["status"])
        self.assertEqual("cancelled", self.ct.registry.jobs[job_id]["status"])

    def test_cancel_other_user_returns_404(self):
        """M4-058 取消他人任务应返回 404，不泄露任务信息。"""
        job_id = self._create_job(user_id="user_1")
        response = asyncio.run(self.ct.cancel_cloud_training_job(job_id, user_id="intruder"))
        self.assertEqual(404, response.status_code)

    def test_cancel_finished_job_is_noop(self):
        """M4-059 取消已结束任务返回 cancelled=False。"""
        job_id = self._create_job()
        self.ct.registry.jobs[job_id]["status"] = "completed"
        result = asyncio.run(self.ct.cancel_cloud_training_job(job_id, user_id="user_1"))
        self.assertFalse(result["cancelled"])
        self.assertEqual("completed", result["status"])

    def test_agent_status_offline_when_no_agent(self):
        """M4-060 无在线 Agent 时查询状态返回 online=False。"""
        status = self.ct.get_agent_status(user_id="nobody")
        self.assertFalse(status["online"])

    def test_agent_update_for_unknown_job_is_ignored(self):
        """M4-061 回传未知任务的进度应被忽略（accepted=False）。"""
        result = self.ct.handle_agent_training_update("agent_x", {
            "type": "training_update",
            "job_id": "job_does_not_exist",
            "status": "running",
        })
        self.assertFalse(result["accepted"])
        self.assertEqual("ignored", result["status"])

    def test_heartbeat_cleanup_removes_stale_agent_and_notifies_clients(self):
        """超时 Agent 被移除、连接被关闭，并向浏览器广播离线。"""
        websocket = mock.AsyncMock()
        session = self.ct.AgentSession("user_1", websocket)
        session.agent_id = "agent_stale"
        session.last_heartbeat_at = 100.0
        self.ct.registry.agents["user_1"] = session

        with mock.patch.object(
            self.ct.registry, "broadcast_to_clients", new=mock.AsyncMock()
        ) as broadcast:
            removed = asyncio.run(
                self.ct.cleanup_stale_agents(now=200.0, timeout_seconds=45.0)
            )

        self.assertEqual(["user_1"], removed)
        self.assertNotIn("user_1", self.ct.registry.agents)
        websocket.close.assert_awaited_once_with(code=1001, reason="Agent 心跳超时")
        broadcast.assert_awaited_once_with(
            "user_1", {"type": "agent_status", "online": False}
        )

    def test_heartbeat_cleanup_keeps_fresh_agent(self):
        """仍在心跳时限内的 Agent 不应被清理。"""
        websocket = mock.AsyncMock()
        session = self.ct.AgentSession("user_1", websocket)
        session.last_heartbeat_at = 180.0
        self.ct.registry.agents["user_1"] = session

        removed = asyncio.run(
            self.ct.cleanup_stale_agents(now=200.0, timeout_seconds=45.0)
        )

        self.assertEqual([], removed)
        self.assertIs(session, self.ct.registry.agents["user_1"])
        websocket.close.assert_not_awaited()

    def test_heartbeat_cleanup_does_not_offline_replacement_agent(self):
        """旧连接关闭期间若新 Agent 接管，不应把新会话广播为离线。"""
        stale_websocket = mock.AsyncMock()
        stale = self.ct.AgentSession("user_1", stale_websocket)
        stale.last_heartbeat_at = 100.0
        replacement = self.ct.AgentSession("user_1", mock.AsyncMock())
        replacement.last_heartbeat_at = 200.0
        self.ct.registry.agents["user_1"] = stale

        async def replace_on_close(**_kwargs):
            self.ct.registry.agents["user_1"] = replacement

        stale_websocket.close.side_effect = replace_on_close
        with mock.patch.object(
            self.ct.registry, "broadcast_to_clients", new=mock.AsyncMock()
        ) as broadcast:
            removed = asyncio.run(
                self.ct.cleanup_stale_agents(now=200.0, timeout_seconds=45.0)
            )

        self.assertEqual(["user_1"], removed)
        self.assertIs(replacement, self.ct.registry.agents["user_1"])
        broadcast.assert_not_awaited()

    def test_replaced_agent_messages_are_ignored(self):
        """被新会话覆盖的旧 Agent 即使还有在途消息，也不能继续更新任务。"""
        stale = self.ct.AgentSession("user_1", mock.AsyncMock())
        stale.agent_id = "agent_old"
        replacement = self.ct.AgentSession("user_1", mock.AsyncMock())
        replacement.agent_id = "agent_new"
        self.ct.registry.agents["user_1"] = replacement

        with mock.patch.object(
            self.ct, "handle_agent_training_update"
        ) as update, mock.patch.object(
            self.ct.registry, "broadcast_to_clients", new=mock.AsyncMock()
        ) as broadcast:
            asyncio.run(self.ct._handle_agent_message(stale, {
                "type": "training_update",
                "job_id": "job_1",
                "status": "running",
            }))

        update.assert_not_called()
        broadcast.assert_not_awaited()

    def test_agent_response_returns_only_to_originating_tab(self):
        """Agent RPC 响应通过代理 request_id 定向返回，不广播到其它标签页。"""
        agent_socket = mock.AsyncMock()
        session = self.ct.AgentSession("user_1", agent_socket)
        session.agent_id = "agent_current"
        self.ct.registry.agents["user_1"] = session

        first_tab = mock.AsyncMock()
        second_tab = mock.AsyncMock()
        self.ct.registry.add_client("user_1", first_tab)
        self.ct.registry.add_client("user_1", second_tab)

        asyncio.run(self.ct._handle_client_message(
            "user_1",
            first_tab,
            {
                "type": "agent_request",
                "request_id": "req_from_first_tab",
                "action": "devices",
                "payload": {},
            },
        ))

        forwarded = agent_socket.send_json.await_args.args[0]
        proxy_id = forwarded["request_id"]
        self.assertNotEqual("req_from_first_tab", proxy_id)

        asyncio.run(self.ct._handle_agent_message(session, {
            "type": "agent_response",
            "request_id": proxy_id,
            "ok": True,
            "data": {"available_devices": ["cpu"]},
        }))

        first_tab.send_json.assert_awaited_once()
        response = first_tab.send_json.await_args.args[0]
        self.assertEqual("req_from_first_tab", response["request_id"])
        self.assertTrue(response["ok"])
        second_tab.send_json.assert_not_awaited()
        self.assertNotIn(proxy_id, self.ct.registry.agent_requests)


if __name__ == "__main__":
    unittest.main()

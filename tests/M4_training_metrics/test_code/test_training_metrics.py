"""M4 训练与指标模块测试。

被测代码（本仓库真实路径）：
    local_agent/runtime/trainer.py       —— 训练任务创建、执行、状态/结果查询
    local_agent/runtime/model_builder.py —— 由模型图构建 PyTorch 模型
    local_agent/runtime/device.py        —— CPU/GPU 设备选择
    local_agent/runtime/schemas.py       —— TrainConfig 训练配置校验
    local_agent/runtime/validator.py     —— 结构校验（用于“未通过校验不允许训练”）
    backend/cloud_training.py            —— /train、/train/{job_id}/status、
                                            /train/{job_id}/result 中转接口

说明：
- 任务描述里的 backend/trainer.py、backend/model_builder.py 在本仓库实际位于
  local_agent/runtime/ 下（云端不执行 PyTorch，真实训练在本机 Agent 运行时）；
  main.py 中的 /train 系列接口实际由 backend/cloud_training.py 的 router 提供。
- 为避免下载 MNIST 数据集并缩短用时，训练相关用例用一个很小的合成数据集
  替换 trainer.prepare_dataset，只跑 CPU、极少样本，用来验证流程与返回格式，
  而不是验证真实收敛效果。
- 运行方式（在 softwareProject 目录下）：
      python -m pytest tests/M4_training_metrics/test_code/test_training_metrics.py
  或： python -m unittest tests.M4_training_metrics.test_code.test_training_metrics
"""

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import torch
import torch.utils.data

# 保证无论从哪个目录运行，都能 import 到 local_agent 和 backend 包
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from local_agent.runtime import trainer
from local_agent.runtime.device import (
    get_available_devices,
    is_cuda_available,
    resolve_device,
)
from local_agent.runtime.schemas import TrainConfig
from local_agent.runtime.validator import validate_model_graph


# —————————————————————————————————————————————
# 公共测试夹具：模型图、合成数据集
# —————————————————————————————————————————————

def layer(layer_id, layer_type, params=None):
    return {"id": layer_id, "type": layer_type, "params": params or {}}


def connection(source, target):
    return {"source": source, "target": target}


def valid_cnn_graph():
    """一个能通过校验、可训练的最小 CNN（输入 [1,28,28]，输出 10 类）。"""
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


def invalid_graph_missing_output():
    """缺少 Output 节点，无法通过结构校验。"""
    return {
        "layers": [
            layer("input", "Input", {"shape": [1, 28, 28]}),
            layer("flatten", "Flatten"),
        ],
        "connections": [connection("input", "flatten")],
    }


def make_tiny_loaders(num_samples=20, batch_size=10):
    """构造与 valid_cnn_graph 匹配的小型合成数据集 DataLoader。

    返回 (train_loader, test_loader)，形状 [N,1,28,28]，标签 0-9，
    用于替换真实 MNIST，让训练几秒内跑完且不触网。
    """
    images = torch.randn(num_samples, 1, 28, 28)
    labels = torch.randint(0, 10, (num_samples,))
    dataset = torch.utils.data.TensorDataset(images, labels)
    train_loader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=False)
    test_loader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=False)
    return train_loader, test_loader


class _JobsIsolationMixin(unittest.TestCase):
    """每个用例前后清空全局 TRANING_JOBS，避免任务互相污染。"""

    def setUp(self):
        super().setUp()
        trainer.TRANING_JOBS.clear()
        self._tmp_artifacts = tempfile.mkdtemp(prefix="m4_artifacts_")

    def tearDown(self):
        trainer.TRANING_JOBS.clear()
        super().tearDown()


# —————————————————————————————————————————————
# 1. 训练配置校验（合法 / 非法）
# —————————————————————————————————————————————

class TrainConfigValidationTests(unittest.TestCase):
    def test_valid_train_config_passes(self):
        """M4-001 合法训练配置应无任何校验错误。"""
        config = TrainConfig(
            dataset_name="MNIST",
            epochs=2,
            batch_size=32,
            rate=0.01,
            device="cpu",
            loss_fn="cross_entropy",
            optimizer="sgd",
        )
        self.assertEqual([], config.check_all())

    def test_non_positive_epochs_and_batch_size_are_invalid(self):
        """M4-002 epochs、batch_size 非正整数应报错。"""
        config = TrainConfig.model_construct(
            dataset_name="MNIST",
            epochs=0,
            batch_size=-1,
            rate=0.01,
            device="cpu",
            loss_fn="cross_entropy",
            optimizer="sgd",
        )
        errors = config.check_all()
        self.assertTrue(any("epochs" in e for e in errors))
        self.assertTrue(any("batch_size" in e for e in errors))

    def test_non_positive_rate_is_invalid(self):
        """M4-003 学习率必须为正数。"""
        config = TrainConfig.model_construct(
            dataset_name="MNIST", epochs=1, batch_size=32, rate=0.0,
            device="cpu", loss_fn="cross_entropy", optimizer="sgd",
        )
        self.assertTrue(any("rate" in e for e in config.check_all()))

    def test_empty_string_fields_are_invalid(self):
        """M4-004 dataset_name/device/loss_fn/optimizer 为空字符串应报错。"""
        config = TrainConfig.model_construct(
            dataset_name="  ", epochs=1, batch_size=32, rate=0.01,
            device="", loss_fn="", optimizer="",
        )
        errors = config.check_all()
        self.assertTrue(any("dataset_name" in e for e in errors))
        self.assertTrue(any("device" in e for e in errors))
        self.assertTrue(any("loss_fn" in e for e in errors))
        self.assertTrue(any("optimizer" in e for e in errors))


# —————————————————————————————————————————————
# 2. CPU/GPU 设备选择
# —————————————————————————————————————————————

class DeviceSelectionTests(unittest.TestCase):
    def test_available_devices_always_include_cpu(self):
        """M4-005 可用设备列表必含 cpu；有 CUDA 时含 cuda。"""
        devices = get_available_devices()
        self.assertIn("cpu", devices)
        if is_cuda_available():
            self.assertIn("cuda", devices)

    def test_resolve_cpu_returns_cpu(self):
        """M4-006 明确选择 cpu 时始终返回 CPU 设备。"""
        self.assertEqual("cpu", resolve_device("cpu").type)

    def test_resolve_gpu_and_auto_fall_back_without_cuda(self):
        """M4-007 无 CUDA 时，cuda/gpu/auto 均回退到 CPU；有 CUDA 时选 cuda。"""
        expected = "cuda" if is_cuda_available() else "cpu"
        self.assertEqual(expected, resolve_device("cuda").type)
        self.assertEqual(expected, resolve_device("gpu").type)
        self.assertEqual(expected, resolve_device("auto").type)

    def test_resolve_none_defaults_to_cpu(self):
        """M4-008 未指定设备时默认 CPU。"""
        self.assertEqual("cpu", resolve_device(None).type)


# —————————————————————————————————————————————
# 3. 训练任务创建
# —————————————————————————————————————————————

class CreateTrainingJobTests(_JobsIsolationMixin):
    def test_create_training_job_registers_pending_job(self):
        """M4-009 创建训练任务应登记为 pending 并返回 job_id。"""
        config = {"epochs": 3, "batch_size": 16, "rate": 0.01, "device": "cpu"}
        result = trainer.create_training_job(valid_cnn_graph(), config)

        self.assertIn("job_id", result)
        self.assertEqual("pending", result["status"])
        self.assertEqual(0, result["current_epoch"])
        self.assertEqual(3, result["total_epochs"])

        job = trainer.TRANING_JOBS[result["job_id"]]
        self.assertEqual("pending", job["status"])
        self.assertEqual([], job["metrics"])
        self.assertFalse(job["cancel_requested"])


# —————————————————————————————————————————————
# 4. 训练完成 / 状态查询 / 结果格式
# —————————————————————————————————————————————

class TrainingRunAndStatusTests(_JobsIsolationMixin):
    def _run_job(self, epochs=2):
        config = {
            "epochs": epochs,
            "batch_size": 10,
            "rate": 0.01,
            "device": "cpu",
            "artifacts_dir": self._tmp_artifacts,
        }
        created = trainer.create_training_job(valid_cnn_graph(), config)
        job_id = created["job_id"]
        with mock.patch.object(trainer, "prepare_dataset", return_value=make_tiny_loaders()):
            trainer.run_training_job(job_id)
        return job_id

    def test_training_completes_and_records_per_epoch_metrics(self):
        """M4-010 训练完成后状态为 completed，且逐轮 metrics 数量与 epochs 一致。"""
        job_id = self._run_job(epochs=2)
        job = trainer.TRANING_JOBS[job_id]

        self.assertEqual("completed", job["status"])
        self.assertEqual(2, len(job["metrics"]))
        for epoch_index, epoch_metrics in enumerate(job["metrics"], start=1):
            self.assertEqual(epoch_index, epoch_metrics["epoch"])
            self.assertIn("train", epoch_metrics)
            self.assertIn("eval", epoch_metrics)

    def test_status_query_returns_progress_and_fields(self):
        """M4-011 完成后状态查询返回完整字段，进度为 1.0。"""
        job_id = self._run_job(epochs=2)
        status = trainer.get_job_status(job_id)

        for key in ("job_id", "status", "current_epoch", "total_epochs",
                    "current_step", "total_steps", "progress", "metrics", "error"):
            self.assertIn(key, status)
        self.assertEqual("completed", status["status"])
        self.assertEqual(2, status["current_epoch"])
        self.assertEqual(1.0, status["progress"])
        self.assertIsNone(status["error"])

    def test_result_loss_accuracy_format(self):
        """M4-012 结果 loss/accuracy 为浮点数，metrics 每轮含 train/eval 的 loss 与 accuracy。"""
        job_id = self._run_job(epochs=2)
        result = trainer.get_job_result(job_id)

        self.assertEqual("completed", result["status"])
        self.assertIsInstance(result["loss"], float)
        self.assertIsInstance(result["accuracy"], float)
        self.assertEqual("cpu", result["device"])
        self.assertIsNotNone(result["artifacts"])

        last_epoch = result["metrics"][-1]
        for split in ("train", "eval"):
            self.assertIsInstance(last_epoch[split]["loss"], float)
            self.assertIsInstance(last_epoch[split]["accuracy"], float)
            self.assertGreaterEqual(last_epoch[split]["accuracy"], 0.0)
            self.assertLessEqual(last_epoch[split]["accuracy"], 1.0)

    def test_artifacts_are_saved_to_disk(self):
        """M4-013 训练产物（模型权重、指标）应写入磁盘。"""
        job_id = self._run_job(epochs=1)
        artifacts = trainer.TRANING_JOBS[job_id]["result"]["artifacts"]
        self.assertTrue(os.path.isfile(artifacts["model_path"]))
        self.assertTrue(os.path.isfile(artifacts["metrics_path"]))

    def test_status_of_unknown_job_raises(self):
        """M4-014 查询不存在的任务应抛出 ValueError。"""
        with self.assertRaises(ValueError):
            trainer.get_job_status("does_not_exist")
        with self.assertRaises(ValueError):
            trainer.get_job_result("does_not_exist")


# —————————————————————————————————————————————
# 5. 训练失败
# —————————————————————————————————————————————

class TrainingFailureTests(_JobsIsolationMixin):
    def test_training_failure_marks_job_failed_and_records_error(self):
        """M4-015 训练过程中抛异常时，任务状态置为 failed 并记录错误信息。"""
        config = {"epochs": 1, "batch_size": 10, "rate": 0.01, "device": "cpu"}
        created = trainer.create_training_job(valid_cnn_graph(), config)
        job_id = created["job_id"]

        # 模拟本机训练时模型构建/前向失败
        with mock.patch.object(trainer, "build_model", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                trainer.run_training_job(job_id)

        job = trainer.TRANING_JOBS[job_id]
        self.assertEqual("failed", job["status"])
        self.assertIsNotNone(job["error"])

        result = trainer.get_job_result(job_id)
        self.assertEqual("failed", result["status"])
        self.assertIsNotNone(result["error"])
        # 未产生有效指标时 loss/accuracy 为 None
        self.assertIsNone(result["loss"])
        self.assertIsNone(result["accuracy"])


# —————————————————————————————————————————————
# 6. 未通过 Validate 不允许训练
# —————————————————————————————————————————————

class ValidateGatingTests(_JobsIsolationMixin):
    def test_invalid_graph_fails_validation(self):
        """M4-016 结构非法的模型图在校验阶段即被拒绝（valid=False）。"""
        report = validate_model_graph(invalid_graph_missing_output())
        self.assertFalse(report["valid"])
        self.assertTrue(report["errors"])

    def test_valid_graph_passes_validation(self):
        """M4-017 结构合法的模型图校验通过，可进入训练。"""
        report = validate_model_graph(valid_cnn_graph())
        self.assertTrue(report["valid"])
        self.assertEqual([], report["errors"])

    def test_training_an_unvalidated_invalid_graph_fails(self):
        """M4-018 若跳过校验直接用非法模型图训练，训练会失败（说明必须先通过校验）。"""
        config = {"epochs": 1, "batch_size": 10, "rate": 0.01, "device": "cpu"}
        created = trainer.create_training_job(invalid_graph_missing_output(), config)
        job_id = created["job_id"]

        with mock.patch.object(trainer, "prepare_dataset", return_value=make_tiny_loaders()):
            with self.assertRaises(Exception):
                trainer.run_training_job(job_id)

        self.assertEqual("failed", trainer.TRANING_JOBS[job_id]["status"])


# —————————————————————————————————————————————
# 7. 云端中转接口 /train、/status、/result
# —————————————————————————————————————————————

class CloudTrainingApiTests(unittest.TestCase):
    """直接调用 backend.cloud_training 的接口函数（不依赖 TestClient/httpx）。"""

    @classmethod
    def setUpClass(cls):
        # cloud_training 依赖 backend.security（python-jose），单独导入避免
        # 触发 backend.main 里 sqlalchemy 等未安装依赖。
        from backend import cloud_training as ct
        from backend.schemas import CloudModelGraph, CloudTrainRequest
        cls.ct = ct
        cls.CloudModelGraph = CloudModelGraph
        cls.CloudTrainRequest = CloudTrainRequest

    def setUp(self):
        self.ct.registry.jobs.clear()
        self.ct.registry.agents.clear()

    def tearDown(self):
        self.ct.registry.jobs.clear()
        self.ct.registry.agents.clear()

    def _make_request(self):
        graph = valid_cnn_graph()
        model = self.CloudModelGraph(layers=graph["layers"], connections=graph["connections"])
        return self.CloudTrainRequest(
            model=model,
            train_config={"epochs": 2, "batch_size": 16, "rate": 0.01, "device": "cpu"},
        )

    def test_create_job_without_agent_reports_offline(self):
        """M4-019 无在线 Agent 时创建训练任务，返回 no_agent/offline 并登记任务。"""
        request = self._make_request()
        result = asyncio.run(self.ct.create_cloud_training_job(request, user_id="user_1"))

        self.assertEqual("ok", result["status"])
        self.assertEqual("no_agent", result["job_status"])
        self.assertEqual("offline", result["agent_status"])
        self.assertIn(result["job_id"], self.ct.registry.jobs)

    def test_status_query_returns_registered_fields(self):
        """M4-020 状态查询返回 job_id、status、epoch、progress、metrics 等字段。"""
        request = self._make_request()
        created = asyncio.run(self.ct.create_cloud_training_job(request, user_id="user_1"))
        job_id = created["job_id"]

        status = self.ct.get_cloud_training_status(job_id, user_id="user_1")
        for key in ("job_id", "status", "current_epoch", "total_epochs",
                    "current_step", "total_steps", "progress", "metrics", "error"):
            self.assertIn(key, status)
        self.assertEqual(job_id, status["job_id"])
        self.assertEqual(2, status["total_epochs"])

    def test_status_query_for_other_user_returns_404(self):
        """M4-021 用非任务所属用户查询状态应返回 404。"""
        request = self._make_request()
        created = asyncio.run(self.ct.create_cloud_training_job(request, user_id="user_1"))
        response = self.ct.get_cloud_training_status(created["job_id"], user_id="other_user")
        self.assertEqual(404, response.status_code)

    def test_result_query_before_completion_has_null_metrics(self):
        """M4-022 任务尚未回传结果时，result 的 loss/accuracy 为 None。"""
        request = self._make_request()
        created = asyncio.run(self.ct.create_cloud_training_job(request, user_id="user_1"))
        result = self.ct.get_cloud_training_result(created["job_id"], user_id="user_1")

        self.assertEqual(created["job_id"], result["job_id"])
        self.assertIsNone(result["loss"])
        self.assertIsNone(result["accuracy"])
        self.assertEqual([], result["metrics"])

    def test_agent_update_flows_into_status_and_result(self):
        """M4-023 Agent 回传进度/结果后，status 与 result 反映最新 loss/accuracy。"""
        request = self._make_request()
        created = asyncio.run(self.ct.create_cloud_training_job(request, user_id="user_1"))
        job_id = created["job_id"]

        # 模拟本机 Agent 回传最终训练结果
        self.ct.handle_agent_training_update("agent_x", {
            "type": "training_result",
            "job_id": job_id,
            "status": "completed",
            "current_epoch": 2,
            "total_epochs": 2,
            "progress": 1.0,
            "metrics": [
                {"epoch": 1, "train": {"loss": 1.0, "accuracy": 0.5}, "eval": {"loss": 1.1, "accuracy": 0.45}},
                {"epoch": 2, "train": {"loss": 0.6, "accuracy": 0.75}, "eval": {"loss": 0.7, "accuracy": 0.70}},
            ],
            "loss": 0.7,
            "accuracy": 0.70,
            "device": "cuda",
        })

        status = self.ct.get_cloud_training_status(job_id, user_id="user_1")
        self.assertEqual("completed", status["status"])
        self.assertEqual(1.0, status["progress"])
        self.assertEqual(2, len(status["metrics"]))

        result = self.ct.get_cloud_training_result(job_id, user_id="user_1")
        self.assertEqual("completed", result["status"])
        self.assertEqual(0.7, result["loss"])
        self.assertEqual(0.70, result["accuracy"])
        self.assertEqual("cuda", result["device"])


if __name__ == "__main__":
    unittest.main()

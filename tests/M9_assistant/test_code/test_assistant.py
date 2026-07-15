"""AI 助手后端模块测试。

所有大模型和浏览器交互均使用内存替身，不访问 OpenAI API，也不需要启动前端。
"""

import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import backend.assistant as assistant


NEW_BROWSER_COMMANDS = {
    "get_train_config",
    "get_training_result",
    "wait_training",
    "get_system_status",
    "set_dataset",
    "set_train_config",
    "stop_training",
    "save_model",
    "clear_canvas",
}


class FakeWebSocket:
    def __init__(self):
        self.sent = []

    async def send_json(self, message):
        self.sent.append(message)


class TestCommandDefinitions(unittest.TestCase):
    def test_specs_have_unique_names_and_required_fields(self):
        specs = assistant.command_specs()
        names = [item["name"] for item in specs]

        self.assertEqual(len(names), len(set(names)))
        self.assertIn("get_model_graph", names)
        self.assertIn("load_template", names)
        self.assertIn("help", names)
        for spec in specs:
            self.assertIn(spec["category"], {"read", "write", "meta"})
            self.assertIn(spec["runs_on"], {"browser", "backend"})
            self.assertIsInstance(spec["params"], list)

    def test_all_new_commands_are_exposed_as_browser_tools(self):
        specs = {item["name"]: item for item in assistant.command_specs()}

        self.assertTrue(NEW_BROWSER_COMMANDS.issubset(specs))
        for name in NEW_BROWSER_COMMANDS:
            self.assertEqual(specs[name]["runs_on"], "browser")

    def test_new_command_parameter_schemas(self):
        tools = {
            tool["function"]["name"]: tool["function"]["parameters"]
            for tool in assistant.build_command_tools()
        }

        self.assertEqual(tools["set_dataset"]["required"], ["name"])
        self.assertEqual(tools["set_dataset"]["properties"]["name"]["type"], "string")
        train = tools["set_train_config"]
        self.assertEqual(train["required"], [])
        self.assertEqual(set(train["properties"]), {
            "epochs", "batch_size", "rate", "optimizer", "loss_fn", "device",
        })
        self.assertEqual(train["properties"]["epochs"]["type"], "integer")
        self.assertEqual(train["properties"]["rate"]["type"], "number")
        for name in ("get_train_config", "get_training_result", "get_system_status", "stop_training"):
            self.assertEqual(tools[name]["properties"], {})
            self.assertEqual(tools[name]["required"], [])
        self.assertEqual(tools["wait_training"]["required"], [])
        self.assertEqual(tools["wait_training"]["properties"]["timeout_seconds"]["type"], "integer")
        self.assertEqual(tools["save_model"]["required"], ["name"])
        self.assertEqual(set(tools["save_model"]["properties"]), {"name", "description"})

    def test_tools_use_openai_function_call_format(self):
        tools = assistant.build_command_tools()
        by_name = {tool["function"]["name"]: tool for tool in tools}

        self.assertEqual(len(tools), len(assistant.command_specs()))
        self.assertTrue(all(tool["type"] == "function" for tool in tools))
        load_template = by_name["load_template"]["function"]["parameters"]
        self.assertEqual(load_template["type"], "object")
        self.assertEqual(load_template["required"], ["key"])
        self.assertEqual(load_template["properties"]["key"]["type"], "string")
        self.assertFalse(load_template["additionalProperties"])

    def test_help_is_derived_from_specs(self):
        help_text = assistant.build_help_text()
        for spec in assistant.command_specs():
            self.assertIn(spec["name"], help_text)
            self.assertIn(spec["usage"], help_text)

    def test_system_prompt_contains_project_summary(self):
        prompt = assistant.build_system_prompt("当前为 LeNet，校验通过。")
        self.assertIn("模型工坊", prompt)
        self.assertIn("当前为 LeNet，校验通过。", prompt)
        self.assertIn("delete_node", prompt)
        self.assertIn("wait_training", prompt)
        self.assertIn("save_model", prompt)
        self.assertIn("严禁忙等", prompt)
        self.assertIn("反复调用 get_training_result", prompt)

    def test_project_snapshot_summary(self):
        text = assistant.summarize_project_snapshot({
            "model": {
                "layers": [{"type": "Input"}, {"type": "Conv2D"}, {"type": "Output"}],
                "connections": [{"source": "a", "target": "b"}],
            },
            "validation": {"valid": True, "errors": [], "warnings": ["提示"]},
            "training_config": {"dataset": "MNIST", "epochs": 5},
        })
        self.assertIn("3 个层", text)
        self.assertIn("Input → Conv2D → Output", text)
        self.assertIn("校验通过", text)
        self.assertIn("数据集=MNIST", text)


class TestConnectionAndHub(unittest.IsolatedAsyncioTestCase):
    async def test_pending_call_can_be_resolved(self):
        connection = assistant.AssistantConnection("user_1", FakeWebSocket())
        future = connection.make_pending_call("call_1")

        connection.resolve_pending_call("call_1", {"ok": True, "result": 42})

        self.assertEqual(await future, {"ok": True, "result": 42})
        self.assertNotIn("call_1", connection._pending_calls)

    async def test_unknown_or_duplicate_result_is_ignored(self):
        connection = assistant.AssistantConnection("user_1", FakeWebSocket())
        connection.resolve_pending_call("missing", {"ok": True})
        connection.resolve_pending_call("missing", {"ok": True})
        self.assertEqual(connection._pending_calls, {})

    async def test_execute_command_round_trip(self):
        local_hub = assistant.AssistantHub()
        websocket = FakeWebSocket()
        connection = assistant.AssistantConnection("user_1", websocket)
        local_hub.register("user_1", connection)

        task = asyncio.create_task(local_hub.execute_command_in_browser(
            "user_1", "load_template", {"key": "lenet"}, timeout=1,
        ))
        await asyncio.sleep(0)
        request = websocket.sent[0]
        connection.resolve_pending_call(request["call_id"], {
            "ok": True, "result": {"template": "lenet"}, "error": None,
        })

        self.assertEqual((await task)["result"]["template"], "lenet")
        self.assertEqual(request["type"], "tool_request")
        self.assertEqual(request["command"], "load_template")
        self.assertEqual(request["args"], {"key": "lenet"})

    async def test_execute_command_without_connection_fails_cleanly(self):
        result = await assistant.AssistantHub().execute_command_in_browser(
            "offline", "list_nodes", {},
        )
        self.assertFalse(result["ok"])
        self.assertIn("未连接", result["error"])

    async def test_execute_command_timeout_cleans_pending_future(self):
        local_hub = assistant.AssistantHub()
        connection = assistant.AssistantConnection("user_1", FakeWebSocket())
        local_hub.register("user_1", connection)

        result = await local_hub.execute_command_in_browser(
            "user_1", "list_nodes", {}, timeout=0.001,
        )

        self.assertFalse(result["ok"])
        self.assertIn("超时", result["error"])
        self.assertEqual(connection._pending_calls, {})

    async def test_unregister_only_removes_matching_connection(self):
        local_hub = assistant.AssistantHub()
        old = assistant.AssistantConnection("user_1", FakeWebSocket())
        new = assistant.AssistantConnection("user_1", FakeWebSocket())
        local_hub.register("user_1", old)
        local_hub.register("user_1", new)

        local_hub.unregister("user_1", old)
        self.assertIs(local_hub.connection_for("user_1"), new)


class TestToolHandling(unittest.IsolatedAsyncioTestCase):
    async def test_help_runs_locally(self):
        with patch.object(assistant.hub, "execute_command_in_browser", new=AsyncMock()) as execute:
            result = await assistant.handle_tool_use("user_1", "help", {})
        self.assertTrue(result["ok"])
        self.assertIn("模型工坊可用命令", result["result"])
        execute.assert_not_awaited()

    async def test_browser_tool_is_forwarded(self):
        expected = {"ok": True, "result": ["node_1"], "error": None}
        with patch.object(
            assistant.hub, "execute_command_in_browser", new=AsyncMock(return_value=expected),
        ) as execute:
            result = await assistant.handle_tool_use("user_1", "list_nodes", {})
        self.assertEqual(result, expected)
        execute.assert_awaited_once_with("user_1", "list_nodes", {})

    async def test_each_new_browser_tool_is_forwarded_without_renaming(self):
        arguments = {
            "get_train_config": {},
            "get_training_result": {},
            "wait_training": {"timeout_seconds": 60},
            "get_system_status": {},
            "set_dataset": {"name": "CIFAR10"},
            "set_train_config": {"epochs": 10, "rate": 0.001, "device": "cpu"},
            "stop_training": {},
            "save_model": {"name": "LeNet", "description": "test"},
        }
        with patch.object(
            assistant.hub,
            "execute_command_in_browser",
            new=AsyncMock(return_value={"ok": True, "result": None}),
        ) as execute:
            for name, args in arguments.items():
                result = await assistant.handle_tool_use("user_1", name, args)
                self.assertTrue(result["ok"])

        self.assertEqual(execute.await_count, len(arguments))
        for name, args in arguments.items():
            if name == "wait_training":
                self.assertIn(
                    unittest.mock.call("user_1", name, args, timeout=70),
                    execute.await_args_list,
                )
            else:
                self.assertIn(unittest.mock.call("user_1", name, args), execute.await_args_list)

    async def test_wait_training_rejects_invalid_timeout(self):
        with patch.object(assistant.hub, "execute_command_in_browser", new=AsyncMock()) as execute:
            result = await assistant.handle_tool_use(
                "user_1", "wait_training", {"timeout_seconds": 7201},
            )
        self.assertFalse(result["ok"])
        self.assertIn("1~7200", result["error"])
        execute.assert_not_awaited()

    async def test_unknown_tool_is_rejected(self):
        result = await assistant.handle_tool_use("user_1", "does_not_exist", {})
        self.assertFalse(result["ok"])
        self.assertIn("未知命令", result["error"])


def openai_response(content="", tool_calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
        content=content,
        tool_calls=tool_calls or [],
    ))])


def openai_tool_call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


class TestAssistantTurn(unittest.IsolatedAsyncioTestCase):
    async def test_plain_answer_is_sent_and_added_to_history(self):
        client = Mock()
        client.chat.completions.create.return_value = openai_response("这是最终答案。")
        websocket = FakeWebSocket()
        connection = assistant.AssistantConnection("user_1", websocket)
        history = []

        with patch.object(assistant, "create_openai_client", return_value=client):
            result = await assistant.run_assistant_turn(
                connection, "什么是卷积？", history, "当前项目为空。",
                model="test-model", api_key="test-key", base_url="https://example.test/v1",
            )

        self.assertEqual(result, "这是最终答案。")
        self.assertEqual(history[-1], {"role": "assistant", "content": "这是最终答案。"})
        self.assertTrue(websocket.sent[-1]["final"])
        request = client.chat.completions.create.call_args.kwargs
        self.assertEqual(request["messages"][0]["role"], "system")
        self.assertIn("当前项目为空。", request["messages"][0]["content"])
        self.assertEqual(request["tools"][0]["type"], "function")
        self.assertEqual(request["model"], "test-model")

    async def test_tool_call_result_is_returned_to_openai(self):
        tool_call = openai_tool_call("call_1", "list_nodes", "{}")
        client = Mock()
        client.chat.completions.create.side_effect = [
            openai_response(tool_calls=[tool_call]),
            openai_response("画布中有一个输入节点。"),
        ]
        connection = assistant.AssistantConnection("user_1", FakeWebSocket())

        with (
            patch.object(assistant, "create_openai_client", return_value=client) as create_client,
            patch.object(
                assistant, "handle_tool_use",
                new=AsyncMock(return_value={"ok": True, "result": [{"id": "input_1"}], "error": None}),
            ) as execute,
        ):
            result = await assistant.run_assistant_turn(
                connection, "看看画布", [],
                model="test-model", api_key="test-key", base_url="https://example.test/v1",
            )

        self.assertEqual(result, "画布中有一个输入节点。")
        execute.assert_awaited_once_with("user_1", "list_nodes", {})
        second_messages = client.chat.completions.create.call_args_list[1].kwargs["messages"]
        tool_message = next(message for message in second_messages if message["role"] == "tool")
        self.assertEqual(tool_message["tool_call_id"], "call_1")
        self.assertTrue(json.loads(tool_message["content"])["ok"])
        create_client.assert_called_once_with("test-key", "https://example.test/v1")

    async def test_invalid_tool_arguments_are_reported_to_model(self):
        tool_call = openai_tool_call("bad_call", "list_nodes", "not-json")
        client = Mock()
        client.chat.completions.create.side_effect = [
            openai_response(tool_calls=[tool_call]),
            openai_response("工具参数无效，未执行。"),
        ]
        connection = assistant.AssistantConnection("user_1", FakeWebSocket())

        with (
            patch.object(assistant, "create_openai_client", return_value=client),
            patch.object(assistant, "handle_tool_use", new=AsyncMock()) as execute,
        ):
            await assistant.run_assistant_turn(
                connection, "测试", [],
                model="test-model", api_key="test-key", base_url="https://example.test/v1",
            )

        execute.assert_not_awaited()
        messages = client.chat.completions.create.call_args_list[1].kwargs["messages"]
        error_payload = json.loads(next(m for m in messages if m["role"] == "tool")["content"])
        self.assertFalse(error_payload["ok"])
        self.assertIn("参数无效", error_payload["error"])

    async def test_empty_user_message_is_rejected_before_client_creation(self):
        with patch.object(assistant, "create_openai_client") as create_client:
            with self.assertRaises(ValueError):
                await assistant.run_assistant_turn(
                    assistant.AssistantConnection("user_1", FakeWebSocket()), "  ", [],
                )
        create_client.assert_not_called()

    async def test_missing_model_configuration_does_not_call_openai(self):
        connection = assistant.AssistantConnection("user_1", FakeWebSocket())
        with patch.object(assistant, "create_openai_client") as create_client:
            result = await assistant.run_assistant_turn(
                connection, "查看系统状态", [], model="", api_key="", base_url="",
            )

        create_client.assert_not_called()
        self.assertIn("配置模型", result)
        self.assertTrue(connection.websocket.sent[-1]["final"])


class TestFrontendCommandContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parent.parent.parent.parent
        cls.dispatcher = (root / "frontend" / "src" / "assistant.ts").read_text(encoding="utf-8")
        cls.panel = (root / "frontend" / "src" / "components" / "AssistantPanel.vue").read_text(encoding="utf-8")
        cls.command_help = json.loads(
            (root / "frontend" / "src" / "assistantHelp.json").read_text(encoding="utf-8")
        )

    def test_every_backend_browser_command_has_frontend_switch_case(self):
        browser_commands = {
            spec["name"] for spec in assistant.command_specs()
            if spec["runs_on"] == "browser"
        }
        missing = {
            name for name in browser_commands
            if f'case "{name}"' not in self.dispatcher
        }
        self.assertEqual(missing, set(), f"前端缺少命令分发：{sorted(missing)}")

    def test_new_commands_are_listed_in_command_help(self):
        help_names = {item["name"] for item in self.command_help["commands"]}
        missing = NEW_BROWSER_COMMANDS - help_names
        self.assertEqual(missing, set(), f"命令面板帮助缺少：{sorted(missing)}")

    def test_save_model_is_available_to_direct_user_commands(self):
        self.assertIn("parseCommandLine", self.panel)
        self.assertIn("executeAssistantCommand(parsed.command, parsed.args)", self.panel)
        self.assertIn('case "save_model"', self.dispatcher)

    def test_command_and_ai_paths_share_the_same_dispatcher(self):
        self.assertIn("executeAssistantCommand(parsed.command, parsed.args)", self.panel)
        self.assertIn("executeAssistantCommand(command, args)", self.panel)


class TestAuthentication(unittest.TestCase):
    def test_verify_token_returns_existing_user_id(self):
        fake_security = SimpleNamespace(verify_access_token=Mock(return_value={"sub": "user_1"}))
        fake_auth = SimpleNamespace(get_user=Mock(return_value={"id": "user_1"}))
        with patch.dict(sys.modules, {
            "backend.security": fake_security,
            "backend.auth": fake_auth,
        }):
            self.assertEqual(assistant.verify_assistant_token("valid-token"), "user_1")

    def test_verify_token_rejects_missing_user(self):
        fake_security = SimpleNamespace(verify_access_token=Mock(return_value={"sub": "deleted"}))
        fake_auth = SimpleNamespace(get_user=Mock(return_value=None))
        with patch.dict(sys.modules, {
            "backend.security": fake_security,
            "backend.auth": fake_auth,
        }):
            with self.assertRaises(ValueError):
                assistant.verify_assistant_token("valid-token")


class TestRouterRegistration(unittest.TestCase):
    def test_assistant_router_exposes_websocket_path(self):
        paths = {route.path for route in assistant.router.routes}
        self.assertIn("/assistant/ws", paths)


if __name__ == "__main__":
    unittest.main()

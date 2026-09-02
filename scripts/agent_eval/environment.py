import copy
from typing import Any, Dict, Optional

from scripts.agent_eval.task_io import target_state_of


TYPE_CHECKS = {
    "string": lambda value: isinstance(value, str),
    "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
    "bool": lambda value: isinstance(value, bool),
    "boolean": lambda value: isinstance(value, bool),
    "list": lambda value: isinstance(value, list),
    "array": lambda value: isinstance(value, list),
    "object": lambda value: isinstance(value, dict),
}


class MockDatabase:
    def __init__(self, params_state: Dict[str, Any]):
        self._data = copy.deepcopy(params_state)

    def get(self, key: str, default: Any = None) -> Any:
        return copy.deepcopy(self._data.get(key, default))


class MockEnvironment:
    def __init__(self, task: Dict[str, Any]):
        self.task = copy.deepcopy(task)
        self.state = copy.deepcopy(task.get("input", {}).get("initial_state", {}))
        self.tool_specs = {
            tool["name"]: copy.deepcopy(tool)
            for tool in task.get("input", {}).get("tools", [])
            if isinstance(tool, dict) and isinstance(tool.get("name"), str)
        }
        hidden = task.get("extra", {}).get("hidden", {})
        self.tool_effects = copy.deepcopy(hidden.get("tool_effects", {}))
        self.database = MockDatabase(hidden.get("params_state", {}))
        self.target_state, _ = target_state_of(task)

    def target_view(self) -> Dict[str, Any]:
        return {key: copy.deepcopy(self.state.get(key)) for key in self.target_state}

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        spec = self.tool_specs.get(name)
        if spec is None:
            return self._error("TOOL_NOT_FOUND", "工具未注册: {}".format(name))
        if not isinstance(arguments, dict):
            return self._error("INVALID_ARGUMENT", "arguments 必须是 object")

        validation_error = self._validate_arguments(spec, arguments)
        if validation_error:
            return validation_error

        effect_spec = self.tool_effects.get(name, {})
        for key, expected in effect_spec.get("preconditions", {}).items():
            if self.state.get(key) != expected:
                return self._error(
                    "PRECONDITION_FAILED",
                    "调用 {} 前要求 {}={!r}".format(name, key, expected),
                )

        handler = getattr(self, "_handle_{}".format(name), None)
        if handler is None:
            result = self._handle_static(name, arguments)
        else:
            result = handler(arguments)

        if not result.get("ok"):
            return result

        for key, value in effect_spec.get("effects", {}).items():
            self.state[key] = copy.deepcopy(value)
        if name == "hold_case":
            self.state["hold_reason"] = arguments.get("reason", "")
        if name == "approve_case" and "hold_reason" in self.state:
            self.state["hold_reason"] = ""
        return result

    def _validate_arguments(self, spec: Dict[str, Any], arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for parameter_name, parameter_spec in spec.get("parameters", {}).items():
            if parameter_spec.get("required") and parameter_name not in arguments:
                return self._error("INVALID_ARGUMENT", "缺少必填参数: {}".format(parameter_name))
            if parameter_name not in arguments:
                continue
            expected_type = parameter_spec.get("type")
            checker = TYPE_CHECKS.get(expected_type)
            if checker and not checker(arguments[parameter_name]):
                return self._error(
                    "INVALID_ARGUMENT",
                    "参数 {} 类型应为 {}".format(parameter_name, expected_type),
                )
        return None

    def _handle_verify_identity(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if not self._entity_matches(arguments):
            return self._error("ENTITY_NOT_FOUND", "主体标识不匹配")
        code_type = arguments["code_type"]
        expected = self.state.get(code_type)
        if expected is None or str(arguments["code"]) != str(expected):
            return self._error("IDENTITY_MISMATCH", "身份凭证不匹配")
        return {"ok": True, "name": self.state.get("name", "")}

    def _handle_query_case(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if not self._entity_matches(arguments):
            return self._error("ENTITY_NOT_FOUND", "主体标识不匹配")
        payload = self.database.get("case_payload") or self.database.get("query_case_data")
        if payload is None:
            payload = {"items": self.database.get("_chosen_items", [])}
        return {"ok": True, "items": list(payload.get("items", []))}

    def _handle_check_item(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if not self._entity_matches(arguments):
            return self._error("ENTITY_NOT_FOUND", "主体标识不匹配")
        item_results = self.database.get("item_results") or self.database.get("check_item_data") or {}
        item_name = arguments["item_name"]
        if item_name not in item_results:
            return self._error("ITEM_NOT_FOUND", "核查项不存在: {}".format(item_name))
        item = item_results[item_name]
        return {
            "ok": True,
            "item": item_name,
            "issue": bool(item.get("issue")),
            "detail": item.get("detail", ""),
        }

    def _handle_approve_case(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if not self._entity_matches(arguments):
            return self._error("ENTITY_NOT_FOUND", "主体标识不匹配")
        return {"ok": True, "status": "approved"}

    def _handle_hold_case(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if not self._entity_matches(arguments):
            return self._error("ENTITY_NOT_FOUND", "主体标识不匹配")
        reason = arguments.get("reason", "")
        return {"ok": True, "status": "held", "reason": reason}

    def _handle_query_related(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        related = self.database.get("related_data", {})
        reference = arguments.get("related_ref")
        if reference not in related:
            return self._error("ENTITY_NOT_FOUND", "关联主体不存在: {}".format(reference))
        value = related[reference]
        if isinstance(value, dict):
            return {"ok": True, "ref": reference, **value}
        return {"ok": True, "ref": reference, "data": value}

    def _handle_query_log(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        log_data = self.database.get("log_data", {})
        if isinstance(log_data, dict):
            return {"ok": True, **log_data}
        return {"ok": True, "data": log_data}

    def _handle_static(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        del arguments
        responses = self.database.get("tool_responses", {})
        if name not in responses:
            return self._error("NOT_IMPLEMENTED", "mock 环境未实现工具: {}".format(name))
        response = responses[name]
        if isinstance(response, dict):
            return {"ok": True, **response}
        return {"ok": True, "data": response}

    def _entity_matches(self, arguments: Dict[str, Any]) -> bool:
        for name, value in arguments.items():
            if name.endswith("_id") and name in self.state:
                return self.state[name] == value
        return True

    @staticmethod
    def _error(error_code: str, reason: str) -> Dict[str, Any]:
        return {"ok": False, "error_code": error_code, "reason": reason}

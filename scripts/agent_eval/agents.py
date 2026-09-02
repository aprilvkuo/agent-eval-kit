import json
from typing import Any, Dict, List, Optional


TYPE_MAP = {
    "string": "string",
    "number": "number",
    "bool": "boolean",
    "boolean": "boolean",
    "list": "array",
    "array": "array",
    "object": "object",
}


class OraclePolicy:
    name = "oracle"

    def next_turn(self, task: Dict[str, Any], transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
        trace = task.get("extra", {}).get("hidden", {}).get("oracle_trace", [])
        completed_calls = sum(
            len(item.get("tool_calls", []))
            for item in transcript
            if item.get("type") == "assistant"
        )
        if completed_calls >= len(trace):
            return {"content": "Oracle 轨迹执行完成。", "tool_calls": [], "usage": {}}
        call = trace[completed_calls]
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": "oracle_call_{}".format(completed_calls + 1),
                    "name": call["tool"],
                    "arguments": call.get("arguments", {}),
                }
            ],
            "usage": {},
        }


class ScriptedPolicy:
    name = "scripted"

    def __init__(self, turns: List[Dict[str, Any]]):
        self.turns = turns
        self.index = 0

    def begin(self, task: Dict[str, Any]) -> None:
        del task
        self.index = 0

    def next_turn(self, task: Dict[str, Any], transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
        del task, transcript
        if self.index >= len(self.turns):
            return {"content": "脚本执行结束。", "tool_calls": [], "usage": {}}
        turn = self.turns[self.index]
        self.index += 1
        return turn


class OpenAICompatiblePolicy:
    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.0,
        client: Any = None,
    ):
        self.model = model
        self.name = "openai-compatible:{}".format(model)
        self.temperature = temperature
        if client is not None:
            self.client = client
        else:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError("OpenAI-compatible 模式需要安装 openai>=2") from exc
            kwargs = {}
            if api_key is not None:
                kwargs["api_key"] = api_key
            if base_url is not None:
                kwargs["base_url"] = base_url
            self.client = OpenAI(**kwargs)

    def next_turn(self, task: Dict[str, Any], transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
        messages = self._messages(task, transcript)
        tools = self._tools(task)
        request = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "temperature": self.temperature,
        }
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            temperature=self.temperature,
        )
        choice = response.choices[0]
        message = choice.message
        tool_calls = []
        for raw_call in message.tool_calls or []:
            try:
                arguments = json.loads(raw_call.function.arguments)
            except (TypeError, json.JSONDecodeError):
                arguments = {"_raw_arguments": raw_call.function.arguments}
            tool_calls.append(
                {
                    "id": raw_call.id,
                    "name": raw_call.function.name,
                    "arguments": arguments,
                }
            )
        usage = self._usage(response)
        return {
            "content": message.content or "",
            "tool_calls": tool_calls,
            "usage": usage,
            "finish_reason": getattr(choice, "finish_reason", None),
            "model_request": request,
        }

    def _messages(self, task: Dict[str, Any], transcript: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        visible_input = task.get("input", {})
        payload = {
            "prompt": visible_input.get("prompt", ""),
            "files": visible_input.get("files", []),
            "initial_state": visible_input.get("initial_state", {}),
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "你是一个执行型 Agent。请根据任务和当前状态自主选择工具。"
                    "遵守工具说明和前置条件；需要逐项核查时不得遗漏。"
                    "完成后用简洁中文说明处理结果。"
                ),
            },
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        for item in transcript:
            if item.get("type") == "assistant":
                message = {"role": "assistant", "content": item.get("content") or None}
                if item.get("tool_calls"):
                    message["tool_calls"] = [
                        {
                            "id": call["id"],
                            "type": "function",
                            "function": {
                                "name": call["name"],
                                "arguments": json.dumps(call.get("arguments", {}), ensure_ascii=False),
                            },
                        }
                        for call in item["tool_calls"]
                    ]
                messages.append(message)
            elif item.get("type") == "tool_result":
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": item["call_id"],
                        "content": json.dumps(item["result"], ensure_ascii=False),
                    }
                )
        return messages

    def _tools(self, task: Dict[str, Any]) -> List[Dict[str, Any]]:
        tools = []
        for spec in task.get("input", {}).get("tools", []):
            properties = {}
            required = []
            for name, parameter in spec.get("parameters", {}).items():
                schema = {
                    "type": TYPE_MAP.get(parameter.get("type"), "string"),
                    "description": parameter.get("description", ""),
                }
                properties[name] = schema
                if parameter.get("required"):
                    required.append(name)
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": spec["name"],
                        "description": spec.get("description", ""),
                        "parameters": {
                            "type": "object",
                            "properties": properties,
                            "required": required,
                            "additionalProperties": False,
                        },
                    },
                }
            )
        return tools

    @staticmethod
    def _usage(response: Any) -> Dict[str, int]:
        usage = getattr(response, "usage", None)
        if usage is None:
            return {}
        return {
            "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
            "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
            "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
        }

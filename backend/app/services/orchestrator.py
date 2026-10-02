import json
from typing import ClassVar

from pydantic import BaseModel, ValidationError

from app.models import StrategyProfile
from app.services.llm.base import LLMMessage, LLMProvider


class ChatResult(BaseModel):
    kind: str
    message: str
    preview: dict | None = None


def _strip_code_fence(content: str) -> str:
    text = content.strip().lstrip("\ufeff")
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _decode_json_value(content: str):
    text = _strip_code_fence(content)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, (dict, list, str)):
            return value
    return None


def _extract_json_string(text: str, key: str) -> str | None:
    marker = f'"{key}"'
    marker_index = text.find(marker)
    if marker_index < 0:
        return None
    colon_index = text.find(":", marker_index + len(marker))
    if colon_index < 0:
        return None
    start = text.find('"', colon_index + 1)
    if start < 0:
        return None

    escaped = False
    index = start + 1
    while index < len(text):
        character = text[index]
        if character == '"' and not escaped:
            break
        if character == "\\" and not escaped:
            escaped = True
        else:
            escaped = False
        index += 1
    if index >= len(text):
        return None

    raw = text[start + 1 : index]
    escaped_newlines = raw.replace("\r", "\\r").replace("\n", "\\n")
    try:
        return json.loads(f'"{escaped_newlines}"')
    except json.JSONDecodeError:
        return (
            raw.replace("\\n", "\n")
            .replace("\\r", "\r")
            .replace("\\t", "\t")
            .replace('\\"', '"')
        )


def _recover_chat_fields(content: str) -> dict | None:
    text = _strip_code_fence(content)
    message = _extract_json_string(text, "message")
    if message is None:
        return None
    kind = _extract_json_string(text, "kind") or "analysis"
    return {"kind": kind, "message": message}


def _parse_model_payload(content: str) -> dict | None:
    value = _decode_json_value(content)
    if value is None:
        return _recover_chat_fields(content)
    for _ in range(3):
        if isinstance(value, dict):
            return value
        if not isinstance(value, str) or not value.strip():
            return None
        nested = _decode_json_value(value)
        if nested == value:
            return None
        value = nested
    return None


class Orchestrator:
    ALLOWED_KINDS: ClassVar[set[str]] = {"analysis", "recommendation", "question", "error"}

    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    async def handle(
        self,
        message: str,
        profile: StrategyProfile | None,
        learning_context: dict | None = None,
        read_only_context: dict | None = None,
    ) -> ChatResult:
        if profile is None:
            strategy_context = "当前投放策略：未配置；目标=未配置；约束={}"
        else:
            strategy_context = (
                f"当前投放策略 v{profile.version}: {profile.business_direction}; "
                f"{profile.primary_objective}; 约束={profile.hard_constraints}"
            )
        context = (
            f"{strategy_context}; "
            f"learning_context={json.dumps(learning_context, ensure_ascii=False, default=str)}; "
            f"read_only_context={json.dumps(read_only_context, ensure_ascii=False, default=str)}; "
            '请优先输出 JSON：{"kind":"analysis|recommendation|question|error",'
            '"message":"给用户看的中文回答","preview":null}。'
            "如果不方便输出 JSON，也可以直接输出自然语言分析。"
        )
        response = await self.llm.complete(
            [
                LLMMessage(role="system", content=context),
                LLMMessage(role="user", content=message),
            ],
            tools=[],
        )
        payload = _parse_model_payload(response.content)
        if payload is not None:
            try:
                result = ChatResult.model_validate(payload)
            except ValidationError:
                result = None
            if result is not None:
                if result.kind not in self.ALLOWED_KINDS:
                    return ChatResult(kind="error", message="模型返回了不支持的操作类型。")
                return result

        text = response.content.strip()
        if text:
            return ChatResult(kind="analysis", message=text)
        return ChatResult(kind="error", message="模型返回格式无效，请重试。")
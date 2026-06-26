from collections.abc import Iterator
from dataclasses import asdict, is_dataclass
import json
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents.chatbot_agent import handle_chatbot_message
from app.agents.chatbot_agent.agent import ChatbotAgent
from app.models.schemas import ChatbotMessageRequest, ChatbotMessageResponse


router = APIRouter(prefix="/chatbot", tags=["chatbot"])


@router.post("/message", response_model=ChatbotMessageResponse)
def post_chatbot_message(request: ChatbotMessageRequest) -> ChatbotMessageResponse:
    """Handle one floating-chatbot message through the chatbot agent."""
    return handle_chatbot_message(request)


@router.post("/message/stream")
def stream_chatbot_message(request: ChatbotMessageRequest) -> StreamingResponse:
    """Stream chatbot progress events as Server-Sent Events."""
    return StreamingResponse(
        _chatbot_event_stream(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _chatbot_event_stream(request: ChatbotMessageRequest) -> Iterator[str]:
    try:
        for item in ChatbotAgent().stream(request):
            yield _format_sse(item["event"], item["data"])
    except Exception as exc:
        yield _format_sse(
            "error",
            {
                "message": "聊天 agent 暂时没有响应。请检查后端服务是否启动，稍后再试。",
                "detail": str(exc),
            },
        )


def _format_sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {_json_dumps(data)}\n\n"


def _json_dumps(data: Any) -> str:
    return json.dumps(_jsonable(data), ensure_ascii=False, separators=(",", ":"))


def _jsonable(data: Any) -> Any:
    if isinstance(data, BaseModel):
        return data.model_dump(mode="json")
    if is_dataclass(data) and not isinstance(data, type):
        return asdict(data)
    if isinstance(data, list):
        return [_jsonable(item) for item in data]
    if isinstance(data, tuple):
        return [_jsonable(item) for item in data]
    if isinstance(data, dict):
        return {key: _jsonable(value) for key, value in data.items()}
    return data

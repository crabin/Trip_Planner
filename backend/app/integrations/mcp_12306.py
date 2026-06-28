from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

import httpx


class Mcp12306Error(RuntimeError):
    """Raised when the 12306 MCP service cannot return usable tool data."""


@dataclass(frozen=True)
class Mcp12306ToolResult:
    text: str
    payload: Any | None = None


class Remote12306McpClient:
    """Minimal Streamable HTTP MCP client for the 12306 MCP server."""

    def __init__(self, *, url: str, timeout_seconds: int = 30) -> None:
        self.url = url
        self.timeout_seconds = timeout_seconds
        self._next_id = 1

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Mcp12306ToolResult:
        response = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next_request_id(),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        content = response.get("result", {}).get("content") or []
        if not content:
            raise Mcp12306Error(f"12306 MCP 工具 {name} 未返回内容。")
        text = str(content[0].get("text") or "").strip()
        if not text:
            raise Mcp12306Error(f"12306 MCP 工具 {name} 返回空内容。")
        if text.lower().startswith("error:"):
            raise Mcp12306Error(text)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
        return Mcp12306ToolResult(text=text, payload=payload)

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        if not self.url:
            raise Mcp12306Error("未配置 MCP_12306_URL。")
        try:
            response = httpx.post(
                self.url,
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
                timeout=float(self.timeout_seconds),
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise Mcp12306Error(f"12306 MCP 请求失败：{exc}") from exc

        return parse_mcp_http_response(response.text)

    def _next_request_id(self) -> int:
        request_id = self._next_id
        self._next_id += 1
        return request_id


def parse_mcp_http_response(text: str) -> dict[str, Any]:
    """Parse JSON or SSE-style MCP HTTP response text."""

    stripped = text.strip()
    if not stripped:
        raise Mcp12306Error("12306 MCP 返回空响应。")
    if stripped.startswith("{"):
        payload = json.loads(stripped)
    else:
        data_lines = []
        for line in stripped.splitlines():
            if line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").strip())
        if not data_lines:
            raise Mcp12306Error("12306 MCP 响应缺少 data 字段。")
        payload = json.loads("\n".join(data_lines))
    if "error" in payload:
        error = payload["error"]
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise Mcp12306Error(f"12306 MCP 返回错误：{message}")
    return payload

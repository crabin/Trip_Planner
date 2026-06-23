from __future__ import annotations

from app.models.schemas import ChatbotMessageRequest, ChatbotMessageResponse

from ..state import IntentDecision


class AskNode:
    def run(
        self,
        request: ChatbotMessageRequest,
        decision: IntentDecision,
    ) -> ChatbotMessageResponse:
        itinerary = request.current_itinerary
        if itinerary is None:
            reply = "我可以帮你整理旅行需求，也可以在结果页打开后帮你查询或修改行程。你可以先告诉我目的地、日期、人数、预算和偏好。"
        else:
            day_count = len(itinerary.days)
            first_day = itinerary.days[0] if itinerary.days else None
            first_spot = first_day.spots[0].name if first_day and first_day.spots else "待确认景点"
            reply = (
                f"当前结果页是 {itinerary.destination} 的 {day_count} 天游，"
                f"预算约 {itinerary.estimated_budget:.0f} 元。"
                f"第一天重点是 {first_spot}。"
                "如果你想改某一天，可以直接说“把第2天改轻松一点”或“查询某景点最新开放时间”。"
            )
        return ChatbotMessageResponse(
            intent=decision.intent,
            reply=reply,
            reason=decision.reason,
        )


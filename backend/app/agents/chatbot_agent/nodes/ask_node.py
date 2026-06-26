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
        if decision.intent == "clarify":
            slots = "、".join(decision.missing_slots) if decision.missing_slots else "目的地、日期、人数、预算或偏好"
            reply = f"我需要先补充 {slots}，再给你稳妥建议。你可以直接告诉我最重要的一个约束。"
        elif decision.intent == "compare":
            reply = (
                "我可以帮你比较两个方案。请把要比较的选项发给我，"
                "例如“住春熙路 vs 宽窄巷子”，我会按交通、预算、体验和风险给取舍建议。"
            )
        elif decision.intent == "personalize":
            reply = (
                "我可以按你的画像个性化调整行程。"
                "下一步请告诉我最重要的偏好，例如少走路、不早起、亲子、拍照或预算敏感。"
            )
        elif itinerary is None:
            reply = (
                "我是你的智旅顾问，会先帮你理清目的地、日期、人数、预算和节奏，"
                "再给可执行建议。你可以先告诉我这次旅行最重要的约束。"
            )
        else:
            day_count = len(itinerary.days)
            first_day = itinerary.days[0] if itinerary.days else None
            first_spot = first_day.spots[0].name if first_day and first_day.spots else "待确认景点"
            profile_note = _profile_note(request)
            reply = (
                f"当前结果页是 {itinerary.destination} 的 {day_count} 天游，"
                f"预算约 {itinerary.estimated_budget:.0f} 元。"
                f"第一天重点是 {first_spot}。"
                f"{profile_note}"
                "下一步你可以直接说“把第2天改轻松一点”、"
                "“比较这两个住宿区域”或“查询某景点最新开放时间”。"
            )
        return ChatbotMessageResponse(
            intent=decision.intent,
            reply=reply,
            reason=decision.reason,
        )


def _profile_note(request: ChatbotMessageRequest) -> str:
    profile = request.profile
    notes: list[str] = []
    if profile.pace_preference:
        notes.append(f"偏好{profile.pace_preference}节奏")
    if profile.avoidances:
        notes.append(f"避免{profile.avoidances[0]}")
    if profile.interests:
        notes.append(f"关注{profile.interests[0]}")
    if not notes:
        return ""
    return f"我会记住你{'、'.join(notes[:3])}。"

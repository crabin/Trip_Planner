from __future__ import annotations

from collections.abc import Callable

from app.models.schemas import ChatbotMessageRequest, ChatbotMessageResponse, Itinerary, TravelerProfile, TripEditRequest

from ..prompts import UPDATE_PRESERVE_CONSTRAINTS
from ..state import IntentDecision


class UpdateNode:
    def __init__(self, edit_itinerary: Callable[[TripEditRequest], Itinerary]) -> None:
        self.edit_itinerary = edit_itinerary

    def run(
        self,
        request: ChatbotMessageRequest,
        decision: IntentDecision,
    ) -> ChatbotMessageResponse:
        if request.current_itinerary is None:
            return ChatbotMessageResponse(
                intent="ask",
                reply="我还没有拿到当前结果页行程，先生成或打开一个结果页后，我就可以按你的话修改它。",
                reason="缺少当前 itinerary，无法执行更新。",
            )

        if decision.intent == "personalize" and _is_empty_profile(request.profile):
            return ChatbotMessageResponse(
                intent="clarify",
                reply=(
                    "我可以按你的偏好重排行程，但还缺少画像约束。"
                    "你更想优先少走路、少早起、控制预算，还是多打卡？"
                ),
                reason="个性化调整缺少 traveler_profile 约束，先确认偏好。",
            )

        if decision.intent == "update" and _needs_scope_confirmation(request.message, decision.edit_scope):
            return ChatbotMessageResponse(
                intent="clarify",
                reply=(
                    "这个修改可能会影响多天安排。为了避免误改整份行程，"
                    "请确认是只改某一天，还是允许我重排全部行程。"
                ),
                reason="修改范围不明确，先确认影响范围。",
            )

        instruction = request.message
        if decision.intent == "personalize":
            instruction = (
                f"{request.message}\n\n"
                f"请结合以下旅行偏好画像做个性化调整：{_format_profile(request.profile)}。"
                "优先调整节奏、顺路程度、餐饮和兴趣匹配；未被偏好影响的日期和项目保持不变。"
            )

        updated = self.edit_itinerary(
            TripEditRequest(
                trip_id=request.trip_id or request.current_itinerary.trip_id,
                current_itinerary=request.current_itinerary,
                user_instruction=instruction,
                edit_scope=decision.edit_scope,
                preserve_constraints=UPDATE_PRESERVE_CONSTRAINTS,
            )
        )
        scope_text = f"（{decision.edit_scope}）" if decision.edit_scope else ""
        if decision.intent == "personalize":
            reply = f"我已按你的旅行画像调整当前行程{scope_text}。下一步建议你重点检查每天步行量、早出发时间和预算是否符合预期。"
        else:
            reply = f"已根据你的要求更新结果页行程{scope_text}。下一步可以继续指定某一天微调，或让我检查交通和开放时间风险。"
        return ChatbotMessageResponse(
            intent=decision.intent,
            reply=reply,
            reason=decision.reason,
            updated_itinerary=updated,
        )


def _is_empty_profile(profile: TravelerProfile) -> bool:
    return (
        profile.pace_preference is None
        and not profile.food_preferences
        and not profile.avoidances
        and not profile.interests
        and profile.budget_sensitivity is None
        and not profile.confirmed_facts
    )


def _format_profile(profile: TravelerProfile) -> str:
    parts: list[str] = []
    if profile.pace_preference:
        parts.append(f"节奏={profile.pace_preference}")
    if profile.food_preferences:
        parts.append(f"饮食={','.join(profile.food_preferences)}")
    if profile.avoidances:
        parts.append(f"避免={','.join(profile.avoidances)}")
    if profile.interests:
        parts.append(f"兴趣={','.join(profile.interests)}")
    if profile.budget_sensitivity:
        parts.append(f"预算敏感度={profile.budget_sensitivity}")
    if profile.confirmed_facts:
        parts.append(f"已确认={';'.join(profile.confirmed_facts[:5])}")
    return "；".join(parts) if parts else "暂无明确画像"


def _needs_scope_confirmation(message: str, edit_scope: str | None) -> bool:
    if edit_scope:
        return False
    broad_terms = (
        "整体",
        "整份",
        "全部",
        "所有",
        "整个",
        "全程",
        "重排",
        "重新安排",
        "优化一下",
        "调整一下",
        "改轻松",
        "安排得更",
    )
    return any(term in message for term in broad_terms)

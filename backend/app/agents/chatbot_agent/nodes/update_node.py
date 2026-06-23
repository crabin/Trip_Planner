from __future__ import annotations

from collections.abc import Callable

from app.models.schemas import ChatbotMessageRequest, ChatbotMessageResponse, Itinerary, TripEditRequest

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

        updated = self.edit_itinerary(
            TripEditRequest(
                trip_id=request.trip_id or request.current_itinerary.trip_id,
                current_itinerary=request.current_itinerary,
                user_instruction=request.message,
                edit_scope=decision.edit_scope,
                preserve_constraints=[
                    "保留目的地、日期、人数和已明确预算，除非用户要求修改。",
                    "只修改用户提到的范围，避免重写整份行程。",
                ],
            )
        )
        scope_text = f"（{decision.edit_scope}）" if decision.edit_scope else ""
        return ChatbotMessageResponse(
            intent="update",
            reply=f"已根据你的要求更新结果页行程{scope_text}，你可以在页面上继续查看或再让我微调。",
            reason=decision.reason,
            updated_itinerary=updated,
        )


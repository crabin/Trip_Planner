from fastapi import APIRouter

from app.agents.chatbot_agent import handle_chatbot_message
from app.models.schemas import ChatbotMessageRequest, ChatbotMessageResponse


router = APIRouter(prefix="/chatbot", tags=["chatbot"])


@router.post("/message", response_model=ChatbotMessageResponse)
def post_chatbot_message(request: ChatbotMessageRequest) -> ChatbotMessageResponse:
    """Handle one floating-chatbot message through the chatbot agent."""
    return handle_chatbot_message(request)

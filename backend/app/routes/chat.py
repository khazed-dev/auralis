"""
Chat API routes.
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from loguru import logger

from app.models.schemas import ChatRequest, ChatResponse, ConversationHistory, Message
from app.services.rag_engine import RAGEngine, get_rag_engine
from app.database import get_mongodb
from app.config import settings
from app.core.security import get_client_ip
from app.routes.dependencies import require_widget_site
from app.routes.auth import require_auth
from app.core.site_access import can_manage_site
from app.services.subscriptions import enforce_quota, increment_usage
from app.services.byok import record_model_usage, tenant_llm_for_site

router = APIRouter(prefix="/api/chat", tags=["Chat"])

# Rate limiter
limiter = Limiter(key_func=get_client_ip)


async def _validate_widget_site(request: Request, site_id: str) -> dict:
    """Backward-compatible wrapper around the shared widget guard."""
    if not site_id:
        raise HTTPException(status_code=422, detail="site_id is required")
    return await require_widget_site(request, site_id)


async def check_handoff_suggestion(site_id: str, answer: str, confidence: float) -> tuple[bool, str]:
    """Check if handoff should be suggested based on confidence and response content."""
    mongodb = await get_mongodb()
    
    config = await mongodb.get_site_handoff_config(site_id) if site_id else None
    
    if not config or not config.get("enabled", True):
        return False, None
    
    threshold = config.get("confidence_threshold", 0.3)
    auto_phrases = config.get("auto_suggest_phrases", [
        "I'm not sure",
        "I don't have information",
        "I cannot help with",
        "please contact support"
    ])
    
    if confidence < threshold:
        return True, "low_confidence"
    
    answer_lower = answer.lower()
    for phrase in auto_phrases:
        if phrase.lower() in answer_lower:
            return True, "uncertain_response"
    
    return False, None


@router.post("", response_model=ChatResponse)
@limiter.limit(f"{settings.RATE_LIMIT_REQUESTS}/minute")
async def chat(request: Request, body: ChatRequest):
    """
    Send a message and get a response from the chatbot.
    
    - **message**: The user's message
    - **session_id**: Unique session identifier for conversation tracking
    - **user_id**: Optional user ID for long-term memory
    - **stream**: Whether to stream the response (use /stream endpoint instead)
    """
    try:
        site = await _validate_widget_site(request, body.site_id)
        mongodb = await get_mongodb()
        owner_id = str(site.get("user_id") or "")
        if owner_id:
            await enforce_quota(mongodb, owner_id, "messages")
        tenant_llm = await tenant_llm_for_site(mongodb, site)
        rag_engine = RAGEngine(llm_service=tenant_llm) if tenant_llm else get_rag_engine()

        response = await rag_engine.chat(
            message=body.message,
            session_id=body.session_id,
            user_id=body.user_id,
            site_id=body.site_id
        )
        
        suggest_handoff, handoff_reason = await check_handoff_suggestion(
            body.site_id,
            response.answer,
            response.confidence
        )
        
        response.suggest_handoff = suggest_handoff
        response.handoff_reason = handoff_reason
        if owner_id:
            await increment_usage(mongodb, owner_id, "messages")
            await record_model_usage(mongodb, owner_id, tenant_llm)
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preview", response_model=ChatResponse)
@limiter.limit(f"{settings.RATE_LIMIT_REQUESTS}/minute")
async def preview_chat(
    request: Request,
    body: ChatRequest,
    user: dict = Depends(require_auth),
):
    """Run the real site-scoped RAG flow from the authenticated dashboard."""
    if not body.site_id:
        raise HTTPException(status_code=422, detail="site_id is required")
    try:
        mongodb = await get_mongodb()
        site = await mongodb.get_site(body.site_id)
        if not site:
            raise HTTPException(status_code=404, detail="Site not found")
        if not can_manage_site(user, site):
            raise HTTPException(status_code=403, detail="Access denied")

        owner_id = str(site.get("user_id") or "")
        if owner_id:
            await enforce_quota(mongodb, owner_id, "messages")
        tenant_llm = await tenant_llm_for_site(mongodb, site)
        rag_engine = RAGEngine(llm_service=tenant_llm) if tenant_llm else get_rag_engine()
        response = await rag_engine.chat(
            message=body.message,
            session_id=body.session_id,
            user_id=body.user_id,
            site_id=body.site_id,
        )
        if owner_id:
            await increment_usage(mongodb, owner_id, "messages")
            await record_model_usage(mongodb, owner_id, tenant_llm)
        return response
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Preview chat error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/stream")
@limiter.limit(f"{settings.RATE_LIMIT_REQUESTS}/minute")
async def chat_stream(request: Request, body: ChatRequest):
    """
    Send a message and get a streaming response.
    
    Returns Server-Sent Events (SSE) with the response chunks.
    """
    try:
        site = await _validate_widget_site(request, body.site_id)
        mongodb = await get_mongodb()
        owner_id = str(site.get("user_id") or "")
        if owner_id:
            await enforce_quota(mongodb, owner_id, "messages")
        tenant_llm = await tenant_llm_for_site(mongodb, site)
        rag_engine = RAGEngine(llm_service=tenant_llm) if tenant_llm else get_rag_engine()

        async def event_generator():
            try:
                async for event in rag_engine.chat_stream(
                    message=body.message,
                    session_id=body.session_id,
                    user_id=body.user_id,
                    site_id=body.site_id,
                ):
                    if event.get("type") == "done":
                        suggest_handoff, handoff_reason = await check_handoff_suggestion(
                            body.site_id,
                            event.get("answer", ""),
                            float(event.get("confidence") or 0.0),
                        )
                        event["suggest_handoff"] = suggest_handoff
                        event["handoff_reason"] = handoff_reason
                        if owner_id:
                            await increment_usage(mongodb, owner_id, "messages")
                            await record_model_usage(mongodb, owner_id, tenant_llm)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                event = {"type": "error", "message": str(e)}
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Stream error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{session_id}", response_model=ConversationHistory)
async def get_history(session_id: str):
    """
    Get conversation history for a session.
    
    - **session_id**: The session ID to get history for
    """
    try:
        mongodb = await get_mongodb()
        messages = await mongodb.get_conversation_history(session_id, limit=50)
        
        return ConversationHistory(
            session_id=session_id,
            messages=[
                Message(
                    role=m["role"],
                    content=m["content"],
                    sources=m.get("sources", []),
                    timestamp=m.get("timestamp")
                )
                for m in messages
            ],
            created_at=messages[0]["timestamp"] if messages else None,
            updated_at=messages[-1]["timestamp"] if messages else None
        )
        
    except Exception as e:
        logger.error(f"History error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/history/{session_id}")
async def clear_history(session_id: str):
    """
    Clear conversation history for a session.
    
    - **session_id**: The session ID to clear
    """
    try:
        mongodb = await get_mongodb()
        result = await mongodb.clear_conversation(session_id)
        
        return {"success": result, "message": "Conversation cleared"}
        
    except Exception as e:
        logger.error(f"Clear history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def get_sessions(limit: int = 20):
    """
    Get all conversation sessions.
    
    - **limit**: Maximum number of sessions to return
    """
    try:
        mongodb = await get_mongodb()
        sessions = await mongodb.get_all_sessions(limit=limit)
        
        return {
            "sessions": [
                {
                    "session_id": s["session_id"],
                    "created_at": s.get("created_at"),
                    "updated_at": s.get("updated_at")
                }
                for s in sessions
            ]
        }
        
    except Exception as e:
        logger.error(f"Sessions error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feedback")
async def submit_feedback(
    session_id: str,
    message_index: int,
    feedback: str
):
    """
    Submit feedback for a chat message.
    
    - **session_id**: The conversation session ID
    - **message_index**: Index of the message to rate
    - **feedback**: Either "positive" or "negative"
    """
    if feedback not in ["positive", "negative"]:
        raise HTTPException(status_code=400, detail="Feedback must be 'positive' or 'negative'")
    
    try:
        mongodb = await get_mongodb()
        result = await mongodb.add_feedback_by_index(session_id, message_index, feedback)
        
        if result:
            return {"success": True, "message": "Feedback recorded"}
        else:
            raise HTTPException(status_code=404, detail="Message not found")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Feedback error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

import os
import hashlib
import hmac
import json
import re
import httpx
from fastapi import APIRouter, Request, HTTPException
from loguru import logger

from app.services.rag_engine import get_rag_engine

router = APIRouter(prefix="/api/messenger", tags=["messenger"])

VERIFY_TOKEN = os.getenv("FB_VERIFY_TOKEN", "").strip()
APP_SECRET = os.getenv("FB_APP_SECRET", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN", "").strip()
GRAPH_VERSION = os.getenv("FB_GRAPH_API_VERSION", "v20.0").strip()

# Site ID lấy từ embed code của bạn
EURO_SITE_ID = os.getenv("MESSENGER_SITE_ID", "dd3e2142f3a8").strip()


@router.get("/webhook")
async def verify_webhook(request: Request):
    if not VERIFY_TOKEN:
        raise HTTPException(status_code=503, detail="Messenger verification is not configured")
    params = request.query_params

    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token and hmac.compare_digest(token.encode(), VERIFY_TOKEN.encode()):
        if not challenge or not re.fullmatch(r"[0-9]{1,20}", challenge):
            raise HTTPException(status_code=400, detail="Invalid challenge")
        return int(challenge)

    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def receive_message(request: Request):
    if not APP_SECRET:
        raise HTTPException(status_code=503, detail="Messenger webhook is not configured")
    raw_body = await request.body()
    supplied = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    if not re.fullmatch(r"sha256=[0-9a-fA-F]{64}", supplied) or not hmac.compare_digest(supplied.lower(), expected):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    try:
        body = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook body") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid webhook body")

    if body.get("object") != "page":
        return {"status": "ignored"}

    for entry in body.get("entry", []):
        for event in entry.get("messaging", []):
            sender_id = event.get("sender", {}).get("id")

            # Bỏ qua echo để tránh bot tự đọc lại tin nhắn mình gửi
            message = event.get("message", {})
            if message.get("is_echo"):
                continue

            text = message.get("text")
            if not sender_id or not text:
                continue

            try:
                answer = await ask_rag(text, sender_id)
            except Exception as e:
                logger.exception(f"Messenger RAG error: {e}")
                answer = "Xin lỗi anh/chị, hiện hệ thống tư vấn tự động đang gặp lỗi. Anh/chị vui lòng để lại số điện thoại/Zalo để nhân viên hỗ trợ sớm nhất."

            await send_messenger_message(sender_id, answer)

    return {"status": "ok"}

def build_messenger_sources(sources) -> str:
    if not sources:
        return ""

    lines = []
    seen_urls = set()

    for source in sources[:3]:
        url = None
        title = None

        # Nếu source là object Pydantic/class
        if hasattr(source, "url"):
            url = getattr(source, "url", None)
        if hasattr(source, "title"):
            title = getattr(source, "title", None)

        # Nếu source là dict
        if isinstance(source, dict):
            url = source.get("url") or source.get("source") or source.get("link")
            title = source.get("title") or source.get("name")

        # Một số repo lưu URL trong metadata
        metadata = None
        if hasattr(source, "metadata"):
            metadata = getattr(source, "metadata", None)
        elif isinstance(source, dict):
            metadata = source.get("metadata")

        if isinstance(metadata, dict):
            url = url or metadata.get("url") or metadata.get("source") or metadata.get("link")
            title = title or metadata.get("title") or metadata.get("name")

        if not url or url in seen_urls:
            continue

        seen_urls.add(url)

        if title:
            lines.append(f"- {title}: {url}")
        else:
            lines.append(f"- {url}")

    return "\n".join(lines)

async def ask_rag(text: str, sender_id: str) -> str:
    rag = get_rag_engine()

    session_id = f"messenger_{sender_id}"

    result = await rag.chat(
        message=text,
        session_id=session_id,
        site_id=EURO_SITE_ID,
    )

    # Lấy câu trả lời
    if hasattr(result, "answer"):
        answer = result.answer or ""
    elif isinstance(result, dict):
        answer = result.get("answer", "") or ""
    else:
        answer = str(result)

    # Lấy sources
    sources = []
    if hasattr(result, "sources"):
        sources = result.sources or []
    elif isinstance(result, dict):
        sources = result.get("sources", []) or []

    source_text = build_messenger_sources(sources)

    final_answer = answer.strip()

    if source_text:
        final_answer = f"{final_answer}\n\nNguồn tham khảo:\n{source_text}"

    if not final_answer:
        return "Hiện em chưa có đủ thông tin để trả lời chính xác. Anh/chị vui lòng để lại số điện thoại/Zalo:082 820 8218 để nhân viên tư vấn thêm."

    return final_answer[:1900]

async def send_messenger_message(recipient_id: str, text: str):
    if not PAGE_ACCESS_TOKEN or PAGE_ACCESS_TOKEN == "PASTE_PAGE_ACCESS_TOKEN_HERE":
        logger.error("FB_PAGE_ACCESS_TOKEN is missing")
        return

    url = f"https://graph.facebook.com/{GRAPH_VERSION}/me/messages"

    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text[:1900]},
        "messaging_type": "RESPONSE",
    }

    params = {
        "access_token": PAGE_ACCESS_TOKEN
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, params=params, json=payload)

    if response.status_code >= 400:
        logger.error(f"Messenger send error: {response.status_code} {response.text}")
        raise HTTPException(status_code=500, detail=response.text)

"""One bounded inference; no conversation, quota, or database writes."""
import asyncio
import sys

from loguru import logger

logger.remove()


async def main():
    from app.services.factory import get_llm_service

    answer = await asyncio.wait_for(
        get_llm_service().generate("Reply with OK.", max_tokens=256, temperature=0),
        timeout=75,
    )
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("Empty model response")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"LLM smoke check failed ({type(exc).__name__}); credentials and response omitted.", file=sys.stderr)
        sys.exit(1)
    print("LLM inference passed; no conversation persisted.")

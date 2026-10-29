"""Streaming parity, early output and split reasoning-marker regressions."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.documents import Document

from app.services.rag_engine import RAGEngine, clean_model_output, _ModelOutputCleaner


@pytest.fixture
def streaming_engine(monkeypatch):
    database = MagicMock()
    database.db.sites.find_one = AsyncMock(return_value={
        "url": "https://example.test", "name": "Fixture",
        "config": {"behavior": {"temperature": 0.2, "max_tokens": 200}},
    })
    database.get_conversation_history = AsyncMock(return_value=[])
    database.get_user_memory = AsyncMock(return_value={"language": "Vietnamese"})
    database.increment_qa_use_count = AsyncMock()
    database.save_message = AsyncMock()
    monkeypatch.setattr("app.services.rag_engine.get_mongodb", AsyncMock(return_value=database))
    monkeypatch.setattr("app.services.rag_engine.get_vector_store", lambda: MagicMock())
    llm = MagicMock()
    llm.generate = AsyncMock(return_value="Model answer")
    engine = RAGEngine(llm_service=llm)
    engine._check_qa_match = AsyncMock(return_value=None)
    engine._rewrite_query = AsyncMock(return_value="query")
    docs = [(Document(page_content="Fixture evidence", metadata={"url": "https://example.test/policy", "title": "Policy"}), 0.2)]
    engine._retrieve_documents = AsyncMock(return_value=docs)
    engine._grade_documents = AsyncMock(return_value=docs)
    return engine, database, llm


def saved_content(call):
    return call.kwargs["content"] if "content" in call.kwargs else call.args[2]


async def test_stream_uses_the_same_trained_qa_without_calling_model(streaming_engine):
    engine, database, llm = streaming_engine
    engine._check_qa_match.return_value = ({"id": "qa-1", "answer": "<think>PRIVATE</think> Approved answer"}, 0.99)
    normal = await engine.chat("question", "normal", site_id="site")

    streamed = [part async for part in engine.chat_stream("question", "stream", site_id="site")]

    assert streamed == [normal.answer] == ["Approved answer"]
    assert engine._check_qa_match.await_count == 2
    engine._retrieve_documents.assert_not_awaited()
    llm.generate.assert_not_awaited()
    llm.generate_stream.assert_not_called()
    assert database.increment_qa_use_count.await_count == 2
    assert database.save_message.await_count == 4
    assert saved_content(database.save_message.await_args) == "Approved answer"
    assert database.save_message.await_args.kwargs["sources"] == []


async def test_first_visible_output_does_not_wait_for_later_provider_tokens(streaming_engine):
    engine, database, llm = streaming_engine
    consumed = []

    async def tokens(*_args, **_kwargs):
        for part in ["Xin ", "chào", " bạn"]:
            consumed.append(part)
            yield part

    llm.generate_stream = tokens
    stream = engine.chat_stream("question", "session", site_id="site")
    first = await anext(stream)
    assert consumed == ["Xin "]
    assert first == "Xin"
    database.save_message.assert_not_awaited()
    remainder = [part async for part in stream]
    assert "".join([first, *remainder]) == "Xin chào bạn"
    assert saved_content(database.save_message.await_args) == "Xin chào bạn"


@pytest.mark.parametrize("size", [1, 2, 7])
@pytest.mark.parametrize("raw,expected", [
    ("<think>PRIVATE</think>  Xin chào!  ", "Xin chào!"),
    ("Trước <THINK>PRIVATE</THINK> sau", "Trước  sau"),
    ("<think>PRIVATE<think>PRIVATE</think>PRIVATE</think>Answer", "Answer"),
    ("<think>PRIVATE", ""),
    ("Analysis:   Kết quả\nReasoning: Dòng hai", "Kết quả\nDòng hai"),
    ("  Chain-of-thought:   Kết quả  ", "Kết quả"),
    ("Chain of-thought: Kết quả", "Kết quả"),
    ("Xin chào!\n\nA < B và C > D.\n", "Xin chào!\n\nA < B và C > D."),
    ("x<t", "x<t"),
    ("Analog và Reasoning không có dấu hai chấm.", "Analog và Reasoning không có dấu hai chấm."),
])
async def test_split_markers_are_hidden_and_history_matches_visible_output(streaming_engine, size, raw, expected):
    engine, database, llm = streaming_engine

    async def tokens(*_args, **_kwargs):
        for start in range(0, len(raw), size):
            yield raw[start:start + size]

    llm.generate_stream = tokens
    parts = [part async for part in engine.chat_stream("question", "session", site_id="site")]
    assert "".join(parts) == expected
    assert all("PRIVATE" not in part for part in parts)
    assert saved_content(database.save_message.await_args) == expected
    assert clean_model_output(raw) == expected


async def test_cancel_closes_provider_and_does_not_save_an_incomplete_answer(streaming_engine):
    engine, database, llm = streaming_engine
    closed = []

    async def tokens(*_args, **_kwargs):
        try:
            yield "First"
            yield "Second"
        finally:
            closed.append(True)

    llm.generate_stream = tokens
    stream = engine.chat_stream("question", "session", site_id="site")
    assert await anext(stream) == "First"
    assert not closed
    await stream.aclose()
    assert closed == [True]
    database.save_message.assert_not_awaited()


async def test_provider_failure_propagates_without_saving_partial_history(streaming_engine):
    engine, database, llm = streaming_engine

    async def tokens(*_args, **_kwargs):
        yield "First"
        raise RuntimeError("provider failed")

    llm.generate_stream = tokens
    stream = engine.chat_stream("question", "session", site_id="site")
    assert await anext(stream) == "First"
    with pytest.raises(RuntimeError, match="provider failed"):
        await anext(stream)
    database.save_message.assert_not_awaited()


async def test_stream_respects_hidden_sources_and_trusted_user_preferences(streaming_engine):
    engine, database, llm = streaming_engine
    database.db.sites.find_one.return_value["config"]["behavior"]["show_sources"] = False

    async def tokens(prompt, system_prompt, **kwargs):
        assert "User preferences:" in system_prompt
        assert kwargs == {"temperature": 0.2, "max_tokens": 200}
        yield "Answer"

    llm.generate_stream = tokens
    assert [part async for part in engine.chat_stream("question", "session", user_id="owner", site_id="site")] == ["Answer"]
    assert database.save_message.await_args.kwargs["sources"] == []


@pytest.mark.parametrize("raw,expected", [
    (" " * 10000 + "Analysis:" + " " * 10000 + "Answer", "Answer"),
    ("<" * 10000 + " Answer", "<" * 10000 + " Answer"),
    ("<think>" + "PRIVATE" * 5000 + "</think>Answer", "Answer"),
], ids=["long-whitespace", "literal-angle-brackets", "long-hidden-block"])
def test_large_chunks_keep_batch_and_incremental_cleanup_consistent(raw, expected):
    cleaner = _ModelOutputCleaner()
    visible = [cleaner.feed(raw[start:start + 4096]) for start in range(0, len(raw), 4096)]
    visible.append(cleaner.finish())
    assert "".join(visible) == clean_model_output(raw) == expected

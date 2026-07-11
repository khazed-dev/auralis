from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.indexer import IndexerService


@pytest.mark.asyncio
async def test_index_pages_saves_complete_content_for_reindexing():
    content = "A" * 1500
    page = {
        "url": "https://example.vn/long-page",
        "title": "Long page",
        "content": content,
    }
    vector_store = MagicMock()
    mongodb = MagicMock()
    mongodb.save_page = AsyncMock()

    with patch("app.services.indexer.get_vector_store", return_value=vector_store), patch(
        "app.services.indexer.get_mongodb", AsyncMock(return_value=mongodb)
    ):
        await IndexerService().index_pages([page], site_id="site-1")

    assert mongodb.save_page.await_args.kwargs["content"] == content

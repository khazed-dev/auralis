"""Focused tests for small-corpus Vietnamese hybrid retrieval."""
from types import SimpleNamespace

from langchain_core.documents import Document

from app.database.vector_store import VectorStore


def _store_with(documents, dense_results):
    store = VectorStore.__new__(VectorStore)
    store._initialized = True
    store.vector_store = SimpleNamespace(
        index=SimpleNamespace(ntotal=len(documents)),
        docstore=SimpleNamespace(
            _dict={str(index): doc for index, doc in enumerate(documents)}
        ),
        similarity_search_with_score=lambda query, k: dense_results[:k],
    )
    return store


def test_hybrid_search_promotes_exact_vietnamese_product_code():
    generic = Document(
        page_content="Khóa thông minh dành cho cửa nhôm.",
        metadata={"url": "https://example.vn/khoa", "title": "Khóa thông minh", "chunk_index": 0},
    )
    exact = Document(
        page_content="Mã C114 có cảm biến vân tay và mật khẩu.",
        metadata={"url": "https://example.vn/c114", "title": "Khóa C114", "chunk_index": 0},
    )
    store = _store_with([generic, exact], [(generic, 0.2), (exact, 0.5)])

    results = store.hybrid_search_with_score("khóa C114", k=2)

    assert results[0][0].metadata["url"].endswith("/c114")
    assert results[0][0].metadata["_keyword_score"] > 0


def test_hybrid_search_filters_site_before_final_top_k():
    other_site = Document(
        page_content="Sản phẩm HUAVY",
        metadata={"url": "https://other.vn/huavy", "site_id": "other", "chunk_index": 0},
    )
    target_site = Document(
        page_content="Keo HUAVY dùng cho cửa kính.",
        metadata={"url": "https://target.vn/huavy", "site_id": "target", "chunk_index": 0},
    )
    store = _store_with(
        [other_site, target_site],
        [(other_site, 0.1), (target_site, 0.4)],
    )

    results = store.hybrid_search_with_score(
        "keo HUAVY",
        k=2,
        filter={"site_id": "target"},
        url_prefix="https://target.vn",
    )

    assert [doc.metadata["site_id"] for doc, _ in results] == ["target"]


def test_hybrid_search_does_not_mutate_persisted_documents():
    document = Document(
        page_content="Lock model C114 supports fingerprints.",
        metadata={"url": "https://example.vn/c114", "title": "C114", "chunk_index": 0},
    )
    store = _store_with([document], [(document, 0.3)])

    results = store.hybrid_search_with_score("what is C114", k=1)

    assert results[0][0] is not document
    assert results[0][0].metadata["_retrieval"] == "hybrid"
    assert all(not key.startswith("_retrieval") for key in document.metadata)
    assert "_dense_score" not in document.metadata


def test_filtered_dense_search_fetches_candidates_before_top_k():
    other = Document(page_content="C114", metadata={"site_id": "other"})
    target = Document(page_content="C114 target", metadata={"site_id": "target"})
    store = _store_with([other, target], [(other, 0.1), (target, 0.2)])

    results = store.similarity_search_with_score(
        "C114", k=1, filter={"site_id": "target"}
    )

    assert results == [(target, 0.2)]


def test_lexical_metadata_measures_informative_query_coverage():
    generic = Document(
        page_content="What is this product?",
        metadata={"url": "https://example.vn/generic", "chunk_index": 0},
    )
    exact = Document(
        page_content="C114 supports fingerprints.",
        metadata={"url": "https://example.vn/c114", "chunk_index": 0},
    )
    store = _store_with([generic, exact], [(generic, 0.1), (exact, 0.4)])

    results = store.hybrid_search_with_score("what is product C114", k=2)
    by_url = {doc.metadata["url"]: doc for doc, _ in results}

    assert by_url["https://example.vn/c114"].metadata["_keyword_match_ratio"] == 1.0
    assert by_url["https://example.vn/generic"].metadata["_keyword_score"] == 0.0

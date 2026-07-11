"""
Vector store operations using FAISS.
"""
import os
import math
import re
import unicodedata
from collections import Counter
from typing import List, Dict, Optional
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.documents import Document
from loguru import logger

from app.config import settings


# Keep lexical retrieval focused on terms that carry meaning. BM25's IDF is not
# enough for very small corpora, where a generic word can otherwise look rare
# and promote an unrelated chunk.
_SEARCH_STOPWORDS = {
    "a", "an", "and", "are", "be", "for", "from", "how", "in", "is", "me",
    "of", "on", "or", "please", "product", "tell", "the", "this", "to", "what",
    "with", "you", "your",
    "ai", "ban", "bang", "bi", "cac", "cho", "co", "cua", "da", "de", "do",
    "duoc", "gi", "hay", "khong", "la", "minh", "mot", "nay", "nhung", "o",
    "san", "pham", "thi", "toi", "tu", "va", "ve", "voi",
    "bạn", "bằng", "bị", "các", "cho", "có", "của", "đã", "để", "đó",
    "được", "gì", "hãy", "không", "là", "mình", "một", "này", "những", "ở",
    "sản", "phẩm", "thì", "tôi", "từ", "và", "về", "với",
}


def search_tokens(text: str, *, drop_stopwords: bool = False) -> List[str]:
    """Tokenize Vietnamese text and product codes consistently."""
    normalized = unicodedata.normalize("NFKC", text or "").lower()
    tokens = re.findall(r"[\w]+(?:[-./][\w]+)*", normalized, flags=re.UNICODE)
    if not drop_stopwords:
        return tokens
    informative = [token for token in tokens if token not in _SEARCH_STOPWORDS]
    # A stopword-only query is still searchable instead of becoming empty.
    return informative or tokens


_TRANSIENT_RETRIEVAL_KEYS = {
    "_retrieval",
    "_dense_score",
    "_keyword_score",
    "_keyword_match_count",
    "_keyword_match_ratio",
    "_exact_phrase_match",
}


class VectorStore:
    """FAISS vector store with HuggingFace embeddings."""
    
    def __init__(self):
        self.embeddings = None
        self.vector_store = None
        self._initialized = False
        model_slug = re.sub(r"[^a-z0-9]+", "_", settings.EMBEDDINGS_MODEL.lower()).strip("_")
        self.index_path = os.path.join(
            settings.CHROMA_PERSIST_DIR,
            f"faiss_index_{model_slug}",
        )
    
    def initialize(self):
        """Initialize the vector store and embeddings."""
        if self._initialized:
            return
        
        try:
            # Create directories
            os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
            
            # Initialize embeddings (HuggingFace - runs locally)
            logger.info("Loading embedding model...")
            self.embeddings = HuggingFaceEmbeddings(
                model_name=settings.EMBEDDINGS_MODEL,
                model_kwargs={"device": settings.EMBEDDINGS_DEVICE},
                encode_kwargs={
                    "normalize_embeddings": True,
                    "batch_size": settings.EMBEDDINGS_BATCH_SIZE,
                },
            )
            
            # Try to load existing index
            if os.path.exists(self.index_path):
                logger.info("Loading existing FAISS index...")
                self.vector_store = FAISS.load_local(
                    self.index_path,
                    self.embeddings,
                    allow_dangerous_deserialization=True
                )
            else:
                logger.info("Creating new FAISS index...")
                # Create empty index with a dummy document
                self.vector_store = FAISS.from_texts(
                    ["Initial document"],
                    self.embeddings,
                    metadatas=[{"source": "init"}]
                )
                self._save_index()
            
            self._initialized = True
            logger.info("Vector store initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize vector store: {e}")
            raise
    
    def _save_index(self):
        """Save the FAISS index to disk."""
        if self.vector_store:
            self.vector_store.save_local(self.index_path)
    
    def add_documents(self, documents: List[Document]) -> List[str]:
        """Add documents to the vector store."""
        if not self._initialized:
            self.initialize()
        
        try:
            if not documents:
                return []
            
            # Add documents
            ids = self.vector_store.add_documents(documents)
            
            # Save to disk
            self._save_index()
            
            logger.info(f"Added {len(documents)} documents to vector store")
            return ids
        except Exception as e:
            logger.error(f"Failed to add documents: {e}")
            raise
    
    def similarity_search(
        self,
        query: str,
        k: int = None,
        filter: Dict = None
    ) -> List[Document]:
        """Search for similar documents."""
        if not self._initialized:
            self.initialize()
        
        k = k or settings.RETRIEVAL_K
        
        try:
            # Fetch before filtering. Filtering only the unscoped top-k can return
            # no hits for a tenant even when matching documents exist lower down.
            fetch_k = k
            if filter:
                ntotal = int(getattr(self.vector_store.index, "ntotal", 0) or 0)
                fetch_k = min(ntotal, max(k, settings.RAG_MAX_CANDIDATES))
            results = self.vector_store.similarity_search(query, k=fetch_k)
            
            # Apply filter if provided
            if filter:
                results = [
                    doc for doc in results
                    if all(doc.metadata.get(key) == value for key, value in filter.items())
                ]
            
            return results[:k]
        except Exception as e:
            logger.error(f"Similarity search failed: {e}")
            return []
    
    def similarity_search_with_score(
        self,
        query: str,
        k: int = None,
        filter: Dict = None
    ) -> List[tuple]:
        """Search for similar documents with relevance scores."""
        if not self._initialized:
            self.initialize()
        
        k = k or settings.RETRIEVAL_K
        
        try:
            fetch_k = k
            if filter:
                ntotal = int(getattr(self.vector_store.index, "ntotal", 0) or 0)
                fetch_k = min(ntotal, max(k, settings.RAG_MAX_CANDIDATES))
            results = self.vector_store.similarity_search_with_score(query, k=fetch_k)
            
            # Apply filter if provided
            if filter:
                results = [
                    (doc, score) for doc, score in results
                    if all(doc.metadata.get(key) == value for key, value in filter.items())
                ]
            
            return results[:k]
        except Exception as e:
            logger.error(f"Similarity search with score failed: {e}")
            return []

    @staticmethod
    def _tokens(text: str) -> List[str]:
        """Tokenize Vietnamese and product codes without external NLP packages."""
        return search_tokens(text)

    @staticmethod
    def _matches_filter(doc: Document, filter: Dict = None) -> bool:
        if not filter:
            return True
        return all(doc.metadata.get(key) == value for key, value in filter.items())

    @staticmethod
    def _doc_key(doc: Document) -> tuple:
        """Stable identity shared by FAISS and docstore document instances."""
        return (
            doc.metadata.get("url") or doc.metadata.get("source") or "",
            doc.metadata.get("chunk_index", -1),
            doc.page_content,
        )

    def hybrid_search_with_score(
        self,
        query: str,
        k: int = None,
        filter: Dict = None,
        url_prefix: str = None,
    ) -> List[tuple]:
        """
        Combine dense FAISS retrieval and BM25-style lexical retrieval.

        The corpus is intentionally scanned because this project targets small
        websites. That also lets filtering happen before final top-k selection.
        Returned scores are normalized distances in [0, 1] (lower is better).
        """
        if not self._initialized:
            self.initialize()

        k = k or settings.RETRIEVAL_K
        max_candidates = max(k, settings.RAG_MAX_CANDIDATES)
        ntotal = int(getattr(self.vector_store.index, "ntotal", 0) or 0)
        dense_k = min(ntotal, max_candidates)
        dense_results = (
            self.vector_store.similarity_search_with_score(query, k=dense_k)
            if dense_k
            else []
        )

        def in_scope(doc: Document) -> bool:
            if not self._matches_filter(doc, filter):
                return False
            if url_prefix:
                url = doc.metadata.get("url", "") or doc.metadata.get("source", "")
                if not url.startswith(url_prefix):
                    return False
            return doc.metadata.get("source") != "init"

        dense_results = [(doc, score) for doc, score in dense_results if in_scope(doc)]

        docstore = getattr(self.vector_store.docstore, "_dict", {})
        corpus = [doc for doc in docstore.values() if isinstance(doc, Document) and in_scope(doc)]
        query_tokens = search_tokens(query, drop_stopwords=True)
        query_counts = Counter(query_tokens)
        unique_query_tokens = set(query_tokens)
        normalized_query = unicodedata.normalize("NFKC", query).lower().strip()

        lexical_scores = []
        if query_tokens and corpus:
            tokenized = [self._tokens(f"{doc.metadata.get('title', '')} {doc.page_content}") for doc in corpus]
            document_frequency = Counter()
            for tokens in tokenized:
                document_frequency.update(set(tokens))
            avg_len = sum(len(tokens) for tokens in tokenized) / max(1, len(tokenized))

            for doc, tokens in zip(corpus, tokenized):
                counts = Counter(tokens)
                score = 0.0
                for token, qtf in query_counts.items():
                    if not counts[token]:
                        continue
                    df = document_frequency[token]
                    idf = math.log(1 + (len(corpus) - df + 0.5) / (df + 0.5))
                    tf = counts[token]
                    length_norm = 1.2 * (0.25 + 0.75 * len(tokens) / max(1.0, avg_len))
                    score += qtf * idf * (tf * 2.2) / (tf + length_norm)

                title = unicodedata.normalize("NFKC", doc.metadata.get("title", "")).lower()
                normalized_doc = unicodedata.normalize(
                    "NFKC", f"{doc.metadata.get('title', '')} {doc.page_content}"
                ).lower()
                matched_tokens = unique_query_tokens.intersection(counts)
                match_count = len(matched_tokens)
                match_ratio = match_count / max(1, len(unique_query_tokens))
                exact_phrase_match = bool(
                    normalized_query and normalized_query in normalized_doc
                )
                if normalized_query and normalized_query in title:
                    score += 3.0
                if score > 0:
                    lexical_scores.append(
                        (doc, score, match_count, match_ratio, exact_phrase_match)
                    )

        lexical_scores.sort(key=lambda item: item[1], reverse=True)
        dense_results.sort(key=lambda item: item[1])

        # Reciprocal-rank fusion is robust across model-specific distance scales.
        fused: Dict[tuple, Dict] = {}
        dense_weight = settings.RAG_DENSE_WEIGHT
        keyword_weight = settings.RAG_KEYWORD_WEIGHT
        rrf_constant = 60

        for rank, (doc, dense_score) in enumerate(dense_results, start=1):
            key = self._doc_key(doc)
            fused.setdefault(
                key,
                {"doc": doc, "score": 0.0, "dense_score": None, "keyword_score": 0.0},
            )
            fused[key]["score"] += dense_weight / (rrf_constant + rank)
            fused[key]["dense_score"] = dense_score
        for rank, lexical_result in enumerate(lexical_scores, start=1):
            doc, lexical_score, match_count, match_ratio, exact_phrase_match = lexical_result
            key = self._doc_key(doc)
            fused.setdefault(
                key,
                {
                    "doc": doc,
                    "score": 0.0,
                    "dense_score": None,
                    "keyword_score": 0.0,
                    "keyword_match_count": 0,
                    "keyword_match_ratio": 0.0,
                    "exact_phrase_match": False,
                },
            )
            fused[key]["score"] += keyword_weight / (rrf_constant + rank)
            if exact_phrase_match:
                # RRF normally ignores score magnitude. Preserve a controlled
                # advantage for exact product names/codes without letting raw
                # BM25 scales dominate semantic retrieval.
                fused[key]["score"] += (keyword_weight * 0.5) / (rrf_constant + 1)
            fused[key]["keyword_score"] = lexical_score
            fused[key]["keyword_match_count"] = match_count
            fused[key]["keyword_match_ratio"] = match_ratio
            fused[key]["exact_phrase_match"] = exact_phrase_match

        ranked = sorted(fused.values(), key=lambda item: item["score"], reverse=True)[:k]
        if not ranked:
            return []
        best = ranked[0]["score"]
        results = []
        for item in ranked:
            source_doc = item["doc"]
            metadata = {
                key: value
                for key, value in source_doc.metadata.items()
                if key not in _TRANSIENT_RETRIEVAL_KEYS
            }
            metadata.update(
                {
                    "_retrieval": "hybrid",
                    "_dense_score": item["dense_score"],
                    "_keyword_score": item["keyword_score"],
                    "_keyword_match_count": item.get("keyword_match_count", 0),
                    "_keyword_match_ratio": item.get("keyword_match_ratio", 0.0),
                    "_exact_phrase_match": item.get("exact_phrase_match", False),
                }
            )
            result_doc = Document(
                page_content=source_doc.page_content,
                metadata=metadata,
            )
            results.append((result_doc, 1.0 - item["score"] / best))
        return results
    
    def delete_by_metadata(self, filter: Dict) -> bool:
        """Delete documents by metadata filter."""
        if not self._initialized:
            self.initialize()
        
        try:
            docstore = getattr(self.vector_store.docstore, "_dict", {})
            ids_to_delete = [
                doc_id
                for doc_id, doc in docstore.items()
                if isinstance(doc, Document) and self._matches_filter(doc, filter)
            ]
            if not ids_to_delete:
                return True
            self.vector_store.delete(ids=ids_to_delete)
            self._save_index()
            logger.info(f"Deleted {len(ids_to_delete)} vector documents matching {filter}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete documents: {e}")
            return False

    def get_documents_by_metadata(
        self,
        filter: Dict,
        limit: int = 100,
    ) -> List[Document]:
        """Return a read-only snapshot of documents matching metadata."""
        if not self._initialized:
            self.initialize()

        safe_limit = max(1, min(limit, 200))
        docstore = getattr(self.vector_store.docstore, "_dict", {})
        documents = [
            doc
            for doc in docstore.values()
            if (
                isinstance(doc, Document)
                and doc.metadata.get("source") != "init"
                and self._matches_filter(doc, filter)
            )
        ]
        documents.sort(
            key=lambda doc: (
                doc.metadata.get("url", ""),
                doc.metadata.get("chunk_index", -1),
            )
        )

        # Return new Document instances so callers cannot mutate FAISS docstore
        # metadata or page content accidentally.
        return [
            Document(page_content=doc.page_content, metadata=dict(doc.metadata))
            for doc in documents[:safe_limit]
        ]

    def count_unique_metadata_values(
        self,
        field: str,
        filter: Dict = None,
    ) -> int:
        """Count unique metadata values without changing the FAISS docstore."""
        if not self._initialized:
            self.initialize()

        docstore = getattr(self.vector_store.docstore, "_dict", {})
        values = {
            doc.metadata.get(field)
            for doc in docstore.values()
            if (
                isinstance(doc, Document)
                and doc.metadata.get("source") != "init"
                and self._matches_filter(doc, filter)
                and doc.metadata.get(field)
            )
        }
        return len(values)
    
    def clear_collection(self):
        """Clear all documents from the collection."""
        if not self._initialized:
            self.initialize()
        
        try:
            # Remove the index file and reinitialize
            if os.path.exists(self.index_path):
                import shutil
                shutil.rmtree(self.index_path, ignore_errors=True)
            
            # Reinitialize with empty index
            self.vector_store = FAISS.from_texts(
                ["Initial document"],
                self.embeddings,
                metadatas=[{"source": "init"}]
            )
            self._save_index()
            
            logger.info("Cleared vector store collection")
        except Exception as e:
            logger.error(f"Failed to clear collection: {e}")
            raise
    
    def get_collection_stats(self) -> Dict:
        """Get statistics about the collection."""
        if not self._initialized:
            self.initialize()
        
        try:
            count = self.vector_store.index.ntotal if self.vector_store else 0
            return {
                "name": "faiss_index",
                "count": count
            }
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {"name": "faiss_index", "count": 0}


# Singleton instance
_vector_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """Get or create VectorStore instance."""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
        _vector_store.initialize()
    return _vector_store

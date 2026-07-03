"""
RAG Engine with all best practices:
- Hybrid search (semantic + keyword)
- Query rewriting
- Document grading
- Conversation memory
- Structured output
- Source citations
- Q&A pair matching for trained responses
"""
import asyncio
import re
from typing import List, Dict, Optional, Tuple, AsyncGenerator
from datetime import datetime
from langchain_core.documents import Document
from loguru import logger
import numpy as np

from app.config import settings
from app.database import get_mongodb, get_vector_store
from app.services.factory import get_llm_service
from app.models.schemas import ChatResponse, SourceDocument


def _truncate_text(text: str, max_chars: int) -> str:
    if max_chars <= 0 or not text or len(text) <= max_chars:
        return text or ""
    return text[: max_chars - 1].rstrip() + "…"


def clean_model_output(text: str) -> str:
    """Clean model output before showing it to users."""
    if not text:
        return ""

    # Remove Qwen/Qwen3 reasoning blocks if any.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = text.replace("<think>", "").replace("</think>", "")

    # Remove common reasoning labels if they accidentally appear.
    text = re.sub(r"(?im)^\s*(analysis|reasoning|chain[- ]?of[- ]?thought)\s*:\s*", "", text)

    return text.strip()


class RAGEngine:
    """RAG Engine with production-ready features."""
    
    QA_MATCH_THRESHOLD = 0.85  # Confidence threshold for using Q&A pair directly
    
    def __init__(self, llm_service=None):
        self.llm = llm_service or get_llm_service()
        self.vector_store = get_vector_store()
        self._qa_cache: Dict[str, List[Dict]] = {}  # Cache Q&A pairs by site_id
        self._qa_embeddings_cache: Dict[str, List[Tuple[str, List[float]]]] = {}  # Cache Q&A embeddings
    
    async def _check_qa_match(
        self,
        query: str,
        site_id: str
    ) -> Optional[Tuple[Dict, float]]:
        """
        Check if there's a matching Q&A pair for the query.
        Returns the best matching Q&A pair and its similarity score if above threshold.
        """
        if not site_id:
            return None
        
        mongodb = await get_mongodb()
        
        # Get Q&A pairs (use cache if available)
        if site_id not in self._qa_cache:
            qa_pairs = await mongodb.get_qa_for_rag(site_id)
            self._qa_cache[site_id] = qa_pairs
            # Clear embeddings cache when Q&A pairs change
            self._qa_embeddings_cache.pop(site_id, None)
        
        qa_pairs = self._qa_cache.get(site_id, [])
        
        if not qa_pairs:
            return None
        
        try:
            # Get embeddings for Q&A questions if not cached
            if site_id not in self._qa_embeddings_cache:
                embeddings_model = self.vector_store.embeddings
                qa_embeddings = []
                
                for qa in qa_pairs:
                    question = qa.get("question", "")
                    embedding = embeddings_model.embed_query(question)
                    qa_embeddings.append((qa["id"], embedding))
                
                self._qa_embeddings_cache[site_id] = qa_embeddings
            
            qa_embeddings = self._qa_embeddings_cache.get(site_id, [])
            
            if not qa_embeddings:
                return None
            
            # Get query embedding
            embeddings_model = self.vector_store.embeddings
            query_embedding = embeddings_model.embed_query(query)
            query_embedding = np.array(query_embedding)
            
            # Find best matching Q&A pair using cosine similarity
            best_match = None
            best_score = 0.0
            
            for qa_id, qa_emb in qa_embeddings:
                qa_emb_array = np.array(qa_emb)
                
                # Cosine similarity
                dot_product = np.dot(query_embedding, qa_emb_array)
                norm_product = np.linalg.norm(query_embedding) * np.linalg.norm(qa_emb_array)
                
                if norm_product > 0:
                    similarity = dot_product / norm_product
                else:
                    similarity = 0.0
                
                if similarity > best_score:
                    best_score = similarity
                    best_match = next((qa for qa in qa_pairs if qa["id"] == qa_id), None)
            
            if best_match and best_score >= self.QA_MATCH_THRESHOLD:
                logger.info(f"Q&A match found: '{best_match['question'][:50]}...' with score {best_score:.3f}")
                return best_match, best_score
            
            return None
            
        except Exception as e:
            logger.warning(f"Q&A matching error: {e}")
            return None
    
    def invalidate_qa_cache(self, site_id: str = None):
        """Invalidate Q&A cache for a site or all sites."""
        if site_id:
            self._qa_cache.pop(site_id, None)
            self._qa_embeddings_cache.pop(site_id, None)
        else:
            self._qa_cache.clear()
            self._qa_embeddings_cache.clear()
    
    async def chat(
        self,
        message: str,
        session_id: str,
        user_id: str = None,
        site_id: str = None,
        stream: bool = False
    ) -> ChatResponse:
        """
        Process a chat message and generate a response.
        
        Args:
            message: User's message
            session_id: Conversation session ID
            user_id: Optional user ID for long-term memory
            site_id: Optional site ID to filter documents
            stream: Whether to stream the response
        
        Returns:
            ChatResponse with answer, sources, and suggestions
        """
        mongodb = await get_mongodb()
        
        # Get site URL filter and name if site_id provided
        site_url_filter = None
        site_name = None
        if site_id:
            site = await mongodb.db.sites.find_one({"site_id": site_id})
            if site:
                site_url_filter = site.get("url", "").rstrip("/")
                site_name = site.get("name") or site_url_filter.replace("https://", "").replace("http://", "")
                logger.info(f"Filtering by site: {site_url_filter}")
        
        try:
            # Load history and trained Q&A concurrently, then make follow-up
            # questions standalone before retrieval.
            history, qa_match = await asyncio.gather(
                mongodb.get_conversation_history(session_id, site_id=site_id),
                self._check_qa_match(message, site_id),
            )
            retrieved_docs = None

            if qa_match:
                qa_pair, qa_score = qa_match
                logger.info(f"Using Q&A pair response (score: {qa_score:.3f})")
                
                # Use Q&A pair directly
                answer = clean_model_output(qa_pair["answer"])
                # Trained Q&A is an administrator-authored answer, not an
                # external citation. Keep it out of customer-facing sources.
                sources = []
                confidence = min(0.98, qa_score + 0.05)
                
                # Increment Q&A use count
                await mongodb.increment_qa_use_count(qa_pair["id"])
                
                # Follow-up suggestions are disabled to avoid an extra LLM call.
                follow_ups = []
                
                # Save messages to history
                await mongodb.save_message(
                    session_id=session_id,
                    role="user",
                    content=message,
                    site_id=site_id
                )
                await mongodb.save_message(
                    session_id=session_id,
                    role="assistant",
                    content=answer,
                    sources=[s.dict() for s in sources],
                    site_id=site_id
                )
                
                return ChatResponse(
                    answer=answer,
                    sources=sources,
                    confidence=confidence,
                    follow_up_questions=follow_ups,
                    session_id=session_id
                )
            
            # 4. No Q&A match - rewrite follow-ups and retrieve documents.
            rewritten_query = await self._rewrite_query(message, history)
            if retrieved_docs is None:
                retrieved_docs = await self._retrieve_documents(
                    rewritten_query,
                    site_url_filter=site_url_filter,
                    site_id=site_id,
                )
            
            # 5. Grade documents for relevance
            relevant_docs = await self._grade_documents(rewritten_query, retrieved_docs)
            
            # 6. Build context from relevant docs
            context, sources = self._build_context(relevant_docs)
            
            # 7. Generate response
            answer = await self._generate_response(
                question=message,
                context=context,
                history=history,
                user_id=user_id,
                site_name=site_name
            )
            
            # 8. Follow-up suggestions are disabled to avoid an extra LLM call.
            follow_ups = []
            
            # 9. Calculate confidence
            confidence = self._calculate_confidence(relevant_docs)
            
            # 10. Save messages to history
            await mongodb.save_message(
                session_id=session_id,
                role="user",
                content=message,
                site_id=site_id
            )
            await mongodb.save_message(
                session_id=session_id,
                role="assistant",
                content=answer,
                sources=[s.dict() for s in sources],
                site_id=site_id
            )
            
            return ChatResponse(
                answer=answer,
                sources=sources,
                confidence=confidence,
                follow_up_questions=follow_ups,
                session_id=session_id
            )
            
        except Exception as e:
            logger.error(f"RAG engine error: {e}")
            raise
    
    async def chat_stream(
        self,
        message: str,
        session_id: str,
        user_id: str = None,
        site_id: str = None,
    ) -> AsyncGenerator[str, None]:
        """Stream a chat response (history + retrieval run in parallel)."""
        mongodb = await get_mongodb()

        site_url_filter = None
        site_name = None
        if site_id:
            site = await mongodb.db.sites.find_one({"site_id": site_id})
            if site:
                site_url_filter = site.get("url", "").rstrip("/")
                site_name = site.get("name") or site_url_filter.replace("https://", "").replace("http://", "")

        try:
            history = await mongodb.get_conversation_history(session_id, site_id=site_id)
            rewritten_query = await self._rewrite_query(message, history)
            retrieved_docs = await self._retrieve_documents(
                rewritten_query,
                site_url_filter=site_url_filter,
                site_id=site_id,
            )
            relevant_docs = await self._grade_documents(rewritten_query, retrieved_docs)
            context, sources = self._build_context(relevant_docs)

            prompt = self._build_prompt(message, context, history)
            system_prompt = self._get_system_prompt(site_name)

            full_response = ""
            async for chunk in self.llm.generate_stream(
                prompt,
                system_prompt,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
            ):
                full_response += chunk

            cleaned_response = clean_model_output(full_response)
            if cleaned_response:
                yield cleaned_response

            await mongodb.save_message(
                session_id, "user", message, site_id=site_id
            )
            await mongodb.save_message(
                session_id,
                "assistant",
                cleaned_response,
                sources=[s.dict() for s in sources],
                site_id=site_id,
            )
            
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield f"\n\nError: {str(e)}"
    
    async def _rewrite_query(
        self,
        query: str,
        history: List[Dict]
    ) -> str:
        """Rewrite query with conversation context."""
        if not history:
            return query
        
        # Format history
        history_text = "\n".join([
            f"{m['role'].title()}: {m['content'][:200]}"
            for m in history[-4:]  # Last 4 messages
        ])
        
        prompt = f"""Given the conversation history and the user's new question, rewrite the question to be a standalone search query that captures the full context.

Conversation history:
{history_text}

New question: {query}

Rewritten search query (just the query, no explanation):"""
        
        try:
            rewritten = await self.llm.generate(
                prompt,
                temperature=0.3,
                max_tokens=150
            )
            return rewritten.strip() or query
        except Exception as e:
            logger.warning(f"Query rewriting failed: {e}")
            return query
    
    async def _retrieve_documents(
        self,
        query: str,
        k: int = None,
        site_url_filter: str = None,
        site_id: str = None,
    ) -> List[Tuple[Document, float]]:
        """Retrieve relevant documents using hybrid search (runs in a thread pool so it can overlap I/O)."""
        k_val = k or settings.RETRIEVAL_K
        oversample = max(1, getattr(settings, "RAG_RETRIEVAL_OVERSAMPLE", 2))
        vs = self.vector_store
        sf = site_url_filter

        def _sync_retrieve() -> List[Tuple[Document, float]]:
            metadata_filter = {"site_id": site_id} if site_id else None
            use_hybrid = (
                getattr(settings, "RAG_HYBRID_SEARCH", True)
                and hasattr(vs, "hybrid_search_with_score")
            )
            if use_hybrid:
                results = vs.hybrid_search_with_score(
                    query,
                    k=k_val * oversample,
                    filter=metadata_filter,
                    url_prefix=sf,
                )
            else:
                results = vs.similarity_search_with_score(
                    query,
                    k=k_val * oversample,
                    filter=metadata_filter,
                )
            if sf:
                filtered_results = []
                for doc, score in results:
                    doc_url = doc.metadata.get("url", "") or doc.metadata.get("source", "")
                    if doc_url.startswith(sf):
                        filtered_results.append((doc, score))
                results = filtered_results
                logger.info(f"Filtered to {len(results)} docs for site: {sf}")
            results.sort(key=lambda x: x[1])
            return results[:k_val]

        return await asyncio.to_thread(_sync_retrieve)
    
    async def _grade_documents(
        self,
        query: str,
        docs: List[Tuple[Document, float]]
    ) -> List[Tuple[Document, float]]:
        """Grade documents for relevance."""
        if not docs:
            return []
        
        graded = []
        query_terms = set(re.findall(r"[\w-]+", query.lower(), flags=re.UNICODE))
        best_score = min(score for _, score in docs)

        for index, (doc, score) in enumerate(docs):
            doc_text = f"{doc.metadata.get('title', '')} {doc.page_content}".lower()
            overlap_ratio = (
                sum(1 for term in query_terms if term in doc_text) / len(query_terms)
                if query_terms
                else 0.0
            )

            if doc.metadata.get("_retrieval") == "hybrid":
                dense_score = doc.metadata.get("_dense_score")
                keyword_score = float(doc.metadata.get("_keyword_score") or 0.0)
                keep = (
                    keyword_score > 0
                    or (dense_score is not None and dense_score <= settings.RAG_MAX_DENSE_DISTANCE)
                    or overlap_ratio >= 0.25
                )
            else:
                # Dense distance scales differ by embedding model, so compare
                # with the best hit instead of using MiniLM's fixed threshold.
                keep = (
                    (score <= settings.RAG_MAX_DENSE_DISTANCE and score <= best_score + 0.45)
                    or overlap_ratio >= 0.3
                )

            if keep:
                graded.append((doc, score))

        return graded
    
    def _build_context(
        self,
        docs: List[Tuple[Document, float]]
    ) -> Tuple[str, List[SourceDocument]]:
        """Build context string and source list from documents."""
        if not docs:
            return "", []
        
        context_parts = []
        sources = []
        seen_urls = set()
        
        chunk_limit = getattr(settings, "RAG_CONTEXT_CHUNK_MAX_CHARS", 900)
        for doc, score in docs:
            body = _truncate_text(doc.page_content, chunk_limit)
            # Add to context
            context_parts.append(f"[Source: {doc.metadata.get('title', 'Unknown')}]\n{body}")
            
            # Add to sources (deduplicate by URL)
            url = doc.metadata.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                sources.append(SourceDocument(
                    url=url,
                    title=doc.metadata.get("title", "Unknown"),
                    content_preview=doc.page_content[:200] + "...",
                    relevance_score=self._normalized_relevance(doc, score),
                ))
        
        context = "\n\n---\n\n".join(context_parts)
        return context, sources

    @staticmethod
    def _normalized_relevance(doc: Document, score: float) -> float:
        """Normalize model-specific retrieval signals for UI/confidence."""
        if doc.metadata.get("_retrieval") == "hybrid":
            dense_score = doc.metadata.get("_dense_score")
            semantic = (
                max(0, min(1, 1 - float(dense_score) / 2))
                if dense_score is not None
                else 0.0
            )
            keyword_bonus = 0.15 if doc.metadata.get("_keyword_score", 0) else 0.0
            return min(1.0, semantic + keyword_bonus)
        return max(0, min(1, 1 - score / 2))
    
    def _get_system_prompt(self, site_name: str = None) -> str:
        """Get the system prompt for the chatbot (kept compact for lower latency)."""
        site_desc = site_name if site_name else "website này"
        return (
            f"Bạn là chatbot tư vấn bán hàng của {site_desc}. "
            "Yêu cầu đầu ra bắt buộc: chỉ hiển thị câu trả lời cuối cùng bằng tiếng Việt. "
            "Không hiển thị suy luận nội bộ, phân tích trung gian, chain-of-thought hoặc nội dung trong thẻ <think>. "
            "Nếu người dùng hỏi bằng tiếng Anh hoặc ngôn ngữ khác, vẫn trả lời bằng tiếng Việt, trừ khi người dùng yêu cầu dịch nguyên văn. "
            "Trả lời ngắn gọn, rõ ràng, lịch sự, phù hợp với chatbot tư vấn bán hàng. "
            "Không dùng các cụm như 'dựa trên ngữ cảnh', 'theo thông tin được cung cấp' hoặc 'cơ sở tri thức'. "
            "Nếu chưa có đủ thông tin, hãy nói chưa có đủ thông tin và đề nghị khách để lại số điện thoại/Zalo để nhân viên tư vấn."
        )
    
    def _build_prompt(
        self,
        question: str,
        context: str,
        history: List[Dict]
    ) -> str:
        """Build the full prompt with context and history."""
        # Format history
        history_text = ""
        if history:
            hmax = getattr(settings, "CHAT_HISTORY_MAX_MESSAGES", 4)
            cmax = getattr(settings, "CHAT_HISTORY_MESSAGE_MAX_CHARS", 350)
            history_text = "\n".join([
                f"{m['role'].title()}: {_truncate_text(m.get('content', '') or '', cmax)}"
                for m in history[-hmax:]
            ])
            history_text = f"Previous conversation:\n{history_text}\n\n"
        
        prompt = f"""{history_text}[Thông tin tham khảo]
{context if context else "Chưa có thông tin cụ thể trong dữ liệu."}

[Câu hỏi của khách]
{question}

[Yêu cầu đầu ra]
- Chỉ hiển thị câu trả lời cuối cùng bằng tiếng Việt.
- Không hiển thị suy luận nội bộ, phân tích trung gian, chain-of-thought hoặc nội dung trong thẻ <think>.
- Nếu khách hỏi bằng tiếng Anh hoặc ngôn ngữ khác, vẫn trả lời bằng tiếng Việt, trừ khi khách yêu cầu dịch nguyên văn.
- Trả lời tự nhiên, ngắn gọn, lịch sự và phù hợp với khách hàng đang cần tư vấn sản phẩm.
- Không nhắc các cụm như "ngữ cảnh", "thông tin được cung cấp" hoặc "cơ sở tri thức".
- Nếu dữ liệu chưa đủ để trả lời chắc chắn, hãy nói chưa có đủ thông tin và đề nghị khách để lại số điện thoại/Zalo để nhân viên tư vấn.
- Chỉ trả lời nội dung cần thiết cho khách, không giải thích cách bạn suy luận."""
        
        return prompt
    
    async def _generate_response(
        self,
        question: str,
        context: str,
        history: List[Dict],
        user_id: str = None,
        site_name: str = None
    ) -> str:
        """Generate the response using the LLM."""
        prompt = self._build_prompt(question, context, history)
        system_prompt = self._get_system_prompt(site_name)
        
        # Add user-specific context if available
        if user_id:
            mongodb = await get_mongodb()
            user_memory = await mongodb.get_user_memory(user_id)
            if user_memory:
                system_prompt += f"\n\nUser preferences: {user_memory}"
        
        response = await self.llm.generate(
            prompt,
            system_prompt,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
        )
        return clean_model_output(response)
    
    async def _generate_follow_ups(
        self,
        question: str,
        answer: str
    ) -> List[str]:
        """Generate follow-up question suggestions."""
        prompt = f"""Based on this Q&A, suggest 2-3 natural follow-up questions the user might ask.

Question: {question}
Answer: {answer[:500]}

Return only the questions, one per line, no numbering:"""
        
        try:
            response = await self.llm.generate(
                prompt,
                temperature=0.7,
                max_tokens=200
            )
            
            # Parse questions
            lines = response.strip().split("\n")
            questions = [
                line.strip().strip("-").strip("•").strip()
                for line in lines
                if line.strip() and "?" in line
            ][:3]
            
            return questions
        except Exception as e:
            logger.warning(f"Follow-up generation failed: {e}")
            return []
    
    def _calculate_confidence(
        self,
        docs: List[Tuple[Document, float]]
    ) -> float:
        """Calculate confidence score based on document relevance."""
        if not docs:
            return 0.3  # Low confidence with no sources
        
        scores = [self._normalized_relevance(doc, score) for doc, score in docs]
        avg_score = sum(scores) / len(scores)
        
        # Boost confidence if we have multiple sources
        source_bonus = min(0.2, len(docs) * 0.05)
        
        return min(0.95, avg_score + source_bonus)


# Singleton instance
_rag_engine: Optional[RAGEngine] = None


def get_rag_engine() -> RAGEngine:
    """Get or create RAGEngine instance."""
    global _rag_engine
    if _rag_engine is None:
        _rag_engine = RAGEngine()
    return _rag_engine

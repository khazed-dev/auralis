# SiteChat RAG — Tài liệu kỹ thuật chuyên sâu

## 1. Phạm vi tài liệu

Tài liệu này trình bày chi tiết bốn phần kỹ thuật cốt lõi của SiteChat:

1. Luồng thu thập và xử lý dữ liệu website.
2. Cách model embedding biểu diễn và so sánh dữ liệu.
3. Toàn bộ pipeline RAG từ câu hỏi đến câu trả lời.
4. Các nhánh xử lý và trường hợp trả lời khác nhau.

Tài liệu được viết dựa trên implementation hiện tại:

- Backend: FastAPI.
- Database nghiệp vụ: MongoDB.
- Embedding model: `BAAI/bge-m3`.
- Vector store: FAISS.
- Retrieval: dense search kết hợp keyword search.
- LLM sinh câu trả lời: `qwen/qwen3-32b` qua Groq API.
- Ngôn ngữ đầu ra chính: tiếng Việt.

Tài liệu tổng quan hệ thống và triển khai được trình bày tại
[`RAG_SYSTEM_VI.md`](./RAG_SYSTEM_VI.md).

---

# Phần I — Luồng thu thập và xử lý dữ liệu

## 2. Tổng quan ingestion pipeline

Ingestion là quá trình chuyển nội dung website thành dữ liệu có thể truy xuất bằng RAG.

```text
URL website
    |
    v
Crawler tải từng trang
    |
    v
HTML được phân tích thành văn bản
    |
    v
Indexer chia văn bản thành chunk
    |
    v
Tiêu đề + nội dung + metadata
    |
    v
BGE-M3 tạo embedding
    |
    v
FAISS lưu vector và Document
```

MongoDB và FAISS giữ hai loại dữ liệu khác nhau:

```text
MongoDB
  - Website
  - Crawl job
  - Metadata trang
  - Hội thoại
  - Trained Q&A

FAISS
  - Vector embedding
  - Nội dung từng chunk
  - Metadata phục vụ retrieval
```

## 3. Crawl website

Crawler bắt đầu từ một URL gốc và duyệt các liên kết nội bộ cho tới khi:

- Đạt giới hạn `MAX_PAGES`.
- Không còn liên kết hợp lệ.
- URL bị loại bởi include/exclude pattern.
- Trang không thể tải hoặc không có nội dung hữu ích.

Đầu ra logic của mỗi trang có dạng:

```python
{
    "url": "https://example.com/san-pham/c114",
    "title": "Khóa thông minh C114",
    "content": "Nội dung văn bản đã trích xuất...",
    "metadata": {
        # Metadata mở rộng nếu có
    }
}
```

Crawler chịu trách nhiệm thu thập dữ liệu, nhưng chưa tạo embedding. Việc chia chunk và embedding thuộc `IndexerService`.

## 4. Điều kiện một trang được index

Indexer đọc trường `content`:

```python
content = page.get("content", "")
```

Trang bị bỏ qua nếu:

- Không có nội dung.
- Nội dung ngắn hơn 50 ký tự.

Điều kiện này tránh tạo vector cho trang trống, redirect page hoặc nội dung không mang đủ thông tin.

## 5. Recursive text splitting

SiteChat sử dụng `RecursiveCharacterTextSplitter`.

Cấu hình:

```env
CHUNK_SIZE=700
CHUNK_OVERLAP=120
```

Danh sách separator:

```python
["\n\n", "\n", ". ", " ", ""]
```

Splitter lần lượt ưu tiên:

1. Tách theo đoạn văn.
2. Nếu đoạn vẫn quá dài, tách theo dòng.
3. Nếu vẫn quá dài, tách theo câu.
4. Sau đó tách theo khoảng trắng.
5. Cuối cùng mới tách cứng theo ký tự.

Mục tiêu là giữ các đơn vị ngữ nghĩa gần nhau lâu nhất có thể.

### 5.1. Ý nghĩa của chunk size

`CHUNK_SIZE=700` được tính theo ký tự, không phải token.

Chunk quá lớn:

- Có nhiều chủ đề trong cùng vector.
- Retrieval khó xác định đoạn nào thực sự liên quan.
- Context gửi tới LLM dài hơn.

Chunk quá nhỏ:

- Thông tin sản phẩm dễ bị chia vụn.
- Một chunk có thể mất tên sản phẩm hoặc điều kiện kỹ thuật liên quan.
- Retrieval cần lấy nhiều chunk hơn mới đủ nội dung.

Với website sản phẩm tiếng Việt, 700 ký tự là mức cân bằng giữa độ chi tiết và tính tập trung.

### 5.2. Ý nghĩa của overlap

`CHUNK_OVERLAP=120` giữ lại khoảng 120 ký tự giữa hai chunk liên tiếp.

Ví dụ trước khi chia:

```text
... sản phẩm sử dụng cho cửa nhôm Xingfa hệ 55.
Khóa hỗ trợ vân tay, mật khẩu và thẻ từ...
```

Nếu ranh giới chunk nằm giữa hai câu, overlap giúp chunk sau vẫn giữ phần mô tả đối tượng của chunk trước.

Đổi lại, overlap tạo một lượng nội dung trùng lặp trong FAISS. Vì vậy overlap không nên quá lớn so với chunk size.

## 6. Bổ sung tiêu đề vào chunk

Tên hoặc mã sản phẩm thường chỉ xuất hiện trong:

- Thẻ `<title>`.
- Heading H1.
- Tên trang.

Phần mô tả bên dưới có thể chỉ dùng các đại từ như “sản phẩm”, “thiết bị” hoặc “mẫu này”.

Indexer kiểm tra 200 ký tự đầu của chunk. Nếu tiêu đề chưa xuất hiện, nội dung dùng để embedding được tạo như sau:

```text
{title}

{chunk_content}
```

Ví dụ:

```text
Khóa thông minh C114

Sản phẩm hỗ trợ vân tay, mật khẩu, thẻ từ và chìa khóa cơ...
```

Điều này giúp:

- Dense embedding gắn thông số với đúng sản phẩm.
- Keyword search tìm được mã nằm trong title.
- Source hiển thị đúng tên trang.

## 7. Metadata của chunk

Mỗi chunk được chuyển thành một LangChain `Document`:

```python
Document(
    page_content=embedding_text,
    metadata={
        "url": page["url"],
        "title": title,
        "chunk_index": i,
        "total_chunks": len(texts),
        "source": page["url"],
        "word_count": len(text.split()),
        "site_id": effective_site_id,
    },
)
```

### 7.1. Vai trò của từng trường

| Trường | Vai trò |
|---|---|
| `url` | Liên kết source và định danh trang |
| `title` | Tăng chất lượng retrieval và hiển thị citation |
| `chunk_index` | Xác định vị trí chunk trong trang |
| `total_chunks` | Tổng số chunk của trang |
| `source` | Nguồn tương thích với LangChain |
| `word_count` | Thống kê độ dài |
| `site_id` | Cô lập dữ liệu giữa các website |

`site_id` được lấy theo thứ tự ưu tiên:

```text
site_id truyền trực tiếp vào index_pages
    ↓ nếu không có
page["site_id"]
    ↓ nếu không có
page["metadata"]["site_id"]
```

## 8. Xử lý khi crawl lại

Trước khi thêm chunk mới, indexer gọi:

```python
vector_store.delete_by_metadata({"url": page["url"]})
```

FAISS wrapper tìm các document ID có URL phù hợp, xóa chúng và lưu index lại.

Sau đó:

```python
vector_store.add_documents(chunks)
```

Quy trình cập nhật một URL:

```text
URL đã tồn tại
    |
    v
Xóa tất cả chunk cũ của URL
    |
    v
Chia lại nội dung hiện tại
    |
    v
Embedding lại bằng BGE-M3
    |
    v
Thêm chunk mới vào FAISS
```

Nhờ đó crawl lặp không làm tăng dần các bản sao của cùng một trang.

## 9. Ghi dữ liệu sau index

Sau khi FAISS lưu thành công:

- FAISS index được ghi xuống ổ đĩa.
- MongoDB lưu thông tin trang và số lượng chunk.
- Crawl job được cập nhật tiến độ.

MongoDB hiện lưu một preview của nội dung trang thay vì toàn bộ bản gốc trong luồng crawl. Vì vậy khi thay embedding model hoặc thay logic chunk, phương án chính xác nhất là crawl lại website nguồn.

## 10. Tính nhất quán khi cập nhật index

FAISS là vector store dạng file cục bộ. SiteChat chạy một Uvicorn worker để tránh:

- Hai process cùng ghi một index.
- Hai scheduler cùng crawl một website.
- Trạng thái FAISS trong RAM khác nhau giữa các worker.

Đối với quy mô dưới 100 trang, mô hình một process giúp implementation đơn giản và đủ hiệu năng.

---

# Phần II — Model embedding hiểu dữ liệu như thế nào?

## 11. “Hiểu” trong embedding có nghĩa gì?

Embedding model không hiểu dữ liệu giống con người và cũng không tạo câu trả lời.

Trong hệ thống này, “hiểu” nghĩa là:

> Model học một hàm biến đổi văn bản thành vector sao cho các văn bản có quan hệ ngữ nghĩa thường nằm gần nhau trong không gian vector.

Ký hiệu:

```text
f(text) = vector
```

Với BGE-M3:

```text
f("Khóa cửa mở bằng vân tay") → vector 1024 chiều
```

Ví dụ minh họa rút gọn còn ba chiều:

```text
"Khóa vân tay cho cửa nhôm"   → [0.81, 0.12, -0.34]
"Smart lock nhận diện tay"    → [0.78, 0.16, -0.29]
"Bản lề sàn chịu tải 150 kg"  → [-0.20, 0.74, 0.51]
```

Hai câu đầu có ý nghĩa gần nhau nên vector gần nhau. Câu thứ ba nói về sản phẩm khác nên vector xa hơn.

Vector thật có 1024 chiều; không thể gán trực tiếp một chiều cho “khóa” và một chiều cho “vân tay”. Ý nghĩa được phân bố trên toàn bộ representation.

## 12. Các bước bên trong embedding model

Ở mức khái niệm, quá trình gồm:

```text
Văn bản
  |
  v
Tokenizer
  |
  v
Danh sách token/subword
  |
  v
Transformer encoder
  |
  v
Contextual token representations
  |
  v
Pooling
  |
  v
Vector câu/đoạn văn
  |
  v
Normalization
```

### 12.1. Tokenization

Tokenizer không nhất thiết tách đúng từng từ tiếng Việt theo khoảng trắng. Nó có thể chia văn bản thành token hoặc subword đã học trong vocabulary.

Ví dụ minh họa:

```text
"khóa thông minh C114"
```

có thể được chia thành nhiều đơn vị biểu diễn nhỏ. Model sau đó kết hợp chúng theo ngữ cảnh.

### 12.2. Contextual encoding

Transformer tạo representation khác nhau cho cùng một từ tùy ngữ cảnh.

Ví dụ:

```text
"khóa cửa"
"khóa tài khoản"
```

Từ “khóa” xuất hiện trong cả hai câu nhưng ngữ nghĩa khác nhau. Các token xung quanh giúp model phân biệt hai trường hợp.

### 12.3. Pooling

Transformer tạo vector cho từng token. Pooling tổng hợp các vector token thành một vector đại diện cho toàn bộ chunk.

Đầu ra của BGE-M3 dense embedding trong cấu hình hiện tại có 1024 chiều.

## 13. BGE-M3 được dùng ở chế độ nào?

BGE-M3 hỗ trợ nhiều cơ chế retrieval:

- Dense retrieval.
- Sparse retrieval.
- Multi-vector/ColBERT-style retrieval.

SiteChat hiện sử dụng BGE-M3 qua `HuggingFaceEmbeddings`, do đó sử dụng phần dense embedding.

Sparse retrieval gốc của BGE-M3 chưa được gọi trực tiếp. Thay vào đó, SiteChat tự bổ sung keyword search kiểu BM25 để bắt mã sản phẩm và từ khóa chính xác.

Vì vậy hybrid search hiện tại là:

```text
BGE-M3 dense retrieval
        +
BM25-style lexical retrieval do SiteChat triển khai
```

## 14. Chuẩn hóa embedding

Cấu hình:

```python
encode_kwargs={
    "normalize_embeddings": True,
    "batch_size": 8,
}
```

Sau normalization:

```text
||vector|| = 1
```

Với hai vector chuẩn hóa `a` và `b`, squared L2 distance có quan hệ với cosine similarity:

```text
||a - b||² = 2 - 2 × cosine_similarity(a, b)
```

Điều này có nghĩa:

- Cosine similarity cao → L2 distance thấp.
- Cosine similarity thấp → L2 distance cao.

FAISS trả distance; code sắp xếp distance tăng dần.

## 15. Embedding document và embedding câu hỏi

Khi crawl:

```text
Document chunk → BGE-M3 → document vector → FAISS
```

Khi chat:

```text
Search query → BGE-M3 → query vector
```

Hai vector chỉ so sánh có ý nghĩa khi được tạo bởi cùng:

- Model.
- Phiên bản model.
- Cách chuẩn hóa.
- Không gian vector.

Vì vậy khi đổi embedding model, không thể tiếp tục dùng index cũ.

SiteChat tạo đường dẫn index theo model:

```text
faiss_index_baai_bge_m3
```

Điều này giảm nguy cơ nạp nhầm vector của model khác số chiều.

## 16. Vì sao embedding tìm được câu không trùng từ?

Giả sử document chứa:

```text
Sản phẩm đạt chuẩn chống nước IP65, phù hợp lắp đặt ngoài trời.
```

Người dùng hỏi:

```text
Khóa này có chịu được mưa không?
```

Keyword overlap có thể thấp vì:

- “chống nước” khác “chịu mưa”.
- “lắp ngoài trời” không xuất hiện trong câu hỏi.

BGE-M3 đã học quan hệ ngữ nghĩa giữa các cách diễn đạt này, nên vector có thể vẫn gần nhau.

Đây là ưu điểm của semantic retrieval so với tìm kiếm chuỗi đơn thuần.

## 17. Giới hạn của embedding

Embedding có một số giới hạn:

### 17.1. Mã sản phẩm

Các mã:

```text
C114
CO1148
AO11303
```

có ít ý nghĩa ngôn ngữ. Hai mã gần giống ký tự có thể không mang ý nghĩa gần nhau, và model không biết mã nào là sản phẩm nào nếu dữ liệu huấn luyện không chứa chúng.

Giải pháp: keyword search và title boosting.

### 17.2. Chunk chứa nhiều chủ đề

Nếu một chunk đồng thời nói về khóa, bản lề, gioăng và keo, vector là representation trung bình của nhiều chủ đề. Kết quả retrieval có thể kém tập trung.

Giải pháp: chunk nhỏ, dữ liệu trang rõ ràng và tiêu đề gắn vào chunk.

### 17.3. Thiếu dữ liệu nguồn

Embedding không tạo ra thông tin không tồn tại. Nếu crawler không lấy được thông số sản phẩm, retrieval không thể tìm thấy thông số đó.

### 17.4. Ý nghĩa phụ thuộc context

Vector cho cả đoạn có thể bị chi phối bởi phần nội dung dài, trong khi một thông số quan trọng chỉ xuất hiện một lần.

Giải pháp: chunking, keyword search và Trained Q&A cho thông tin cần cố định.

---

# Phần III — RAG hoạt động như thế nào?

## 18. Pipeline tổng thể

Pipeline của endpoint chat thông thường:

```text
1. Nhận message, session_id, site_id
2. Đọc website và URL cần lọc
3. Đọc lịch sử + kiểm tra Trained Q&A song song
4. Nếu Q&A khớp: trả trực tiếp
5. Nếu không: rewrite query theo lịch sử
6. Hybrid retrieval
7. Grade và lọc document
8. Build context + source
9. Build prompt
10. Gọi Groq/Qwen3
11. Làm sạch output
12. Tính confidence
13. Lưu hội thoại vào MongoDB
14. Trả ChatResponse
```

## 19. Input của RAG Engine

Các tham số chính:

```python
message: str
session_id: str
user_id: Optional[str]
site_id: Optional[str]
```

Ý nghĩa:

- `message`: câu hỏi gốc.
- `session_id`: khóa của hội thoại.
- `user_id`: dùng cho memory theo người dùng nếu có.
- `site_id`: giới hạn tri thức vào một website.

Nếu có `site_id`, backend đọc:

```text
site.url
site.name
```

URL được chuẩn hóa bằng cách bỏ dấu `/` cuối và dùng làm `url_prefix` khi retrieval.

## 20. Trained Q&A matching

## 20.1. Q&A cache

Các Q&A của từng website được tải từ MongoDB và cache theo `site_id`.

Cache gồm:

```text
_qa_cache
  site_id -> danh sách Q&A

_qa_embeddings_cache
  site_id -> [(qa_id, question_embedding)]
```

Embedding câu hỏi huấn luyện chỉ cần tạo lại khi cache bị invalidated.

## 20.2. Tính cosine similarity

Query mới được embedding:

```python
query_embedding = embeddings_model.embed_query(query)
```

Mỗi Q&A question embedding được so sánh bằng:

```text
cosine_similarity(q, d)
    = dot(q, d) / (norm(q) × norm(d))
```

Hệ thống chọn Q&A có score cao nhất.

Điều kiện direct answer:

```python
best_score >= 0.85
```

## 20.3. Direct-answer branch

Nếu Q&A khớp:

```text
answer = qa_pair["answer"]
sources = []
confidence = min(0.98, qa_score + 0.05)
```

Sau đó:

- Tăng `use_count`.
- Lưu user message.
- Lưu assistant message.
- Trả response.

Không gọi:

- Query rewrite.
- FAISS retrieval.
- Document grading.
- Groq generation.

## 21. Query rewriting

Nếu không có Q&A match, hệ thống dùng tối đa bốn message gần nhất để tạo standalone search query.

Prompt rewrite gồm:

```text
Conversation history
New question
Yêu cầu chỉ trả rewritten query
```

Ví dụ:

```text
Lịch sử:
User: Khóa C114 dùng cho cửa nào?
Assistant: ...

Câu mới:
Còn màu sắc?

Rewritten:
Khóa C114 có những màu sắc nào?
```

Rewrite query dùng để retrieval:

```text
rewritten_query → embedding/search
```

Câu hỏi gốc vẫn dùng khi tạo câu trả lời:

```text
message → final prompt
```

Nếu Groq rewrite lỗi hoặc trả chuỗi rỗng, hệ thống quay về query gốc.

## 22. Dense retrieval

FAISS nhận rewritten query và tạo query embedding.

Với website nhỏ, dense search có thể lấy tối đa:

```python
min(index.ntotal, RAG_MAX_CANDIDATES)
```

Mặc định:

```env
RAG_MAX_CANDIDATES=2000
```

Sau đó document được lọc theo:

- Metadata `site_id`.
- URL bắt đầu bằng URL website.
- Loại bỏ dummy document có `source="init"`.

Việc lấy nhiều candidate trước khi lọc khắc phục lỗi phổ biến:

> Lấy top-k toàn hệ thống trước, rồi mới lọc site có thể làm mất toàn bộ kết quả đúng của site.

## 23. Lexical retrieval kiểu BM25

## 23.1. Tokenization

Text được chuẩn hóa Unicode NFKC, chuyển lowercase và token hóa bằng regex:

```python
r"[\w]+(?:[-./][\w]+)*"
```

Regex giữ được các token như:

```text
c114
huavy
nhôm-kính
abc/123
```

Lexical text của mỗi document gồm:

```text
title + page_content
```

## 23.2. Document frequency

Với mỗi token, hệ thống đếm số document chứa token đó:

```text
df(token) = số document có token
```

Token hiếm như `c114` được đánh giá cao hơn token xuất hiện ở hầu hết document như `sản`, `phẩm`.

## 23.3. IDF

Công thức:

```text
idf = log(1 + (N - df + 0.5) / (df + 0.5))
```

Trong đó:

- `N`: tổng số document trong corpus đã lọc.
- `df`: số document chứa token.

## 23.4. Term frequency và length normalization

Với mỗi document:

```text
tf = số lần token xuất hiện
```

Length normalization:

```text
length_norm
  = 1.2 × (0.25 + 0.75 × doc_length / avg_doc_length)
```

Điểm token:

```text
token_score
  = query_tf × idf × (tf × 2.2) / (tf + length_norm)
```

Điểm lexical của document là tổng điểm các query token.

## 23.5. Title phrase boost

Nếu toàn bộ query xuất hiện trong title:

```python
score += 3.0
```

Ví dụ:

```text
Query: "khóa C114"
Title: "Khóa thông minh C114"
```

Document nhận title boost mạnh.

## 24. Reciprocal Rank Fusion

Dense score và lexical score có scale khác nhau:

- Dense dùng FAISS distance.
- Lexical dùng BM25-style score.

Không thể cộng trực tiếp hai giá trị.

SiteChat chuyển mỗi danh sách thành rank và dùng Reciprocal Rank Fusion:

```text
RRF contribution = weight / (60 + rank)
```

Trọng số:

```env
RAG_DENSE_WEIGHT=0.65
RAG_KEYWORD_WEIGHT=0.35
```

Fused score:

```text
fused(document)
  = 0.65 / (60 + dense_rank)
  + 0.35 / (60 + lexical_rank)
```

Nếu document chỉ xuất hiện trong một danh sách, nó chỉ nhận contribution từ danh sách đó.

Sau fusion, document được sắp xếp theo fused score giảm dần.

## 25. Retrieval score và metadata nội bộ

Kết quả hybrid trả một normalized ranking distance:

```text
score = 1 - fused_score / best_fused_score
```

- Document tốt nhất có score gần 0.
- Document kém hơn có score lớn hơn.

Để grading không nhầm rank score với semantic relevance tuyệt đối, document giữ thêm:

```text
_retrieval = "hybrid"
_dense_score = FAISS distance gốc
_keyword_score = lexical score gốc
```

Ba trường này là metadata nội bộ của retrieval.

## 26. Oversampling và final top-k

RAG Engine yêu cầu:

```text
k_val × oversample
```

Với cấu hình:

```env
RETRIEVAL_K=4
RAG_RETRIEVAL_OVERSAMPLE=3
```

Hybrid search trả tối đa 12 ứng viên. RAG Engine sắp xếp và cắt về bốn document trước document grading.

Oversampling tạo khoảng trống để:

- Fusion xếp hạng.
- Filter theo site.
- Loại document kém liên quan.

## 27. Document grading

Grading xác định document có đủ điều kiện đưa vào prompt hay không.

## 27.1. Query term overlap

Query được token hóa bằng regex Unicode. Hệ thống tính:

```text
overlap_ratio
  = số query term xuất hiện trong title/content
    / tổng số query term
```

## 27.2. Điều kiện cho hybrid result

Document được giữ nếu thỏa ít nhất một điều kiện:

```text
keyword_score > 0
```

hoặc:

```text
dense_score <= 1.25
```

hoặc:

```text
overlap_ratio >= 0.25
```

Điều này phản ánh ba kiểu bằng chứng:

1. Có từ khóa/mã sản phẩm khớp.
2. Có ngữ nghĩa đủ gần.
3. Có đủ query term xuất hiện trực tiếp.

## 27.3. Dense fallback

Nếu hybrid search bị tắt, dense result được giữ khi:

```text
score <= RAG_MAX_DENSE_DISTANCE
và
score <= best_score + 0.45
```

hoặc:

```text
overlap_ratio >= 0.3
```

Điều kiện relative window tránh giữ document quá xa so với kết quả tốt nhất.

## 28. Context construction

Mỗi relevant document được cắt tối đa:

```env
RAG_CONTEXT_CHUNK_MAX_CHARS=800
```

Context format:

```text
[Source: {title}]
{chunk body}

---

[Source: {title}]
{chunk body}
```

Source list được deduplicate theo URL.

Một URL có thể đóng góp nhiều chunk vào context, nhưng chỉ hiển thị một source link trong giao diện.

## 29. Relevance score hiển thị

Với hybrid result:

```text
semantic = clamp(1 - dense_score / 2, 0, 1)
keyword_bonus = 0.15 nếu keyword_score > 0
relevance = min(1, semantic + keyword_bonus)
```

Với dense fallback:

```text
relevance = clamp(1 - score / 2, 0, 1)
```

Đây là score quy ước cho UI, không phải xác suất document đúng.

## 30. Prompt construction

## 30.1. Lịch sử

Mặc định:

```env
CHAT_HISTORY_MAX_MESSAGES=4
CHAT_HISTORY_MESSAGE_MAX_CHARS=350
```

Chỉ một số message gần nhất được đưa vào prompt, mỗi message bị giới hạn độ dài.

## 30.2. User prompt

User prompt có cấu trúc:

```text
Previous conversation:
...

[Thông tin tham khảo]
{context}

[Câu hỏi của khách]
{original_question}

[Yêu cầu đầu ra]
- Trả lời tiếng Việt
- Không lộ suy luận nội bộ
- Ngắn gọn, lịch sự
- Không nói "dựa trên ngữ cảnh"
- Nếu thiếu dữ liệu, đề nghị để lại số điện thoại/Zalo
```

## 30.3. System prompt

System prompt xác định:

- Vai trò chatbot tư vấn bán hàng.
- Tên website/doanh nghiệp.
- Ngôn ngữ đầu ra.
- Phong cách phản hồi.
- Quy tắc xử lý khi thiếu dữ liệu.

## 30.4. Ranh giới trách nhiệm

```text
Retrieval quyết định LLM được nhìn thấy dữ liệu nào.
Prompt quyết định LLM phải hành xử như thế nào.
LLM quyết định cách diễn đạt câu trả lời.
```

Nếu retrieval lấy sai tài liệu, model có thể trả lời sai dù model ngôn ngữ mạnh.

Nếu retrieval đúng nhưng prompt không giới hạn, model có thể thêm suy đoán ngoài dữ liệu.

RAG tốt cần đồng thời:

- Dữ liệu nguồn tốt.
- Chunk tốt.
- Embedding phù hợp.
- Retrieval tốt.
- Prompt rõ ràng.

## 31. Gọi Groq

Payload OpenAI-compatible:

```json
{
  "model": "qwen/qwen3-32b",
  "messages": [
    {
      "role": "system",
      "content": "..."
    },
    {
      "role": "user",
      "content": "..."
    }
  ],
  "temperature": 0.4,
  "max_tokens": 600
}
```

Groq trả:

```text
choices[0].message.content
```

Backend làm sạch:

- Thẻ `<think>...</think>`.
- Nhãn `analysis`, `reasoning`, `chain-of-thought`.
- Khoảng trắng thừa.

## 32. Confidence

Nếu không có relevant document:

```text
confidence = 0.3
```

Nếu có document:

```text
avg_score = trung bình normalized relevance
source_bonus = min(0.2, số document × 0.05)
confidence = min(0.95, avg_score + source_bonus)
```

Với Trained Q&A:

```text
confidence = min(0.98, qa_similarity + 0.05)
```

Confidence là heuristic phục vụ UI và handoff logic; nó không phải xác suất được calibration.

## 33. Lưu kết quả

Backend lưu hai message:

```text
role=user
content=original_question

role=assistant
content=cleaned_answer
sources=[...]
```

Các message được gắn:

```text
session_id
site_id
timestamp
```

Lịch sử này được sử dụng ở lượt chat sau.

---

# Phần IV — Các trường hợp trả lời

## 34. Ma trận quyết định

| Điều kiện | Retrieval | Groq generation | Sources | Confidence |
|---|---:|---:|---:|---:|
| Trained Q&A score ≥ 0.85 | Không | Không | Ẩn | Rất cao |
| Không có Q&A, có relevant documents | Có | Có | Có thể hiện | Theo retrieval |
| Không có relevant documents | Có nhưng rỗng sau grading | Có | Không | 0.3 |
| Câu hỏi nối tiếp | Rewrite rồi retrieval | Có | Theo kết quả | Theo retrieval |
| Q&A cache/embedding lỗi | Bỏ qua Q&A | Có | Theo RAG | Theo retrieval |
| Query rewrite lỗi | Dùng query gốc | Có | Theo RAG | Theo retrieval |
| Groq generation lỗi | Pipeline báo lỗi | Lỗi | Không tạo answer bình thường | Không áp dụng |

## 35. Trường hợp A — Exact Trained Q&A

Ví dụ:

```text
Q&A đã huấn luyện:
Q: Ai là chủ website này?
A: ...

Người dùng:
Ai là chủ web này?
```

Nếu cosine similarity đạt 0.85:

```text
User query
   |
   v
Q&A embedding comparison
   |
   v
Direct answer
```

Kết quả:

- Nội dung đúng nguyên tắc do admin định nghĩa.
- Không có source link.
- Không phụ thuộc dữ liệu crawl.
- Không tốn một lượt Groq generation.

## 36. Trường hợp B — Semantic match

Document:

```text
Khóa đạt chuẩn chống nước, phù hợp lắp ngoài trời.
```

Query:

```text
Mẫu này có chịu được mưa không?
```

Luồng:

```text
Query rewrite nếu cần
  -> BGE-M3
  -> FAISS dense match
  -> relevant document
  -> context
  -> Groq
```

Dense retrieval là tín hiệu chính vì query và document không trùng nhiều từ.

## 37. Trường hợp C — Exact product code

Query:

```text
C114
```

Dense embedding có thể không đủ ổn định với mã ngắn. Keyword search:

- Tìm token `c114`.
- Ưu tiên title chứa `c114`.
- Kết hợp với dense rank.

Kết quả mong muốn là trang sản phẩm C114 đứng trước các sản phẩm có tên gần giống.

## 38. Trường hợp D — Query vừa có ý nghĩa vừa có mã

Query:

```text
Khóa C114 dùng cho cửa nhôm được không?
```

Hybrid search tận dụng:

- Dense: ý nghĩa “dùng cho cửa nhôm”.
- Lexical: mã `C114`.
- Title boost: tiêu đề chứa “C114”.

Đây là trường hợp hybrid search có lợi nhất.

## 39. Trường hợp E — Câu hỏi nối tiếp

Hội thoại:

```text
User: Gioăng EPDM có những loại nào?
Assistant: ...
User: Loại nào dùng cho cửa kính?
```

Rewrite:

```text
Trong các loại gioăng EPDM, loại nào dùng cho cửa kính?
```

Retrieval dùng rewritten query, nhưng final prompt vẫn hiển thị câu hỏi gốc cùng history.

## 40. Trường hợp F — Có retrieval nhưng thiếu dữ kiện để kết luận

Ví dụ document chỉ mô tả:

```text
Sản phẩm có nhiều màu sắc.
```

Query hỏi:

```text
Mẫu này có màu đen mờ không?
```

Retrieval có thể lấy đúng trang sản phẩm, nhưng context không xác nhận màu đen mờ.

System prompt yêu cầu model:

- Không tự suy đoán.
- Nói chưa đủ thông tin.
- Mời khách để lại số điện thoại/Zalo.

Đây là khác biệt giữa “tìm được trang liên quan” và “có đủ dữ kiện trả lời”.

## 41. Trường hợp G — Không có relevant document

Sau grading:

```text
relevant_docs = []
context = ""
sources = []
confidence = 0.3
```

Prompt nhận:

```text
Chưa có thông tin cụ thể trong dữ liệu.
```

Model được yêu cầu phản hồi theo fallback thay vì bịa câu trả lời.

## 42. Trường hợp H — Hỏi ngoài phạm vi website

Ví dụ:

```text
Thời tiết Hà Nội hôm nay thế nào?
```

Nếu website không chứa dữ liệu thời tiết:

- Keyword score gần 0.
- Dense distance thường cao.
- Document bị loại bởi grading.
- Chatbot dùng nhánh thiếu thông tin.

## 43. Trường hợp I — Nhiều document cùng URL

Một trang dài có thể cung cấp nhiều chunk:

```text
Chunk 0: giới thiệu sản phẩm
Chunk 1: thông số kỹ thuật
Chunk 2: ứng dụng
```

Nhiều chunk có thể được đưa vào context để LLM tổng hợp. Source list chỉ hiển thị URL một lần.

## 44. Trường hợp J — Nhiều website trong cùng FAISS

FAISS có thể chứa document của nhiều `site_id`.

Khi chatbot site A nhận câu hỏi:

```text
filter={"site_id": "site-A"}
url_prefix="https://site-a.example"
```

Document site B bị loại trước final top-k. Điều này ngăn chatbot lấy nhầm sản phẩm của website khác.

## 45. Trường hợp K — Query rewrite thất bại

Nếu Groq không phản hồi ở bước rewrite:

```python
return query
```

Pipeline vẫn tiếp tục retrieval bằng câu hỏi gốc.

Đây là graceful degradation: chất lượng câu hỏi nối tiếp có thể giảm nhưng request không dừng ngay tại rewrite.

## 46. Trường hợp L — Q&A matching thất bại

Nếu:

- MongoDB Q&A lỗi.
- Embedding Q&A lỗi.
- Cache bị lỗi.

`_check_qa_match` trả `None`.

Pipeline chuyển sang RAG thông thường. Người dùng vẫn có khả năng nhận câu trả lời từ dữ liệu crawl.

## 47. Trường hợp M — Groq lỗi

Nếu Groq trả HTTP status lỗi:

- Service ghi log status và response.
- HTTP client phát sinh exception.
- RAG Engine không tạo câu trả lời giả.
- Route/API xử lý lỗi theo cơ chế ứng dụng.

Widget hiển thị thông báo chung:

```text
Xin lỗi, đã có lỗi xảy ra. Vui lòng thử lại.
```

## 48. Trường hợp N — Human handoff

Handoff là nhánh ngoài RAG generation:

```text
Người dùng chọn "Gặp nhân viên"
    |
    v
Kiểm tra availability
    |
    +--> Có nhân viên: tạo pending handoff
    |
    +--> Không có: form liên hệ
```

Khi handoff active, tin nhắn được gửi tới agent thay vì RAG Engine.

## 49. Trường hợp O — Source visibility

Source từ website:

```text
https://...
```

có thể được trả về widget nếu cấu hình `show_sources=true`.

Trained Q&A:

```text
sources=[]
```

vì đây là câu trả lời do quản trị viên thiết lập, không phải citation từ một trang web.

## 50. Tóm tắt kỹ thuật

Toàn bộ pipeline có thể rút gọn thành:

```text
INGESTION
HTML
 -> text
 -> 700-char chunks, overlap 120
 -> title enrichment
 -> BGE-M3 1024-d normalized vectors
 -> FAISS

QUERY
message
 -> Trained Q&A cosine match
 -> query rewriting
 -> BGE-M3 dense search
 -> BM25-style keyword search
 -> weighted RRF
 -> site filtering
 -> document grading
 -> top relevant chunks
 -> context + history + original question
 -> Groq/Qwen3
 -> cleaned Vietnamese answer
 -> MongoDB conversation history
```

Vai trò của từng thành phần:

| Thành phần | Trách nhiệm |
|---|---|
| Crawler | Thu thập nội dung |
| Text splitter | Tạo đơn vị retrieval |
| BGE-M3 | Mã hóa ngữ nghĩa thành vector |
| FAISS | Tìm vector gần |
| Keyword scorer | Tìm mã/từ khóa chính xác |
| RRF | Hợp nhất dense và lexical rank |
| Document grader | Loại context kém liên quan |
| Prompt builder | Đóng gói dữ liệu và quy tắc |
| Qwen3/Groq | Sinh câu trả lời tự nhiên |
| MongoDB | Lưu dữ liệu nghiệp vụ và hội thoại |

Điểm quan trọng nhất:

> LLM không trực tiếp “nhớ” website. Website được biến thành các vector có thể tìm kiếm; tại mỗi câu hỏi, RAG chỉ chọn một số đoạn liên quan rồi đưa chúng cho LLM đọc và diễn đạt lại.

# Rà soát và vá bảo mật Auralis — 28/10/2026

## Mục tiêu

Người dùng không bị lộ hoặc mất hội thoại do API thiếu quyền; nội dung chatbot không được thực thi như mã của website; các đầu vào công khai/tenant không được dùng để gọi mạng nội bộ hoặc giả webhook. Vá các lỗi xác nhận được, giữ dữ liệu và các luồng hợp lệ.

Phạm vi: mã nguồn hiện tại trên `staging` (`bcb99f9`), API FastAPI, Next.js, widget, thư viện khóa phiên bản và cấu hình triển khai trong repository. Nhánh sửa: `codex/security-hardening`. Nhánh giao diện `codex/unified-web-interface` được giữ riêng. Không thử tấn công trên production, không đổi secrets/MongoDB/FAISS/model, không tự deploy.

## Phase 0 — Khảo sát và tái hiện (đã xác nhận các nhóm dưới)

**Phục vụ mục tiêu:** phân biệt lỗi có bằng chứng với khuyến nghị chung; chọn bản vá ở đúng ranh giới tin cậy.

- Đã đọc các route auth/chat/conversations/handoff/checkout/messenger, crawler/BYOK/upload/storage, widget và embed cùng các test hiện có.
- Tái hiện trong ứng dụng/transport giả lập hoặc thư mục tạm, không kết nối MongoDB thật, không gửi tin nhắn hay thanh toán thật.
- API/pattern được dùng: dependency auth và site access hiện có; response schema hiện có; aiohttp resolver/connector, httpx transport theo bản cài thực tế; HTML encoding theo đúng ngữ cảnh; HMAC SHA-256 trên raw webhook body.
- Tài liệu đối chiếu: [OWASP object-level authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/), [OWASP XSS](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html), [OWASP SSRF](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html). Thư viện được kiểm tra qua registry/advisory hiện hành, không suy đoán CVE từ tên gói.

| Nhóm đã xác nhận | Bằng chứng trước vá | Hướng sửa |
|---|---|---|
| Lịch sử chat thiếu quyền | `/api/chat/sessions`, GET/DELETE `/history/{session_id}` không yêu cầu auth; có thể lấy ID rồi đọc/xóa | Kiểm tra đăng nhập, quyền site cho từng đối tượng; không mở API legacy làm đường vòng |
| Handoff/SSE | Tra active handoff bằng session nhưng không kiểm tra site; xác thực SSE bỏ token_version/password gate | Kiểm tra site trước đọc/mutate; dùng cùng trạng thái auth như REST |
| Widget XSS | User/model/source/branding/agent-name có đường tới innerHTML không escape; link cho phép javascript | Encode nội dung và thuộc tính; allowlist giao thức URL; giữ markdown an toàn |
| Mã nhúng | Khi SITE_URL rỗng, forwarded host có thể thoát chuỗi JavaScript trong embed | Mã hóa JS literal và HTML attribute; kiểm tra URL và không tin forwarded host tùy ý |
| SSRF | BYOK nhận loopback; crawler kiểm tra DNS rồi resolver kết nối bằng đáp án DNS khác | Chặn đích không public tại cấu hình và kết nối; giữ hostname/SNI khi pin đích public; kiểm tra redirect |
| Upload/storage | Đọc toàn bộ upload trước giới hạn; DOCX nhỏ giải nén thành XML lớn; key storage đi ra khỏi base directory | Đọc có giới hạn, giới hạn archive, kiểm tra đường dẫn và symlink; không thay dữ liệu hiện có |
| Messenger webhook | POST không kiểm chữ ký; verify token mặc định rỗng | Fail closed khi thiếu cấu hình, HMAC raw body trước RAG/gửi tin |

Không coi việc có hàm `allow_dangerous_deserialization` trong FAISS là lỗ hổng từ xa nếu chưa có đường ghi index của kẻ tấn công; không đổi model hay định dạng vector index trong đợt này.

## Phase 1 — Vá và kiểm thử hồi quy

**Phục vụ mục tiêu:** đóng đường khai thác đã tái hiện mà vẫn giữ thao tác hợp lệ.

1. Auth/session/handoff/webhook: giữ pattern `require_auth` và `site_access`; test anonymous, owner, tenant khác, agent, token bị thu hồi và webhook không hợp lệ; xác nhận không có mutate/outbound call trước khi quyền/chữ ký đạt.
2. Widget/embed: vá tất cả sink đã tìm; test HTML, quote, URL nguy hiểm và mẫu bình thường; build widget, giữ API/markup tương thích. Không dựa riêng vào CSP.
3. Outbound/upload/storage: test private/metadata/IPv6, DNS rebind, redirect, upload quá cỡ, archive phình và key vượt thư mục; transport giả hoặc loopback lab tách biệt.
4. Dependency/request boundary: cập nhật tối thiểu gói có advisory qua lockfile; kiểm tra parser/proxy header được tin đúng; không chạy upgrade toàn bộ hoặc đổi model.

**Chống sai lệch:** không sửa rule giá/gói, không làm mềm phân quyền để test pass, không mock rỗng test chứng minh lỗi, không chỉ validate DNS một lần rồi tuyên bố đã chặn rebind, không thay secrets/dữ liệu production.

## Phase 2 — Kiểm chứng và bàn giao

**Phục vụ mục tiêu:** có bằng chứng bản vá hoạt động và biết rõ giới hạn còn lại.

- Chạy test tái hiện trước/sau khi hợp lý và toàn bộ pytest sau khi tích hợp.
- Web lint/build; widget regression/build/syntax; kiểm tra dependency advisory sau cập nhật.
- Review chéo diff, các caller và các trường hợp hợp lệ; ghi lại lỗi đã vá, mức độ, test và hạn chế thực tế ở phần kết quả.
- Commit/push nhánh vá để review; không merge `staging` hoặc deploy nếu chưa được người dùng yêu cầu cho đợt này.

## Kết quả

Các bản vá nằm trên nhánh `codex/security-hardening` để review riêng; không merge hoặc deploy production trong đợt rà soát này.

### Đã vá

- Legacy chat: bắt buộc đăng nhập và kiểm tra quyền site trước liệt kê/đọc/xóa; giới hạn tham số liệt kê. Feedback kiểm tra origin/site/session và chỉ số tin nhắn.
- Chặn tái sử dụng session và handoff của site khác; ghi hội thoại có điều kiện site. Public chat không được chọn bộ nhớ riêng của tài khoản bằng `user_id` tùy ý.
- SSE dùng cùng kiểm tra quyền, phiên bị thu hồi và buộc đổi mật khẩu như REST; kiểm tra lại trong stream.
- Đổi mật khẩu thu hồi JWT/refresh bằng một lần ghi nguyên tử. Refresh dùng compare-and-swap để chặn replay đồng thời và không hồi sinh phiên sau đổi mật khẩu. UI chuyển về đăng nhập.
- Messenger kiểm HMAC SHA-256 trên raw body trước gọi model/gửi tin; từ chối khi thiếu secret hoặc verify token. Sửa tham số RAG không được hỗ trợ để giữ luồng hợp lệ.
- Widget encode các nội dung visitor/model/agent/branding, xây citation bằng DOM, lọc URL và màu; giữ Markdown được hỗ trợ và lịch sử hợp lệ.
- Embed dùng generator chung và literal JSON an toàn; không lấy nguồn script từ forwarded host tùy ý; production cần `SITE_URL` hợp lệ trước tạo site/crawl.
- Crawler/BYOK kiểm địa chỉ DNS ở connector thực sự kết nối; chặn private/mixed DNS, metadata và redirect không an toàn, giữ TLS. Chỉ endpoint Ollama đúng cấu hình operator được phép local.
- Giới hạn byte thực của request trước parser/mutation, kể cả thiếu hoặc giả Content-Length; 10MB chung, 51MB cho multipart upload. Rate limiter dùng IP ASGI đã được server xử lý tin cậy, không tin raw X-Forwarded-For.
- Upload đọc có giới hạn; kiểm kích thước/số entry Office ZIP, số section và độ dài text; parser chạy ngoài event loop. Storage kiểm đường dẫn nằm trong thư mục gốc, gồm symlink.
- CSV leads/hội thoại trung hòa ô bắt đầu như công thức; không coi đây là bảo đảm mọi hành vi lưu/mở lại của mọi spreadsheet.
- Cập nhật `pypdf` lên 6.21.2; cập nhật tối thiểu zod/brace-expansion/fast-uri trong lock npm. Widget có regression suite và CI chạy suite trước build.

### Bằng chứng kiểm tra

- Toàn bộ backend: **680 passed, 6 skipped**, môi trường development, JWT test, model offline và database/transport tách biệt; không chạy lifespan production.
- Test lỗi trước vá đã thất bại đúng dự kiến ở các nhóm XSS, embed, request boundary, SSRF và quyền truy cập; sau vá đều đạt.
- Widget: **6 tests passed**, build và syntax check cả hai output đạt sau tích hợp.
- npm audit sau cập nhật trước lượt kiểm tra cuối: web và widget đều báo **0** advisory; đây là kiểm tra dependency npm, không chứng nhận toàn dự án an toàn.
- Web lint và build production kiểm tra lại đều đạt; TypeScript và 18 trang hoàn tất. Agent phụ đã dừng do workspace hết credits; parent hoàn tất lượt kiểm chứng cuối và chuẩn bị nhánh bàn giao.

### Cấu hình và giới hạn còn lại

- Messenger cần cấu hình `FB_APP_SECRET` thật để nhận callback hợp lệ. Không điền secret giả hay bỏ kiểm chữ ký để bật lại.
- Python inventory vẫn có **17 advisory ID khác nhau trên 9 package** sau khi vá pypdf (25 dòng feed do một số ID lặp). Torch bản CPU không được PyPI audit nhận diện. Xem `SECURITY_DEPENDENCY_RESIDUALS_2026-10-28.md`.
- Các thư viện AI/model còn cảnh báo, gồm đường tải model đang hoạt động từ cấu hình operator. Chưa nâng major LangChain/transformers/sentence-transformers, chưa xác minh revision/cache production; cần nhánh kiểm thử tương thích riêng. Không đánh dấu các cảnh báo đó là đã sửa hoặc false positive.
- Giới hạn upload và chạy parser ở thread không tạo CPU/memory sandbox; chưa kiểm tra tải đồng thời hoặc mọi dạng PDF độc hại. Storage traversal được tái hiện ở provider, chưa tìm thấy API công khai gọi provider này.
- Chưa chạy clean-install toàn bộ Linux lock, kiểm tra thực tế MongoDB/SSM, giao dịch thanh toán hoặc gửi Messenger thật. Không đổi dữ liệu, model, index, secret hay service production.

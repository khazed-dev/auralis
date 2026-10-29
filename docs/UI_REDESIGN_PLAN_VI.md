# Làm lại giao diện Auralis

## Mục tiêu

Toàn bộ web và widget dùng cùng ngôn ngữ thiết kế với landing page đã được duyệt: navy sâu, cyan nhẹ, chữ rõ ràng, nội dung gắn với website, tri thức và hội thoại. Chỉ thay đổi cách trình bày; giữ API, phân quyền, dữ liệu, các trường biểu mẫu, quy tắc gói và thanh toán.

Ngày kiểm kê: 27/10/2026. Điểm bắt đầu: `2b9a6dd`, nhánh `codex/modern-ai-landing`. Yêu cầu cập nhật của người dùng: triển khai giao diện, không chỉ lập kế hoạch. Trong lúc thực hiện, landing đã được merge qua PR #21 vào `origin/staging` (`bcb99f9`). Phần giao diện toàn website được bàn giao riêng trên nhánh `codex/unified-web-interface`; không tự merge hoặc triển khai phần này.

## Định hướng thiết kế

| Vai trò | Màu gốc | Cách dùng |
|---|---|---|
| Night | `#081721` | Sidebar, mảng nhận diện, tiêu đề trên nền sáng |
| Panel | `#10232f` | Bề mặt tối phân cấp |
| Cyan | `#62e6d0` | Điểm nhấn trên nền tối, trạng thái chọn |
| Ink | `#142934` | Nội dung chính trên nền sáng |
| Muted | `#62727b` | Nội dung phụ, không dùng cho thông tin quan trọng nếu thiếu tương phản |
| Paper | `#f6f9fa` | Nền khu vực thao tác |

- Giữ font đã cài: Plus Jakarta Sans cho tiêu đề, Inter cho biểu mẫu và nội dung; JetBrains Mono chỉ cho mã nhúng và định danh.
- Landing và mảng nhận diện có thể tối; biểu mẫu, danh sách và hộp hội thoại dùng nền sáng để đọc lâu.
- Màu thương hiệu do người dùng cấu hình vẫn được giữ; không thay màu riêng của chatbot bằng cyan cố định.
- Tiêu đề trang 26–32px, tiêu đề khối 17–20px, nội dung 14–16px, thông tin phụ tối thiểu 12px. Dòng nội dung thông thường dưới khoảng 80 ký tự khi có thể.
- Khoảng cách theo nhịp 4/8px; bo góc theo vai trò, không bo giống nhau mọi khối; bóng nhẹ chỉ cho khối nổi và hộp thoại.
- Không thêm số liệu, lời chứng thực hay khả năng AI chưa có. Không trang trí dashboard bằng orb/gradient ở mọi ô.
- Chuyển động ngắn cho thao tác mở/đóng/phản hồi; tôn trọng `prefers-reduced-motion`.

### Bố cục chủ đạo

```text
Desktop workspace
┌─────────────────┬───────────────────────────────────────────┐
│ Logo            │ Tên màn hình               Thao tác chính│
│ Điều hướng      ├───────────────────────────────────────────┤
│                 │ Bộ lọc / thông tin trạng thái             │
│ Website         │                                           │
│ Hội thoại       │ Nội dung thực tế: bảng / form / hội thoại │
│ Nhân viên       │                                           │
│ ...             │                                           │
│ Tài khoản       │                                           │
└─────────────────┴───────────────────────────────────────────┘

Hội thoại: danh sách bên trái | nội dung bên phải.
Cấu hình chatbot: biểu mẫu | xem trước ở màn hình rộng, xếp dọc khi hẹp.
Mobile: thanh đầu trang + menu mở theo yêu cầu; bảng cuộn trong khối;
giữ nút gửi/lưu và nội dung biểu mẫu trong vùng nhìn thấy.
```

Đã tự rà soát theo `frontend-design`: không sao chép hero thành dashboard tối toàn bộ; tính riêng của Auralis nằm ở nguồn tri thức, bản xem trước chatbot và hộp hội thoại. Các vùng thao tác còn lại tiết chế và nhất quán.

## Kiểm kê phạm vi và các hành vi phải giữ

| Màn hình / khối | Nguồn hiện có | Hành vi cần giữ |
|---|---|---|
| Landing `/` | `web/components/landing/LandingPage.tsx`, `landing.module.css` | Thiết kế đã duyệt, demo minh họa, liên kết, bảng gói |
| Đăng nhập `/login` | `web/app/login/page.tsx`, `web/components/auth/LoginForm.tsx` | Đăng nhập thật, trạng thái chờ/lỗi, chuyển trang theo vai trò |
| Chọn gói `/register` | `web/components/register/RegisterPage.tsx`, `landing/Pricing.tsx` | Đường dẫn checkout và liên hệ hiện có |
| Thanh toán `/checkout` | `web/components/checkout/CheckoutPage.tsx` | Quote, promo, tổng tiền, gateway POST, token phiên, pending/completed/expired |
| Khung dashboard | `web/components/dashboard/DashboardShell.tsx` | Vai trò, logout, menu mobile/thu gọn, phím tắt, buộc đổi mật khẩu |
| Website `/dashboard/sites` | `web/components/sites/SitesModule.tsx` | Thêm/xóa, max_pages, trạng thái crawl, polling |
| Chi tiết website | `web/components/sites/detail/*` | Đủ 11 tab; lưu từng phần; reset có xác nhận |
| Giao diện / hành vi AI | `ConfigPanels.tsx`, `ChatbotLivePreview.tsx` | Màu, avatar, lời chào, vị trí, prompt, tham số, nguồn; live preview chỉ khi chủ động |
| Câu hỏi gợi ý / trigger | `ManagementPanels.tsx` | CRUD, thứ tự, cooldown và trạng thái bật |
| Kho tri thức | `ManagementPanels.tsx` | Upload multipart, tài liệu, Q&A, xóa và bật/tắt |
| Thu thập dữ liệu | `CrawlingPanel.tsx` | Hàng đợi, đang chạy, hủy, lịch và lịch sử |
| Leads / handoff / bảo mật / nhúng | `OperationsPanels.tsx` | Thời gian làm việc, danh sách/xuất lead, domain, giới hạn, mã nhúng/SRI từ backend |
| Hội thoại | `web/components/conversations/ConversationsModule.tsx` | Tìm kiếm, lọc, phân trang, đánh dấu đã đọc, đổi trạng thái |
| Hộp thư nhân viên | `web/components/handoffs/HandoffsModule.tsx` | Queue 5s, detail 3s, nhận/gửi/kết thúc, khóa composer khi resolved/abandoned |
| Phân tích | `web/components/analytics/AnalyticsModule.tsx` | Số liệu thật, lọc website và 7d/30d, biểu đồ và nguồn |
| Đội ngũ | `web/components/team/TeamModule.tsx` | Người dùng/agent theo quyền, gán website, tạo/sửa/xóa |
| Cài đặt / trợ giúp | `web/components/settings/*`, `help/*` | Hồ sơ, branding, sức khỏe, hướng dẫn/phím tắt |
| Gói dịch vụ | `web/components/subscriptions/SubscriptionModule.tsx` | Hạn mức, nâng/hạ gói, yêu cầu, quote, BYOK không đọc lại key |
| Quản lý subscription cũ | `AdminSubscriptionsModule.tsx` | Lịch sử, hạn mức, duyệt yêu cầu, promo; không bỏ route |
| Platform | `web/components/platform/{PlatformShell,PlatformModule}.tsx` | 7 phần: tổng quan, khách hàng, gói, yêu cầu, promo, thanh toán, audit |
| Widget nhúng | `widget/src/chatbot.js` | Cấu hình từng site, session/history, nguồn, feedback, lead capture, trigger và handoff |

## Phase 0 — Khảo sát và tài liệu (đã hoàn tất)

**Phục vụ mục tiêu:** biết chính xác các màn hình và luồng đang chạy để giao diện mới không làm mất chức năng.

- Đã kiểm kê nguồn web, widget, API liên quan, role guards và kiểm thử.
- Đã đọc skill `C:/Users/KHA/.codex/skills/frontend-design/SKILL.md`.
- Tài liệu Next đi kèm bản cài: `web/node_modules/next/dist/docs/01-app/01-getting-started/11-css.md:188` (CSS Modules), `:294` (CSS global có thể xung đột giữa các route), `:458` (kiểm tra bản build); `05-server-and-client-components.md`; `03-api-reference/01-directives/use-client.md`.
- Pattern thực tế: `web/lib/auth.ts:76` (`authFetch`), `ui/PlatformBranding.tsx:50`, `ui/BrandLogo.tsx`, `ui/Icon.tsx`, `landing/LandingNavigation.tsx` và `landing/ProductDemo.tsx`.
- Tài liệu giao diện: [dialog và focus](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/), [tab bàn phím](https://www.w3.org/WAI/ARIA/apg/patterns/tabs/), [native dialog](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/dialog), [tương phản chữ](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).
- API được phép dùng: API và các hàm hiện có; CSS Modules, CSS custom properties, HTML semantic và hook React đang dùng. Không thêm framework giao diện hoặc đổi giao thức widget.
- Khoảng trống đã phát hiện: E2E còn nhắm `/app`/`/demo`; CI chưa chạy Playwright; giá trị gói trên marketing và backend không khớp; link quên mật khẩu chưa có route. Đây là vấn đề hiện có, không được tự thay quy tắc nghiệp vụ trong đợt giao diện.

**Kiểm chứng:** nguồn từng nhóm đã được đọc độc lập; các đề xuất chưa được xem là chức năng đã tồn tại.

## Phase 1 — Triển khai toàn bộ bề mặt giao diện

**Phục vụ mục tiêu:** áp dụng bộ nhận diện đã duyệt vào các màn hình hiện có mà giữ nguyên hành vi.

Ba phần công việc tách file để tránh ghi đè nhau:

1. **Nền tảng và dashboard:** token dùng chung, typography, biểu mẫu, nút, trạng thái, khung điều hướng và tất cả module dashboard; CSS được scope trong workspace, giữ landing độc lập.
2. **Trang công khai:** login/register/checkout, các trạng thái đợi/kết quả thanh toán, bảng chọn gói; tận dụng branding và giữ toàn bộ handler/payload hiện có.
3. **Platform và widget:** khung/tables/forms/modals quản trị, màu sắc và tỷ lệ widget, bản xem trước chatbot; giữ namespace `.sitechat-*` và màu do từng website cấu hình.

**Tài liệu và mẫu:** sao chép cách import CSS Modules trong Next docs; tái dùng font, branding, icon hiện có; giữ `authFetch`, cấu trúc config ở `sites/detail/types.ts`, toàn bộ API/handler thực tế.

**Chống sai lệch:** không đổi backend, schema, trạng thái nghiệp vụ, tên field, API, token, timer, localStorage/sessionStorage, quote/tổng tiền, model embedding, FAISS, MongoDB hay cấu hình deploy. Không thêm/sửa dữ liệu sản xuất khi xem thử. Không đổi sang React cho widget. Không sửa file widget build bằng tay. Không tạo nút chức năng giả.

**Kiểm chứng:** diff không có thay đổi backend; lint/build web; build và syntax-check widget; kiểm tra không mất input/action; review source các vùng có handler; chụp màn hình desktop/mobile và rà tràn ngang, focus, trạng thái chờ/lỗi.

## Phase 2 — Kiểm chứng, rà thiết kế và bàn giao

**Phục vụ mục tiêu:** chứng minh giao diện mới dùng được và vẫn nối đúng các luồng cũ.

- Review từng nhóm file, kiểm tra thay đổi CSS không vô tình tác động landing hay màu thương hiệu của khách hàng.
- Dùng trình duyệt với dữ liệu local hoặc response fixture tách biệt; ghi rõ màn nào đã kiểm tra tương tác và màn nào chỉ build/source review.
- Kích thước mục tiêu: 320/390/768/1440px. Kiểm tra chữ dài, bảng, menu thu gọn, menu mobile, các form/hộp thoại, danh sách hội thoại, mã nhúng, widget trái/phải.
- Bàn phím: tab/focus nhìn thấy, Escape và trở lại điểm mở khi có modal; không cho vượt màn buộc đổi mật khẩu. Chữ thông thường tương phản mục tiêu 4.5:1, chữ lớn 3:1 theo tài liệu W3C trên.
- Không xem E2E cũ là bằng chứng pass cho Next UI. Chỉ thêm test mới có mục đích rõ ràng nếu cần xác nhận hành vi UI thay đổi.
- Các lệnh bắt buộc: `web: npm run lint`, `web: npm run build`, `widget: npm run build`, `node --check widget/dist/chatbot.js`, `node --check widget/dist/chatbot.min.js`, `git diff --check`.
- Chưa merge/push staging trong lúc chỉnh sửa: staging đang tự deploy lên EC2. Sau khi kiểm tra, commit/push nhánh giao diện; chỉ merge khi người dùng yêu cầu cho đợt này.

**Bằng chứng cần bàn giao:** danh sách file, screenshot, kết quả kiểm tra, giới hạn kiểm chứng thực tế. API/CI cũ vẫn là hàng rào khi tạo PR nhưng không thay thế visual QA.

## Ngoài phạm vi giao diện

- Sửa catalog giá/hạn mức, dựng lại checkout hoặc thay gateway.
- Xây tính năng khôi phục mật khẩu, thêm notes/tags/export chưa có trên UI.
- Đổi cơ chế auth, role, polling sang SSE, cache dữ liệu hoặc API.
- Thay model, vector store, crawl engine, dữ liệu hay dịch vụ production.
- Thêm theme switcher, framework CSS, thư viện animation/chart nếu CSS/SVG và các thành phần có sẵn đã đủ.

## Cách tiếp tục ở một phiên khác

Đọc file này, skill frontend-design và `git status` trước. Kiểm tra nhánh và diff hiện tại, không ghi đè thay đổi đang có. Đọc báo cáo kiểm chứng đi kèm nếu có; hoàn thành phần còn thiếu của Phase 1–2. Giữ yêu cầu cốt lõi: chỉ giao diện, giữ hành vi và dữ liệu.

## Bản ghi triển khai và kiểm chứng — 27/10/2026

**Trạng thái:** đã hoàn thành Phase 1–2 trong phạm vi giao diện, gồm lượt lint/build cuối sau visual QA. Nhánh bàn giao là `codex/unified-web-interface`, tách khỏi landing đã merge ở PR #21. Không tự merge hoặc triển khai phần giao diện toàn website lên EC2.

### Phạm vi đã hoàn thành

| Nhóm | Tệp triển khai | Kết quả |
|---|---|---|
| Nền tảng và dashboard | `web/app/theme.css`, import trong `layout.tsx`, `components/dashboard/{DashboardShell.tsx,workspace.module.css}` | Token chung; sidebar navy, bề mặt thao tác sáng; typography, form, nút, bảng, trạng thái và responsive cho tất cả module dashboard trong bảng kiểm kê. Giữ `globals.css` hiện có, scope lớp mới trong workspace. |
| Website | `components/sites/SitesModule.tsx`, workspace CSS | Sửa mô tả cũ về chức năng “sắp chuyển”; giữ danh sách, thêm/xóa, polling và toàn bộ 11 tab cấu hình. Màu, trường biểu mẫu, tài liệu, nguồn, lịch crawl và mã nhúng vẫn dùng cấu trúc cũ. |
| Trang công khai | `app/login/page.tsx`, `components/auth/{LoginForm.tsx,auth.module.css}`, `components/register/{RegisterPage.tsx,register.module.css}`, `components/checkout/{CheckoutPage.tsx,checkout.module.css}` | Nhận diện thống nhất cho đăng nhập, chọn gói, thanh toán và các trạng thái kết quả. Thay lời chứng thực không có nguồn bằng sơ đồ website → tri thức → câu trả lời. Không đổi giá, quote, gateway hoặc dữ liệu đơn hàng. |
| Platform | `components/platform/{PlatformShell.tsx,PlatformModule.tsx,platform.module.css}` | Chung shell với dashboard; giao diện bảy khu vực, bảng, form và hộp thoại quản trị. |
| Chatbot | `widget/src/chatbot.js`, `components/sites/detail/{ChatbotLivePreview.tsx,preview.module.css}` | Giao diện widget và preview đồng bộ; vẫn dùng màu riêng của website, namespace `.sitechat-*`, session/history, nguồn và các trạng thái hiện có. Widget dist được tạo bằng build, không chỉnh tay. |

Đường dẫn ở bảng trên nằm trong `web/` trừ khi đã ghi rõ `web/`, `widget/` hoặc `docs/` ở đầu.

### Kiểm tra mã nguồn và lệnh

- Lượt kiểm tra cuối: `web: npm run lint` và `web: npm run build` thành công, build 18 trang. Bản production dùng API `/api`, không bật mock auth hoặc dev bypass.
- `widget: npm run build`, `node --check widget/dist/chatbot.js` và `node --check widget/dist/chatbot.min.js` thành công; `git diff --check` sạch. Hai tệp CSS nền tảng/workspace được PostCSS parse thành công.
- So sánh AST TypeScript, bỏ import và JSX, xác nhận logic còn lại không đổi trong `LoginForm`, `CheckoutPage`, `DashboardShell`, `PlatformModule`, `PlatformShell` và `ChatbotLivePreview`. Review diff JSX giữ handler, trường và hành động; thay đổi gồm trình bày, nội dung và thuộc tính hỗ trợ truy cập.
- Nguồn widget ngoài chuỗi `baseWidgetCss` không đổi khi chuẩn hóa CRLF/LF. Các hàm gọi API, timer, session/history và render hành vi được giữ nguyên.
- Diff không thay backend, schema, package/lock, workflow, deploy, model embedding hay dữ liệu. Giá và hạn mức hiện có không được sửa trong đợt này.

### Kiểm tra trình duyệt đã thực hiện

Các kiểm tra sau dùng môi trường local và phản hồi fixture tách biệt, không phải thao tác trên tài khoản hay dữ liệu production.

| Khu vực | Bằng chứng đã quan sát |
|---|---|
| Dashboard desktop | Đã xem Website, cấu hình Giao diện, Phân tích, Hội thoại, Handoff, Đội ngũ, Cài đặt và Trợ giúp ở 1440px. |
| Dashboard mobile | Các màn trên cùng login/register/checkout không tràn ngang ở 320px. Cấu hình Giao diện ở 390px giữ form và điều hướng đủ 11 tab. Chọn mục trong menu mobile đóng menu; menu đóng không để link ngoài màn hình nhận focus. |
| Phân tích | Nút chọn 30 ngày hoạt động. Đây là kiểm tra tương tác với fixture, không xác nhận tính đúng số liệu backend. |
| Platform | Bảy route mở được ở 390px, gồm audit có bản ghi fixture. Modal tạo gói nằm trong viewport và cuộn được; không submit thay đổi. |
| Phân quyền điều hướng | Bản web build ở production mode với auth fixture chuyển đúng người dùng platform và người dùng dashboard. Không thay thế kiểm thử bảo mật API. |
| Gói dịch vụ | Fixture nạp vào component thực tế và hiển thị hạn mức. Không gửi yêu cầu đổi gói hoặc thanh toán. |
| Trang công khai production | Register ở 1440px không tràn ngang; đã rà giao diện đăng nhập trên bản production. |
| Thanh toán | Bản production ở 320px nạp được quote fixture và các trường biểu mẫu hiện có; mã promo `INVALID` hiển thị thông báo lỗi. Không submit thanh toán hoặc tạo đơn. |
| Widget | Ở 390px và 320px, gửi câu hỏi nhận phản hồi minh họa kèm nguồn, khôi phục history và giữ màu website. Khung cuối rộng 366px tại 390px và 296px tại 320px, cách mép trái 12px. |

Ảnh kiểm chứng local nằm tại `../audit-2026-10-27/full-ui-redesign/` tính từ thư mục gốc repository: `platform-desktop.jpg`, `widget-mobile.jpg`; các ảnh khác có thể được bổ sung trong lượt kiểm tra cuối.

### Giới hạn và việc không thực hiện

- Không thanh toán thật, không tạo/xóa dữ liệu production, không thay secrets hoặc dịch vụ EC2.
- Không chạy bộ E2E cũ nhắm giao diện `/app`; không dùng các spec đó làm bằng chứng cho Next UI. Không chạy lại backend test vì diff chỉ giao diện và logic backend giữ nguyên.
- Không tuyên bố đạt WCAG đầy đủ hoặc kiểm toán toàn bộ bàn phím/tương phản. Bề mặt form, dialog và focus đã được cải thiện; các hành vi modal có sẵn không được viết lại trong đợt này.
- Chưa kiểm tra mọi tổ hợp lỗi mạng, mọi trạng thái thanh toán/handoff/lead trên trình duyệt hoặc mọi màu thương hiệu do khách hàng nhập. Các nhánh tương ứng được giữ qua source review và build; không suy ra chúng đã được thử giao dịch thực tế.
- Mâu thuẫn catalog giá/hạn mức, link quên mật khẩu chưa có route và khoảng trống E2E là vấn đề có sẵn, vẫn ngoài phạm vi giao diện như kế hoạch.

**Bước bàn giao tiếp theo:** review diff trên `codex/unified-web-interface`; có thể tạo PR vào `staging` để CI kiểm tra. Chỉ merge khi người dùng yêu cầu cho phần giao diện này vì merge staging sẽ kích hoạt triển khai EC2. Không coi kiểm tra local với fixture là bằng chứng một giao dịch hay thao tác quản trị thật đã thành công.

import Link from "next/link";
import { Icon, type IconName } from "@/components/ui/Icon";

const steps: Array<{
  step: string;
  title: string;
  description: string;
  href: string;
  icon: IconName;
}> = [
  {
    step: "Bước 1",
    title: "Thêm website",
    description:
      "Nhập địa chỉ website để Auralis bắt đầu xây dựng kho tri thức.",
    href: "/dashboard/sites",
    icon: "globe",
  },
  {
    step: "Bước 2",
    title: "Chờ lập chỉ mục",
    description:
      "Theo dõi tiến trình crawl và số trang đã được xử lý trong chi tiết website.",
    href: "/dashboard/sites",
    icon: "chart",
  },
  {
    step: "Bước 3",
    title: "Tinh chỉnh trợ lý",
    description:
      "Cấu hình giao diện, system prompt và bổ sung tài liệu hoặc Q&A.",
    href: "/dashboard/sites",
    icon: "sparkles",
  },
  {
    step: "Bước 4",
    title: "Cài đặt chatbot",
    description:
      "Sao chép mã bảo mật trong tab Mã nhúng và đặt trước thẻ đóng </body>.",
    href: "/dashboard/sites",
    icon: "document",
  },
];

const faqs = [
  {
    question: "Website được crawl lại bao lâu một lần?",
    answer:
      "Mặc định website không tự crawl lại. Mở Chi tiết website → Crawling để bật lịch hàng ngày, hàng tuần, hàng tháng hoặc cron tùy chỉnh.",
  },
  {
    question: "Làm thế nào để chuyển hội thoại cho nhân viên?",
    answer:
      "Bật Human Handoff trong cấu hình website. Khi khách yêu cầu hoặc AI không đủ tự tin, phiên sẽ xuất hiện trong module Handoff để nhân viên tiếp nhận.",
  },
  {
    question: "Có thể tải lên những định dạng tài liệu nào?",
    answer:
      "Hệ thống hỗ trợ PDF, DOC, DOCX, TXT, Markdown, CSV, PowerPoint, Excel và HTML. Giới hạn hiện tại là 50 MB cho mỗi tệp.",
  },
  {
    question: "Thêm nhân viên hỗ trợ như thế nào?",
    answer:
      "Mở module Đội ngũ, chọn Nhân viên hỗ trợ và phân công những website họ được phép tiếp nhận handoff.",
  },
  {
    question: "Tôi có thể tùy chỉnh chatbot không?",
    answer:
      "Có. Trong Chi tiết website → Giao diện, bạn có thể đổi màu, tiêu đề, lời chào, vị trí, ảnh đại diện và branding.",
  },
  {
    question: "Vì sao widget báo Unauthorized hoặc không hiển thị?",
    answer:
      "Kiểm tra domain trong tab Security, mã nhúng và data-site-id. Với production, domain đang chạy widget phải nằm trong danh sách cho phép.",
  },
];

export function HelpModule() {
  return (
    <main className="dashboard-content help-module">
      <section className="help-hero-new">
        <span>
          <Icon name="help" />
        </span>
        <div>
          <h1>Auralis có thể giúp gì cho bạn?</h1>
          <p>Hướng dẫn bắt đầu và câu trả lời cho những vấn đề thường gặp.</p>
        </div>
      </section>

      <section className="help-section-new">
        <header>
          <h2>Bắt đầu nhanh</h2>
          <p>Đưa trợ lý AI lên website qua bốn bước.</p>
        </header>
        <div className="help-step-grid">
          {steps.map((item) => (
            <Link href={item.href} key={item.step}>
              <span className="help-step-icon">
                <Icon name={item.icon} />
              </span>
              <small>{item.step}</small>
              <h3>{item.title}</h3>
              <p>{item.description}</p>
              <strong>Mở module →</strong>
            </Link>
          ))}
        </div>
      </section>

      <div className="help-bottom-grid">
        <section className="help-section-new help-faq-new">
          <header>
            <h2>Câu hỏi thường gặp</h2>
            <p>Những câu trả lời ngắn cho các tình huống phổ biến.</p>
          </header>
          <div>
            {faqs.map((faq, index) => (
              <details key={faq.question} open={index === 0}>
                <summary>
                  <span>{faq.question}</span>
                  <strong>+</strong>
                </summary>
                <p>{faq.answer}</p>
              </details>
            ))}
          </div>
        </section>

        <aside>
          <section className="help-section-new help-links">
            <header>
              <h2>Đi tới nhanh</h2>
            </header>
            <Link href="/dashboard/sites">
              <Icon name="globe" /> Quản lý website
            </Link>
            <Link href="/dashboard/conversations">
              <Icon name="message" /> Xem hội thoại
            </Link>
            <Link href="/dashboard/handoffs">
              <Icon name="headset" /> Hàng chờ Handoff
            </Link>
            <Link href="/dashboard/team">
              <Icon name="users" /> Quản lý đội ngũ
            </Link>
            <Link href="/dashboard/settings">
              <Icon name="settings" /> Cài đặt tài khoản
            </Link>
          </section>

          <section className="help-section-new help-shortcuts-new">
            <header>
              <h2>Phím tắt</h2>
            </header>
            <div>
              <span>Website</span>
              <kbd>G</kbd><i>rồi</i><kbd>S</kbd>
            </div>
            <div>
              <span>Hội thoại</span>
              <kbd>G</kbd><i>rồi</i><kbd>C</kbd>
            </div>
            <div>
              <span>Handoff</span>
              <kbd>G</kbd><i>rồi</i><kbd>H</kbd>
            </div>
            <div>
              <span>Cài đặt</span>
              <kbd>,</kbd>
            </div>
          </section>
        </aside>
      </div>
    </main>
  );
}

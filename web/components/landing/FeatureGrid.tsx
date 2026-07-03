import { Icon, type IconName } from "@/components/ui/Icon";

const features: Array<{
  icon: IconName;
  title: string;
  text: string;
  className?: string;
  badge?: string;
}> = [
  {
    icon: "globe",
    title: "Thu thập dữ liệu website thông minh",
    text: "Tự động đồng bộ website, blog và trung tâm trợ giúp. Auralis đọc, hiểu nội dung để đưa ra câu trả lời chính xác.",
    className: "feature-large feature-art",
    badge: "Đang đồng bộ 48 trang...",
  },
  {
    icon: "document",
    title: "Tải tài liệu lên",
    text: "Thêm PDF, Word và tệp văn bản để mở rộng kho tri thức chỉ trong vài thao tác.",
  },
  {
    icon: "sparkles",
    title: "Kiến trúc RAG",
    text: "Câu trả lời được tổng hợp trực tiếp từ nguồn dữ liệu của bạn, giúp hạn chế thông tin sai lệch.",
  },
  {
    icon: "headset",
    title: "Chuyển tiếp cho nhân viên liền mạch",
    text: "Khi gặp yêu cầu phức tạp, hội thoại được chuyển ngay cho nhân viên kèm đầy đủ ngữ cảnh và lịch sử trao đổi.",
    className: "feature-large",
    badge: "AI  →  Nhân viên",
  },
];

export function FeatureGrid() {
  return (
    <section className="section container" id="features">
      <div className="section-heading">
        <h2>Mọi thứ bạn cần để tự động hóa hỗ trợ khách hàng</h2>
        <p>Công nghệ RAG mạnh mẽ trong một giao diện trực quan, dễ sử dụng.</p>
      </div>
      <div className="feature-grid">
        {features.map((feature) => (
          <article className={`feature-card ${feature.className ?? ""}`} key={feature.title}>
            <Icon name={feature.icon} />
            <h3>{feature.title}</h3>
            <p>{feature.text}</p>
            {feature.badge && <span className="feature-badge">{feature.badge}</span>}
          </article>
        ))}
      </div>
    </section>
  );
}

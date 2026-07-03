import { Icon } from "@/components/ui/Icon";

const plans = [
  {
    key: "starter",
    name: "Khởi đầu",
    price: "Miễn phí",
    suffix: "",
    features: [
      "Dùng thử đầy đủ trong 7 ngày",
      "100 hội thoại AI",
      "Lập chỉ mục 50 trang",
      "Báo cáo cơ bản",
    ],
    cta: "Bắt đầu dùng thử",
  },
  {
    key: "growth",
    name: "Tăng trưởng",
    price: "2,4 triệu",
    suffix: "VNĐ/tháng",
    features: [
      "2.000 hội thoại AI mỗi tháng",
      "Không giới hạn số trang",
      "Tải lên PDF và Word",
      "Chuyển tiếp cho nhân viên",
    ],
    cta: "Chọn gói Tăng trưởng",
    popular: true,
  },
  {
    key: "business",
    name: "Doanh nghiệp",
    price: "9,8 triệu",
    suffix: "VNĐ/tháng",
    features: [
      "10.000 hội thoại AI mỗi tháng",
      "Hỗ trợ ưu tiên",
      "Truy cập API",
      "Tùy chỉnh thương hiệu",
    ],
    cta: "Liên hệ tư vấn",
  },
  {
    key: "custom",
    name: "Tùy chỉnh",
    price: "Linh hoạt",
    suffix: "",
    features: [
      "Kết nối API model riêng",
      "Tự chọn nhà cung cấp AI",
      "Không tính phí sử dụng model",
      "Hỗ trợ cấu hình và triển khai",
    ],
    cta: "Liên hệ triển khai",
  },
];

export function Pricing() {
  return (
    <section className="section pricing" id="pricing">
      <div className="container">
        <div className="section-heading">
          <h2>Bảng giá đơn giản, minh bạch</h2>
          <p>Linh hoạt mở rộng theo nhu cầu hỗ trợ của doanh nghiệp.</p>
        </div>
        <div className="pricing-grid">
          {plans.map((plan) => (
            <article className={`plan ${plan.popular ? "popular" : ""}`} key={plan.name}>
              {plan.popular && <span className="popular-label">Phổ biến nhất</span>}
              <h3>{plan.name}</h3>
              <div className="price">
                {plan.price} <small>{plan.suffix}</small>
              </div>
              <ul>
                {plan.features.map((feature) => (
                  <li key={feature}>
                    <Icon name="check" /> {feature}
                  </li>
                ))}
              </ul>
              <a className={plan.popular ? "button" : "plan-button"} href={plan.key === "custom" ? "/#contact" : `/checkout?plan=${plan.key}`}>
                {plan.cta}
              </a>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

import { Icon } from "@/components/ui/Icon";
import { ChatMockup } from "./ChatMockup";

export function Hero() {
  return (
    <section className="hero">
      <div className="container hero-grid">
        <div className="hero-copy">
          <div className="eyebrow">
            <Icon name="sparkles" />
            Dành cho đội ngũ hỗ trợ hiện đại
          </div>
          <h1>
            Biến website thành{" "}
            <span className="gradient-text">trợ lý AI chăm sóc khách hàng</span>
          </h1>
          <p>
            Auralis ứng dụng công nghệ RAG để trả lời khách hàng tức thì dựa trên
            chính website, tài liệu và kho tri thức của doanh nghiệp.
          </p>
          <div className="hero-actions">
            <a className="button" href="/login">
              Dùng thử miễn phí
            </a>
            <a className="button button-secondary" href="#demo">
              <Icon name="play" />
              Xem bản demo
            </a>
          </div>
        </div>
        <div className="hero-visual" id="demo">
          <div className="browser">
            <div className="browser-top">
              <i />
              <i />
              <i />
            </div>
            <div className="browser-content">
              <span className="skeleton title" />
              <span className="skeleton" />
              <span className="skeleton short" />
              <ChatMockup />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

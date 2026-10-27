import { BrandLogo } from "@/components/ui/BrandLogo";
import { PlatformFooter } from "@/components/ui/PlatformBranding";
import { Icon } from "@/components/ui/Icon";
import { LandingNavigation } from "./LandingNavigation";
import { Pricing } from "./Pricing";
import { ProductDemo } from "./ProductDemo";
import styles from "./landing.module.css";

const steps = [
  {
    number: "01",
    title: "Kết nối tri thức",
    text: "Thêm địa chỉ website, tài liệu hoặc những câu hỏi đội ngũ thường gặp. Auralis tập hợp dữ liệu thành một kho tri thức riêng.",
  },
  {
    number: "02",
    title: "Tạo trợ lý của bạn",
    text: "Điều chỉnh lời chào, màu sắc và cách trò chuyện. Kiểm tra câu trả lời trước khi đưa trợ lý đến với khách hàng.",
  },
  {
    number: "03",
    title: "Đưa lên website",
    text: "Sao chép đoạn mã nhúng, thêm vào website và bắt đầu hội thoại. Quản lý mọi hoạt động trong cùng một dashboard.",
  },
];

const questions = [
  {
    question: "Auralis lấy thông tin từ đâu để trả lời?",
    answer:
      "Từ website, tài liệu PDF/Word và các cặp hỏi đáp bạn cung cấp. Auralis tìm nội dung liên quan trong kho tri thức của từng website, rồi dùng nội dung đó để tạo câu trả lời có nguồn tham chiếu.",
  },
  {
    question: "Tôi có cần biết lập trình để sử dụng không?",
    answer:
      "Bạn quản lý nguồn dữ liệu và tùy chỉnh trợ lý ngay trong dashboard. Để hiển thị chatbot, chỉ cần thêm đoạn mã nhúng vào website; nếu website do đơn vị khác quản lý, bạn có thể gửi đoạn mã cho họ.",
  },
  {
    question: "Nhân viên có thể tiếp nhận cuộc trò chuyện không?",
    answer:
      "Có. Tính năng handoff cho phép nhân viên tiếp nhận và trả lời khách hàng cùng lịch sử trao đổi trước đó, để cuộc trò chuyện được tiếp tục trong cùng một cửa sổ.",
  },
  {
    question: "Có thể sử dụng API model riêng không?",
    answer:
      "Gói Tùy chỉnh hỗ trợ BYOK: kết nối API key và model của nhà cung cấp bạn lựa chọn. Bạn chủ động quản lý cấu hình và chi phí model theo chính sách của nhà cung cấp đó.",
  },
  {
    question: "Tôi có thể quản lý nhiều website không?",
    answer:
      "Có. Mỗi website có nguồn tri thức, cấu hình chatbot và hội thoại riêng. Bạn chuyển giữa các website trong dashboard; số website và hạn mức sử dụng phụ thuộc gói đã chọn.",
  },
];

export function LandingPage() {
  return (
    <div className={styles.page} id="top">
      <a className={styles.skipLink} href="#main-content">
        Đến nội dung chính
      </a>
      <div className={styles.navWrap}>
        <LandingNavigation />
      </div>
      <main id="main-content">
        <div className={styles.heroBackdrop}>
          <section className={styles.hero}>
            <div className={styles.heroTag}>
              <span>
                <Icon name="sparkles" />
              </span>
              Trợ lý AI từ chính tri thức của bạn
            </div>
            <h1>
              Hiểu doanh nghiệp bạn.
              <br />
              Hỗ trợ khách hàng tốt&nbsp;hơn.
            </h1>
            <p className={styles.heroDescription}>
              Từ website và tài liệu đến những câu trả lời hữu ích.
              <br className={styles.desktopBreak} /> Auralis đồng hành cùng đội
              ngũ của bạn trong từng cuộc hội thoại.
            </p>
            <div className={styles.heroActions}>
              <a className={styles.primaryButton} href="/register">
                Bắt đầu với Auralis <Icon name="arrow" />
              </a>
              <a className={styles.secondaryButton} href="#demo">
                <Icon name="play" />
                Khám phá cách hoạt động
              </a>
            </div>
            <div className={styles.heroBenefits}>
              <span>
                <Icon name="check" />
                Tri thức riêng của doanh nghiệp
              </span>
              <span>
                <Icon name="check" />
                AI và đội ngũ cùng hỗ trợ
              </span>
            </div>
          </section>
          <div className={styles.demoWrap}>
            <ProductDemo />
          </div>
          <div className={styles.compatibility}>
            <p>Linh hoạt với nhà cung cấp AI của bạn</p>
            <div>
              <span className={styles.providerOpenAi}>
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="m12 2 8.7 5v10L12 22l-8.7-5V7L12 2Zm0 5-4.3 2.5v5L12 17l4.3-2.5v-5L12 7Z" />
                </svg>
                OpenAI
              </span>
              <span className={styles.providerGroq}>groq</span>
              <span className={styles.providerOllama}>
                <Icon name="bot" />
                Ollama
              </span>
              <span className={styles.byokProvider}>
                API của bạn
                <Icon name="settings" />
              </span>
            </div>
          </div>
        </div>

        <section
          className={styles.features}
          id="features"
          aria-labelledby="features-heading"
        >
          <div className={styles.container}>
            <div className={styles.sectionHeading}>
              <span className={styles.sectionLabel}>
                <i />
                Được xây dựng cho cuộc hội thoại thực
              </span>
              <h2 id="features-heading">
                Không chỉ trả lời.
                <br />
                Thật sự hiểu khách hàng.
              </h2>
              <p>
                AI làm những việc lặp lại. Đội ngũ của bạn tập trung vào những
                cuộc trò chuyện cần sự quan tâm.
              </p>
            </div>
            <div className={styles.featureGrid}>
              <article className={styles.knowledgeFeature}>
                <div className={styles.featureCopy}>
                  <span className={styles.featureIcon}>
                    <Icon name="document" />
                  </span>
                  <h3>
                    Mọi tri thức.
                    <br />
                    Một trợ lý am hiểu.
                  </h3>
                  <p>
                    Website, tài liệu và kinh nghiệm của đội ngũ cùng trở thành
                    nền tảng cho mỗi câu trả lời.
                  </p>
                </div>
                <div className={styles.documentStack} aria-hidden="true">
                  <div className={styles.documentBack}>
                    <Icon name="globe" />
                    <span>website-cua-ban.vn</span>
                  </div>
                  <div className={styles.documentFront}>
                    <span className={styles.pdfBadge}>PDF</span>
                    <strong>Tri thức doanh nghiệp</strong>
                    <span className={styles.documentLine} />
                    <span className={styles.documentLine} />
                    <span className={styles.documentHighlight}>
                      Chính sách, sản phẩm & hướng dẫn
                    </span>
                    <span className={styles.documentLine} />
                    <small>
                      <i />
                      Sẵn sàng cho câu trả lời tiếp theo
                    </small>
                  </div>
                  <span className={styles.documentSpark}>
                    <Icon name="sparkles" />
                  </span>
                </div>
              </article>
              <article className={styles.citationFeature}>
                <span className={styles.featureIcon}>
                  <Icon name="globe" />
                </span>
                <h3>Câu trả lời có căn cứ.</h3>
                <p>
                  Hiển thị nguồn tham chiếu để khách hàng và đội ngũ dễ dàng
                  kiểm chứng.
                </p>
                <div className={styles.citationArt}>
                  <p>
                    Thông tin rõ ràng.
                    <br />
                    Nguồn gốc minh bạch.
                  </p>
                  <span>
                    <Icon name="document" />
                    Chính sách doanh nghiệp
                    <Icon name="check" />
                  </span>
                </div>
              </article>
              <article className={styles.handoffFeature}>
                <span className={styles.featureIcon}>
                  <Icon name="users" />
                </span>
                <h3>Có AI. Luôn có con người.</h3>
                <p>
                  Chuyển tiếp cùng đầy đủ ngữ cảnh khi khách hàng cần đội ngũ tư
                  vấn.
                </p>
                <div className={styles.handoffArt} aria-hidden="true">
                  <span className={styles.handoffAi}>
                    <Icon name="sparkles" />
                  </span>
                  <div className={styles.handoffLine}>
                    <i />
                    <i />
                    <i />
                    <Icon name="arrow" />
                  </div>
                  <span className={styles.handoffHuman}>NV</span>
                  <small>Tiếp nối cuộc trò chuyện</small>
                </div>
              </article>
              <article className={styles.controlFeature}>
                <div>
                  <span className={styles.featureIcon}>
                    <Icon name="settings" />
                  </span>
                  <h3>Trợ lý AI mang dấu ấn của bạn.</h3>
                  <p>
                    Tùy chỉnh giao diện, quản lý nhiều website và kiểm soát
                    domain được phép nhúng. Mọi thứ nằm trong cùng một không
                    gian làm việc.
                  </p>
                  <a href="/register" className={styles.textLink}>
                    Tạo trợ lý của bạn
                    <Icon name="arrow" />
                  </a>
                </div>
                <div className={styles.customizationArt} aria-hidden="true">
                  <div>
                    <span>Thương hiệu của bạn</span>
                    <Icon name="check" />
                  </div>
                  <div>
                    <span>Màu chủ đạo</span>
                    <span className={styles.swatches}>
                      <i />
                      <i />
                      <i />
                      <i />
                    </span>
                  </div>
                  <div>
                    <span>Nguồn tri thức</span>
                    <span className={styles.settingPill}>
                      Theo từng website
                    </span>
                  </div>
                </div>
              </article>
            </div>
          </div>
        </section>

        <section
          className={styles.process}
          id="how-it-works"
          aria-labelledby="process-heading"
        >
          <div className={styles.container}>
            <div className={styles.processHeading}>
              <div>
                <span className={styles.sectionLabel}>
                  <i />
                  Từ dữ liệu đến hội thoại
                </span>
                <h2 id="process-heading">
                  Một khởi đầu đơn giản.
                  <br />
                  Nhiều khả năng hơn.
                </h2>
              </div>
              <a href="#demo" className={styles.textLink}>
                Xem trải nghiệm mẫu
                <Icon name="play" />
              </a>
            </div>
            <div className={styles.steps}>
              {steps.map((step) => (
                <article key={step.number}>
                  <span className={styles.stepNumber}>{step.number}</span>
                  <h3>{step.title}</h3>
                  <p>{step.text}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <div className={styles.pricing}>
          <Pricing />
        </div>

        <section className={styles.faq} id="faq" aria-labelledby="faq-heading">
          <div className={`${styles.container} ${styles.faqGrid}`}>
            <div>
              <span className={styles.sectionLabel}>
                <i />
                Giải đáp trước khi bắt đầu
              </span>
              <h2 id="faq-heading">
                Bạn hỏi.
                <br />
                Chúng mình giải đáp.
              </h2>
              <p>
                Những điều cần biết để đưa Auralis vào quy trình hỗ trợ của bạn.
              </p>
              <a href="/api/docs" className={styles.textLink}>
                Khám phá tài liệu API
                <Icon name="arrow" />
              </a>
            </div>
            <div className={styles.faqItems}>
              {questions.map((item) => (
                <details key={item.question}>
                  <summary>
                    {item.question}
                    <span aria-hidden="true">+</span>
                  </summary>
                  <p>{item.answer}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        <section className={styles.contact} id="contact">
          <div className={styles.ctaOrb} aria-hidden="true">
            <Icon name="sparkles" />
          </div>
          <div className={styles.ctaCopy}>
            <span>Sẵn sàng cho cuộc hội thoại tiếp theo?</span>
            <h2>
              Để khách hàng được lắng nghe.
              <br />
              Để đội ngũ có thêm thời gian.
            </h2>
            <p>Bắt đầu xây dựng trợ lý AI hiểu doanh nghiệp của bạn.</p>
            <a className={styles.primaryButton} href="/register">
              Bắt đầu với Auralis
              <Icon name="arrow" />
            </a>
            <PlatformFooter />
          </div>
        </section>
      </main>

      <footer className={styles.footer}>
        <div className={`${styles.container} ${styles.footerTop}`}>
          <div>
            <a
              href="#top"
              className={styles.logo}
              aria-label="Auralis — về đầu trang"
            >
              <BrandLogo />
            </a>
            <p>
              Tri thức của bạn.
              <br />
              Trải nghiệm khách hàng tốt hơn.
            </p>
          </div>
          <div className={styles.footerLinks}>
            <div>
              <strong>Sản phẩm</strong>
              <a href="#features">Nền tảng Auralis</a>
              <a href="#demo">Trải nghiệm mẫu</a>
              <a href="#pricing">Bảng giá</a>
            </div>
            <div>
              <strong>Khám phá</strong>
              <a href="#how-it-works">Cách hoạt động</a>
              <a href="#faq">Câu hỏi thường gặp</a>
              <a href="/api/docs">Tài liệu API</a>
            </div>
            <div>
              <strong>Không gian của bạn</strong>
              <a href="/login">Đăng nhập</a>
              <a href="/register">Bắt đầu sử dụng</a>
            </div>
          </div>
        </div>
        <div className={`${styles.container} ${styles.footerBottom}`}>
          <span>
            © {new Date().getFullYear()} Auralis AI. Bảo lưu mọi quyền.
          </span>
          <span>
            Được xây dựng cho những cuộc trò chuyện tốt hơn.
            <span className={styles.footerDot} />
          </span>
        </div>
      </footer>
    </div>
  );
}

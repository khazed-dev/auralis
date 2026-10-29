import Link from "next/link";
import { LoginForm } from "@/components/auth/LoginForm";
import styles from "@/components/auth/auth.module.css";
import { BrandLogo } from "@/components/ui/BrandLogo";
import { Icon } from "@/components/ui/Icon";
import { LoginBrandCopy, PlatformFooter } from "@/components/ui/PlatformBranding";

export const metadata = {
  title: "Đăng nhập — Auralis AI",
  description: "Đăng nhập để quản lý các trợ lý AI của bạn.",
};

export default function LoginPage() {
  return (
    <main className={styles.page}>
      <section className={styles.shell}>
        <div className={styles.panel}>
          <Link className={styles.logo} href="/" aria-label="Về trang chủ">
            <BrandLogo priority />
          </Link>
          <div className={styles.intro}>
            <LoginBrandCopy />
          </div>
          <LoginForm />
          <p className={styles.register}>
            Chưa có tài khoản? <Link href="/register">Đăng ký</Link>
          </p>
          <PlatformFooter />
          <Link href="/" className={styles.back}>Về trang chủ</Link>
        </div>
        <aside className={styles.visual} aria-label="Từ tri thức doanh nghiệp đến hỗ trợ khách hàng">
          <div className={styles.visualHeading}>
            <span className={styles.status}><span /> Tri thức luôn kết nối</span>
            <h2>Mỗi câu trả lời<br />bắt đầu từ sự thấu hiểu.</h2>
            <p>Kết nối nội dung của bạn. Đưa thông tin đúng đến khách hàng, ngay trong cuộc trò chuyện.</p>
          </div>
          <div className={styles.workflow} aria-hidden="true">
            <div className={styles.sources}>
              <span><Icon name="globe" /> Website</span>
              <span><Icon name="document" /> Tài liệu</span>
              <span><Icon name="message" /> Hỏi & đáp</span>
            </div>
            <div className={styles.connection}><span /><Icon name="bot" /><span /></div>
            <div className={styles.answer}>
              <div className={styles.answerHeading}><span><Icon name="sparkles" /> Câu trả lời có nguồn</span><Icon name="check" /></div>
              <div className={styles.answerLine} /><div className={styles.answerLine} /><div className={styles.answerLine} />
              <span className={styles.citation}><Icon name="document" /> Dựa trên tri thức doanh nghiệp</span>
            </div>
          </div>
          <p className={styles.visualFooter}><Icon name="headset" /> AI hỗ trợ. Đội ngũ của bạn tiếp nối.</p>
        </aside>
      </section>
    </main>
  );
}

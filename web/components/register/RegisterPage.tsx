import Link from "next/link";

import { Pricing } from "@/components/landing/Pricing";
import { BrandLogo } from "@/components/ui/BrandLogo";
import { Icon } from "@/components/ui/Icon";
import styles from "./register.module.css";

export function RegisterPage() {
  return (
    <main className={`register-page ${styles.page}`}>
      <header className={`register-header ${styles.header}`}>
        <div className="container register-header-inner">
          <Link href="/" aria-label="Về trang chủ Auralis">
            <BrandLogo priority />
          </Link>
          <div>
            <span>Đã có tài khoản?</span>
            <Link href="/login">Đăng nhập</Link>
          </div>
        </div>
      </header>
      <section className={styles.intro}>
        <div>
          <span className={styles.marker}><span /> Bắt đầu cùng đội ngũ của bạn</span>
          <h1>Chọn không gian<br />cho trợ lý AI của bạn.</h1>
          <p>Từ website đầu tiên đến đội ngũ hỗ trợ lớn hơn. Chọn gói phù hợp và kết nối tri thức của doanh nghiệp.</p>
        </div>
        <div className={styles.journey} aria-label="Các bước bắt đầu">
          <span><Icon name="grid" /><strong>Chọn gói</strong><small>Phù hợp với nhu cầu</small></span>
          <span><Icon name="globe" /><strong>Kết nối website</strong><small>Đưa tri thức vào trợ lý</small></span>
          <span><Icon name="message" /><strong>Bắt đầu hỗ trợ</strong><small>Ngay trên website của bạn</small></span>
        </div>
      </section>
      <div className={styles.pricing}><Pricing /></div>
      <footer className={styles.footer}><Link href="/">Về trang chủ</Link><p>Đã có tài khoản? <Link href="/login">Đăng nhập để tiếp tục</Link></p></footer>
    </main>
  );
}

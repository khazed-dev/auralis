import Image from "next/image";
import Link from "next/link";
import { LoginForm } from "@/components/auth/LoginForm";
import { BrandLogo } from "@/components/ui/BrandLogo";
import { LoginBrandCopy, PlatformFooter } from "@/components/ui/PlatformBranding";

export const metadata = {
  title: "Đăng nhập — Auralis AI",
  description: "Đăng nhập để quản lý các trợ lý AI của bạn.",
};

export default function LoginPage() {
  return (
    <main className="login-page">
      <div className="login-glow login-glow-left" />
      <div className="login-glow login-glow-right" />

      <section className="login-shell">
        <div className="login-panel">
          <Link className="login-mobile-logo" href="/" aria-label="Về trang chủ Auralis">
            <BrandLogo priority />
          </Link>

          <LoginBrandCopy />

          <div className="login-divider">
            <span />
            <small>Đăng nhập</small>
            <span />
          </div>

          <LoginForm />

          <p className="login-register">
            Chưa có tài khoản? <Link href="/register">Đăng ký</Link>
          </p>
          <PlatformFooter />
        </div>

        <aside className="login-visual" aria-label="Giới thiệu Auralis">
          <Image
            className="login-visual-logo"
            src="/logo-auralis.png"
            alt="Auralis"
            width={1254}
            height={1254}
            priority
          />
          <Image
            className="login-visual-gradient"
            src="/login-visual.svg"
            alt=""
            fill
            sizes="(max-width: 900px) 0px, 50vw"
          />
          <blockquote>
            <strong>“Auralis đã thay đổi cách đội ngũ chúng tôi làm việc.”</strong>
            <p>
              Khai thác sức mạnh của AI thấu hiểu ngữ cảnh để tổng hợp dữ liệu và
              đẩy nhanh quá trình ra quyết định trong toàn doanh nghiệp.
            </p>
          </blockquote>
        </aside>
      </section>
    </main>
  );
}

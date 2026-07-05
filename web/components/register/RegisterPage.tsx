import Link from "next/link";

import { Pricing } from "@/components/landing/Pricing";
import { BrandLogo } from "@/components/ui/BrandLogo";

export function RegisterPage() {
  return (
    <main className="register-page">
      <header className="register-header">
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
      <Pricing />
    </main>
  );
}

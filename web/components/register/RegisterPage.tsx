import Image from "next/image";
import Link from "next/link";

import { Pricing } from "@/components/landing/Pricing";

export function RegisterPage() {
  return (
    <main className="register-page">
      <header className="register-header">
        <div className="container register-header-inner">
          <Link href="/" aria-label="Về trang chủ Auralis">
            <Image src="/logo-auralis.png" alt="Auralis" width={144} height={48} priority />
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

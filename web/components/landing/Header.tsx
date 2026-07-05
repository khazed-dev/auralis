import Image from "next/image";

const nav = [
  ["Nền tảng", "#features"],
  ["Giải pháp", "#solutions"],
  ["Tài nguyên", "#resources"],
  ["Bảng giá", "#pricing"],
];

export function Header() {
  return (
    <header className="site-header">
      <div className="container header-inner">
        <a className="brand" href="#" aria-label="Auralis home">
          <Image
            src="/logo-auralis.png"
            alt="Auralis"
            width={144}
            height={48}
            priority
          />
        </a>
        <nav className="desktop-nav" aria-label="Main navigation">
          {nav.map(([label, href]) => (
            <a href={href} key={label}>
              {label}
            </a>
          ))}
        </nav>
        <div className="header-actions">
          <a className="sign-in" href="/login">
            Đăng nhập
          </a>
          <a className="button button-pill button-small" href="/register">
            Bắt đầu ngay
          </a>
        </div>
      </div>
    </header>
  );
}

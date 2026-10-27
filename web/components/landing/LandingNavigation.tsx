"use client";

import { useRef, useState } from "react";
import { BrandLogo } from "@/components/ui/BrandLogo";
import { Icon } from "@/components/ui/Icon";
import styles from "./landing.module.css";

const links = [
  ["Nền tảng", "#features"],
  ["Cách hoạt động", "#how-it-works"],
  ["Bảng giá", "#pricing"],
  ["Câu hỏi thường gặp", "#faq"],
];

export function LandingNavigation() {
  const [open, setOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);

  return (
    <header
      className={styles.header}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          setOpen(false);
          menuButton.current?.focus();
        }
      }}
    >
      <a
        href="#top"
        className={styles.logo}
        aria-label="Auralis — về đầu trang"
        onClick={() => setOpen(false)}
      >
        <BrandLogo priority />
      </a>
      <nav className={styles.desktopNav} aria-label="Điều hướng chính">
        {links.map(([label, href]) => (
          <a key={href} href={href}>
            {label}
          </a>
        ))}
      </nav>
      <div className={styles.navActions}>
        <a className={styles.loginLink} href="/login">
          Đăng nhập
        </a>
        <a className={styles.navCta} href="/register">
          Bắt đầu ngay <Icon name="arrow" />
        </a>
        <button
          ref={menuButton}
          className={styles.menuButton}
          type="button"
          aria-expanded={open}
          aria-controls="landing-mobile-nav"
          aria-label={open ? "Đóng menu" : "Mở menu"}
          onClick={() => setOpen(!open)}
        >
          {open ? (
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="m6 6 12 12M6 18 18 6" />
            </svg>
          ) : (
            <Icon name="menu" />
          )}
        </button>
      </div>
      {open && (
        <nav
          id="landing-mobile-nav"
          className={styles.mobileNav}
          aria-label="Điều hướng di động"
        >
          {links.map(([label, href]) => (
            <a key={href} href={href} onClick={() => setOpen(false)}>
              {label}
              <Icon name="arrow" />
            </a>
          ))}
          <a href="/login">
            Đăng nhập
            <Icon name="arrow" />
          </a>
        </nav>
      )}
    </header>
  );
}

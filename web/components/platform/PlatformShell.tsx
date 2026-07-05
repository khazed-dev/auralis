"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";

import { BrandLogo } from "@/components/ui/BrandLogo";
import { Icon, type IconName } from "@/components/ui/Icon";
import { DashboardUser, getCurrentUser, logout } from "@/lib/auth";

const nav: Array<{ href: string; label: string; icon: IconName }> = [
  { href: "/platform", label: "Tổng quan", icon: "grid" },
  { href: "/platform/customers", label: "Khách hàng", icon: "users" },
  { href: "/platform/plans", label: "Cấu hình gói", icon: "settings" },
  { href: "/platform/requests", label: "Yêu cầu & ngoại lệ", icon: "message" },
  { href: "/platform/promos", label: "Mã giảm giá", icon: "bolt" },
  { href: "/platform/payments", label: "Thanh toán", icon: "document" },
  { href: "/platform/audit", label: "Nhật ký quản trị", icon: "clock" },
];

export function PlatformShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<DashboardUser | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    setCollapsed(localStorage.getItem("auralis-sidebar-collapsed") === "true");
    getCurrentUser()
      .then((current) => {
        if (!current) return router.replace("/login");
        if (current.role !== "platform_admin") return router.replace("/dashboard");
        setUser(current);
      })
      .catch(() => router.replace("/login"));
  }, [router]);

  function toggleCollapsed() {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem("auralis-sidebar-collapsed", String(next));
  }

  async function signOut() {
    await logout();
    router.replace("/login");
  }

  if (!user) {
    return <div className="platform-loading"><span className="dashboard-spinner" /><p>Đang tải khu vực quản trị...</p></div>;
  }

  const initial = (user.name || user.email).charAt(0).toUpperCase();

  return <div className={`dashboard-shell platform-shell ${collapsed ? "is-collapsed" : ""}`}>
    <button
      className={`dashboard-overlay ${mobileOpen ? "is-visible" : ""}`}
      onClick={() => setMobileOpen(false)}
      aria-label="Đóng menu"
    />
    <aside className={`dashboard-sidebar platform-sidebar ${mobileOpen ? "is-open" : ""}`}>
      <div className="dashboard-brand">
        <Link href="/platform" aria-label="Auralis Platform Admin">
          <Image src="/logo-auralis.png" alt="Auralis" width={140} height={48} priority />
        </Link>
        <button
          className="sidebar-collapse"
          type="button"
          onClick={toggleCollapsed}
          aria-label={collapsed ? "Mở rộng menu" : "Thu gọn menu"}
        >
          ‹
        </button>
      </div>

      <nav className="dashboard-nav" aria-label="Điều hướng quản trị nền tảng">
        {nav.map((item) => {
          const active = item.href === "/platform"
            ? pathname === item.href
            : pathname.startsWith(item.href);
          return <Link
            href={item.href}
            className={active ? "active" : ""}
            key={item.href}
            title={collapsed ? item.label : undefined}
            onClick={() => setMobileOpen(false)}
          >
            <Icon name={item.icon} /><span>{item.label}</span>
          </Link>;
        })}
      </nav>

      <div className="dashboard-sidebar-footer">
        <div className="dashboard-user">
          <span className="dashboard-avatar">{initial}</span>
          <span className="dashboard-user-copy">
            <strong>{user.name || "Auralis Platform Admin"}</strong>
            <small>Quản trị nền tảng</small>
          </span>
          <button type="button" onClick={signOut} aria-label="Đăng xuất" title="Đăng xuất">
            <Icon name="logout" />
          </button>
        </div>
      </div>
    </aside>

    <section className="dashboard-main platform-main">
      <header className="dashboard-mobile-header">
        <button type="button" onClick={() => setMobileOpen(true)} aria-label="Mở menu">
          <Icon name="menu" />
        </button>
        <BrandLogo />
        <span className="dashboard-avatar">{initial}</span>
      </header>
      {children}
    </section>
  </div>;
}

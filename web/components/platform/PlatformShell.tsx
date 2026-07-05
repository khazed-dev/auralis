"use client";

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
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    getCurrentUser().then((current) => {
      if (!current) return router.replace("/login");
      if (current.role !== "platform_admin") return router.replace("/dashboard");
      setUser(current);
    }).catch(() => router.replace("/login"));
  }, [router]);

  async function signOut() {
    await logout();
    router.replace("/login");
  }

  if (!user) return <div className="platform-loading"><span className="dashboard-spinner" /><p>Đang tải khu vực quản trị...</p></div>;

  return <div className="platform-shell">
    <button className={`platform-overlay ${mobileOpen ? "visible" : ""}`} onClick={() => setMobileOpen(false)} aria-label="Đóng menu" />
    <aside className={`platform-sidebar ${mobileOpen ? "open" : ""}`}>
      <div className="platform-brand"><Link href="/platform"><BrandLogo priority /></Link><small>PLATFORM ADMIN</small></div>
      <nav>{nav.map(item => {
        const active = item.href === "/platform" ? pathname === item.href : pathname.startsWith(item.href);
        return <Link href={item.href} className={active ? "active" : ""} key={item.href} onClick={() => setMobileOpen(false)}>
          <Icon name={item.icon} /><span>{item.label}</span>
        </Link>;
      })}</nav>
      <div className="platform-user">
        <span className="dashboard-avatar">{(user.name || user.email).charAt(0).toUpperCase()}</span>
        <div><strong>{user.name || "Platform Admin"}</strong><small>{user.email}</small></div>
        <button type="button" onClick={signOut} title="Đăng xuất"><Icon name="logout" /></button>
      </div>
    </aside>
    <section className="platform-main">
      <header className="platform-mobile-header"><button onClick={() => setMobileOpen(true)}><Icon name="menu" /></button><BrandLogo /></header>
      {children}
    </section>
  </div>;
}

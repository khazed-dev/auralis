"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { Icon, type IconName } from "@/components/ui/Icon";
import { DashboardUser, getCurrentUser, logout } from "@/lib/auth";

const primaryNav: Array<{
  label: string;
  href: string;
  icon: IconName;
  hideForAgent?: boolean;
}> = [
  { label: "Website", href: "/dashboard/sites", icon: "grid" },
  { label: "Hội thoại", href: "/dashboard/conversations", icon: "message" },
  { label: "Handoff", href: "/dashboard/handoffs", icon: "headset" },
  { label: "Phân tích", href: "/dashboard/analytics", icon: "chart" },
  { label: "Đội ngũ", href: "/dashboard/team", icon: "users", hideForAgent: true },
];

const utilityNav = [
  { label: "Cài đặt", href: "/dashboard/settings", icon: "settings" as IconName },
  { label: "Trợ giúp", href: "/dashboard/help", icon: "help" as IconName },
];

const roleLabels = {
  admin: "Quản trị viên",
  user: "Chủ website",
  agent: "Nhân viên hỗ trợ",
};

export function DashboardShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<DashboardUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      setCollapsed(
        localStorage.getItem("auralis-sidebar-collapsed") === "true",
      );
    });

    getCurrentUser()
      .then((currentUser) => {
        if (!currentUser) {
          router.replace("/login");
          return;
        }
        setUser(currentUser);
        if (currentUser.role === "agent" && pathname === "/dashboard/sites") {
          router.replace("/dashboard/handoffs");
        }
      })
      .catch(() => router.replace("/login"))
      .finally(() => setLoading(false));

    return () => cancelAnimationFrame(frame);
  }, [pathname, router]);

  function toggleCollapsed() {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem("auralis-sidebar-collapsed", String(next));
  }

  async function handleLogout() {
    await logout();
    router.replace("/login");
  }

  if (loading && !user) {
    return (
      <div className="dashboard-loading">
        <span className="dashboard-spinner" />
        <p>Đang tải không gian làm việc...</p>
      </div>
    );
  }

  const navItems = primaryNav.filter(
    (item) => !(item.hideForAgent && user?.role === "agent"),
  );
  const initial = (user?.name || user?.email || "A").charAt(0).toUpperCase();

  return (
    <div className={`dashboard-shell ${collapsed ? "is-collapsed" : ""}`}>
      <button
        className={`dashboard-overlay ${mobileOpen ? "is-visible" : ""}`}
        aria-label="Đóng menu"
        onClick={() => setMobileOpen(false)}
      />
      <aside className={`dashboard-sidebar ${mobileOpen ? "is-open" : ""}`}>
        <div className="dashboard-brand">
          <Link href="/dashboard/sites" aria-label="Auralis">
            <Image src="/logo-auralis.png" alt="Auralis" width={140} height={48} priority />
          </Link>
          <button
            className="sidebar-collapse"
            type="button"
            onClick={toggleCollapsed}
            aria-label={collapsed ? "Mở rộng thanh điều hướng" : "Thu gọn thanh điều hướng"}
          >
            ‹
          </button>
        </div>

        <nav className="dashboard-nav" aria-label="Điều hướng chính">
          {navItems.map((item) => (
            <Link
              className={pathname === item.href ? "active" : ""}
              href={item.href}
              key={item.href}
              title={collapsed ? item.label : undefined}
              onClick={() => setMobileOpen(false)}
            >
              <Icon name={item.icon} />
              <span>{item.label}</span>
            </Link>
          ))}
        </nav>

        <div className="dashboard-sidebar-footer">
          <nav className="dashboard-nav dashboard-utility-nav">
            {utilityNav.map((item) => (
              <Link
                className={pathname === item.href ? "active" : ""}
                href={item.href}
                key={item.href}
                title={collapsed ? item.label : undefined}
              >
                <Icon name={item.icon} />
                <span>{item.label}</span>
              </Link>
            ))}
          </nav>

          <div className="dashboard-user">
            <span className="dashboard-avatar">{initial}</span>
            <span className="dashboard-user-copy">
              <strong>{user?.name || user?.email || "Auralis"}</strong>
              <small>{user ? roleLabels[user.role] : ""}</small>
            </span>
            <button type="button" onClick={handleLogout} aria-label="Đăng xuất" title="Đăng xuất">
              <Icon name="logout" />
            </button>
          </div>
        </div>
      </aside>

      <div className="dashboard-main">
        <header className="dashboard-mobile-header">
          <button type="button" onClick={() => setMobileOpen(true)} aria-label="Mở menu">
            <Icon name="menu" />
          </button>
          <Image src="/logo-auralis.png" alt="Auralis" width={112} height={38} />
          <span className="dashboard-avatar">{initial}</span>
        </header>
        {children}
      </div>
    </div>
  );
}

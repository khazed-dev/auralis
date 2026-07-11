"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { FormEvent, ReactNode, useEffect, useState } from "react";
import { Icon, type IconName } from "@/components/ui/Icon";
import { BrandLogo } from "@/components/ui/BrandLogo";
import { API_BASE, authFetch, DashboardUser, getCurrentUser, logout } from "@/lib/auth";

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
  { label: "Gói dịch vụ", href: "/dashboard/subscription", icon: "bolt" as IconName },
  { label: "Cài đặt", href: "/dashboard/settings", icon: "settings" as IconName },
  { label: "Trợ giúp", href: "/dashboard/help", icon: "help" as IconName },
];

const roleLabels = {
  platform_admin: "Quản trị nền tảng",
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
        if (
          currentUser.role === "platform_admin" &&
          pathname.startsWith("/dashboard")
        ) {
          router.replace("/platform");
        }
        if (currentUser.role === "agent" && pathname === "/dashboard/sites") {
          router.replace("/dashboard/handoffs");
        }
      })
      .catch(() => router.replace("/login"))
      .finally(() => setLoading(false));

    return () => cancelAnimationFrame(frame);
  }, [pathname, router]);

  useEffect(() => {
    let prefix = "";
    let prefixTimer: ReturnType<typeof setTimeout> | null = null;
    function handleShortcut(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (
        target?.matches("input, textarea, select") ||
        target?.isContentEditable ||
        event.ctrlKey ||
        event.metaKey ||
        event.altKey
      ) {
        return;
      }
      const key = event.key.toLowerCase();
      if (key === ",") {
        event.preventDefault();
        router.push("/dashboard/settings");
        return;
      }
      if (key === "g") {
        prefix = "g";
        if (prefixTimer) clearTimeout(prefixTimer);
        prefixTimer = setTimeout(() => {
          prefix = "";
        }, 1200);
        return;
      }
      if (prefix === "g") {
        const destinations: Record<string, string> = {
          s: "/dashboard/sites",
          c: "/dashboard/conversations",
          h: "/dashboard/handoffs",
        };
        if (destinations[key]) {
          event.preventDefault();
          router.push(destinations[key]);
        }
        prefix = "";
      }
    }
    window.addEventListener("keydown", handleShortcut);
    return () => {
      window.removeEventListener("keydown", handleShortcut);
      if (prefixTimer) clearTimeout(prefixTimer);
    };
  }, [router]);

  function toggleCollapsed() {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem("auralis-sidebar-collapsed", String(next));
  }

  async function handleLogout() {
    await logout();
    router.replace("/login");
  }

  async function changeRequiredPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const password = String(data.get("new_password") ?? "");
    const confirmation = String(data.get("confirm_password") ?? "");
    const error = form.querySelector<HTMLElement>("[data-password-error]");
    if (password !== confirmation) {
      if (error) error.textContent = "Mật khẩu xác nhận không khớp.";
      return;
    }
    const button = form.querySelector<HTMLButtonElement>("button[type=submit]");
    if (button) button.disabled = true;
    if (error) error.textContent = "";
    const response = await authFetch(`${API_BASE}/auth/me`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_password: password }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (error) error.textContent = typeof body.detail === "string" ? body.detail : "Không thể đổi mật khẩu.";
      if (button) button.disabled = false;
      return;
    }
    const updated = body as DashboardUser;
    localStorage.setItem("user", JSON.stringify(updated));
    setUser(updated);
  }

  if (loading && !user) {
    return (
      <div className="dashboard-loading">
        <span className="dashboard-spinner" />
        <p>Đang tải không gian làm việc...</p>
      </div>
    );
  }

  const navItems = user?.role === "platform_admin"
    ? [{ label: "Khách hàng", href: "/dashboard/team", icon: "users" as IconName }]
    : primaryNav.filter((item) => !(item.hideForAgent && user?.role === "agent"));
  const visibleUtilityNav = user?.role === "platform_admin" ? [] : utilityNav;
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
          <Link href={user?.role === "platform_admin" ? "/dashboard/admin/subscriptions" : "/dashboard/sites"} aria-label="Auralis">
            <BrandLogo priority />
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
            {(user?.role === "platform_admin" || user?.role === "admin") && (
              <Link
                className={pathname === "/dashboard/admin/subscriptions" ? "active" : ""}
                href="/dashboard/admin/subscriptions"
                title={collapsed ? "Quản lý gói" : undefined}
              >
                <Icon name="users" />
                <span>Quản lý gói</span>
              </Link>
            )}
            {visibleUtilityNav.map((item) => (
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
          <BrandLogo />
          <span className="dashboard-avatar">{initial}</span>
        </header>
        {children}
      </div>
      {user?.must_change_password && (
        <div className="required-password-layer" role="dialog" aria-modal="true" aria-labelledby="required-password-title">
          <div className="required-password-backdrop" />
          <form className="required-password-modal" onSubmit={changeRequiredPassword}>
            <h2 id="required-password-title">Đổi mật khẩu lần đầu</h2>
            <p>Để bảo vệ tài khoản, bạn cần đặt mật khẩu mới trước khi sử dụng Dashboard.</p>
            <label>Mật khẩu mới<input name="new_password" type="password" minLength={8} autoComplete="new-password" required autoFocus /></label>
            <label>Xác nhận mật khẩu<input name="confirm_password" type="password" minLength={8} autoComplete="new-password" required /></label>
            <p className="required-password-error" data-password-error role="alert" />
            <button type="submit">Đổi mật khẩu và tiếp tục</button>
          </form>
        </div>
      )}
    </div>
  );
}

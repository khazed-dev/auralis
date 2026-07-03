"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import {
  API_BASE,
  authFetch,
  DashboardUser,
  DEV_AUTH_ENABLED,
  getStoredUser,
} from "@/lib/auth";

type Panel = "profile" | "branding" | "system" | "subscription";

type Branding = {
  app_name: string;
  logo_url?: string | null;
  favicon_url?: string | null;
  primary_color: string;
  secondary_color: string;
  login_title: string;
  login_subtitle: string;
  footer_text?: string | null;
  support_email?: string | null;
  hide_sitechat_branding: boolean;
};

type Health = {
  status: string;
  mongodb: string;
  vector_store: string;
  ollama: string;
};

const defaultBranding: Branding = {
  app_name: "Auralis AI",
  logo_url: "",
  favicon_url: "",
  primary_color: "#091C66",
  secondary_color: "#12D6C7",
  login_title: "Chào mừng bạn trở lại",
  login_subtitle: "Đăng nhập để quản lý các trợ lý AI của bạn",
  footer_text: "",
  support_email: "",
  hide_sitechat_branding: false,
};

async function apiError(response: Response, fallback: string) {
  const data = (await response.json().catch(() => ({}))) as {
    detail?: string | Array<{ msg?: string }>;
  };
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail.map((item) => item.msg).filter(Boolean).join(", ");
  }
  return fallback;
}

export function SettingsModule() {
  const initialUser = useMemo(() => getStoredUser(), []);
  const isAdmin = initialUser?.role === "admin";
  const [panel, setPanel] = useState<Panel>("profile");
  const [user, setUser] = useState<DashboardUser | null>(initialUser);
  const [branding, setBranding] = useState<Branding>(defaultBranding);
  const [health, setHealth] = useState<Health | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const loadBranding = useCallback(async () => {
    if (!isAdmin || DEV_AUTH_ENABLED) return;
    const response = await authFetch(`${API_BASE}/platform/whitelabel`);
    if (response.ok) setBranding((await response.json()) as Branding);
  }, [isAdmin]);

  const loadHealth = useCallback(async () => {
    if (!isAdmin) return;
    setHealthLoading(true);
    try {
      if (DEV_AUTH_ENABLED) {
        setHealth({
          status: "healthy",
          mongodb: "healthy",
          vector_store: "healthy (480 documents)",
          ollama: "healthy (API provider)",
        });
        return;
      }
      const response = await authFetch(`${API_BASE}/admin/health`);
      if (!response.ok) throw new Error(await apiError(response, "Không thể kiểm tra hệ thống."));
      setHealth((await response.json()) as Health);
    } catch (healthError) {
      setMessage({
        type: "error",
        text: healthError instanceof Error ? healthError.message : "Không thể kiểm tra hệ thống.",
      });
    } finally {
      setHealthLoading(false);
    }
  }, [isAdmin]);

  useEffect(() => {
    const frame = requestAnimationFrame(() => void loadBranding());
    return () => cancelAnimationFrame(frame);
  }, [loadBranding]);

  useEffect(() => {
    if (panel !== "system") return;
    const frame = requestAnimationFrame(() => void loadHealth());
    return () => cancelAnimationFrame(frame);
  }, [loadHealth, panel]);

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setSaving(true);
    setMessage(null);
    const form = new FormData(formElement);
    const name = String(form.get("name") ?? "").trim();
    const currentPassword = String(form.get("current_password") ?? "");
    const newPassword = String(form.get("new_password") ?? "");

    try {
      if (newPassword && !currentPassword && !DEV_AUTH_ENABLED) {
        throw new Error("Vui lòng nhập mật khẩu hiện tại để đổi mật khẩu.");
      }
      let updated: DashboardUser;
      if (DEV_AUTH_ENABLED) {
        updated = { ...(user as DashboardUser), name };
      } else {
        const body: Record<string, string> = { name };
        if (newPassword) {
          body.current_password = currentPassword;
          body.new_password = newPassword;
        }
        const response = await authFetch(`${API_BASE}/auth/me`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        if (!response.ok) throw new Error(await apiError(response, "Không thể lưu hồ sơ."));
        updated = (await response.json()) as DashboardUser;
      }
      setUser(updated);
      localStorage.setItem("user", JSON.stringify(updated));
      (formElement.elements.namedItem("current_password") as HTMLInputElement).value = "";
      (formElement.elements.namedItem("new_password") as HTMLInputElement).value = "";
      setMessage({ type: "success", text: "Đã lưu thay đổi hồ sơ." });
    } catch (saveError) {
      setMessage({
        type: "error",
        text: saveError instanceof Error ? saveError.message : "Không thể lưu hồ sơ.",
      });
    } finally {
      setSaving(false);
    }
  }

  async function saveBranding(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMessage(null);
    const form = new FormData(event.currentTarget);
    const next: Branding = {
      app_name: String(form.get("app_name") ?? ""),
      logo_url: String(form.get("logo_url") ?? "") || null,
      favicon_url: String(form.get("favicon_url") ?? "") || null,
      primary_color: String(form.get("primary_color") ?? "#091C66"),
      secondary_color: String(form.get("secondary_color") ?? "#12D6C7"),
      login_title: String(form.get("login_title") ?? ""),
      login_subtitle: String(form.get("login_subtitle") ?? ""),
      footer_text: String(form.get("footer_text") ?? "") || null,
      support_email: String(form.get("support_email") ?? "") || null,
      hide_sitechat_branding: form.get("hide_sitechat_branding") === "on",
    };
    try {
      if (!DEV_AUTH_ENABLED) {
        const response = await authFetch(`${API_BASE}/platform/whitelabel`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(next),
        });
        if (!response.ok) throw new Error(await apiError(response, "Không thể lưu thương hiệu."));
        setBranding((await response.json()) as Branding);
      } else {
        setBranding(next);
      }
      setMessage({ type: "success", text: "Đã cập nhật nhận diện thương hiệu." });
    } catch (saveError) {
      setMessage({
        type: "error",
        text: saveError instanceof Error ? saveError.message : "Không thể lưu thương hiệu.",
      });
    } finally {
      setSaving(false);
    }
  }

  async function resetBranding() {
    if (!window.confirm("Khôi phục toàn bộ cấu hình thương hiệu mặc định?")) return;
    if (!DEV_AUTH_ENABLED) {
      const response = await authFetch(`${API_BASE}/platform/whitelabel/reset`, {
        method: "POST",
      });
      if (!response.ok) {
        setMessage({ type: "error", text: await apiError(response, "Không thể khôi phục.") });
        return;
      }
      setBranding((await response.json()) as Branding);
    } else {
      setBranding(defaultBranding);
    }
    setMessage({ type: "success", text: "Đã khôi phục cấu hình mặc định." });
  }

  const nav: Array<{ id: Panel; label: string; description: string; admin?: boolean }> = [
    { id: "profile", label: "Hồ sơ cá nhân", description: "Thông tin và mật khẩu" },
    { id: "branding", label: "Thương hiệu", description: "Tên, logo và màu sắc", admin: true },
    { id: "system", label: "Hệ thống", description: "Trạng thái dịch vụ", admin: true },
    { id: "subscription", label: "Gói dịch vụ & API", description: "Thanh toán và model AI" },
  ];

  return (
    <main className="dashboard-content settings-module">
      <div className="dashboard-page-heading">
        <span><Icon name="settings" /></span>
        <div><h1>Cài đặt</h1><p>Quản lý tài khoản và không gian làm việc Auralis.</p></div>
      </div>

      <div className="settings-workspace">
        <aside className="settings-nav">
          {nav.filter((item) => !item.admin || isAdmin).map((item) => (
            <button key={item.id} className={panel === item.id ? "active" : ""} onClick={() => { setPanel(item.id); setMessage(null); }}>
              <strong>{item.label}</strong><small>{item.description}</small>
            </button>
          ))}
        </aside>

        <section className="settings-panel">
          {message && <div className={`settings-message ${message.type}`} role="alert">{message.text}</div>}

          {panel === "profile" && (
            <>
              <header><h2>Hồ sơ cá nhân</h2><p>Cập nhật tên hiển thị và mật khẩu đăng nhập.</p></header>
              <form className="settings-form-new" onSubmit={saveProfile}>
                <div className="settings-section">
                  <h3>Thông tin tài khoản</h3>
                  <div className="settings-form-grid">
                    <label>Họ và tên<input name="name" defaultValue={user?.name || ""} minLength={2} required /></label>
                    <label>Email<input type="email" value={user?.email || ""} disabled /></label>
                  </div>
                </div>
                <div className="settings-section">
                  <h3>Đổi mật khẩu</h3><p>Để trống nếu bạn không muốn thay đổi mật khẩu.</p>
                  <div className="settings-form-grid">
                    <label>Mật khẩu hiện tại<input name="current_password" type="password" autoComplete="current-password" /></label>
                    <label>Mật khẩu mới<input name="new_password" type="password" minLength={8} autoComplete="new-password" /></label>
                  </div>
                </div>
                <footer><button className="sites-primary-button" disabled={saving}>{saving ? "Đang lưu..." : "Lưu thay đổi"}</button></footer>
              </form>
            </>
          )}

          {panel === "branding" && isAdmin && (
            <>
              <header><h2>Nhận diện thương hiệu</h2><p>Tùy chỉnh tên, logo và màu sắc của nền tảng.</p></header>
              <form
                className="settings-form-new"
                key={JSON.stringify(branding)}
                onSubmit={saveBranding}
              >
                <div className="settings-section">
                  <h3>Nhận diện chính</h3>
                  <div className="settings-form-grid">
                    <label>Tên ứng dụng<input name="app_name" defaultValue={branding.app_name} required /></label>
                    <label>Email hỗ trợ<input name="support_email" type="email" defaultValue={branding.support_email || ""} /></label>
                    <label className="wide">URL logo<input name="logo_url" type="url" defaultValue={branding.logo_url || ""} placeholder="https://example.com/logo.png" /></label>
                    <label className="wide">URL favicon<input name="favicon_url" type="url" defaultValue={branding.favicon_url || ""} placeholder="https://example.com/favicon.png" /></label>
                    <label>Màu chính<span className="settings-color"><input name="primary_color" type="color" defaultValue={branding.primary_color} /><code>{branding.primary_color}</code></span></label>
                    <label>Màu phụ<span className="settings-color"><input name="secondary_color" type="color" defaultValue={branding.secondary_color} /><code>{branding.secondary_color}</code></span></label>
                  </div>
                </div>
                <div className="settings-section">
                  <h3>Trang đăng nhập</h3>
                  <div className="settings-form-grid">
                    <label>Tiêu đề<input name="login_title" defaultValue={branding.login_title} /></label>
                    <label>Phụ đề<input name="login_subtitle" defaultValue={branding.login_subtitle} /></label>
                    <label className="wide">Nội dung chân trang<input name="footer_text" defaultValue={branding.footer_text || ""} /></label>
                  </div>
                  <label className="settings-checkbox"><input name="hide_sitechat_branding" type="checkbox" defaultChecked={branding.hide_sitechat_branding} /><span>Ẩn toàn bộ nhận diện mặc định của Auralis AI</span></label>
                </div>
                <footer><button type="button" onClick={() => void resetBranding()}>Khôi phục mặc định</button><button className="sites-primary-button" disabled={saving}>{saving ? "Đang lưu..." : "Lưu thương hiệu"}</button></footer>
              </form>
            </>
          )}

          {panel === "system" && isAdmin && (
            <>
              <header className="settings-system-header"><div><h2>Trạng thái hệ thống</h2><p>Các dịch vụ đang vận hành chatbot của bạn.</p></div><button onClick={() => void loadHealth()} disabled={healthLoading}>↻ Kiểm tra lại</button></header>
              <div className="settings-section health-services">
                {[
                  ["MongoDB", "Kho dữ liệu chính", health?.mongodb],
                  ["Vector Store", "Chỉ mục tìm kiếm ngữ nghĩa", health?.vector_store],
                  ["Mô hình AI", "Dịch vụ sinh câu trả lời", health?.ollama],
                ].map(([name, description, value]) => (
                  <div className="health-service" key={name}>
                    <span><strong>{name}</strong><small>{description}</small></span>
                    <em className={value?.startsWith("healthy") ? "healthy" : value ? "unhealthy" : "loading"}>
                      {healthLoading ? "Đang kiểm tra" : value || "Chưa kiểm tra"}
                    </em>
                  </div>
                ))}
              </div>
            </>
          )}

          {panel === "subscription" && (
            <>
              <header><h2>Gói dịch vụ & API model</h2><p>Quản lý hạn mức, thanh toán và nhà cung cấp AI.</p></header>
              <div className="settings-section subscription-current">
                <span><Icon name="sparkles" /></span>
                <div><small>Gói hiện tại</small><h3>Chưa kết nối hệ thống subscription</h3><p>Phần này sẽ hiển thị gói đang dùng, quota hội thoại và kỳ thanh toán.</p></div>
                <em>Sắp triển khai</em>
              </div>
              <div className="settings-section custom-api-preview">
                <div><h3>API model riêng</h3><p>Khách hàng gói Tùy chỉnh có thể kết nối OpenAI-compatible API, chọn model và tự thanh toán chi phí cho nhà cung cấp.</p></div>
                <button disabled>Thêm nhà cung cấp AI</button>
              </div>
            </>
          )}
        </section>
      </div>
    </main>
  );
}

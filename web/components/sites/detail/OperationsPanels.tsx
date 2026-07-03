"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { API_BASE, authFetch, DEV_AUTH_ENABLED, getStoredUser } from "@/lib/auth";
import { SiteConfig } from "./types";

async function apiError(response: Response, fallback: string) {
  const data = (await response.json().catch(() => ({}))) as { detail?: string };
  return data.detail || fallback;
}

type SaveConfig = (
  section: "security" | "lead_capture",
  value: SiteConfig["security"] | SiteConfig["lead_capture"],
) => Promise<{ ok: boolean; message: string }>;

export function SecurityPanel({
  config,
  onSave,
}: {
  config: SiteConfig["security"];
  onSave: SaveConfig;
}) {
  const [message, setMessage] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const result = await onSave("security", {
      allowed_domains: String(data.get("allowed_domains") || "")
        .split(/\r?\n|,/)
        .map((item) => item.trim())
        .filter(Boolean),
      enforce_domain_validation: data.get("enforce_domain_validation") === "on",
      require_referrer: data.get("require_referrer") === "on",
      rate_limit_per_session: Number(data.get("rate_limit_per_session")),
    });
    setMessage(result.message);
  }
  return (
    <form className="site-config-form" onSubmit={submit}>
      <header><h2>Bảo mật widget</h2><p>Kiểm soát website được phép sử dụng chatbot và giới hạn yêu cầu.</p></header>
      <section>
        <label>Domain được phép<small>Mỗi dòng một domain. Có thể dùng wildcard như *.example.com.</small><textarea name="allowed_domains" rows={6} defaultValue={config.allowed_domains.join("\n")} placeholder="example.com&#10;*.example.com" /></label>
        <label className="site-config-checkbox"><input name="enforce_domain_validation" type="checkbox" defaultChecked={config.enforce_domain_validation} /><span>Chặn yêu cầu từ domain không nằm trong danh sách</span></label>
        <label className="site-config-checkbox"><input name="require_referrer" type="checkbox" defaultChecked={config.require_referrer} /><span>Yêu cầu trình duyệt gửi Referer hợp lệ</span></label>
        <label>Giới hạn yêu cầu mỗi phiên/phút<input name="rate_limit_per_session" type="number" min={1} max={1000} defaultValue={config.rate_limit_per_session} /></label>
      </section>
      <footer>{message && <span>{message}</span>}<button className="sites-primary-button">Lưu bảo mật</button></footer>
    </form>
  );
}

type HandoffConfig = {
  enabled: boolean;
  confidence_threshold: number;
  auto_suggest_phrases: string[];
  business_hours: {
    enabled: boolean;
    timezone: string;
    offline_message: string;
    schedule: Record<string, { enabled: boolean; start: string; end: string }>;
  };
};

const defaultSchedule = Object.fromEntries(
  ["mon", "tue", "wed", "thu", "fri", "sat", "sun"].map((day, index) => [
    day,
    { enabled: index < 5, start: "09:00", end: "17:00" },
  ]),
);

export function HandoffConfigPanel({ siteId }: { siteId: string }) {
  const [config, setConfig] = useState<HandoffConfig>({
    enabled: true,
    confidence_threshold: 0.3,
    auto_suggest_phrases: ["Tôi không chắc", "Vui lòng liên hệ hỗ trợ"],
    business_hours: { enabled: false, timezone: "Asia/Ho_Chi_Minh", offline_message: "Hiện tại chúng tôi đang ngoại tuyến. Vui lòng để lại email.", schedule: defaultSchedule },
  });
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    if (DEV_AUTH_ENABLED) return;
    const response = await authFetch(`${API_BASE}/sites/${siteId}/handoff/config`);
    if (response.ok) {
      const data = (await response.json()) as Partial<HandoffConfig>;
      setConfig((current) => ({ ...current, ...data, business_hours: { ...current.business_hours, ...(data.business_hours || {}) } }));
    }
  }, [siteId]);
  useEffect(() => { const frame = requestAnimationFrame(() => void load()); return () => cancelAnimationFrame(frame); }, [load]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const next: HandoffConfig = {
      ...config,
      enabled: data.get("enabled") === "on",
      confidence_threshold: Number(data.get("confidence_threshold")),
      auto_suggest_phrases: String(data.get("auto_suggest_phrases") || "").split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
      business_hours: {
        ...config.business_hours,
        enabled: data.get("business_hours_enabled") === "on",
        timezone: String(data.get("timezone")),
        offline_message: String(data.get("offline_message")),
      },
    };
    if (!DEV_AUTH_ENABLED) {
      const response = await authFetch(`${API_BASE}/sites/${siteId}/handoff/config`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(next) });
      if (!response.ok) { setMessage(await apiError(response, "Không thể lưu handoff.")); return; }
    }
    setConfig(next);
    setMessage("Đã lưu cấu hình handoff.");
  }

  return (
    <form className="site-config-form" onSubmit={submit}>
      <header><h2>Human Handoff</h2><p>Cấu hình khi nào và bằng cách nào khách được kết nối với nhân viên.</p></header>
      <section>
        <label className="site-config-checkbox"><input name="enabled" type="checkbox" defaultChecked={config.enabled} /><span>Cho phép khách yêu cầu nhân viên hỗ trợ</span></label>
        <div className="site-config-grid">
          <label>Ngưỡng độ tin cậy<small>Đề xuất handoff khi độ tin cậy thấp hơn mức này.</small><input name="confidence_threshold" type="number" min={0} max={1} step={0.05} defaultValue={config.confidence_threshold} /></label>
          <label>Múi giờ<select name="timezone" defaultValue={config.business_hours.timezone}><option value="Asia/Ho_Chi_Minh">Asia/Ho_Chi_Minh</option><option value="UTC">UTC</option></select></label>
          <label className="wide">Cụm từ tự động đề xuất handoff<small>Mỗi dòng một cụm từ.</small><textarea name="auto_suggest_phrases" rows={5} defaultValue={config.auto_suggest_phrases.join("\n")} /></label>
        </div>
      </section>
      <section>
        <h3>Giờ làm việc</h3>
        <label className="site-config-checkbox"><input name="business_hours_enabled" type="checkbox" defaultChecked={config.business_hours.enabled} /><span>Chỉ cho phép handoff trong giờ làm việc</span></label>
        <label>Thông báo ngoài giờ<textarea name="offline_message" rows={3} defaultValue={config.business_hours.offline_message} /></label>
      </section>
      <footer>{message && <span>{message}</span>}<button className="sites-primary-button">Lưu handoff</button></footer>
    </form>
  );
}

type Lead = { id: string; session_id: string; email?: string | null; name?: string | null; captured_at: string; source: string };

export function LeadsPanel({
  siteId,
  config,
  onSave,
}: {
  siteId: string;
  config: SiteConfig["lead_capture"];
  onSave: SaveConfig;
}) {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [message, setMessage] = useState("");
  const canDelete = getStoredUser()?.role !== "agent";
  const load = useCallback(async () => {
    if (DEV_AUTH_ENABLED) {
      setLeads([{ id: "demo-lead", session_id: "demo-session", email: "khach@example.com", name: "Khách hàng mẫu", captured_at: new Date().toISOString(), source: "chat" }]);
      return;
    }
    const response = await authFetch(`${API_BASE}/sites/${siteId}/leads?limit=100`);
    if (response.ok) setLeads(((await response.json()) as { leads: Lead[] }).leads);
  }, [siteId]);
  useEffect(() => { const frame = requestAnimationFrame(() => void load()); return () => cancelAnimationFrame(frame); }, [load]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const result = await onSave("lead_capture", {
      collect_email: data.get("collect_email") === "on",
      email_required: data.get("email_required") === "on",
      email_prompt: String(data.get("email_prompt")),
      collect_name: data.get("collect_name") === "on",
      name_required: data.get("name_required") === "on",
      capture_timing: String(data.get("capture_timing")),
      messages_before_capture: Number(data.get("messages_before_capture")),
    });
    setMessage(result.message);
  }

  async function remove(id: string) {
    if (!DEV_AUTH_ENABLED) await authFetch(`${API_BASE}/leads/${id}`, { method: "DELETE" });
    setLeads(leads.filter((lead) => lead.id !== id));
  }

  async function exportCsv() {
    if (DEV_AUTH_ENABLED) { setMessage("Xuất CSV chỉ khả dụng với dữ liệu thật."); return; }
    const response = await authFetch(`${API_BASE}/sites/${siteId}/leads/export`);
    if (!response.ok) return;
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url; link.download = `leads-${siteId}.csv`; link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="site-config-form">
      <header><h2>Thu thập khách hàng tiềm năng</h2><p>Cấu hình biểu mẫu và quản lý thông tin khách để lại.</p></header>
      <form onSubmit={save}>
        <section>
          <div className="site-config-grid">
            <label className="site-config-checkbox"><input name="collect_email" type="checkbox" defaultChecked={config.collect_email} /><span>Thu thập email</span></label>
            <label className="site-config-checkbox"><input name="email_required" type="checkbox" defaultChecked={config.email_required} /><span>Bắt buộc nhập email</span></label>
            <label className="site-config-checkbox"><input name="collect_name" type="checkbox" defaultChecked={config.collect_name} /><span>Thu thập tên</span></label>
            <label className="site-config-checkbox"><input name="name_required" type="checkbox" defaultChecked={config.name_required} /><span>Bắt buộc nhập tên</span></label>
            <label className="wide">Lời nhắc nhập email<input name="email_prompt" defaultValue={config.email_prompt} /></label>
            <label>Thời điểm hiển thị<select name="capture_timing" defaultValue={config.capture_timing}><option value="before_chat">Trước khi chat</option><option value="after_messages">Sau một số tin nhắn</option><option value="on_handoff">Khi handoff</option></select></label>
            <label>Số tin nhắn trước khi hiển thị<input name="messages_before_capture" type="number" min={1} max={20} defaultValue={config.messages_before_capture} /></label>
          </div>
        </section>
        <footer>{message && <span>{message}</span>}<button className="sites-primary-button">Lưu lead capture</button></footer>
      </form>
      <section>
        <div className="management-heading"><h3>Danh sách lead ({leads.length})</h3><button onClick={() => void exportCsv()}>Xuất CSV</button></div>
        <div className="lead-table"><table><thead><tr><th>Khách hàng</th><th>Nguồn</th><th>Thời gian</th><th /></tr></thead><tbody>{leads.map((lead) => <tr key={lead.id}><td><strong>{lead.name || "Chưa có tên"}</strong><small>{lead.email || "Chưa có email"}</small></td><td>{lead.source}</td><td>{new Date(lead.captured_at).toLocaleString("vi-VN")}</td><td>{canDelete && <button onClick={() => void remove(lead.id)}>Xóa</button>}</td></tr>)}</tbody></table></div>
      </section>
    </div>
  );
}

export function EmbedPanel({ siteId }: { siteId: string }) {
  const [script, setScript] = useState("");
  const [sri, setSri] = useState("");
  const [copied, setCopied] = useState(false);
  const load = useCallback(async () => {
    if (DEV_AUTH_ENABLED) {
      const origin = window.location.origin;
      setScript(`<!-- Auralis Widget (Secure) -->\n<script>\n(function() {\n  var s = document.createElement('script');\n  s.src = '${origin}/widget/chatbot.js';\n  s.async = true;\n  s.dataset.siteId = '${siteId}';\n  s.dataset.apiUrl = '${origin}';\n  document.head.appendChild(s);\n})();\n<\\/script>`);
      setSri("sha384-demo-local-development");
      return;
    }
    const response = await authFetch(`${API_BASE}/embed/script/${siteId}`);
    if (response.ok) {
      const data = (await response.json()) as { embed_script: string; sri_hash?: string | null };
      setScript(data.embed_script); setSri(data.sri_hash || "");
    }
  }, [siteId]);
  useEffect(() => { const frame = requestAnimationFrame(() => void load()); return () => cancelAnimationFrame(frame); }, [load]);
  return (
    <div className="site-config-form embed-panel">
      <header><h2>Mã nhúng</h2><p>Mã cài đặt bảo mật được tạo trực tiếp từ backend và gắn với website này.</p></header>
      <section>
        <div className="embed-code-header"><span>HTML</span><button onClick={async () => { await navigator.clipboard.writeText(script); setCopied(true); setTimeout(() => setCopied(false), 1800); }}>{copied ? "Đã sao chép" : "Sao chép"}</button></div>
        <pre><code>{script || "Đang tạo mã nhúng..."}</code></pre>
        {sri && <div className="sri-box"><strong>SRI Hash</strong><code>{sri}</code></div>}
      </section>
    </div>
  );
}

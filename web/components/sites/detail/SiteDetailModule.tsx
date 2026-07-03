"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { API_BASE, authFetch, DEV_AUTH_ENABLED } from "@/lib/auth";
import { AppearancePanel, BehaviorPanel } from "./ConfigPanels";
import { CrawlingPanel } from "./CrawlingPanel";
import {
  QuickPromptsPanel,
  TrainingPanel,
  TriggersPanel,
} from "./ManagementPanels";
import {
  EmbedPanel,
  HandoffConfigPanel,
  LeadsPanel,
  SecurityPanel,
} from "./OperationsPanels";
import {
  AppearanceConfig,
  BehaviorConfig,
  SiteConfig,
  SiteDetail,
} from "./types";

type DetailTab =
  | "overview"
  | "appearance"
  | "embed"
  | "behavior"
  | "quick-prompts"
  | "triggers"
  | "training"
  | "handoff"
  | "leads"
  | "security"
  | "crawling"
  ;

const defaultConfig: SiteConfig = {
  appearance: {
    primary_color: "#2F8BFF",
    chat_title: "Auralis Support",
    welcome_message: "Xin chào! Tôi có thể giúp gì cho bạn?",
    bot_avatar_url: null,
    position: "bottom-right",
    hide_branding: false,
    custom_branding_text: null,
    custom_branding_url: null,
  },
  behavior: {
    system_prompt:
      "Bạn là trợ lý AI hữu ích. Chỉ trả lời dựa trên dữ liệu được cung cấp và nói rõ khi chưa đủ thông tin.",
    temperature: 0.7,
    max_tokens: 500,
    show_sources: true,
  },
  lead_capture: {
    collect_email: false,
    email_required: false,
    email_prompt: "Nhập email để tiếp tục",
    collect_name: false,
    name_required: false,
    capture_timing: "before_chat",
    messages_before_capture: 3,
  },
  security: {
    allowed_domains: [],
    enforce_domain_validation: true,
    require_referrer: false,
    rate_limit_per_session: 60,
  },
  quick_prompts: {
    enabled: true,
    prompts: [
      { id: "demo-1", text: "Tìm sản phẩm phù hợp", icon: "💡", enabled: true },
      { id: "demo-2", text: "Giới thiệu về công ty", icon: "🏢", enabled: true },
    ],
    show_after_response: false,
    max_display: 4,
  },
};

const demoSite: SiteDetail = {
  site_id: "demo-auralis",
  name: "Auralis Demo",
  url: "https://auralisai.duckdns.org",
  status: "completed",
  pages_crawled: 48,
  pages_indexed: 48,
  total_pages: 48,
};

export function SiteDetailModule({ siteId }: { siteId: string }) {
  const [site, setSite] = useState<SiteDetail | null>(null);
  const [config, setConfig] = useState<SiteConfig>(defaultConfig);
  const [tab, setTab] = useState<DetailTab>("overview");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (DEV_AUTH_ENABLED) {
        setSite({ ...demoSite, site_id: siteId });
        setConfig(defaultConfig);
        return;
      }
      const [siteResponse, configResponse] = await Promise.all([
        authFetch(`${API_BASE}/sites/${siteId}`),
        authFetch(`${API_BASE}/sites/${siteId}/config`),
      ]);
      if (!siteResponse.ok || !configResponse.ok) {
        throw new Error("Không thể tải cấu hình website.");
      }
      setSite((await siteResponse.json()) as SiteDetail);
      setConfig((await configResponse.json()) as SiteConfig);
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Không thể tải cấu hình website.",
      );
    } finally {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    const frame = requestAnimationFrame(() => void load());
    return () => cancelAnimationFrame(frame);
  }, [load]);

  async function saveConfig(
    section: "appearance" | "behavior" | "security" | "lead_capture",
    value:
      | AppearanceConfig
      | BehaviorConfig
      | SiteConfig["security"]
      | SiteConfig["lead_capture"],
  ) {
    try {
      if (!DEV_AUTH_ENABLED) {
        const response = await authFetch(`${API_BASE}/sites/${siteId}/config`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ [section]: value }),
        });
        if (!response.ok) {
          const data = (await response.json().catch(() => ({}))) as {
            detail?: string;
          };
          throw new Error(data.detail || "Không thể lưu cấu hình.");
        }
      }
      setConfig((current) => ({ ...current, [section]: value }));
      return { ok: true, message: "Đã lưu thay đổi." };
    } catch (saveError) {
      return {
        ok: false,
        message:
          saveError instanceof Error
            ? saveError.message
            : "Không thể lưu cấu hình.",
      };
    }
  }

  async function resetConfig() {
    if (!window.confirm("Khôi phục toàn bộ cấu hình website về mặc định?")) return;
    if (DEV_AUTH_ENABLED) {
      setConfig(defaultConfig);
      return;
    }
    const response = await authFetch(`${API_BASE}/sites/${siteId}/config/reset`, {
      method: "POST",
    });
    if (response.ok) setConfig((await response.json()) as SiteConfig);
  }

  if (loading) {
    return (
      <div className="dashboard-loading">
        <span className="dashboard-spinner" />
        <p>Đang tải cấu hình website...</p>
      </div>
    );
  }

  if (!site || error) {
    return (
      <main className="dashboard-content">
        <div className="sites-alert">
          <span>{error || "Không tìm thấy website."}</span>
          <Link href="/dashboard/sites">Quay lại</Link>
        </div>
      </main>
    );
  }

  const tabs: Array<{ id: DetailTab; label: string; group: string }> = [
    { id: "overview", label: "Tổng quan", group: "Website" },
    { id: "appearance", label: "Giao diện", group: "Chatbot" },
    { id: "embed", label: "Mã nhúng", group: "Chatbot" },
    { id: "behavior", label: "Hành vi AI", group: "Chatbot" },
    { id: "quick-prompts", label: "Quick Prompts", group: "AI & Nội dung" },
    { id: "triggers", label: "Triggers", group: "AI & Nội dung" },
    { id: "training", label: "Training", group: "AI & Nội dung" },
    { id: "handoff", label: "Handoff", group: "Vận hành" },
    { id: "leads", label: "Leads", group: "Vận hành" },
    { id: "security", label: "Security", group: "Vận hành" },
    { id: "crawling", label: "Crawling", group: "Vận hành" },
  ];

  return (
    <main className="dashboard-content site-detail-module">
      <nav className="site-detail-breadcrumb">
        <Link href="/dashboard/sites">Website</Link>
        <span>›</span>
        <strong>{site.name || site.url}</strong>
      </nav>

      <header className="site-detail-title">
        <div>
          <span className="site-overview-letter">
            {(site.name || site.url).charAt(0).toUpperCase()}
          </span>
          <div>
            <h1>{site.name || site.url}</h1>
            <a href={site.url} target="_blank" rel="noreferrer">
              {site.url} ↗
            </a>
          </div>
        </div>
        <span className={`site-status ${site.status}`}>
          <i /> {site.status === "completed" ? "Sẵn sàng" : site.status}
        </span>
      </header>

      <div className="site-detail-workspace">
        <aside className="site-detail-nav">
          <Link className="site-detail-back" href="/dashboard/sites">
            <Icon name="arrow" />
            <span>Quay lại website</span>
          </Link>
          {tabs.map((item, index) => {
            const showGroup = index === 0 || tabs[index - 1].group !== item.group;
            return (
              <div key={item.id}>
                {showGroup && <small>{item.group}</small>}
                <button
                  className={tab === item.id ? "active" : ""}
                  onClick={() => setTab(item.id)}
                >
                  {item.label}
                </button>
              </div>
            );
          })}
        </aside>

        <section className="site-detail-panel">
          {tab === "overview" && (
            <div className="site-overview-panel">
              <header>
                <h2>Tổng quan website</h2>
                <p>Theo dõi trạng thái dữ liệu và các bước triển khai chatbot.</p>
              </header>
              <div className="site-detail-metrics">
                <article><span>Trạng thái</span><strong>{site.status === "completed" ? "Sẵn sàng" : site.status}</strong></article>
                <article><span>Đã thu thập</span><strong>{site.pages_crawled}</strong></article>
                <article><span>Đã lập chỉ mục</span><strong>{site.pages_indexed}</strong></article>
                <article><span>Tổng số trang</span><strong>{site.total_pages}</strong></article>
              </div>
              <div className="site-detail-steps">
                <button onClick={() => setTab("appearance")}><span><Icon name="sparkles" /></span><div><strong>Tùy chỉnh chatbot</strong><p>Thiết lập màu sắc, lời chào và ảnh đại diện.</p></div>›</button>
                <button onClick={() => setTab("crawling")}><span><Icon name="globe" /></span><div><strong>Cập nhật dữ liệu</strong><p>Crawl lại website hoặc chỉ tìm các trang mới.</p></div>›</button>
                <button onClick={() => setTab("embed")}><span><Icon name="document" /></span><div><strong>Cài đặt lên website</strong><p>Sao chép mã nhúng vào trang của bạn.</p></div>›</button>
              </div>
            </div>
          )}
          {tab === "appearance" && (
            <AppearancePanel
              key={JSON.stringify(config.appearance)}
              config={config.appearance}
              onSave={(value) => saveConfig("appearance", value)}
              onReset={resetConfig}
            />
          )}
          {tab === "behavior" && (
            <BehaviorPanel
              key={JSON.stringify(config.behavior)}
              config={config.behavior}
              onSave={(value) => saveConfig("behavior", value)}
            />
          )}
          {tab === "quick-prompts" && (
            <QuickPromptsPanel
              siteId={siteId}
              initial={config.quick_prompts}
              onChange={(value) =>
                setConfig((current) => ({ ...current, quick_prompts: value }))
              }
            />
          )}
          {tab === "triggers" && <TriggersPanel siteId={siteId} />}
          {tab === "training" && <TrainingPanel siteId={siteId} />}
          {tab === "handoff" && <HandoffConfigPanel siteId={siteId} />}
          {tab === "leads" && (
            <LeadsPanel
              siteId={siteId}
              config={config.lead_capture}
              onSave={saveConfig}
            />
          )}
          {tab === "security" && (
            <SecurityPanel config={config.security} onSave={saveConfig} />
          )}
          {tab === "crawling" && <CrawlingPanel siteId={siteId} />}
          {tab === "embed" && <EmbedPanel siteId={siteId} />}
        </section>
      </div>
    </main>
  );
}

"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import {
  API_BASE,
  authFetch,
  DEV_AUTH_ENABLED,
  getStoredUser,
} from "@/lib/auth";

type SiteStatus =
  | "pending"
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

type Site = {
  site_id: string;
  name?: string | null;
  url: string;
  status: SiteStatus;
  pages_crawled: number;
  pages_indexed: number;
  total_pages: number;
  created_at?: string | null;
  error?: string | null;
};

const demoSites: Site[] = [
  {
    site_id: "demo-auralis",
    name: "Auralis Demo",
    url: "https://auralisai.duckdns.org",
    status: "completed",
    pages_crawled: 48,
    pages_indexed: 48,
    total_pages: 48,
  },
  {
    site_id: "demo-store",
    name: "Cửa hàng mẫu",
    url: "https://store.example.com",
    status: "running",
    pages_crawled: 17,
    pages_indexed: 12,
    total_pages: 12,
  },
];

const statusCopy: Record<SiteStatus, string> = {
  pending: "Chờ xử lý",
  queued: "Đang xếp hàng",
  running: "Đang thu thập",
  completed: "Sẵn sàng",
  failed: "Thất bại",
  cancelled: "Đã dừng",
};

function getDomain(url: string) {
  if (url.startsWith("docs://")) return "Kho tài liệu";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url.replace(/^https?:\/\//, "").replace(/\/$/, "");
  }
}

async function readError(response: Response, fallback: string) {
  const data = (await response.json().catch(() => ({}))) as {
    detail?: string | { message?: string };
  };
  if (typeof data.detail === "string") return data.detail;
  return data.detail?.message || fallback;
}

export function SitesModule() {
  const [sites, setSites] = useState<Site[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const user = useMemo(() => getStoredUser(), []);
  const canManage = user?.role !== "agent";

  const loadSites = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    setError("");

    try {
      if (DEV_AUTH_ENABLED) {
        setSites((current) => (current.length ? current : demoSites));
        setSelectedId((current) => current ?? demoSites[0].site_id);
        return;
      }

      const response = await authFetch(`${API_BASE}/sites`);
      if (!response.ok) {
        throw new Error(await readError(response, "Không thể tải danh sách website."));
      }
      const data = (await response.json()) as Site[];
      setSites(data);
      setSelectedId((current) => {
        if (current && data.some((site) => site.site_id === current)) return current;
        return data[0]?.site_id ?? null;
      });
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Không thể tải danh sách website.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => void loadSites());
    return () => window.cancelAnimationFrame(frame);
  }, [loadSites]);

  useEffect(() => {
    if (!sites.some((site) => ["queued", "running"].includes(site.status))) return;
    const timer = window.setInterval(() => void loadSites(true), 5000);
    return () => window.clearInterval(timer);
  }, [loadSites, sites]);

  const selectedSite =
    sites.find((site) => site.site_id === selectedId) ?? null;

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreating(true);
    setError("");
    const form = new FormData(event.currentTarget);
    const name = String(form.get("name") ?? "").trim();
    const url = String(form.get("url") ?? "").trim();
    const maxPages = Number(form.get("max_pages") ?? 50);

    try {
      if (DEV_AUTH_ENABLED) {
        const site: Site = {
          site_id: `local-${Date.now()}`,
          name: name || getDomain(url),
          url,
          status: "queued",
          pages_crawled: 0,
          pages_indexed: 0,
          total_pages: 0,
        };
        setSites((current) => [site, ...current]);
        setSelectedId(site.site_id);
      } else {
        const response = await authFetch(`${API_BASE}/embed/setup`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: name || undefined,
            url,
            max_pages: maxPages,
          }),
        });
        if (!response.ok) {
          throw new Error(await readError(response, "Không thể thêm website."));
        }
        const created = (await response.json()) as { site_id: string };
        await loadSites(true);
        setSelectedId(created.site_id);
      }
      setModalOpen(false);
    } catch (createError) {
      setError(
        createError instanceof Error
          ? createError.message
          : "Không thể thêm website.",
      );
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete() {
    if (!selectedSite) return;
    const confirmed = window.confirm(
      `Xóa “${selectedSite.name || getDomain(selectedSite.url)}” cùng toàn bộ dữ liệu liên quan?`,
    );
    if (!confirmed) return;

    setDeleting(true);
    setError("");
    try {
      if (DEV_AUTH_ENABLED) {
        setSites((current) =>
          current.filter((site) => site.site_id !== selectedSite.site_id),
        );
        setSelectedId(
          sites.find((site) => site.site_id !== selectedSite.site_id)?.site_id ??
            null,
        );
      } else {
        const response = await authFetch(
          `${API_BASE}/sites/${selectedSite.site_id}`,
          { method: "DELETE" },
        );
        if (!response.ok) {
          throw new Error(await readError(response, "Không thể xóa website."));
        }
        await loadSites(true);
      }
    } catch (deleteError) {
      setError(
        deleteError instanceof Error
          ? deleteError.message
          : "Không thể xóa website.",
      );
    } finally {
      setDeleting(false);
    }
  }

  return (
    <main className="dashboard-content sites-module">
      <div className="sites-toolbar">
        <div className="dashboard-page-heading">
          <span>
            <Icon name="grid" />
          </span>
          <div>
            <h1>Website</h1>
            <p>Quản lý nguồn dữ liệu và trợ lý AI trên từng website.</p>
          </div>
        </div>
        {canManage && (
          <button className="sites-primary-button" onClick={() => setModalOpen(true)}>
            <span>+</span> Thêm website
          </button>
        )}
      </div>

      {error && (
        <div className="sites-alert" role="alert">
          <span>{error}</span>
          <button onClick={() => void loadSites()}>Thử lại</button>
        </div>
      )}

      <div className="sites-workspace">
        <section className="sites-master">
          <div className="sites-master-header">
            <div>
              <strong>Website của bạn</strong>
              <span>{sites.length} website</span>
            </div>
            <button
              className="sites-icon-button"
              onClick={() => void loadSites()}
              title="Làm mới"
              aria-label="Làm mới danh sách"
            >
              ↻
            </button>
          </div>

          <div className="sites-list">
            {loading ? (
              <div className="sites-list-loading">
                <span className="dashboard-spinner" />
                Đang tải website...
              </div>
            ) : sites.length === 0 ? (
              <div className="sites-empty">
                <Icon name="globe" />
                <strong>Chưa có website</strong>
                <p>Thêm website đầu tiên để xây dựng kho tri thức cho trợ lý AI.</p>
                {canManage && (
                  <button onClick={() => setModalOpen(true)}>Thêm website</button>
                )}
              </div>
            ) : (
              sites.map((site) => {
                const domain = getDomain(site.url);
                return (
                  <button
                    className={`sites-list-item ${
                      selectedId === site.site_id ? "active" : ""
                    }`}
                    key={site.site_id}
                    onClick={() => setSelectedId(site.site_id)}
                  >
                    <span className="site-letter">
                      {(site.name || domain).charAt(0).toUpperCase()}
                    </span>
                    <span className="site-list-copy">
                      <strong>{site.name || domain}</strong>
                      <small>{domain}</small>
                    </span>
                    <span className={`site-status ${site.status}`}>
                      <i /> {statusCopy[site.status] ?? site.status}
                    </span>
                  </button>
                );
              })
            )}
          </div>
        </section>

        <section className="sites-detail">
          {!selectedSite ? (
            <div className="sites-detail-empty">
              <Icon name="globe" />
              <h2>Chọn một website</h2>
              <p>Chọn website bên trái để xem trạng thái và quản lý dữ liệu.</p>
            </div>
          ) : (
            <div className="site-overview">
              <div className="site-overview-header">
                <div>
                  <span className="site-overview-letter">
                    {(selectedSite.name || getDomain(selectedSite.url))
                      .charAt(0)
                      .toUpperCase()}
                  </span>
                  <div>
                    <h2>{selectedSite.name || getDomain(selectedSite.url)}</h2>
                    <a href={selectedSite.url} target="_blank" rel="noreferrer">
                      {getDomain(selectedSite.url)} ↗
                    </a>
                  </div>
                </div>
                {canManage && (
                  <button
                    className="site-delete-button"
                    onClick={handleDelete}
                    disabled={deleting}
                  >
                    {deleting ? "Đang xóa..." : "Xóa website"}
                  </button>
                )}
              </div>

              <div className="site-metrics">
                <article>
                  <span>Trạng thái</span>
                  <strong className={`metric-status ${selectedSite.status}`}>
                    {statusCopy[selectedSite.status] ?? selectedSite.status}
                  </strong>
                </article>
                <article>
                  <span>Đã thu thập</span>
                  <strong>{selectedSite.pages_crawled || 0}</strong>
                </article>
                <article>
                  <span>Đã lập chỉ mục</span>
                  <strong>{selectedSite.pages_indexed || 0}</strong>
                </article>
                <article>
                  <span>Tổng số trang</span>
                  <strong>{selectedSite.total_pages || 0}</strong>
                </article>
              </div>

              {selectedSite.error && (
                <div className="site-crawl-error">
                  <strong>Không thể thu thập dữ liệu</strong>
                  <p>{selectedSite.error}</p>
                </div>
              )}

              <div className="site-next-step">
                <span>
                  <Icon name="settings" />
                </span>
                <div>
                  <h3>Cấu hình trợ lý AI</h3>
                  <p>
                    Giao diện cấu hình, tài liệu, crawl và mã nhúng sẽ được chuyển
                    trong module chi tiết website tiếp theo.
                  </p>
                </div>
                <a href={`/dashboard/sites/${selectedSite.site_id}`}>
                  Quản lý
                </a>
              </div>
            </div>
          )}
        </section>
      </div>

      {modalOpen && (
        <div className="sites-modal-layer" role="presentation">
          <button
            className="sites-modal-backdrop"
            onClick={() => setModalOpen(false)}
            aria-label="Đóng"
          />
          <section
            className="sites-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="add-site-title"
          >
            <div className="sites-modal-header">
              <div>
                <h2 id="add-site-title">Thêm website mới</h2>
                <p>Auralis sẽ thu thập nội dung và xây dựng kho tri thức.</p>
              </div>
              <button onClick={() => setModalOpen(false)} aria-label="Đóng">
                ×
              </button>
            </div>
            <form onSubmit={handleCreate}>
              <label>
                Tên website <small>Không bắt buộc</small>
                <input name="name" placeholder="Ví dụ: Trung tâm trợ giúp" />
              </label>
              <label>
                Địa chỉ website
                <input
                  name="url"
                  type="url"
                  placeholder="https://example.com"
                  required
                  autoFocus
                />
              </label>
              <label>
                Số trang thu thập tối đa
                <input
                  name="max_pages"
                  type="number"
                  defaultValue={50}
                  min={1}
                  max={1000}
                  required
                />
              </label>
              <div className="sites-modal-actions">
                <button type="button" onClick={() => setModalOpen(false)}>
                  Hủy
                </button>
                <button className="sites-primary-button" disabled={creating}>
                  {creating ? "Đang tạo..." : "Thêm và thu thập dữ liệu"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </main>
  );
}

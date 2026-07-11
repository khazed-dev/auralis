"use client";

import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { API_BASE, authFetch, DEV_AUTH_ENABLED } from "@/lib/auth";
import { CrawlHistory } from "./types";

export function CrawlingPanel({ siteId }: { siteId: string }) {
  const [isCrawling, setIsCrawling] = useState(false);
  const [pages, setPages] = useState(0);
  const [history, setHistory] = useState<CrawlHistory[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const crawlingRef = useRef(false);
  const notifyOnCompletionRef = useRef(true);
  const [schedule, setSchedule] = useState({
    enabled: false,
    frequency: "weekly",
    custom_cron: "",
    max_pages: 50,
    include_patterns: [] as string[],
    exclude_patterns: [] as string[],
    notify_on_completion: true,
  });

  const load = useCallback(async () => {
    if (DEV_AUTH_ENABLED) {
      setHistory([
        {
          job_id: "demo-crawl",
          trigger: "manual",
          status: "completed",
          pages_crawled: 48,
          pages_indexed: 48,
          created_at: new Date(Date.now() - 86400_000).toISOString(),
          duration_seconds: 31,
        },
      ]);
      return;
    }
    const [statusResponse, historyResponse, scheduleResponse] = await Promise.all([
      authFetch(`${API_BASE}/sites/${siteId}/crawl-status`),
      authFetch(`${API_BASE}/sites/${siteId}/crawl-history?limit=10`),
      authFetch(`${API_BASE}/sites/${siteId}/crawl-schedule`),
    ]);
    let notifyOnCompletion = notifyOnCompletionRef.current;
    if (scheduleResponse.ok) {
      const data = (await scheduleResponse.json()) as {
        schedule: typeof schedule;
      };
      notifyOnCompletion = data.schedule.notify_on_completion !== false;
      notifyOnCompletionRef.current = notifyOnCompletion;
      setSchedule({
        ...data.schedule,
        custom_cron: data.schedule.custom_cron || "",
        include_patterns: data.schedule.include_patterns || [],
        exclude_patterns: data.schedule.exclude_patterns || [],
      });
    }
    if (statusResponse.ok) {
      const status = (await statusResponse.json()) as {
        is_crawling: boolean;
        pages_crawled?: number;
      };
      const justFinished = crawlingRef.current && !status.is_crawling;
      crawlingRef.current = status.is_crawling;
      setIsCrawling(status.is_crawling);
      setPages(status.pages_crawled || 0);
      if (justFinished && notifyOnCompletion) {
        setMessage("Crawl đã hoàn tất. Dữ liệu mới đã sẵn sàng.");
        if (typeof Notification !== "undefined" && Notification.permission === "granted") {
          new Notification("Auralis AI", { body: "Crawl website đã hoàn tất." });
        }
      }
    }
    if (historyResponse.ok) {
      const data = (await historyResponse.json()) as {
        history: CrawlHistory[];
      };
      setHistory(data.history);
    }
  }, [siteId]);

  useEffect(() => {
    const frame = requestAnimationFrame(() => void load());
    const timer = setInterval(() => void load(), 5000);
    return () => {
      cancelAnimationFrame(frame);
      clearInterval(timer);
    };
  }, [load]);

  async function action(path: "crawl-now" | "crawl-new" | "crawl-cancel") {
    setBusy(true);
    setMessage("");
    try {
      if (DEV_AUTH_ENABLED) {
        setIsCrawling(path !== "crawl-cancel");
        setPages(0);
      } else {
        const response = await authFetch(`${API_BASE}/sites/${siteId}/${path}`, {
          method: "POST",
        });
        if (!response.ok) {
          const data = (await response.json().catch(() => ({}))) as {
            detail?: string;
          };
          throw new Error(data.detail || "Không thể thực hiện thao tác.");
        }
        await load();
      }
      setMessage(
        path === "crawl-cancel"
          ? "Đã gửi yêu cầu dừng crawl."
          : "Đã đưa tác vụ crawl vào hàng chờ.",
      );
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Không thể thực hiện thao tác.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function saveSchedule(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const next = {
      enabled: form.get("enabled") === "on",
      frequency: String(form.get("frequency")),
      custom_cron: String(form.get("custom_cron") || "") || null,
      max_pages: Number(form.get("max_pages")),
      include_patterns: String(form.get("include_patterns") || "").split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
      exclude_patterns: String(form.get("exclude_patterns") || "").split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
      notify_on_completion: form.get("notify_on_completion") === "on",
    };
    if (
      next.notify_on_completion &&
      typeof Notification !== "undefined" &&
      Notification.permission === "default"
    ) {
      await Notification.requestPermission();
    }
    if (!DEV_AUTH_ENABLED) {
      const response = await authFetch(`${API_BASE}/sites/${siteId}/crawl-schedule`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(next),
      });
      if (!response.ok) {
        const data = (await response.json().catch(() => ({}))) as { detail?: string };
        setMessage(data.detail || "Không thể lưu lịch crawl.");
        return;
      }
    }
    setSchedule({ ...next, custom_cron: next.custom_cron || "" });
    notifyOnCompletionRef.current = next.notify_on_completion;
    setMessage("Đã lưu lịch crawl.");
  }

  return (
    <div className="site-config-form crawl-panel">
      <header>
        <h2>Thu thập dữ liệu website</h2>
        <p>Cập nhật nội dung để kho tri thức luôn chính xác.</p>
      </header>
      {isCrawling && (
        <div className="crawl-running-banner">
          <span className="dashboard-spinner" />
          <div>
            <strong>Đang thu thập dữ liệu...</strong>
            <small>{pages} trang đã được xử lý</small>
          </div>
          <button disabled={busy} onClick={() => void action("crawl-cancel")}>
            Dừng crawl
          </button>
        </div>
      )}
      <section>
        <h3>Thao tác nhanh</h3>
        <div className="crawl-actions">
          <button
            disabled={busy || isCrawling}
            onClick={() => void action("crawl-now")}
          >
            Crawl lại toàn bộ
          </button>
          <button
            disabled={busy || isCrawling}
            onClick={() => void action("crawl-new")}
          >
            Chỉ tìm trang mới
          </button>
        </div>
        {message && <p className="crawl-action-message">{message}</p>}
      </section>
      <form onSubmit={saveSchedule}>
        <section>
          <h3>Lịch crawl tự động</h3>
          <label className="site-config-checkbox"><input name="enabled" type="checkbox" defaultChecked={schedule.enabled} /><span>Tự động cập nhật dữ liệu theo lịch</span></label>
          <div className="site-config-grid">
            <label>Tần suất<select name="frequency" defaultValue={schedule.frequency}><option value="daily">Hàng ngày</option><option value="weekly">Hàng tuần</option><option value="monthly">Hàng tháng</option><option value="custom">Cron tùy chỉnh</option></select></label>
            <label>Số trang tối đa<input name="max_pages" type="number" min={1} max={1000} defaultValue={schedule.max_pages} /></label>
            <label className="wide">Cron tùy chỉnh<input name="custom_cron" defaultValue={schedule.custom_cron} placeholder="0 2 * * 0" /></label>
            <label>URL cần bao gồm<small>Mỗi dòng một pattern.</small><textarea name="include_patterns" rows={4} defaultValue={schedule.include_patterns.join("\n")} placeholder="/blog/*" /></label>
            <label>URL cần loại trừ<small>Mỗi dòng một pattern.</small><textarea name="exclude_patterns" rows={4} defaultValue={schedule.exclude_patterns.join("\n")} placeholder="/admin/*" /></label>
          </div>
          <label className="site-config-checkbox"><input name="notify_on_completion" type="checkbox" defaultChecked={schedule.notify_on_completion} /><span>Hiển thị thông báo trình duyệt khi crawl hoàn tất</span></label>
          <button className="sites-primary-button">Lưu lịch crawl</button>
        </section>
      </form>
      <section>
        <h3>Lịch sử crawl</h3>
        <div className="crawl-history-table">
          <table>
            <thead>
              <tr>
                <th>Thời gian</th>
                <th>Loại</th>
                <th>Trang</th>
                <th>Trạng thái</th>
                <th>Thời lượng</th>
              </tr>
            </thead>
            <tbody>
              {history.length ? (
                history.map((item, index) => (
                  <Fragment
                    key={item.job_id || `${item.created_at}-${index}`}
                  >
                    <tr
                      title={item.errors?.join("\n") || undefined}
                    >
                      <td>
                        {item.started_at || item.created_at
                          ? new Date(
                              item.started_at || item.created_at || "",
                            ).toLocaleString("vi-VN")
                          : "—"}
                      </td>
                      <td>{item.trigger}</td>
                      <td>
                        {item.pages_crawled || 0} / {item.pages_indexed || 0}
                      </td>
                      <td>
                        <span className={`crawl-history-status ${item.status}`}>
                          {item.status}
                        </span>
                      </td>
                      <td>
                        {item.duration_seconds
                          ? `${Math.round(item.duration_seconds)} giây`
                          : "—"}
                      </td>
                    </tr>
                    {item.errors?.length ? (
                      <tr className="crawl-history-error-row">
                        <td colSpan={5}>
                          {item.errors[item.errors.length - 1]}
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                ))
              ) : (
                <tr>
                  <td colSpan={5}>Chưa có lịch sử crawl.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

"use client";

import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { API_BASE, authFetch, DEV_AUTH_ENABLED } from "@/lib/auth";
import { CrawlHistory } from "./types";

async function crawlError(response: Response, fallback: string) {
  const data = await response.json().catch(() => ({}));
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) return data.detail.map((item: { msg: string }) => item.msg).join("; ");
  return fallback;
}

export function CrawlingPanel({ siteId }: { siteId: string }) {
  const [tab, setTab] = useState<"manual" | "automatic" | "indexing">("manual");
  const [indexStatus, setIndexStatus] = useState<{ pending_pages: number; indexed_pages: number } | null>(null);
  const [manual, setManual] = useState({ mode: "full", max_pages: 100, max_index_pages: 50, include_patterns: "", exclude_patterns: "" });
  const [isCrawling, setIsCrawling] = useState(false);
  const [pages, setPages] = useState(0);
  const [indexedPages, setIndexedPages] = useState(0);
  const [jobStatus, setJobStatus] = useState("running");
  const [jobTrigger, setJobTrigger] = useState("manual");
  const [history, setHistory] = useState<CrawlHistory[]>([]);
  const [busy, setBusy] = useState(false);
  const [savingSchedule, setSavingSchedule] = useState(false);
  const [scheduleReady, setScheduleReady] = useState(DEV_AUTH_ENABLED);
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

  const load = useCallback(async (withSchedule = false) => {
    if (DEV_AUTH_ENABLED) {
      setIndexStatus({ pending_pages: 8, indexed_pages: 48 });
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
    const [statusResponse, historyResponse, scheduleResponse, indexResponse] = await Promise.all([
      authFetch(`${API_BASE}/sites/${siteId}/crawl-status`),
      authFetch(`${API_BASE}/sites/${siteId}/crawl-history?limit=10`),
      withSchedule ? authFetch(`${API_BASE}/sites/${siteId}/crawl-schedule`) : Promise.resolve(null),
      authFetch(`${API_BASE}/sites/${siteId}/index-status`),
    ]);
    if (indexResponse.ok) setIndexStatus(await indexResponse.json());
    let notifyOnCompletion = notifyOnCompletionRef.current;
    if (scheduleResponse?.ok) {
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
      setScheduleReady(true);
    } else if (scheduleResponse) {
      setMessage("Không thể tải lịch crawl. Hãy thử tải lại trước khi lưu.");
    }
    if (statusResponse.ok) {
      const status = (await statusResponse.json()) as {
        is_crawling: boolean;
        pages_crawled?: number;
        pages_indexed?: number;
        status?: string;
        trigger?: string;
        last_crawl?: CrawlHistory;
      };
      const justFinished = crawlingRef.current && !status.is_crawling;
      crawlingRef.current = status.is_crawling;
      setIsCrawling(status.is_crawling);
      setJobStatus(status.status || "running");
      setJobTrigger(status.trigger || "manual");
      setPages(status.pages_crawled ?? status.last_crawl?.pages_crawled ?? 0);
      setIndexedPages(status.pages_indexed ?? status.last_crawl?.pages_indexed ?? 0);
      if (justFinished) {
        const outcome = status.last_crawl?.status;
        const body = outcome === "failed" ? "Tác vụ thất bại. Xem chi tiết trong lịch sử."
          : outcome === "cancelled" ? "Tác vụ đã dừng."
          : "Tác vụ đã hoàn tất. Xem số trang đã lập chỉ mục trong lịch sử.";
        setMessage(body);
        if (notifyOnCompletion && typeof Notification !== "undefined" && Notification.permission === "granted") {
          new Notification("Auralis AI", { body });
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
    const refresh = (withSchedule = false) => void load(withSchedule).catch(() => setMessage("Không thể tải trạng thái crawl. Đang chờ kết nối lại."));
    const frame = requestAnimationFrame(() => refresh(true));
    const timer = setInterval(() => refresh(), 5000);
    return () => {
      cancelAnimationFrame(frame);
      clearInterval(timer);
    };
  }, [load]);

  async function action(path: "crawl-now" | "crawl-new" | "crawl-cancel" | "index-pending") {
    setBusy(true);
    setMessage("");
    try {
      if (DEV_AUTH_ENABLED) {
        setIsCrawling(path !== "crawl-cancel");
        setPages(0);
        setIndexedPages(0);
      } else {
        const response = await authFetch(`${API_BASE}/sites/${siteId}/${path}`, {
          method: "POST",
          ...(path === "crawl-now" || path === "crawl-new" ? {
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              max_pages: manual.max_pages,
              max_index_pages: manual.max_index_pages,
              include_patterns: manual.include_patterns.split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
              exclude_patterns: manual.exclude_patterns.split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
            }),
          } : {}),
        });
        if (!response.ok) {
          throw new Error(await crawlError(response, "Không thể thực hiện thao tác."));
        }
        await load();
      }
      setMessage(
        path === "crawl-cancel"
          ? "Đã gửi yêu cầu dừng tác vụ."
          : path === "index-pending" ? "Đã đưa toàn bộ trang chưa lập chỉ mục vào hàng chờ."
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
    const next = {
      ...schedule,
      custom_cron: schedule.frequency === "custom" ? schedule.custom_cron || null : null,
      include_patterns: schedule.include_patterns.map((item) => item.trim()).filter(Boolean),
      exclude_patterns: schedule.exclude_patterns.map((item) => item.trim()).filter(Boolean),
    };
    setSavingSchedule(true);
    setMessage("");
    try {
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
          throw new Error(await crawlError(response, "Không thể lưu lịch crawl."));
        }
      }
      setSchedule({ ...next, custom_cron: next.custom_cron || "" });
      notifyOnCompletionRef.current = next.notify_on_completion;
      setMessage("Đã lưu lịch crawl.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Không thể lưu lịch crawl.");
    } finally {
      setSavingSchedule(false);
    }
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
            <strong>{jobStatus === "queued" ? "Tác vụ đang chờ chạy..." : jobTrigger === "index_pending" ? "Đang lập chỉ mục nội dung đã lưu..." : "Đang thu thập và lập chỉ mục..."}</strong>
            <small>Đã quét {pages} trang · Đã lập chỉ mục {indexedPages} trang</small>
          </div>
          <button disabled={busy} onClick={() => void action("crawl-cancel")}>
            Dừng tác vụ
          </button>
        </div>
      )}
      <div className="crawl-tabs" role="tablist" aria-label="Cách thu thập dữ liệu">
        {(["manual", "automatic", "indexing"] as const).map((item) => (
          <button key={item} id={`crawl-tab-${item}`} type="button" role="tab" aria-selected={tab === item}
            aria-controls={`crawl-panel-${item}`} tabIndex={tab === item ? 0 : -1}
            onClick={() => setTab(item)} onKeyDown={(event) => {
              if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
              event.preventDefault();
              const tabs = ["manual", "automatic", "indexing"] as const;
              const next = event.key === "Home" ? "manual" : event.key === "End" ? "indexing" : tabs[(tabs.indexOf(tab) + (event.key === "ArrowLeft" ? 2 : 1)) % tabs.length];
              setTab(next);
              document.getElementById(`crawl-tab-${next}`)?.focus();
            }}>{item === "manual" ? "Crawl thủ công" : item === "automatic" ? "Crawl tự động" : "Lập chỉ mục"}</button>
        ))}
      </div>
      {message && <p className="crawl-action-message" role="status">{message}</p>}
      <div id="crawl-panel-manual" className="crawl-tab-panel" role="tabpanel" aria-labelledby="crawl-tab-manual" hidden={tab !== "manual"}>
        <form onSubmit={(event) => { event.preventDefault(); void action(manual.mode === "full" ? "crawl-now" : "crawl-new"); }}>
          <section>
            <h3>Thiết lập lần quét</h3>
            <div className="site-config-grid">
              <label className="wide">Chế độ quét<select value={manual.mode} onChange={(event) => setManual({ ...manual, mode: event.target.value })}>
                <option value="full">Quét lại toàn bộ</option><option value="incremental">Chỉ thêm trang mới</option>
              </select><small>{manual.mode === "full" ? "Cập nhật lại các trang đã có và bổ sung trang mới, trong giới hạn bên dưới." : "Duyệt website để tìm URL mới. Những trang đã lập chỉ mục sẽ được giữ nguyên."}</small></label>
              <label>Số trang quét tối đa<input type="number" required min={1} max={1000} value={manual.max_pages} onChange={(event) => setManual({ ...manual, max_pages: Number(event.target.value) })} /><small>Thu thập tối đa 1.000 trang trong một lần chạy.</small></label>
              <label>Số trang lập chỉ mục tối đa<input type="number" required min={1} max={manual.max_pages} value={manual.max_index_pages} onChange={(event) => setManual({ ...manual, max_index_pages: Number(event.target.value) })} /><small>{manual.mode === "full" ? "Số trang tối đa được đưa vào kho tri thức sau khi quét." : "Chỉ tính các trang mới; không tính URL đã có trong kho tri thức."}</small></label>
            </div>
            <details className="crawl-url-filters"><summary>Lọc URL (tùy chọn)</summary>
              <div className="site-config-grid">
                <label>URL cần bao gồm<small>Biểu thức chính quy, mỗi dòng một mẫu.</small><textarea rows={3} value={manual.include_patterns} onChange={(event) => setManual({ ...manual, include_patterns: event.target.value })} placeholder="/blog/.*" /></label>
                <label>URL cần loại trừ<small>Để trống nếu không cần loại URL.</small><textarea rows={3} value={manual.exclude_patterns} onChange={(event) => setManual({ ...manual, exclude_patterns: event.target.value })} placeholder="/admin/.*" /></label>
              </div>
            </details>
            <div className="crawl-submit-row"><button className="sites-primary-button" disabled={busy || isCrawling}>{busy ? "Đang gửi yêu cầu..." : "Bắt đầu crawl"}</button><small>Áp dụng cho lần chạy này. Số trang thực tế phụ thuộc nội dung website và hạn mức gói.</small></div>
          </section>
        </form>
      </div>
      <div id="crawl-panel-automatic" className="crawl-tab-panel" role="tabpanel" aria-labelledby="crawl-tab-automatic" hidden={tab !== "automatic"}>
      <form onSubmit={saveSchedule}>
        <section>
          <h3>Lịch crawl tự động</h3>
          {!scheduleReady && <button type="button" onClick={() => void load(true).catch(() => setMessage("Không thể tải lịch crawl."))}>Thử tải lại lịch crawl</button>}
          <fieldset disabled={!scheduleReady || savingSchedule}>
          <label className="site-config-checkbox"><input name="enabled" type="checkbox" checked={schedule.enabled} onChange={(event) => setSchedule({ ...schedule, enabled: event.target.checked })} /><span>Tự động cập nhật dữ liệu theo lịch</span></label>
          <div className="site-config-grid">
            <label>Tần suất<select name="frequency" value={schedule.frequency} onChange={(event) => setSchedule({ ...schedule, frequency: event.target.value })}><option value="daily">Hàng ngày</option><option value="weekly">Hàng tuần</option><option value="monthly">Hàng tháng</option><option value="custom">Cron tùy chỉnh</option></select></label>
            <label>Số trang tối đa<input name="max_pages" type="number" required min={1} max={1000} value={schedule.max_pages} onChange={(event) => setSchedule({ ...schedule, max_pages: Number(event.target.value) })} /></label>
            {schedule.frequency === "custom" && <label className="wide">Cron tùy chỉnh<input name="custom_cron" required value={schedule.custom_cron} onChange={(event) => setSchedule({ ...schedule, custom_cron: event.target.value })} placeholder="0 2 * * 0" /></label>}
            <label>URL cần bao gồm<small>Biểu thức chính quy, mỗi dòng một mẫu.</small><textarea name="include_patterns" rows={4} value={schedule.include_patterns.join("\n")} onChange={(event) => setSchedule({ ...schedule, include_patterns: event.target.value.split("\n") })} placeholder="/blog/.*" /></label>
            <label>URL cần loại trừ<small>Biểu thức chính quy, mỗi dòng một mẫu.</small><textarea name="exclude_patterns" rows={4} value={schedule.exclude_patterns.join("\n")} onChange={(event) => setSchedule({ ...schedule, exclude_patterns: event.target.value.split("\n") })} placeholder="/admin/.*" /></label>
          </div>
          <label className="site-config-checkbox"><input name="notify_on_completion" type="checkbox" checked={schedule.notify_on_completion} onChange={(event) => setSchedule({ ...schedule, notify_on_completion: event.target.checked })} /><span>Hiển thị thông báo trình duyệt khi crawl hoàn tất</span></label>
          <button className="sites-primary-button">{savingSchedule ? "Đang lưu..." : "Lưu lịch crawl"}</button>
          </fieldset>
        </section>
      </form>
      </div>
      <div id="crawl-panel-indexing" className="crawl-tab-panel" role="tabpanel" aria-labelledby="crawl-tab-indexing" hidden={tab !== "indexing"}>
        <section>
          <h3>Lập chỉ mục các trang còn chờ</h3>
          <p>Dùng nội dung đã thu thập để bổ sung kho tri thức. Không crawl lại website và không xử lý lại các trang đã lập chỉ mục.</p>
          <div className="crawl-index-summary">
            <div><span>Chờ lập chỉ mục</span><strong>{indexStatus?.pending_pages ?? "—"}</strong></div>
            <div><span>Đã lập chỉ mục</span><strong>{indexStatus?.indexed_pages ?? "—"}</strong></div>
          </div>
          {indexStatus?.pending_pages === 0 && <p>Không có trang nào đang chờ. Bạn có thể crawl website để thu thập thêm nội dung.</p>}
          {!indexStatus && <p role="status">Chưa tải được số trang. Đang chờ cập nhật...</p>}
          <button type="button" className="sites-primary-button" disabled={busy || isCrawling || !indexStatus?.pending_pages} onClick={() => void action("index-pending")}>
            {busy ? "Đang gửi yêu cầu..." : `Lập chỉ mục tất cả${indexStatus?.pending_pages ? ` ${indexStatus.pending_pages} trang` : " trang còn chờ"}`}
          </button>
        </section>
      </div>
      <section>
        <h3>Lịch sử crawl</h3>
        <div className="crawl-history-table">
          <table>
            <thead>
              <tr>
                <th>Thời gian</th>
                <th>Loại</th>
                <th>Đã quét</th>
                <th>Đã lập chỉ mục</th>
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
                      <td>{({ manual: "Thủ công", incremental: "Trang mới", scheduled: "Tự động", index_pending: "Lập chỉ mục" } as Record<string, string>)[item.trigger] || item.trigger}</td>
                      <td>
                        {item.pages_crawled || 0}
                      </td>
                      <td>{item.pages_indexed || 0}</td>
                      <td>
                        <span className={`crawl-history-status ${item.status}`}>
                          {({ queued: "Đang chờ", running: "Đang chạy", completed: "Hoàn tất", failed: "Thất bại", cancelled: "Đã dừng" } as Record<string, string>)[item.status] || item.status}
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
                        <td colSpan={6}>
                          {item.errors[item.errors.length - 1]}
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                ))
              ) : (
                <tr>
                  <td colSpan={6}>Chưa có lịch sử crawl.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

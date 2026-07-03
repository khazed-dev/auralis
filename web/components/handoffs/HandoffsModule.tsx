"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { API_BASE, authFetch, DEV_AUTH_ENABLED, getStoredUser } from "@/lib/auth";

type HandoffStatus = "pending" | "active" | "resolved" | "abandoned";

type HandoffItem = {
  handoff_id: string;
  session_id: string;
  site_id: string;
  status: HandoffStatus;
  visitor_email?: string | null;
  visitor_name?: string | null;
  reason: string;
  message_count: number;
  last_message_preview: string;
  assigned_agent_name?: string | null;
  created_at: string;
  updated_at: string;
  wait_time_seconds: number;
};

type HandoffMessage = {
  id?: string;
  role: "visitor" | "agent" | "user" | "assistant";
  content: string;
  sender_name?: string | null;
  timestamp?: string;
};

type HandoffDetail = HandoffItem & {
  ai_summary?: string | null;
  ai_conversation?: HandoffMessage[];
  messages: HandoffMessage[];
};

type SiteOption = { site_id: string; name?: string | null; url: string };

const statusLabels: Record<HandoffStatus, string> = {
  pending: "Đang chờ",
  active: "Đang hỗ trợ",
  resolved: "Đã giải quyết",
  abandoned: "Khách đã rời",
};

const reasonLabels: Record<string, string> = {
  user_request: "Khách yêu cầu",
  low_confidence: "AI thiếu tự tin",
  ai_suggested: "AI đề xuất",
};

const demoQueue: HandoffDetail[] = [
  {
    handoff_id: "demo-handoff-1",
    session_id: "demo-session-1",
    site_id: "demo-auralis",
    status: "pending",
    visitor_name: "Trần Anh",
    visitor_email: "anh.tran@example.com",
    reason: "user_request",
    message_count: 1,
    last_message_preview: "Tôi cần tư vấn gói phù hợp cho doanh nghiệp.",
    assigned_agent_name: null,
    created_at: new Date(Date.now() - 8 * 60_000).toISOString(),
    updated_at: new Date(Date.now() - 2 * 60_000).toISOString(),
    wait_time_seconds: 8 * 60,
    ai_summary:
      "Khách hàng đang tìm hiểu giải pháp cho doanh nghiệp có nhiều website và muốn được tư vấn về chi phí.",
    ai_conversation: [
      {
        role: "user",
        content: "Bên tôi có 5 website, nên chọn gói nào?",
        timestamp: new Date(Date.now() - 12 * 60_000).toISOString(),
      },
      {
        role: "assistant",
        content: "Tôi có thể giới thiệu tổng quan, hoặc kết nối bạn với chuyên viên tư vấn.",
        timestamp: new Date(Date.now() - 11 * 60_000).toISOString(),
      },
    ],
    messages: [
      {
        id: "demo-message-1",
        role: "visitor",
        sender_name: "Trần Anh",
        content: "Tôi cần tư vấn gói phù hợp cho doanh nghiệp.",
        timestamp: new Date(Date.now() - 2 * 60_000).toISOString(),
      },
    ],
  },
  {
    handoff_id: "demo-handoff-2",
    session_id: "demo-session-2",
    site_id: "demo-store",
    status: "active",
    visitor_name: "Khách #8821",
    visitor_email: null,
    reason: "low_confidence",
    message_count: 3,
    last_message_preview: "Bạn cho mình xin mã đơn hàng nhé.",
    assigned_agent_name: "Auralis Local",
    created_at: new Date(Date.now() - 28 * 60_000).toISOString(),
    updated_at: new Date(Date.now() - 3 * 60_000).toISOString(),
    wait_time_seconds: 0,
    ai_summary: "Khách cần kiểm tra trạng thái giao hàng nhưng chưa cung cấp mã đơn.",
    ai_conversation: [],
    messages: [
      {
        id: "m1",
        role: "visitor",
        sender_name: "Khách #8821",
        content: "Đơn hàng của mình bao giờ tới?",
        timestamp: new Date(Date.now() - 7 * 60_000).toISOString(),
      },
      {
        id: "m2",
        role: "agent",
        sender_name: "Auralis Local",
        content: "Mình sẽ kiểm tra giúp bạn.",
        timestamp: new Date(Date.now() - 5 * 60_000).toISOString(),
      },
      {
        id: "m3",
        role: "agent",
        sender_name: "Auralis Local",
        content: "Bạn cho mình xin mã đơn hàng nhé.",
        timestamp: new Date(Date.now() - 3 * 60_000).toISOString(),
      },
    ],
  },
];

function visitorName(handoff: HandoffItem) {
  return handoff.visitor_name || handoff.visitor_email || "Khách truy cập";
}

function waitTime(seconds: number) {
  if (seconds < 60) return "< 1 phút";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} phút`;
  return `${Math.floor(seconds / 3600)} giờ`;
}

async function apiError(response: Response, fallback: string) {
  const data = (await response.json().catch(() => ({}))) as { detail?: string };
  return data.detail || fallback;
}

export function HandoffsModule() {
  const [queue, setQueue] = useState<HandoffItem[]>([]);
  const [detail, setDetail] = useState<HandoffDetail | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sites, setSites] = useState<SiteOption[]>([]);
  const [siteId, setSiteId] = useState("all");
  const [status, setStatus] = useState("");
  const [pendingCount, setPendingCount] = useState(0);
  const [activeCount, setActiveCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  const loadQueue = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      if (DEV_AUTH_ENABLED) {
        const filtered = demoQueue.filter(
          (item) =>
            (siteId === "all" || item.site_id === siteId) &&
            (!status || item.status === status),
        );
        setQueue(filtered);
        setPendingCount(demoQueue.filter((item) => item.status === "pending").length);
        setActiveCount(demoQueue.filter((item) => item.status === "active").length);
        setSelectedId((current) =>
          current && filtered.some((item) => item.handoff_id === current)
            ? current
            : filtered[0]?.handoff_id ?? null,
        );
        return;
      }
      const params = new URLSearchParams({ page: "1", limit: "50" });
      if (status) params.set("status", status);
      const response = await authFetch(
        `${API_BASE}/sites/${siteId}/handoff/queue?${params}`,
      );
      if (!response.ok) throw new Error(await apiError(response, "Không thể tải hàng chờ."));
      const data = (await response.json()) as {
        handoffs: HandoffItem[];
        pending_count: number;
        active_count: number;
      };
      setQueue(data.handoffs);
      setPendingCount(data.pending_count);
      setActiveCount(data.active_count);
      setSelectedId((current) =>
        current && data.handoffs.some((item) => item.handoff_id === current)
          ? current
          : data.handoffs[0]?.handoff_id ?? null,
      );
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Không thể tải hàng chờ.");
    } finally {
      setLoading(false);
    }
  }, [siteId, status]);

  const loadDetail = useCallback(async (handoffId: string, quiet = false) => {
    if (!quiet) setDetailLoading(true);
    try {
      if (DEV_AUTH_ENABLED) {
        setDetail(demoQueue.find((item) => item.handoff_id === handoffId) ?? null);
        return;
      }
      const response = await authFetch(`${API_BASE}/handoff/${handoffId}/full`);
      if (!response.ok) throw new Error(await apiError(response, "Không thể tải phiên hỗ trợ."));
      setDetail((await response.json()) as HandoffDetail);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Không thể tải phiên hỗ trợ.");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    const frame = requestAnimationFrame(() => void loadQueue());
    const timer = window.setInterval(() => void loadQueue(true), 5000);
    return () => {
      cancelAnimationFrame(frame);
      clearInterval(timer);
    };
  }, [loadQueue]);

  useEffect(() => {
    const frame = requestAnimationFrame(async () => {
      if (DEV_AUTH_ENABLED) {
        setSites([
          { site_id: "demo-auralis", name: "Auralis Demo", url: "" },
          { site_id: "demo-store", name: "Cửa hàng mẫu", url: "" },
        ]);
        return;
      }
      const response = await authFetch(`${API_BASE}/sites`);
      if (response.ok) setSites((await response.json()) as SiteOption[]);
    });
    return () => cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    if (!selectedId) {
      const frame = requestAnimationFrame(() => setDetail(null));
      return () => cancelAnimationFrame(frame);
    }
    const frame = requestAnimationFrame(() => void loadDetail(selectedId));
    const timer = window.setInterval(() => void loadDetail(selectedId, true), 3000);
    return () => {
      cancelAnimationFrame(frame);
      clearInterval(timer);
    };
  }, [loadDetail, selectedId]);

  async function updateStatus(nextStatus: "active" | "resolved") {
    if (!detail) return;
    try {
      if (!DEV_AUTH_ENABLED) {
        const response = await authFetch(`${API_BASE}/handoff/${detail.handoff_id}/status`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: nextStatus }),
        });
        if (!response.ok) throw new Error(await apiError(response, "Không thể cập nhật phiên."));
      }
      const agent = getStoredUser();
      setDetail({
        ...detail,
        status: nextStatus,
        assigned_agent_name:
          nextStatus === "active"
            ? detail.assigned_agent_name || agent?.name || agent?.email
            : detail.assigned_agent_name,
      });
      setQueue((current) =>
        current.map((item) =>
          item.handoff_id === detail.handoff_id ? { ...item, status: nextStatus } : item,
        ),
      );
      void loadQueue(true);
    } catch (statusError) {
      setError(statusError instanceof Error ? statusError.message : "Không thể cập nhật phiên.");
    }
  }

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!detail) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const content = String(data.get("content") ?? "").trim();
    if (!content) return;
    setSending(true);
    try {
      const localMessage: HandoffMessage = {
        id: `local-${Date.now()}`,
        role: "agent",
        sender_name: getStoredUser()?.name || "Nhân viên hỗ trợ",
        content,
        timestamp: new Date().toISOString(),
      };
      if (!DEV_AUTH_ENABLED) {
        const response = await authFetch(
          `${API_BASE}/handoff/${detail.handoff_id}/agent-message`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content }),
          },
        );
        if (!response.ok) throw new Error(await apiError(response, "Không thể gửi tin nhắn."));
      }
      setDetail({
        ...detail,
        status: "active",
        messages: [...(detail.messages || []), localMessage],
      });
      form.reset();
      setTimeout(() => void loadDetail(detail.handoff_id, true), 400);
    } catch (sendError) {
      setError(sendError instanceof Error ? sendError.message : "Không thể gửi tin nhắn.");
    } finally {
      setSending(false);
    }
  }

  const siteName = (id: string) =>
    sites.find((site) => site.site_id === id)?.name || id;

  return (
    <main className="dashboard-content handoffs-module">
      <div className="handoffs-title-row">
        <div className="dashboard-page-heading">
          <span><Icon name="headset" /></span>
          <div><h1>Handoff</h1><p>Tiếp nhận và hỗ trợ trực tiếp khi khách hàng cần nhân viên.</p></div>
        </div>
        <div className="handoff-counts">
          <span className="pending"><strong>{pendingCount}</strong>Đang chờ</span>
          <span className="active"><strong>{activeCount}</strong>Đang hỗ trợ</span>
        </div>
      </div>

      {error && <div className="sites-alert"><span>{error}</span><button onClick={() => setError("")}>Đóng</button></div>}

      <div className="handoff-workspace">
        <section className="handoff-queue">
          <div className="handoff-filters">
            <select value={siteId} onChange={(event) => setSiteId(event.target.value)}>
              <option value="all">Tất cả website</option>
              {sites.map((site) => <option key={site.site_id} value={site.site_id}>{site.name || site.url}</option>)}
            </select>
            <select value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="">Đang chờ và hoạt động</option>
              <option value="pending">Chỉ đang chờ</option>
              <option value="active">Chỉ đang hỗ trợ</option>
              <option value="resolved">Đã giải quyết</option>
              <option value="abandoned">Khách đã rời</option>
            </select>
          </div>
          <div className="handoff-list">
            {loading ? (
              <div className="handoff-empty"><span className="dashboard-spinner" />Đang tải hàng chờ...</div>
            ) : queue.length === 0 ? (
              <div className="handoff-empty"><Icon name="headset" /><strong>Không có yêu cầu handoff</strong><p>Yêu cầu từ khách hàng sẽ xuất hiện tại đây.</p></div>
            ) : queue.map((item) => (
              <button
                key={item.handoff_id}
                className={`handoff-item ${selectedId === item.handoff_id ? "active" : ""}`}
                onClick={() => setSelectedId(item.handoff_id)}
              >
                <span className="handoff-avatar">{visitorName(item).charAt(0).toUpperCase()}</span>
                <span className="handoff-item-copy">
                  <span><strong>{visitorName(item)}</strong><em className={item.status}>{statusLabels[item.status]}</em></span>
                  <small>{item.last_message_preview || reasonLabels[item.reason] || item.reason}</small>
                  <span className="handoff-meta"><span>{siteName(item.site_id)}</span><span>Chờ {waitTime(item.wait_time_seconds)}</span></span>
                </span>
              </button>
            ))}
          </div>
        </section>

        <section className="handoff-detail">
          {!selectedId ? (
            <div className="handoff-empty handoff-detail-empty"><Icon name="message" /><strong>Chọn một yêu cầu hỗ trợ</strong><p>Nội dung trò chuyện trực tiếp sẽ hiển thị tại đây.</p></div>
          ) : detailLoading || !detail ? (
            <div className="handoff-empty handoff-detail-empty"><span className="dashboard-spinner" />Đang tải phiên hỗ trợ...</div>
          ) : (
            <>
              <header className="handoff-detail-header">
                <div>
                  <span className="handoff-avatar">{visitorName(detail).charAt(0).toUpperCase()}</span>
                  <span><strong>{visitorName(detail)}</strong><small>{detail.visitor_email || siteName(detail.site_id)}</small></span>
                </div>
                <div>
                  {detail.status === "pending" && <button className="handoff-claim" onClick={() => void updateStatus("active")}>Nhận hỗ trợ</button>}
                  {detail.status === "active" && <button className="handoff-resolve" onClick={() => void updateStatus("resolved")}>Kết thúc</button>}
                </div>
              </header>

              {detail.ai_summary && (
                <div className="handoff-summary"><span>AI</span><div><strong>Tóm tắt hội thoại</strong><p>{detail.ai_summary}</p></div></div>
              )}

              <div className="handoff-messages">
                {[...(detail.ai_conversation || []), ...(detail.messages || [])].map((message, index) => {
                  const isAgent = ["agent", "assistant"].includes(message.role);
                  return (
                    <article className={isAgent ? "agent" : "visitor"} key={message.id || `${message.timestamp}-${index}`}>
                      <span>{message.sender_name || (isAgent ? "Auralis" : visitorName(detail))}</span>
                      <p>{message.content}</p>
                      {message.timestamp && <time>{new Date(message.timestamp).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}</time>}
                    </article>
                  );
                })}
              </div>

              <form className="handoff-composer" onSubmit={sendMessage}>
                <input
                  name="content"
                  placeholder={
                    detail.status === "resolved" || detail.status === "abandoned"
                      ? "Phiên hỗ trợ đã kết thúc"
                      : "Nhập tin nhắn cho khách hàng..."
                  }
                  disabled={detail.status === "resolved" || detail.status === "abandoned" || sending}
                  autoComplete="off"
                />
                <button disabled={detail.status === "resolved" || detail.status === "abandoned" || sending} aria-label="Gửi tin nhắn">
                  <Icon name="send" />
                </button>
              </form>
            </>
          )}
        </section>
      </div>
    </main>
  );
}

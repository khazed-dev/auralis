"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { API_BASE, authFetch, DEV_AUTH_ENABLED } from "@/lib/auth";

type ConversationStatus = "open" | "resolved" | "closed";

type ConversationSummary = {
  session_id: string;
  site_id?: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
  first_message: string;
  status: ConversationStatus;
  priority: "high" | "medium" | "low";
  tags: string[];
  unread: boolean;
  visitor_name?: string | null;
  visitor_email?: string | null;
  satisfaction_rating?: number | null;
};

type Message = {
  role: string;
  content: string;
  timestamp: string;
  sources: Array<{ title?: string; url?: string; source?: string }>;
  response_time_ms?: number | null;
};

type ConversationDetail = ConversationSummary & {
  messages: Message[];
  stats: {
    message_count: number;
    avg_response_time_ms: number;
    positive_feedback: number;
    negative_feedback: number;
  };
  page_url?: string | null;
};

type SiteOption = { site_id: string; name?: string | null; url: string };

const statusLabels: Record<ConversationStatus, string> = {
  open: "Đang mở",
  resolved: "Đã giải quyết",
  closed: "Đã đóng",
};

const demoConversations: ConversationDetail[] = [
  {
    session_id: "demo-conversation-1",
    site_id: "demo-auralis",
    created_at: new Date(Date.now() - 42 * 60_000).toISOString(),
    updated_at: new Date(Date.now() - 4 * 60_000).toISOString(),
    message_count: 4,
    first_message: "Auralis có thể học dữ liệu từ website của tôi không?",
    status: "open",
    priority: "medium",
    tags: ["sản phẩm"],
    unread: true,
    visitor_name: "Khách truy cập #1248",
    visitor_email: "khach@example.com",
    satisfaction_rating: 5,
    page_url: "https://auralisai.duckdns.org",
    stats: {
      message_count: 4,
      avg_response_time_ms: 1240,
      positive_feedback: 1,
      negative_feedback: 0,
    },
    messages: [
      {
        role: "user",
        content: "Auralis có thể học dữ liệu từ website của tôi không?",
        timestamp: new Date(Date.now() - 42 * 60_000).toISOString(),
        sources: [],
      },
      {
        role: "assistant",
        content:
          "Có. Auralis sẽ thu thập nội dung công khai trên website, lập chỉ mục và sử dụng chúng để trả lời khách hàng.",
        timestamp: new Date(Date.now() - 41 * 60_000).toISOString(),
        response_time_ms: 1180,
        sources: [{ title: "Thu thập dữ liệu website", url: "https://example.com/docs" }],
      },
      {
        role: "user",
        content: "Tôi có thể tải thêm tài liệu PDF không?",
        timestamp: new Date(Date.now() - 7 * 60_000).toISOString(),
        sources: [],
      },
      {
        role: "assistant",
        content:
          "Bạn có thể bổ sung PDF, Word và các tệp văn bản vào kho tri thức của từng website.",
        timestamp: new Date(Date.now() - 4 * 60_000).toISOString(),
        response_time_ms: 1300,
        sources: [],
      },
    ],
  },
  {
    session_id: "demo-conversation-2",
    site_id: "demo-store",
    created_at: new Date(Date.now() - 26 * 60 * 60_000).toISOString(),
    updated_at: new Date(Date.now() - 24 * 60 * 60_000).toISOString(),
    message_count: 3,
    first_message: "Chính sách đổi trả sản phẩm như thế nào?",
    status: "resolved",
    priority: "low",
    tags: ["chính sách"],
    unread: false,
    visitor_name: "Nguyễn Minh",
    visitor_email: null,
    satisfaction_rating: 4,
    stats: {
      message_count: 3,
      avg_response_time_ms: 940,
      positive_feedback: 1,
      negative_feedback: 0,
    },
    messages: [
      {
        role: "user",
        content: "Chính sách đổi trả sản phẩm như thế nào?",
        timestamp: new Date(Date.now() - 26 * 60 * 60_000).toISOString(),
        sources: [],
      },
      {
        role: "assistant",
        content:
          "Bạn có thể đổi sản phẩm trong vòng 7 ngày nếu sản phẩm còn nguyên trạng và đầy đủ phụ kiện.",
        timestamp: new Date(Date.now() - 26 * 60 * 60_000 + 940).toISOString(),
        sources: [{ title: "Chính sách đổi trả" }],
      },
      {
        role: "user",
        content: "Cảm ơn bạn.",
        timestamp: new Date(Date.now() - 24 * 60 * 60_000).toISOString(),
        sources: [],
      },
    ],
  },
];

function relativeTime(value: string) {
  const delta = Date.now() - new Date(value).getTime();
  const minutes = Math.max(1, Math.floor(delta / 60_000));
  if (minutes < 60) return `${minutes} phút trước`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} giờ trước`;
  return `${Math.floor(hours / 24)} ngày trước`;
}

function visitorLabel(conversation: ConversationSummary) {
  return conversation.visitor_name || conversation.visitor_email || "Khách truy cập";
}

async function responseError(response: Response, fallback: string) {
  const data = (await response.json().catch(() => ({}))) as { detail?: string };
  return data.detail || fallback;
}

export function ConversationsModule() {
  const [items, setItems] = useState<ConversationSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [sites, setSites] = useState<SiteOption[]>([]);
  const [siteId, setSiteId] = useState("");
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);

  const loadConversations = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      if (DEV_AUTH_ENABLED) {
        const filtered = demoConversations.filter(
          (item) =>
            (!siteId || item.site_id === siteId) &&
            (!status || item.status === status) &&
            (!activeQuery ||
              item.first_message.toLowerCase().includes(activeQuery.toLowerCase())),
        );
        setItems(filtered);
        setTotal(filtered.length);
        setTotalPages(1);
        setSelectedId((current) =>
          current && filtered.some((item) => item.session_id === current)
            ? current
            : filtered[0]?.session_id ?? null,
        );
        return;
      }

      const params = new URLSearchParams({
        page: String(page),
        limit: "20",
      });
      if (siteId) params.set("site_id", siteId);
      if (status) params.set("status", status);
      const path = activeQuery ? "/conversations/search" : "/conversations";
      if (activeQuery) params.set("q", activeQuery);

      const response = await authFetch(`${API_BASE}${path}?${params}`);
      if (!response.ok) {
        throw new Error(await responseError(response, "Không thể tải hội thoại."));
      }
      const data = (await response.json()) as {
        conversations: ConversationSummary[];
        total: number;
        total_pages: number;
      };
      setItems(data.conversations);
      setTotal(data.total);
      setTotalPages(Math.max(1, data.total_pages));
      setSelectedId((current) =>
        current && data.conversations.some((item) => item.session_id === current)
          ? current
          : data.conversations[0]?.session_id ?? null,
      );
    } catch (loadError) {
      setError(
        loadError instanceof Error ? loadError.message : "Không thể tải hội thoại.",
      );
    } finally {
      setLoading(false);
    }
  }, [activeQuery, page, siteId, status]);

  useEffect(() => {
    const frame = requestAnimationFrame(() => void loadConversations());
    return () => cancelAnimationFrame(frame);
  }, [loadConversations]);

  useEffect(() => {
    const frame = requestAnimationFrame(async () => {
      if (DEV_AUTH_ENABLED) {
        setSites([
          { site_id: "demo-auralis", name: "Auralis Demo", url: "https://auralis.ai" },
          { site_id: "demo-store", name: "Cửa hàng mẫu", url: "https://store.example.com" },
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
    const frame = requestAnimationFrame(async () => {
      setDetailLoading(true);
      try {
        if (DEV_AUTH_ENABLED) {
          setDetail(
            demoConversations.find((item) => item.session_id === selectedId) ?? null,
          );
          return;
        }
        const response = await authFetch(`${API_BASE}/conversations/${selectedId}`);
        if (!response.ok) {
          throw new Error(await responseError(response, "Không thể tải nội dung."));
        }
        setDetail((await response.json()) as ConversationDetail);
        void authFetch(`${API_BASE}/conversations/${selectedId}/read`, {
          method: "PATCH",
        });
        setItems((current) =>
          current.map((item) =>
            item.session_id === selectedId ? { ...item, unread: false } : item,
          ),
        );
      } catch (detailError) {
        setError(
          detailError instanceof Error
            ? detailError.message
            : "Không thể tải nội dung hội thoại.",
        );
      } finally {
        setDetailLoading(false);
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [selectedId]);

  function handleSearch(event: FormEvent) {
    event.preventDefault();
    setPage(1);
    setActiveQuery(query.trim());
  }

  async function changeStatus(nextStatus: ConversationStatus) {
    if (!detail) return;
    if (!DEV_AUTH_ENABLED) {
      const response = await authFetch(
        `${API_BASE}/conversations/${detail.session_id}/status`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: nextStatus }),
        },
      );
      if (!response.ok) {
        setError(await responseError(response, "Không thể cập nhật trạng thái."));
        return;
      }
    }
    setDetail({ ...detail, status: nextStatus });
    setItems((current) =>
      current.map((item) =>
        item.session_id === detail.session_id
          ? { ...item, status: nextStatus }
          : item,
      ),
    );
  }

  return (
    <main className="dashboard-content conversations-module">
      <div className="dashboard-page-heading">
        <span><Icon name="message" /></span>
        <div>
          <h1>Hội thoại</h1>
          <p>Theo dõi nội dung trao đổi giữa khách hàng và trợ lý AI.</p>
        </div>
      </div>

      <div className="conversation-filters">
        <form onSubmit={handleSearch}>
          <Icon name="message" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Tìm trong nội dung hội thoại..."
          />
          {activeQuery && (
            <button
              type="button"
              onClick={() => {
                setQuery("");
                setActiveQuery("");
              }}
            >
              ×
            </button>
          )}
        </form>
        <select value={siteId} onChange={(event) => { setSiteId(event.target.value); setPage(1); }}>
          <option value="">Tất cả website</option>
          {sites.map((site) => (
            <option key={site.site_id} value={site.site_id}>
              {site.name || site.url}
            </option>
          ))}
        </select>
        <select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}>
          <option value="">Mọi trạng thái</option>
          <option value="open">Đang mở</option>
          <option value="resolved">Đã giải quyết</option>
          <option value="closed">Đã đóng</option>
        </select>
      </div>

      {error && <div className="sites-alert" role="alert"><span>{error}</span><button onClick={() => setError("")}>Đóng</button></div>}

      <div className="conversations-workspace">
        <section className="conversation-master">
          <div className="conversation-master-header">
            <strong>{total} hội thoại</strong>
            <button onClick={() => void loadConversations()} aria-label="Làm mới">↻</button>
          </div>
          <div className="conversation-list">
            {loading ? (
              <div className="conversation-empty"><span className="dashboard-spinner" />Đang tải hội thoại...</div>
            ) : items.length === 0 ? (
              <div className="conversation-empty"><Icon name="message" /><strong>Chưa có hội thoại</strong><p>Các cuộc trò chuyện sẽ xuất hiện tại đây.</p></div>
            ) : (
              items.map((item) => (
                <button
                  key={item.session_id}
                  className={`conversation-item ${selectedId === item.session_id ? "active" : ""}`}
                  onClick={() => setSelectedId(item.session_id)}
                >
                  <span className="conversation-avatar">
                    {visitorLabel(item).charAt(0).toUpperCase()}
                    {item.unread && <i />}
                  </span>
                  <span className="conversation-item-copy">
                    <span><strong>{visitorLabel(item)}</strong><time>{relativeTime(item.updated_at)}</time></span>
                    <small>{item.first_message || "Hội thoại mới"}</small>
                    <span className="conversation-item-meta">
                      <em className={item.status}>{statusLabels[item.status]}</em>
                      <span>{item.message_count} tin nhắn</span>
                    </span>
                  </span>
                </button>
              ))
            )}
          </div>
          {totalPages > 1 && (
            <div className="conversation-pagination">
              <button disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>Trước</button>
              <span>{page}/{totalPages}</span>
              <button disabled={page >= totalPages} onClick={() => setPage((value) => value + 1)}>Sau</button>
            </div>
          )}
        </section>

        <section className="conversation-detail">
          {!selectedId ? (
            <div className="conversation-detail-empty"><Icon name="message" /><h2>Chọn một hội thoại</h2><p>Nội dung trao đổi sẽ hiển thị tại đây.</p></div>
          ) : detailLoading || !detail ? (
            <div className="conversation-detail-empty"><span className="dashboard-spinner" />Đang tải nội dung...</div>
          ) : (
            <>
              <header className="conversation-detail-header">
                <div>
                  <span className="conversation-avatar">{visitorLabel(detail).charAt(0).toUpperCase()}</span>
                  <div><h2>{visitorLabel(detail)}</h2><p>{detail.visitor_email || `Phiên ${detail.session_id.slice(0, 12)}`}</p></div>
                </div>
                <select value={detail.status} onChange={(event) => void changeStatus(event.target.value as ConversationStatus)}>
                  <option value="open">Đang mở</option>
                  <option value="resolved">Đã giải quyết</option>
                  <option value="closed">Đã đóng</option>
                </select>
              </header>
              <div className="conversation-stats">
                <span><strong>{detail.stats.message_count}</strong>Tin nhắn</span>
                <span><strong>{(detail.stats.avg_response_time_ms / 1000).toFixed(1)} giây</strong>Phản hồi TB</span>
                <span><strong>{detail.satisfaction_rating ? `${detail.satisfaction_rating}/5` : "—"}</strong>Đánh giá</span>
              </div>
              <div className="conversation-messages">
                {detail.messages.map((message, index) => (
                  <article className={`conversation-message ${message.role}`} key={`${message.timestamp}-${index}`}>
                    <div>
                      <strong>{message.role === "user" ? visitorLabel(detail) : "Auralis AI"}</strong>
                      <time>{new Date(message.timestamp).toLocaleString("vi-VN")}</time>
                    </div>
                    <p>{message.content}</p>
                    {message.sources.length > 0 && (
                      <div className="message-sources">
                        <span>Nguồn tham khảo</span>
                        {message.sources.map((source, sourceIndex) =>
                          source.url ? (
                            <a href={source.url} target="_blank" rel="noreferrer" key={sourceIndex}>{source.title || source.source || "Tài liệu"} ↗</a>
                          ) : (
                            <em key={sourceIndex}>{source.title || source.source || "Tài liệu"}</em>
                          ),
                        )}
                      </div>
                    )}
                  </article>
                ))}
              </div>
            </>
          )}
        </section>
      </div>
    </main>
  );
}

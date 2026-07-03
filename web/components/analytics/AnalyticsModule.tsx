"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { API_BASE, authFetch, DEV_AUTH_ENABLED } from "@/lib/auth";

type Overview = {
  total_conversations: number;
  total_messages: number;
  messages_today: number;
  messages_this_week: number;
  avg_messages_per_conversation: number;
  total_feedback: number;
  positive_feedback: number;
  satisfaction_rate: number;
  active_sites: number;
  total_handoffs: number;
  resolved_handoffs: number;
  handoff_rate: number;
};

type Trend = {
  period: string;
  data: Array<{ date: string; conversations: number; messages: number }>;
  total_conversations: number;
  total_messages: number;
  change_percentage: number;
};

type Question = { question: string; count: number; percentage: number };
type Source = { url: string; title: string; citation_count: number; percentage: number };
type Recent = {
  session_id: string;
  site_id?: string | null;
  message_count: number;
  first_message: string;
  last_activity: string;
  has_feedback: boolean;
};
type SiteOption = { site_id: string; name?: string | null; url: string };

const demoOverview: Overview = {
  total_conversations: 1284,
  total_messages: 7936,
  messages_today: 186,
  messages_this_week: 1240,
  avg_messages_per_conversation: 6.2,
  total_feedback: 412,
  positive_feedback: 379,
  satisfaction_rate: 92,
  active_sites: 4,
  total_handoffs: 96,
  resolved_handoffs: 88,
  handoff_rate: 7.5,
};

function demoTrend(days: number): Trend {
  const data = Array.from({ length: days }, (_, index) => {
    const date = new Date();
    date.setDate(date.getDate() - (days - index - 1));
    const wave = Math.sin(index / 2.2) * 9;
    const conversations = Math.max(3, Math.round(22 + wave + (index % 5) * 2));
    return {
      date: date.toISOString().slice(0, 10),
      conversations,
      messages: conversations * (5 + (index % 3)),
    };
  });
  return {
    period: `${days}d`,
    data,
    total_conversations: data.reduce((sum, item) => sum + item.conversations, 0),
    total_messages: data.reduce((sum, item) => sum + item.messages, 0),
    change_percentage: 18.4,
  };
}

const demoQuestions: Question[] = [
  { question: "Làm thế nào để tích hợp chatbot vào website?", count: 86, percentage: 28 },
  { question: "Auralis hỗ trợ những loại tài liệu nào?", count: 64, percentage: 21 },
  { question: "Tôi có thể dùng API model riêng không?", count: 51, percentage: 17 },
  { question: "Cách chuyển hội thoại cho nhân viên?", count: 38, percentage: 12 },
  { question: "Dữ liệu được cập nhật bao lâu một lần?", count: 29, percentage: 9 },
];

const demoSources: Source[] = [
  { url: "https://example.com/docs/integration", title: "Hướng dẫn tích hợp", citation_count: 124, percentage: 36 },
  { url: "https://example.com/pricing", title: "Bảng giá Auralis", citation_count: 88, percentage: 26 },
  { url: "https://example.com/security", title: "Bảo mật dữ liệu", citation_count: 72, percentage: 21 },
  { url: "https://example.com/handoff", title: "Human Handoff", citation_count: 43, percentage: 13 },
];

const demoRecent: Recent[] = [
  { session_id: "demo-1", site_id: "demo-auralis", message_count: 8, first_message: "Auralis có thể học dữ liệu từ website không?", last_activity: new Date(Date.now() - 8 * 60_000).toISOString(), has_feedback: true },
  { session_id: "demo-2", site_id: "demo-store", message_count: 5, first_message: "Chính sách đổi trả sản phẩm như thế nào?", last_activity: new Date(Date.now() - 43 * 60_000).toISOString(), has_feedback: false },
  { session_id: "demo-3", site_id: "demo-auralis", message_count: 11, first_message: "Tư vấn giúp tôi gói dành cho doanh nghiệp", last_activity: new Date(Date.now() - 2 * 60 * 60_000).toISOString(), has_feedback: true },
];

function compactNumber(value: number) {
  return new Intl.NumberFormat("vi-VN", { notation: value >= 1000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(value);
}

function relativeTime(value: string) {
  const minutes = Math.max(1, Math.floor((Date.now() - new Date(value).getTime()) / 60_000));
  if (minutes < 60) return `${minutes} phút trước`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)} giờ trước`;
  return `${Math.floor(minutes / 1440)} ngày trước`;
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await authFetch(url);
  if (!response.ok) {
    const data = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(data.detail || "Không thể tải dữ liệu phân tích.");
  }
  return response.json() as Promise<T>;
}

export function AnalyticsModule() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [trend, setTrend] = useState<Trend | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [recent, setRecent] = useState<Recent[]>([]);
  const [sites, setSites] = useState<SiteOption[]>([]);
  const [siteId, setSiteId] = useState("");
  const [period, setPeriod] = useState<"7d" | "30d">("7d");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadAnalytics = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      if (DEV_AUTH_ENABLED) {
        setOverview(demoOverview);
        setTrend(demoTrend(period === "7d" ? 7 : 30));
        setQuestions(demoQuestions);
        setSources(demoSources);
        setRecent(demoRecent);
        setSites([
          { site_id: "demo-auralis", name: "Auralis Demo", url: "" },
          { site_id: "demo-store", name: "Cửa hàng mẫu", url: "" },
        ]);
        return;
      }
      const siteParam = siteId ? `&site_id=${encodeURIComponent(siteId)}` : "";
      const overviewParam = siteId ? `?site_id=${encodeURIComponent(siteId)}` : "";
      const [overviewData, trendData, questionsData, sourcesData, recentData, sitesData] =
        await Promise.all([
          fetchJson<Overview>(`${API_BASE}/analytics/overview${overviewParam}`),
          fetchJson<Trend>(`${API_BASE}/analytics/conversations?period=${period}${siteParam}`),
          fetchJson<Question[]>(`${API_BASE}/analytics/popular-questions?limit=5${siteParam}`),
          fetchJson<Source[]>(`${API_BASE}/analytics/sources-used?limit=5${siteParam}`),
          fetchJson<Recent[]>(`${API_BASE}/analytics/recent-conversations?limit=5${siteParam}`),
          fetchJson<SiteOption[]>(`${API_BASE}/sites`),
        ]);
      setOverview(overviewData);
      setTrend(trendData);
      setQuestions(questionsData);
      setSources(sourcesData);
      setRecent(recentData);
      setSites(sitesData);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Không thể tải dữ liệu phân tích.");
    } finally {
      setLoading(false);
    }
  }, [period, siteId]);

  useEffect(() => {
    const frame = requestAnimationFrame(() => void loadAnalytics());
    return () => cancelAnimationFrame(frame);
  }, [loadAnalytics]);

  const chart = useMemo(() => {
    if (!trend?.data.length) return { conversationPoints: "", messagePoints: "", max: 1 };
    const max = Math.max(...trend.data.flatMap((item) => [item.conversations, item.messages]), 1);
    const width = 700;
    const height = 190;
    const points = (key: "conversations" | "messages") =>
      trend.data
        .map((item, index) => {
          const x = trend.data.length === 1 ? width / 2 : (index / (trend.data.length - 1)) * width;
          const y = height - (item[key] / max) * (height - 18);
          return `${x.toFixed(1)},${y.toFixed(1)}`;
        })
        .join(" ");
    return { conversationPoints: points("conversations"), messagePoints: points("messages"), max };
  }, [trend]);

  const kpis = overview
    ? [
        { label: "Tổng hội thoại", value: compactNumber(overview.total_conversations), note: `${overview.messages_today} tin nhắn hôm nay`, icon: "message" as const },
        { label: "Tổng tin nhắn", value: compactNumber(overview.total_messages), note: `TB ${overview.avg_messages_per_conversation} tin/hội thoại`, icon: "chart" as const },
        { label: "Mức độ hài lòng", value: `${overview.satisfaction_rate}%`, note: `${overview.positive_feedback}/${overview.total_feedback} phản hồi tích cực`, icon: "sparkles" as const },
        { label: "Tỷ lệ handoff", value: `${overview.handoff_rate}%`, note: `${overview.resolved_handoffs}/${overview.total_handoffs} đã xử lý`, icon: "headset" as const },
      ]
    : [];

  return (
    <main className="dashboard-content analytics-module">
      <div className="analytics-title-row">
        <div className="dashboard-page-heading">
          <span><Icon name="chart" /></span>
          <div><h1>Phân tích</h1><p>Theo dõi hiệu quả hỗ trợ và hành vi khách hàng.</p></div>
        </div>
        <div className="analytics-controls">
          <select value={siteId} onChange={(event) => setSiteId(event.target.value)}>
            <option value="">Tất cả website</option>
            {sites.map((site) => <option key={site.site_id} value={site.site_id}>{site.name || site.url}</option>)}
          </select>
          <div><button className={period === "7d" ? "active" : ""} onClick={() => setPeriod("7d")}>7 ngày</button><button className={period === "30d" ? "active" : ""} onClick={() => setPeriod("30d")}>30 ngày</button></div>
        </div>
      </div>

      {error && <div className="sites-alert"><span>{error}</span><button onClick={() => void loadAnalytics()}>Thử lại</button></div>}

      {loading || !overview || !trend ? (
        <div className="analytics-loading"><span className="dashboard-spinner" />Đang tổng hợp dữ liệu...</div>
      ) : (
        <>
          <section className="analytics-kpis">
            {kpis.map((kpi) => (
              <article key={kpi.label}>
                <span><Icon name={kpi.icon} /></span>
                <div><small>{kpi.label}</small><strong>{kpi.value}</strong><p>{kpi.note}</p></div>
              </article>
            ))}
          </section>

          <section className="analytics-card analytics-trend">
            <header>
              <div><h2>Xu hướng tương tác</h2><p>Hội thoại và tin nhắn trong {period === "7d" ? "7" : "30"} ngày qua</p></div>
              <div className="analytics-legend"><span className="conversations">Hội thoại</span><span className="messages">Tin nhắn</span></div>
            </header>
            <div className="analytics-chart">
              <svg viewBox="0 0 700 210" role="img" aria-label="Biểu đồ xu hướng hội thoại và tin nhắn">
                {[0, 1, 2, 3, 4].map((line) => <line key={line} x1="0" x2="700" y1={10 + line * 45} y2={10 + line * 45} />)}
                <polyline className="messages" points={chart.messagePoints} />
                <polyline className="conversations" points={chart.conversationPoints} />
              </svg>
              <div className="analytics-chart-labels">
                {trend.data.filter((_, index) => index % Math.max(1, Math.ceil(trend.data.length / 7)) === 0).map((item) => (
                  <span key={item.date}>{new Date(`${item.date}T00:00:00`).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" })}</span>
                ))}
              </div>
            </div>
            <footer>
              <span><strong>{compactNumber(trend.total_conversations)}</strong> hội thoại</span>
              <span><strong>{compactNumber(trend.total_messages)}</strong> tin nhắn</span>
              <span className={trend.change_percentage >= 0 ? "positive" : "negative"}><strong>{trend.change_percentage >= 0 ? "+" : ""}{trend.change_percentage}%</strong> so với kỳ trước</span>
            </footer>
          </section>

          <div className="analytics-grid">
            <section className="analytics-card analytics-ranked">
              <header><div><h2>Câu hỏi phổ biến</h2><p>Những nội dung khách hàng quan tâm nhất</p></div></header>
              {questions.length ? questions.map((item, index) => (
                <div className="analytics-rank-row" key={`${item.question}-${index}`}>
                  <span>{index + 1}</span><div><strong>{item.question}</strong><i><b style={{ width: `${item.percentage}%` }} /></i></div><small>{item.count}</small>
                </div>
              )) : <p className="analytics-empty">Chưa có dữ liệu câu hỏi.</p>}
            </section>

            <section className="analytics-card analytics-ranked">
              <header><div><h2>Nguồn được trích dẫn</h2><p>Tài liệu hỗ trợ nhiều câu trả lời nhất</p></div></header>
              {sources.length ? sources.map((item, index) => (
                <div className="analytics-rank-row" key={item.url}>
                  <span>{index + 1}</span><div><a href={item.url} target="_blank" rel="noreferrer">{item.title}</a><i><b style={{ width: `${item.percentage}%` }} /></i></div><small>{item.citation_count}</small>
                </div>
              )) : <p className="analytics-empty">Chưa có dữ liệu nguồn.</p>}
            </section>
          </div>

          <section className="analytics-card analytics-recent">
            <header><div><h2>Hội thoại gần đây</h2><p>Các tương tác mới nhất trên toàn bộ website</p></div></header>
            <div className="analytics-recent-list">
              {recent.length ? recent.map((item) => (
                <a href={`/dashboard/conversations`} key={item.session_id}>
                  <span><Icon name="message" /></span>
                  <div><strong>{item.first_message || "Hội thoại mới"}</strong><small>{item.message_count} tin nhắn · {relativeTime(item.last_activity)}</small></div>
                  {item.has_feedback && <em>Đã phản hồi</em>}
                </a>
              )) : <p className="analytics-empty">Chưa có hội thoại.</p>}
            </div>
          </section>
        </>
      )}
    </main>
  );
}

"use client";

import { useEffect, useState } from "react";
import { API_BASE, authFetch } from "@/lib/auth";

type Resource = { used: number; limit: number | null; remaining: number | null; percent: number };
type Summary = {
  subscription: { status: string; expires_at?: string | null };
  plan: { key: string; name: string };
  period: string;
  resources: Record<string, Resource>;
};

const labels: Record<string, string> = {
  sites: "Website", members: "Thành viên", messages: "Tin nhắn AI", crawl_pages: "Trang crawl",
};

export function SubscriptionModule() {
  const [data, setData] = useState<Summary | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    authFetch(`${API_BASE}/subscriptions/me`).then(async (response) => {
      if (!response.ok) throw new Error("Không thể tải thông tin gói");
      setData((await response.json()) as Summary);
    }).catch((reason: Error) => setError(reason.message));
  }, []);

  return <main className="dashboard-content subscription-page">
    <div className="dashboard-page-heading"><div><h1>Gói dịch vụ & hạn mức</h1><p>Theo dõi tài nguyên Auralis AI trong kỳ hiện tại.</p></div></div>
    {error && <p className="subscription-error">{error}</p>}
    {!data && !error && <p>Đang tải hạn mức...</p>}
    {data && <>
      <section className="subscription-hero">
        <div><span>Gói hiện tại</span><h2>{data.plan.name}</h2><p>Trạng thái: {data.subscription.status}</p></div>
        <div><span>Kỳ sử dụng</span><strong>{data.period}</strong></div>
        <button type="button">Yêu cầu nâng cấp</button>
      </section>
      <section className="quota-grid">{Object.entries(data.resources).map(([key, resource]) =>
        <article className="quota-card" key={key}>
          <header><h3>{labels[key] || key}</h3><strong>{resource.used.toLocaleString("vi-VN")} / {resource.limit === null ? "Không giới hạn" : resource.limit.toLocaleString("vi-VN")}</strong></header>
          <div className="quota-track"><span className={resource.percent >= 90 ? "danger" : resource.percent >= 80 ? "warning" : ""} style={{ width: `${resource.limit === null ? 0 : resource.percent}%` }} /></div>
          <p>{resource.limit === null ? "Không áp dụng giới hạn" : `Còn lại ${resource.remaining?.toLocaleString("vi-VN")}`}</p>
        </article>)}</section>
    </>}
  </main>;
}

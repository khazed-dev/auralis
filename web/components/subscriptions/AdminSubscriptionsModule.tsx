"use client";

import { useCallback, useEffect, useState } from "react";
import { API_BASE, authFetch } from "@/lib/auth";

type Row = {
  user: { id: string; name?: string; email: string };
  plan: { key: string; name: string };
  subscription: { status: string };
  resources: Record<string, { used: number; limit: number | null }>;
};

export function AdminSubscriptionsModule() {
  const [rows, setRows] = useState<Row[]>([]);
  const [message, setMessage] = useState("");
  const load = useCallback(async () => {
    const response = await authFetch(`${API_BASE}/subscriptions/admin`);
    if (response.ok) setRows((await response.json()) as Row[]);
  }, []);
  useEffect(() => {
    const frame = requestAnimationFrame(() => void load());
    return () => cancelAnimationFrame(frame);
  }, [load]);

  async function changePlan(ownerId: string, plan: string) {
    const response = await authFetch(`${API_BASE}/subscriptions/admin/${ownerId}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan, status: "active", custom_limits: {} }),
    });
    setMessage(response.ok ? "Đã cập nhật gói." : "Không thể cập nhật gói.");
    if (response.ok) await load();
  }

  return <main className="dashboard-content subscription-page">
    <div className="dashboard-page-heading"><div><h1>Quản lý Subscription</h1><p>Gán gói và theo dõi usage của khách hàng.</p></div></div>
    {message && <p className="subscription-notice">{message}</p>}
    <section className="subscription-table-wrap"><table className="subscription-table">
      <thead><tr><th>Khách hàng</th><th>Gói</th><th>Website</th><th>Tin nhắn</th><th>Trạng thái</th></tr></thead>
      <tbody>{rows.map((row) => <tr key={row.user.id}>
        <td><strong>{row.user.name || "Chưa đặt tên"}</strong><small>{row.user.email}</small></td>
        <td><select value={row.plan.key} onChange={(event) => void changePlan(row.user.id, event.target.value)}>
          <option value="starter">Starter</option><option value="growth">Growth</option><option value="business">Business</option><option value="custom">Custom</option><option value="legacy">Legacy</option>
        </select></td>
        <td>{row.resources.sites.used} / {row.resources.sites.limit ?? "∞"}</td>
        <td>{row.resources.messages.used.toLocaleString("vi-VN")} / {row.resources.messages.limit?.toLocaleString("vi-VN") ?? "∞"}</td>
        <td><span className={`subscription-status ${row.subscription.status}`}>{row.subscription.status}</span></td>
      </tr>)}</tbody>
    </table></section>
  </main>;
}

"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { CatalogPlan, fetchPlanCatalog, planPresentation } from "@/lib/plans";

export function Pricing() {
  const [plans, setPlans] = useState<CatalogPlan[] | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let controller: AbortController | undefined;
    function load() {
      controller?.abort();
      controller = new AbortController();
      const signal = controller.signal;
      fetchPlanCatalog(signal).then(value => {
        if (signal.aborted) return;
        setPlans(value);
        setError("");
      }).catch(() => {
        if (signal.aborted) return;
        setPlans(null);
        setError("Không thể tải bảng giá. Vui lòng thử lại.");
      });
    }
    function refresh() { if (document.visibilityState === "visible") load(); }
    load();
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      controller?.abort();
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [attempt]);

  return (
    <section className="section pricing" id="pricing">
      <div className="container">
        <div className="section-heading">
          <h2>Bảng giá đơn giản, minh bạch</h2>
          <p>Linh hoạt mở rộng theo nhu cầu hỗ trợ của doanh nghiệp.</p>
        </div>
        {error ? <p role="alert">{error} <button type="button" onClick={() => setAttempt(value => value + 1)}>Thử lại</button></p>
          : plans === null ? <p role="status">Đang tải bảng giá...</p>
          : plans.length === 0 ? <p>Hiện chưa có gói dịch vụ công khai.</p> : null}
        <div className="pricing-grid">
          {plans?.map((plan) => {
            const view = planPresentation(plan);
            return <article className={`plan ${view.badge ? "popular" : ""}`} key={plan.key}>
              {view.badge && <span className="popular-label">{view.badge}</span>}
              <h3>{view.title}</h3>
              <div className="price">
                {view.price} <small>{view.suffix}</small>
              </div>
              <ul>
                {view.features.map((feature) => (
                  <li key={feature}>
                    <Icon name="check" /> {feature}
                  </li>
                ))}
              </ul>
              {view.href ? <a className={view.badge ? "button" : "plan-button"} href={view.href}>{view.action}</a>
                : <button className="plan-button" type="button" disabled>Tạm ngừng đăng ký</button>}
            </article>;
          })}
        </div>
      </div>
    </section>
  );
}

import { API_BASE } from "./auth";

export type CatalogPlan = {
  key: string;
  name: string;
  monthly_price: number | null;
  vat_rate: number;
  display_features: string[];
  limits: Record<string, number | null>;
  badge?: string | null;
  cta_label?: string;
  is_public: boolean;
  is_active: boolean;
  allow_new_signup: boolean;
  requires_contact: boolean;
  display_order: number;
};

export async function fetchPlanCatalog(signal?: AbortSignal): Promise<CatalogPlan[]> {
  const response = await fetch(`${API_BASE}/plans/public`, { cache: "no-store", signal });
  if (!response.ok) throw new Error("Không thể tải bảng giá. Vui lòng thử lại.");
  const plans = await response.json() as CatalogPlan[];
  if (!Array.isArray(plans)) throw new Error("Phản hồi bảng giá không hợp lệ.");
  return plans.filter(plan => plan.is_public && plan.is_active)
    .sort((first, second) => first.display_order - second.display_order);
}

export async function fetchPlan(key: string, signal?: AbortSignal): Promise<CatalogPlan> {
  const response = await fetch(`${API_BASE}/plans/${encodeURIComponent(key)}`, { cache: "no-store", signal });
  if (!response.ok) throw new Error("Gói dịch vụ không khả dụng. Vui lòng chọn lại gói.");
  return response.json() as Promise<CatalogPlan>;
}

export function planPresentation(plan: CatalogPlan) {
  const contact = plan.requires_contact || plan.monthly_price === null;
  return {
    title: plan.name,
    price: contact ? "Liên hệ" : plan.monthly_price === 0 ? "Miễn phí" : plan.monthly_price!.toLocaleString("vi-VN"),
    suffix: !contact && plan.monthly_price !== 0 ? "VNĐ/tháng" : "",
    badge: plan.badge,
    features: plan.display_features || [],
    action: plan.cta_label || (contact ? "Liên hệ tư vấn" : `Chọn gói ${plan.name}`),
    href: contact ? "/#contact" : plan.allow_new_signup ? `/checkout?plan=${encodeURIComponent(plan.key)}` : null,
  };
}

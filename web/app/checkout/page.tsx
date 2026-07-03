import { Suspense } from "react";
import { CheckoutPage } from "@/components/checkout/CheckoutPage";

export const metadata = { title: "Thanh toán bảo mật — Auralis AI" };
export default function Page() {
  return <Suspense><CheckoutPage /></Suspense>;
}

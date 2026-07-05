import type { Metadata } from "next";

import { RegisterPage } from "@/components/register/RegisterPage";

export const metadata: Metadata = {
  title: "Đăng ký gói dịch vụ — Auralis AI",
  description: "Chọn gói Auralis AI phù hợp và bắt đầu triển khai chatbot cho website.",
};

export default function Page() {
  return <RegisterPage />;
}

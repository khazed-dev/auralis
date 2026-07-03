import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Auralis AI — Trợ lý chăm sóc khách hàng thông minh",
  description:
    "Biến website của bạn thành trợ lý AI hỗ trợ khách hàng, được vận hành bằng công nghệ RAG tiên tiến.",
  icons: {
    icon: "/favicon.png",
    shortcut: "/favicon.png",
    apple: "/favicon.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}

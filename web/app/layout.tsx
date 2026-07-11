import type { Metadata } from "next";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/plus-jakarta-sans/600.css";
import "@fontsource/plus-jakarta-sans/700.css";
import "@fontsource/plus-jakarta-sans/800.css";
import "@fontsource/jetbrains-mono/500.css";
import "./globals.css";
import { PlatformBrandingProvider } from "@/components/ui/PlatformBranding";

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
      <body><PlatformBrandingProvider>{children}</PlatformBrandingProvider></body>
    </html>
  );
}

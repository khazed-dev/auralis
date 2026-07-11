"use client";

import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { API_BASE } from "@/lib/auth";

export type PlatformBrandingConfig = {
  app_name: string;
  logo_url?: string | null;
  favicon_url?: string | null;
  primary_color: string;
  secondary_color: string;
  login_title: string;
  login_subtitle: string;
  footer_text?: string | null;
  support_email?: string | null;
  hide_sitechat_branding: boolean;
};

export const DEFAULT_PLATFORM_BRANDING: PlatformBrandingConfig = {
  app_name: "Auralis AI",
  logo_url: null,
  favicon_url: "/favicon.png",
  primary_color: "#091C66",
  secondary_color: "#12D6C7",
  login_title: "Chào mừng bạn trở lại",
  login_subtitle: "Đăng nhập để quản lý các trợ lý AI của bạn",
  footer_text: null,
  support_email: null,
  hide_sitechat_branding: false,
};

const PlatformBrandingContext = createContext(DEFAULT_PLATFORM_BRANDING);

function applyBranding(config: PlatformBrandingConfig) {
  document.documentElement.style.setProperty("--platform-primary", config.primary_color);
  document.documentElement.style.setProperty("--platform-secondary", config.secondary_color);
  document.title = document.title.replace(/Auralis AI/g, config.app_name);
  const favicon = config.favicon_url;
  if (favicon) {
    let link = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
    if (!link) {
      link = document.createElement("link");
      link.rel = "icon";
      document.head.appendChild(link);
    }
    link.href = favicon;
  }
}

export function PlatformBrandingProvider({ children }: { children: ReactNode }) {
  const [branding, setBranding] = useState(DEFAULT_PLATFORM_BRANDING);

  useEffect(() => {
    let active = true;
    fetch(`${API_BASE}/platform/whitelabel`, { cache: "no-store" })
      .then(async response => response.ok ? response.json() : null)
      .then(value => {
        if (!active || !value) return;
        const next = { ...DEFAULT_PLATFORM_BRANDING, ...value } as PlatformBrandingConfig;
        setBranding(next);
        applyBranding(next);
      })
      .catch(() => undefined);

    function handleUpdate(event: Event) {
      const detail = (event as CustomEvent<PlatformBrandingConfig>).detail;
      if (!detail) return;
      const next = { ...DEFAULT_PLATFORM_BRANDING, ...detail };
      setBranding(next);
      applyBranding(next);
    }
    window.addEventListener("platform-branding-updated", handleUpdate);
    return () => {
      active = false;
      window.removeEventListener("platform-branding-updated", handleUpdate);
    };
  }, []);

  return <PlatformBrandingContext.Provider value={branding}>{children}</PlatformBrandingContext.Provider>;
}

export function usePlatformBranding() {
  return useContext(PlatformBrandingContext);
}

export function LoginBrandCopy() {
  const branding = usePlatformBranding();
  return <>
    <div className="login-heading">
      <h1>{branding.login_title}</h1>
      <p>{branding.login_subtitle}</p>
    </div>
  </>;
}

export function PlatformFooter() {
  const branding = usePlatformBranding();
  if (!branding.footer_text && !branding.support_email) return null;
  return <p className="platform-branding-footer">
    {branding.footer_text}
    {branding.footer_text && branding.support_email ? " · " : null}
    {branding.support_email ? <a href={`mailto:${branding.support_email}`}>{branding.support_email}</a> : null}
  </p>;
}

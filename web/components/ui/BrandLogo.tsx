"use client";

import Image from "next/image";
import { usePlatformBranding } from "./PlatformBranding";

export function BrandLogo({ priority = false }: { priority?: boolean }) {
  const branding = usePlatformBranding();
  if (branding.logo_url) {
    return <span className="brand-logo" aria-label={branding.app_name}>
      {/* User-provided URLs cannot be known in next.config at build time. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={branding.logo_url} alt={branding.app_name} width={160} height={160} />
    </span>;
  }
  return (
    <span className="brand-logo" aria-label={branding.app_name}>
      <Image src="/logo-auralis.png" alt={branding.app_name} width={160} height={160} priority={priority} />
    </span>
  );
}

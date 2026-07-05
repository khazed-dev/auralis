import { PlatformShell } from "@/components/platform/PlatformShell";

export default function Layout({ children }: { children: React.ReactNode }) {
  return <PlatformShell>{children}</PlatformShell>;
}

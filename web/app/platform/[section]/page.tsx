import { PlatformModule } from "@/components/platform/PlatformModule";

export default async function Page({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;
  return <PlatformModule section={section} />;
}

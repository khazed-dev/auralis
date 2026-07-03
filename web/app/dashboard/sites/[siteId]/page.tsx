import { SiteDetailModule } from "@/components/sites/detail/SiteDetailModule";

export default async function SiteDetailPage({
  params,
}: {
  params: Promise<{ siteId: string }>;
}) {
  const { siteId } = await params;
  return <SiteDetailModule siteId={siteId} />;
}

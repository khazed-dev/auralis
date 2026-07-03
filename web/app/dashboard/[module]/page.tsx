import { notFound } from "next/navigation";
import { Icon, type IconName } from "@/components/ui/Icon";

const modules: Record<
  string,
  { title: string; description: string; icon: IconName }
> = {
  sites: {
    title: "Website",
    description: "Quản lý các website và trợ lý AI của bạn.",
    icon: "grid",
  },
  conversations: {
    title: "Hội thoại",
    description: "Theo dõi lịch sử trò chuyện giữa khách hàng và trợ lý AI.",
    icon: "message",
  },
  handoffs: {
    title: "Handoff",
    description: "Tiếp nhận các cuộc hội thoại cần nhân viên hỗ trợ.",
    icon: "headset",
  },
  analytics: {
    title: "Phân tích",
    description: "Theo dõi hiệu quả vận hành và chất lượng hỗ trợ.",
    icon: "chart",
  },
  team: {
    title: "Đội ngũ",
    description: "Quản lý thành viên và quyền truy cập website.",
    icon: "users",
  },
  settings: {
    title: "Cài đặt",
    description: "Quản lý hồ sơ và thiết lập không gian làm việc.",
    icon: "settings",
  },
  help: {
    title: "Trợ giúp",
    description: "Tài liệu hướng dẫn và kênh hỗ trợ dành cho bạn.",
    icon: "help",
  },
};

export default async function DashboardModulePage({
  params,
}: {
  params: Promise<{ module: string }>;
}) {
  const { module } = await params;
  const currentModule = modules[module];
  if (!currentModule) notFound();

  return (
    <main className="dashboard-content">
      <div className="dashboard-page-heading">
        <span>
          <Icon name={currentModule.icon} />
        </span>
        <div>
          <h1>{currentModule.title}</h1>
          <p>{currentModule.description}</p>
        </div>
      </div>
      <section className="module-placeholder">
        <div className="module-placeholder-icon">
          <Icon name={currentModule.icon} />
        </div>
        <h2>Module đang được chuyển sang giao diện mới</h2>
        <p>
          Khung dashboard đã sẵn sàng. Chức năng của module này sẽ được kết nối
          với API hiện tại ở bước tiếp theo.
        </p>
      </section>
    </main>
  );
}

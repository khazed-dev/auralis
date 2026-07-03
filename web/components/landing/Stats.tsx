import { Icon, type IconName } from "@/components/ui/Icon";

const stats: Array<{ icon: IconName; value: string; label: string }> = [
  { icon: "message", value: "12K+", label: "Hội thoại đã phân tích" },
  { icon: "document", value: "480K+", label: "Trang đã lập chỉ mục" },
  { icon: "bolt", value: "2,4 giây", label: "Phản hồi trung bình" },
  { icon: "chart", value: "3,8K+", label: "Khách hàng tiềm năng" },
];

export function Stats() {
  return (
    <section className="container stats" aria-label="Số liệu nổi bật của Auralis">
      {stats.map((stat) => (
        <article className="stat-card" key={stat.label}>
          <Icon name={stat.icon} />
          <strong>{stat.value}</strong>
          <span>{stat.label}</span>
        </article>
      ))}
    </section>
  );
}

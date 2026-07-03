import { Icon } from "@/components/ui/Icon";

export function ChatMockup({ compact = false }: { compact?: boolean }) {
  return (
    <div className={compact ? "chat-widget compact" : "chat-widget"}>
      <div className="chat-header">
        <span className="chat-avatar">
          <Icon name="bot" />
        </span>
        <span>
          <strong>Auralis {compact ? "Trợ lý AI" : "Hỗ trợ"}</strong>
          <small>
            <i /> {compact ? "Luôn trực tuyến" : "Đang trực tuyến"}
          </small>
        </span>
      </div>
      <div className="chat-body">
        <div className="bubble bot-bubble">
          {compact
            ? "Bạn có thể cấu hình đăng nhập một lần cho đội ngũ ngay trên trang quản trị."
            : "Xin chào! Hôm nay tôi có thể giúp gì cho bạn?"}
        </div>
        <div className="bubble user-bubble">
          {compact
            ? "Làm thế nào để cấu hình SSO cho đội ngũ?"
            : "Làm thế nào để đặt lại khóa API?"}
        </div>
        {compact && (
          <div className="source-pill">Nguồn: Hướng dẫn bảo mật doanh nghiệp</div>
        )}
      </div>
      <div className="chat-input">
        <span>Nhập tin nhắn...</span>
        <Icon name="send" />
      </div>
    </div>
  );
}

import { Icon } from "@/components/ui/Icon";
import { ChatMockup } from "./ChatMockup";

export function SourceAnswers() {
  return (
    <section className="source-section" id="solutions">
      <div className="container source-grid">
        <div className="source-copy">
          <h2>Câu trả lời minh bạch, luôn kèm nguồn trích dẫn</h2>
          <p>
            Mỗi phản hồi do AI tạo ra đều chỉ rõ tài liệu hoặc trang web được sử
            dụng làm nguồn, giúp đội ngũ và khách hàng dễ dàng kiểm chứng.
          </p>
          <ul>
            <li>
              <Icon name="check" /> Giảm đến 60% yêu cầu cần nhân viên xử lý
            </li>
            <li>
              <Icon name="check" /> Phản hồi tức thì, hoạt động 24/7
            </li>
          </ul>
        </div>
        <div className="source-demo">
          <ChatMockup compact />
        </div>
      </div>
    </section>
  );
}

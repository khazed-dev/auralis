"use client";

import { useState } from "react";
import { Icon } from "@/components/ui/Icon";
import styles from "./landing.module.css";

const examples = [
  {
    label: "Đổi trả sản phẩm",
    question: "Mình đặt nhầm size, shop có hỗ trợ đổi không?",
    answer:
      "Có bạn nhé! Bạn có thể đổi size trong vòng 7 ngày kể từ khi nhận hàng. Sản phẩm cần còn nguyên tem và chưa qua sử dụng. Mình có thể hướng dẫn bạn các bước đổi hàng.",
    source: "Chính sách đổi trả",
    excerpt:
      "Khách hàng được đổi size trong vòng 7 ngày kể từ ngày nhận hàng. Sản phẩm còn nguyên tem, nhãn và chưa qua sử dụng.",
    file: "chinh-sach-doi-tra.pdf",
    section: "Điều kiện đổi hàng",
  },
  {
    label: "Thông tin giao hàng",
    question: "Shop giao hàng trong bao lâu vậy?",
    answer:
      "Đơn hàng thường được giao trong 2–4 ngày làm việc. Sau khi đơn được gửi đi, bạn sẽ nhận được mã vận đơn để theo dõi hành trình giao hàng.",
    source: "Hướng dẫn mua hàng",
    excerpt:
      "Thời gian giao hàng dự kiến: 2–4 ngày làm việc. Mã vận đơn được gửi cho khách hàng sau khi đơn vị vận chuyển tiếp nhận đơn.",
    file: "huong-dan-mua-hang.docx",
    section: "Vận chuyển & giao nhận",
  },
  {
    label: "Gặp nhân viên",
    question: "Mình muốn trao đổi thêm với nhân viên tư vấn.",
    answer:
      "Được bạn nhé. Mình sẽ chuyển cuộc trò chuyện cùng nội dung bạn vừa trao đổi cho đội ngũ tư vấn, để bạn không cần giải thích lại từ đầu.",
    source: "Chuyển tiếp hội thoại",
    excerpt:
      "Nhân viên tiếp nhận được lịch sử trao đổi, câu hỏi của khách và các nguồn AI đã sử dụng. Khách hàng tiếp tục trò chuyện ngay trong cùng một cửa sổ.",
    file: "Quy trình hỗ trợ khách hàng",
    section: "Tiếp nhận từ trợ lý AI",
  },
];

export function ProductDemo() {
  const [selected, setSelected] = useState(0);
  const [sourceOpen, setSourceOpen] = useState(false);
  const example = examples[selected];

  return (
    <section
      className={styles.demo}
      id="demo"
      aria-label="Trải nghiệm mẫu Auralis"
    >
      <div className={styles.workspaceBar}>
        <div className={styles.workspaceTitle}>
          <span className={styles.workspaceMark}>
            <Icon name="sparkles" />
          </span>
          <strong>Không gian tri thức</strong>
          <span className={styles.workspaceDivider}>/</span>
          <span>Trợ lý của bạn</span>
        </div>
        <span className={styles.demoLabel}>Demo tương tác</span>
      </div>
      <div className={styles.workspace}>
        <svg
          className={styles.connections}
          viewBox="0 0 1100 340"
          preserveAspectRatio="none"
          fill="none"
          aria-hidden="true"
        >
          <defs>
            <linearGradient id="knowledge-path">
              <stop stopColor="#3b6c79" />
              <stop offset=".5" stopColor="#4de2cf" />
              <stop offset="1" stopColor="#7a8be5" />
            </linearGradient>
          </defs>
          <path
            d="M236 100C365 100 325 170 468 170M236 170H468M236 240C365 240 325 170 468 170M584 170H700"
            stroke="url(#knowledge-path)"
            strokeWidth="1.5"
          />
          <circle cx="359" cy="145" r="3" fill="#4de2cf" />
          <circle cx="318" cy="170" r="3" fill="#4de2cf" />
          <circle cx="380" cy="192" r="3" fill="#4de2cf" />
          <circle cx="657" cy="170" r="3" fill="#929cf6" />
        </svg>
        <div className={styles.knowledge}>
          <p className={styles.panelLabel}>Tri thức doanh nghiệp</p>
          <div className={styles.knowledgeItem}>
            <span className={styles.fileIcon}>
              <Icon name="globe" />
            </span>
            <div>
              <strong>Website của bạn</strong>
              <small>Thông tin sản phẩm & dịch vụ</small>
            </div>
            <Icon className={styles.syncedIcon} name="check" />
          </div>
          <div className={`${styles.knowledgeItem} ${styles.activeKnowledge}`}>
            <span className={styles.fileIcon}>
              <Icon name="document" />
            </span>
            <div>
              <strong>Tài liệu nội bộ</strong>
              <small>PDF, Word và văn bản</small>
            </div>
            <Icon className={styles.syncedIcon} name="check" />
          </div>
          <div className={styles.knowledgeItem}>
            <span className={styles.fileIcon}>
              <Icon name="message" />
            </span>
            <div>
              <strong>Câu hỏi thường gặp</strong>
              <small>Câu trả lời từ đội ngũ của bạn</small>
            </div>
            <Icon className={styles.syncedIcon} name="check" />
          </div>
          <span className={styles.knowledgeNote}>
            <i /> Một kho tri thức, nhiều nguồn dữ liệu
          </span>
        </div>
        <div className={styles.intelligence} aria-hidden="true">
          <div className={styles.orbit}>
            <div className={styles.orbitInner} />
            <div className={styles.aiCore}>
              <svg viewBox="0 0 70 70" fill="none">
                <path
                  d="M16 52c9-6 9-35 19-35s10 29 19 35M24 52c6-7 6-23 11-23s5 16 11 23M31 51h8"
                  stroke="currentColor"
                  strokeWidth="3.2"
                  strokeLinecap="round"
                />
              </svg>
            </div>
          </div>
          <strong>Auralis AI</strong>
          <span>Hiểu ngữ cảnh. Đúng tri thức.</span>
        </div>
        <div className={styles.conversation}>
          <div className={styles.conversationHeader}>
            <span className={styles.botAvatar}>
              <Icon name="sparkles" />
            </span>
            <div>
              <strong>Trợ lý Auralis</strong>
              <small>
                <i /> Luôn sẵn sàng hỗ trợ
              </small>
            </div>
            <span className={styles.chatOptions} aria-hidden="true">
              •••
            </span>
          </div>
          <div
            className={styles.messages}
            aria-live="polite"
            aria-atomic="true"
          >
            <p className={styles.customerMessage}>{example.question}</p>
            <div className={styles.assistantMessage}>
              <span className={styles.replyMark}>
                <Icon name="sparkles" />
              </span>
              <div>
                <p>{example.answer}</p>
                <button
                  type="button"
                  className={styles.citation}
                  aria-expanded={sourceOpen}
                  aria-controls="demo-source"
                  onClick={() => setSourceOpen(!sourceOpen)}
                >
                  <Icon name="document" />
                  {example.source}
                  <Icon name="arrow" />
                </button>
              </div>
            </div>
            {sourceOpen && (
              <div className={styles.sourceExcerpt} id="demo-source">
                <strong>{example.file}</strong>
                <span>{example.section}</span>
                <p>{example.excerpt}</p>
              </div>
            )}
          </div>
          <div className={styles.conversationInput}>
            <span>Chọn câu hỏi bên dưới để thử</span>
            <span aria-hidden="true">
              <Icon name="arrow" />
            </span>
          </div>
        </div>
      </div>
      <div className={styles.demoControls}>
        <span>Thử một tình huống</span>
        <div role="group" aria-label="Chọn tình huống demo">
          {examples.map((item, index) => (
            <button
              type="button"
              key={item.label}
              aria-pressed={selected === index}
              onClick={() => {
                setSelected(index);
                setSourceOpen(false);
              }}
            >
              {item.label}
              <Icon name="arrow" />
            </button>
          ))}
        </div>
      </div>
      <p className={styles.demoDisclaimer}>
        Nội dung minh họa. Trợ lý thực tế sẽ trả lời từ dữ liệu bạn kết nối.
      </p>
    </section>
  );
}

"use client";

import Image from "next/image";
import { FormEvent, useMemo, useState } from "react";
import { API_BASE, authFetch, DEV_AUTH_ENABLED } from "@/lib/auth";
import { AppearanceConfig, SiteConfig } from "./types";

type PreviewMessage = {
  role: "user" | "assistant";
  content: string;
  sources?: Array<{ title?: string; url: string }>;
};

export function ChatbotLivePreview({
  siteId,
  siteUrl,
  appearance,
  quickPrompts,
}: {
  siteId: string;
  siteUrl: string;
  appearance: AppearanceConfig;
  quickPrompts: SiteConfig["quick_prompts"];
}) {
  const [live, setLive] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<PreviewMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const sessionId = useMemo(
    () => `dashboard-preview-${siteId}-${Date.now().toString(36)}`,
    [siteId],
  );
  const prompts = quickPrompts.enabled
    ? quickPrompts.prompts
        .filter((prompt) => prompt.enabled)
        .slice(0, quickPrompts.max_display)
    : [];

  async function sendMessage(text: string) {
    const message = text.trim();
    if (!message || sending) return;
    setInput("");
    setError("");
    setMessages((current) => [...current, { role: "user", content: message }]);
    if (!live) return;

    setSending(true);
    try {
      if (DEV_AUTH_ENABLED) {
        await new Promise((resolve) => setTimeout(resolve, 450));
        setMessages((current) => [
          ...current,
          {
            role: "assistant",
            content:
              "Đây là phản hồi mô phỏng ở môi trường local. Khi bật trên server, Live Demo sẽ dùng dữ liệu RAG của đúng website này.",
          },
        ]);
        return;
      }
      const response = await authFetch(`${API_BASE}/chat/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          session_id: sessionId,
          site_id: siteId,
        }),
      });
      const data = (await response.json().catch(() => ({}))) as {
        answer?: string;
        detail?: string | { message?: string };
        sources?: Array<{ title?: string; url: string }>;
      };
      if (!response.ok) {
        const detail =
          typeof data.detail === "string"
            ? data.detail
            : data.detail?.message;
        throw new Error(detail || "Không thể nhận phản hồi từ chatbot.");
      }
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: data.answer || "Không nhận được phản hồi.",
          sources: data.sources,
        },
      ]);
    } catch (sendError) {
      setError(
        sendError instanceof Error
          ? sendError.message
          : "Không thể nhận phản hồi từ chatbot.",
      );
    } finally {
      setSending(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void sendMessage(input);
  }

  return (
    <aside className="chatbot-preview-pane">
      <header>
        <div>
          <strong>Live Demo</strong>
          <span>Cập nhật ngay theo thay đổi bên trái</span>
        </div>
        <label className="preview-live-toggle">
          <input
            type="checkbox"
            checked={live}
            onChange={(event) => setLive(event.target.checked)}
          />
          <span>{live ? "Chat thật đang bật" : "Bật chat thật"}</span>
        </label>
      </header>

      <div className="chatbot-preview-stage">
        <div className="chatbot-preview-window">
          <div
            className="chatbot-preview-header"
            style={{
              background: `linear-gradient(135deg, ${appearance.primary_color}, color-mix(in srgb, ${appearance.primary_color} 78%, #07164d))`,
            }}
          >
            <span className="chatbot-preview-avatar">
              {appearance.bot_avatar_url ? (
                <Image
                  src={appearance.bot_avatar_url}
                  alt=""
                  width={42}
                  height={42}
                  unoptimized
                />
              ) : (
                "◇"
              )}
            </span>
            <div>
              <strong>{appearance.chat_title || "Trợ lý AI"}</strong>
              <small>Trợ lý trực tuyến</small>
            </div>
            <button type="button" aria-label="Làm mới" onClick={() => setMessages([])}>
              ↻
            </button>
            <button type="button" aria-label="Đóng bản xem trước">×</button>
          </div>

          <div className="chatbot-preview-messages">
            {!messages.length && (
              <div className="chatbot-preview-welcome">
                <span
                  className="chatbot-preview-logo"
                  style={{ color: appearance.primary_color }}
                >
                  ◇
                </span>
                <h3>Xin chào! 👋</h3>
                <p>{appearance.welcome_message}</p>
                <div className="chatbot-preview-prompts">
                  {prompts.map((prompt) => (
                    <button
                      type="button"
                      key={prompt.id}
                      onClick={() => void sendMessage(prompt.text)}
                    >
                      {prompt.icon && <span>{prompt.icon}</span>}
                      {prompt.text}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((message, index) => (
              <div
                className={`chatbot-preview-message ${message.role}`}
                key={`${message.role}-${index}`}
              >
                <p>{message.content}</p>
                {!!message.sources?.length && (
                  <div className="chatbot-preview-sources">
                    {message.sources.map((source) => (
                      <a href={source.url} target="_blank" rel="noreferrer" key={source.url}>
                        {source.title || "Nguồn"}
                      </a>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {sending && <div className="chatbot-preview-typing">● ● ●</div>}
            {error && <p className="chatbot-preview-error">{error}</p>}
          </div>

          <form className="chatbot-preview-input" onSubmit={submit}>
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder={
                live
                  ? "Nhập nội dung cần tư vấn..."
                  : "Bật chat thật để kiểm tra phản hồi"
              }
            />
            <button
              type="submit"
              disabled={!input.trim() || sending}
              style={{ background: appearance.primary_color }}
            >
              ➤
            </button>
          </form>

          {!appearance.hide_branding && (
            <a
              className="chatbot-preview-branding"
              href={appearance.custom_branding_url || siteUrl}
              target="_blank"
              rel="noreferrer"
            >
              {appearance.custom_branding_text || siteUrl}
            </a>
          )}
        </div>
      </div>
      <p className="preview-note">
        {live
          ? "Tin nhắn đang dùng RAG và hành vi AI đã lưu của website này."
          : "Chế độ xem trước chỉ mô phỏng giao diện và không tiêu tốn quota."}
      </p>
    </aside>
  );
}

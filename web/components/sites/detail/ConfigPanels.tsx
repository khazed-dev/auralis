"use client";

import { FormEvent, useState } from "react";
import { AppearanceConfig, BehaviorConfig } from "./types";
import { ChatbotLivePreview } from "./ChatbotLivePreview";

type SaveResult = { ok: boolean; message: string };

export function AppearancePanel({
  config,
  onSave,
  onReset,
  siteId,
  siteUrl,
  quickPrompts,
}: {
  config: AppearanceConfig;
  onSave: (config: AppearanceConfig) => Promise<SaveResult>;
  onReset: () => Promise<void>;
  siteId: string;
  siteUrl: string;
  quickPrompts: import("./types").SiteConfig["quick_prompts"];
}) {
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [draft, setDraft] = useState(config);

  function update<K extends keyof AppearanceConfig>(
    key: K,
    value: AppearanceConfig[K],
  ) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    const result = await onSave(draft);
    setMessage(result.message);
    setSaving(false);
  }

  return (
    <div className="appearance-live-layout">
    <form className="site-config-form" onSubmit={submit}>
      <header>
        <h2>Giao diện chatbot</h2>
        <p>Tùy chỉnh cách trợ lý AI xuất hiện trên website.</p>
      </header>
      <section>
        <h3>Thông tin hiển thị</h3>
        <div className="site-config-grid">
          <label>
            Tiêu đề chatbot
            <input name="chat_title" value={draft.chat_title} onChange={(event) => update("chat_title", event.target.value)} required />
          </label>
          <label>
            Màu thương hiệu
            <span className="site-color-input">
              <input
                name="primary_color"
                type="color"
                value={draft.primary_color}
                onChange={(event) => update("primary_color", event.target.value)}
              />
              <code>{draft.primary_color}</code>
            </span>
          </label>
          <label className="wide">
            Lời chào
            <textarea
              name="welcome_message"
              value={draft.welcome_message}
              onChange={(event) => update("welcome_message", event.target.value)}
              rows={3}
              required
            />
          </label>
          <label>
            Vị trí
            <select name="position" value={draft.position} onChange={(event) => update("position", event.target.value)}>
              <option value="bottom-right">Góc dưới bên phải</option>
              <option value="bottom-left">Góc dưới bên trái</option>
            </select>
          </label>
          <label>
            URL ảnh đại diện
            <input
              name="bot_avatar_url"
              type="url"
              value={draft.bot_avatar_url || ""}
              onChange={(event) => update("bot_avatar_url", event.target.value || null)}
              placeholder="https://..."
            />
          </label>
        </div>
      </section>
      <section>
        <h3>White-label</h3>
        <label className="site-config-checkbox">
          <input
            name="hide_branding"
            type="checkbox"
            checked={draft.hide_branding}
            onChange={(event) => update("hide_branding", event.target.checked)}
          />
          <span>Tùy chỉnh hoặc ẩn dòng “Powered by Auralis”</span>
        </label>
        <div className="site-config-grid">
          <label>
            Nội dung thương hiệu
            <input
              name="custom_branding_text"
              value={draft.custom_branding_text || ""}
              onChange={(event) => update("custom_branding_text", event.target.value || null)}
              placeholder="Powered by Công ty bạn"
            />
          </label>
          <label>
            Liên kết thương hiệu
            <input
              name="custom_branding_url"
              type="url"
              value={draft.custom_branding_url || ""}
              onChange={(event) => update("custom_branding_url", event.target.value || null)}
              placeholder="https://..."
            />
          </label>
        </div>
      </section>
      <footer>
        {message && <span>{message}</span>}
        <button type="button" className="site-secondary-button" onClick={() => void onReset()}>
          Khôi phục mặc định
        </button>
        <button className="sites-primary-button" disabled={saving}>
          {saving ? "Đang lưu..." : "Lưu giao diện"}
        </button>
      </footer>
    </form>
    <ChatbotLivePreview
      siteId={siteId}
      siteUrl={siteUrl}
      appearance={draft}
      quickPrompts={quickPrompts}
    />
    </div>
  );
}

export function BehaviorPanel({
  config,
  onSave,
}: {
  config: BehaviorConfig;
  onSave: (config: BehaviorConfig) => Promise<SaveResult>;
}) {
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    const data = new FormData(event.currentTarget);
    const result = await onSave({
      system_prompt: String(data.get("system_prompt")),
      temperature: Number(data.get("temperature")),
      max_tokens: Number(data.get("max_tokens")),
      show_sources: data.get("show_sources") === "on",
    });
    setMessage(result.message);
    setSaving(false);
  }

  return (
    <form className="site-config-form" onSubmit={submit}>
      <header>
        <h2>Hành vi của trợ lý AI</h2>
        <p>Kiểm soát cách chatbot sử dụng dữ liệu và tạo câu trả lời.</p>
      </header>
      <section>
        <label>
          Chỉ dẫn hệ thống
          <small>
            Mô tả vai trò, giọng điệu và những nguyên tắc trợ lý cần tuân theo.
          </small>
          <textarea
            className="system-prompt"
            name="system_prompt"
            defaultValue={config.system_prompt}
            rows={10}
            required
          />
        </label>
      </section>
      <section>
        <div className="site-config-grid">
          <label>
            Temperature
            <small>Thấp hơn giúp câu trả lời ổn định hơn (0–2).</small>
            <input
              name="temperature"
              type="number"
              min={0}
              max={2}
              step={0.1}
              defaultValue={config.temperature}
            />
          </label>
          <label>
            Độ dài câu trả lời tối đa
            <small>Số token tối đa cho mỗi phản hồi.</small>
            <input
              name="max_tokens"
              type="number"
              min={50}
              max={4000}
              defaultValue={config.max_tokens}
            />
          </label>
        </div>
        <label className="site-config-checkbox">
          <input
            name="show_sources"
            type="checkbox"
            defaultChecked={config.show_sources}
          />
          <span>Hiển thị nguồn trích dẫn trong câu trả lời</span>
        </label>
      </section>
      <footer>
        {message && <span>{message}</span>}
        <button className="sites-primary-button" disabled={saving}>
          {saving ? "Đang lưu..." : "Lưu hành vi"}
        </button>
      </footer>
    </form>
  );
}

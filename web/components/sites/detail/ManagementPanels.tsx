"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { API_BASE, authFetch, DEV_AUTH_ENABLED } from "@/lib/auth";
import { SiteConfig } from "./types";

async function errorMessage(response: Response, fallback: string) {
  const data = (await response.json().catch(() => ({}))) as { detail?: string };
  return data.detail || fallback;
}

export function QuickPromptsPanel({
  siteId,
  initial,
  onChange,
}: {
  siteId: string;
  initial: SiteConfig["quick_prompts"];
  onChange: (value: SiteConfig["quick_prompts"]) => void;
}) {
  const [config, setConfig] = useState(initial);
  const [text, setText] = useState("");
  const [icon, setIcon] = useState("💡");
  const [message, setMessage] = useState("");

  async function save(next = config) {
    if (!DEV_AUTH_ENABLED) {
      const response = await authFetch(`${API_BASE}/sites/${siteId}/quick-prompts`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(next),
      });
      if (!response.ok) {
        setMessage(await errorMessage(response, "Không thể lưu gợi ý nhanh."));
        return;
      }
    }
    setConfig(next);
    onChange(next);
    setMessage("Đã lưu gợi ý nhanh.");
  }

  function addPrompt(event: FormEvent) {
    event.preventDefault();
    if (!text.trim()) return;
    const next = {
      ...config,
      prompts: [
        ...config.prompts,
        { id: `prompt-${Date.now()}`, text: text.trim(), icon, enabled: true },
      ],
    };
    setText("");
    void save(next);
  }

  return (
    <div className="site-config-form">
      <header><h2>Quick Prompts</h2><p>Các câu hỏi gợi ý giúp khách hàng bắt đầu hội thoại nhanh hơn.</p></header>
      <section>
        <label className="site-config-checkbox"><input type="checkbox" checked={config.enabled} onChange={(event) => void save({ ...config, enabled: event.target.checked })} /><span>Hiển thị gợi ý nhanh trong chatbot</span></label>
        <div className="prompt-list">
          {config.prompts.map((prompt) => (
            <div key={prompt.id}>
              <span>{prompt.icon || "💬"}</span>
              <strong>{prompt.text}</strong>
              <label><input type="checkbox" checked={prompt.enabled} onChange={(event) => void save({ ...config, prompts: config.prompts.map((item) => item.id === prompt.id ? { ...item, enabled: event.target.checked } : item) })} /> Bật</label>
              <button onClick={() => void save({ ...config, prompts: config.prompts.filter((item) => item.id !== prompt.id) })}>Xóa</button>
            </div>
          ))}
        </div>
        <form className="prompt-add-form" onSubmit={addPrompt}>
          <input value={icon} onChange={(event) => setIcon(event.target.value)} maxLength={4} aria-label="Biểu tượng" />
          <input value={text} onChange={(event) => setText(event.target.value)} maxLength={100} placeholder="Nhập câu hỏi gợi ý..." />
          <button className="sites-primary-button">Thêm</button>
        </form>
      </section>
      <section>
        <div className="site-config-grid">
          <label>Số gợi ý tối đa<input type="number" min={1} max={10} value={config.max_display} onChange={(event) => setConfig({ ...config, max_display: Number(event.target.value) })} /></label>
          <label className="site-config-checkbox"><input type="checkbox" checked={config.show_after_response} onChange={(event) => setConfig({ ...config, show_after_response: event.target.checked })} /><span>Hiện lại sau khi AI trả lời</span></label>
        </div>
      </section>
      <footer>{message && <span>{message}</span>}<button className="sites-primary-button" onClick={() => void save()}>Lưu cấu hình</button></footer>
    </div>
  );
}

type Trigger = {
  id: string;
  name: string;
  enabled: boolean;
  priority: number;
  message: string;
  conditions: Array<{ type: string; operator: string; value: string | number }>;
};

export function TriggersPanel({ siteId }: { siteId: string }) {
  const [triggers, setTriggers] = useState<Trigger[]>([]);
  const [cooldown, setCooldown] = useState(30000);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    if (DEV_AUTH_ENABLED) {
      setTriggers([{ id: "demo-trigger", name: "Chào khách sau 15 giây", enabled: true, priority: 1, message: "Bạn cần mình hỗ trợ tìm thông tin gì không?", conditions: [{ type: "time", operator: "gte", value: 15 }] }]);
      return;
    }
    const response = await authFetch(`${API_BASE}/sites/${siteId}/triggers`);
    if (response.ok) {
      const data = (await response.json()) as { triggers: Trigger[]; global_cooldown_ms: number };
      setTriggers(data.triggers);
      setCooldown(data.global_cooldown_ms);
    }
  }, [siteId]);

  useEffect(() => { const frame = requestAnimationFrame(() => void load()); return () => cancelAnimationFrame(frame); }, [load]);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const trigger: Omit<Trigger, "id"> = {
      name: String(form.get("name")),
      enabled: true,
      priority: Number(form.get("priority") || 0),
      message: String(form.get("message")),
      conditions: [{ type: String(form.get("type")), operator: String(form.get("operator")), value: String(form.get("value")) }],
    };
    if (DEV_AUTH_ENABLED) {
      setTriggers([...triggers, { ...trigger, id: `local-${Date.now()}` }]);
    } else {
      const response = await authFetch(`${API_BASE}/sites/${siteId}/triggers`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(trigger) });
      if (!response.ok) { setMessage(await errorMessage(response, "Không thể tạo trigger.")); return; }
      setTriggers([...triggers, (await response.json()) as Trigger]);
    }
    event.currentTarget.reset();
    setMessage("Đã tạo trigger.");
  }

  async function update(trigger: Trigger, updates: Partial<Trigger>) {
    if (!DEV_AUTH_ENABLED) {
      const response = await authFetch(`${API_BASE}/sites/${siteId}/triggers/${trigger.id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(updates) });
      if (!response.ok) { setMessage(await errorMessage(response, "Không thể cập nhật trigger.")); return; }
    }
    setTriggers(triggers.map((item) => item.id === trigger.id ? { ...item, ...updates } : item));
    setMessage("Đã cập nhật trigger.");
  }

  async function remove(trigger: Trigger) {
    if (!window.confirm(`Xóa trigger “${trigger.name}”?`)) return;
    if (!DEV_AUTH_ENABLED) {
      const response = await authFetch(`${API_BASE}/sites/${siteId}/triggers/${trigger.id}`, { method: "DELETE" });
      if (!response.ok) { setMessage(await errorMessage(response, "Không thể xóa trigger.")); return; }
    }
    setTriggers(triggers.filter((item) => item.id !== trigger.id));
    setMessage("Đã xóa trigger.");
  }

  async function saveCooldown() {
    if (!DEV_AUTH_ENABLED) {
      const response = await authFetch(`${API_BASE}/sites/${siteId}/triggers/cooldown?cooldown_ms=${cooldown}`, { method: "PUT" });
      if (!response.ok) { setMessage(await errorMessage(response, "Không thể lưu thời gian chờ.")); return; }
    }
    setMessage("Đã lưu thời gian chờ.");
  }

  return (
    <div className="site-config-form">
      <header><h2>Proactive Triggers</h2><p>Chủ động mở lời dựa trên hành vi của khách truy cập.</p></header>
      <section>
        <h3>Trigger hiện có</h3>
        <div className="trigger-list">
          {triggers.map((trigger) => (
            <article key={trigger.id}>
              <label><input type="checkbox" checked={trigger.enabled} onChange={(event) => void update(trigger, { enabled: event.target.checked })} /></label>
              <div><strong>{trigger.name}</strong><p>{trigger.message}</p><small>{trigger.conditions[0]?.type}: {String(trigger.conditions[0]?.value)}</small></div>
              <button onClick={() => void remove(trigger)}>Xóa</button>
            </article>
          ))}
          {!triggers.length && <p>Chưa có trigger.</p>}
        </div>
      </section>
      <section>
        <h3>Tạo trigger</h3>
        <form className="trigger-create-form" onSubmit={create}>
          <div className="site-config-grid">
            <label>Tên<input name="name" required /></label>
            <label>Loại điều kiện<select name="type"><option value="time">Thời gian trên trang</option><option value="scroll">Phần trăm cuộn trang</option><option value="visit_count">Số lần truy cập</option><option value="url">URL chứa</option><option value="exit_intent">Ý định thoát trang</option></select></label>
            <label>So sánh<select name="operator"><option value="gte">Lớn hơn hoặc bằng</option><option value="eq">Bằng</option><option value="contains">Chứa</option></select></label>
            <label>Giá trị<input name="value" required /></label>
            <label className="wide">Tin nhắn<textarea name="message" rows={3} required /></label>
            <label>Độ ưu tiên<input name="priority" type="number" defaultValue={0} /></label>
          </div>
          <button className="sites-primary-button">Tạo trigger</button>
        </form>
      </section>
      <footer><label>Thời gian chờ giữa các trigger (giây)<input type="number" min={0} max={300} value={cooldown / 1000} onChange={(event) => setCooldown(Number(event.target.value) * 1000)} /></label>{message && <span>{message}</span>}<button className="sites-primary-button" onClick={() => void saveCooldown()}>Lưu</button></footer>
    </div>
  );
}

type DocumentItem = { id: string; filename: string; file_type: string; word_count: number; chunks: number; status: string; uploaded_at?: string | null };
type QAItem = { id: string; question: string; answer: string; enabled: boolean; use_count: number };

export function TrainingPanel({ siteId }: { siteId: string }) {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [qaPairs, setQaPairs] = useState<QAItem[]>([]);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    if (DEV_AUTH_ENABLED) {
      setDocuments([{ id: "demo-doc", filename: "gioi-thieu-auralis.pdf", file_type: "pdf", word_count: 2450, chunks: 18, status: "indexed", uploaded_at: new Date().toISOString() }]);
      setQaPairs([{ id: "demo-qa", question: "Auralis là gì?", answer: "Auralis là nền tảng trợ lý AI cho website.", enabled: true, use_count: 12 }]);
      return;
    }
    const [docsResponse, qaResponse] = await Promise.all([
      authFetch(`${API_BASE}/documents/${siteId}`),
      authFetch(`${API_BASE}/sites/${siteId}/qa?limit=100`),
    ]);
    if (docsResponse.ok) setDocuments(((await docsResponse.json()) as { documents: DocumentItem[] }).documents);
    if (qaResponse.ok) setQaPairs(((await qaResponse.json()) as { qa_pairs: QAItem[] }).qa_pairs);
  }, [siteId]);

  useEffect(() => { const frame = requestAnimationFrame(() => void load()); return () => cancelAnimationFrame(frame); }, [load]);

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    if (!DEV_AUTH_ENABLED) {
      const response = await authFetch(`${API_BASE}/documents/upload/${siteId}`, { method: "POST", body: formData });
      if (!response.ok) { setMessage(await errorMessage(response, "Không thể tải tài liệu.")); return; }
    }
    setMessage("Đã tải tài liệu lên và đưa vào hàng chờ xử lý.");
    event.currentTarget.reset();
    void load();
  }

  async function addQA(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload = { question: String(form.get("question")), answer: String(form.get("answer")) };
    if (DEV_AUTH_ENABLED) setQaPairs([...qaPairs, { ...payload, id: `local-${Date.now()}`, enabled: true, use_count: 0 }]);
    else {
      const response = await authFetch(`${API_BASE}/sites/${siteId}/qa`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      if (!response.ok) { setMessage(await errorMessage(response, "Không thể thêm Q&A.")); return; }
      setQaPairs([...qaPairs, (await response.json()) as QAItem]);
    }
    event.currentTarget.reset();
    setMessage("Đã thêm câu hỏi và câu trả lời.");
  }

  async function removeDoc(id: string) {
    if (!DEV_AUTH_ENABLED) {
      const response = await authFetch(`${API_BASE}/documents/${siteId}/${id}`, { method: "DELETE" });
      if (!response.ok) { setMessage(await errorMessage(response, "Không thể xóa tài liệu.")); return; }
    }
    setDocuments(documents.filter((item) => item.id !== id));
    setMessage("Đã xóa tài liệu.");
  }

  async function toggleQA(item: QAItem) {
    if (!DEV_AUTH_ENABLED) {
      const response = await authFetch(`${API_BASE}/sites/${siteId}/qa/${item.id}/toggle`, { method: "POST" });
      if (!response.ok) { setMessage(await errorMessage(response, "Không thể cập nhật Q&A.")); return; }
      const updated = (await response.json()) as QAItem;
      setQaPairs(qaPairs.map((qa) => qa.id === item.id ? updated : qa));
    } else {
      setQaPairs(qaPairs.map((qa) => qa.id === item.id ? { ...qa, enabled: !qa.enabled } : qa));
    }
    setMessage("Đã cập nhật Q&A.");
  }

  async function removeQA(id: string) {
    if (!DEV_AUTH_ENABLED) {
      const response = await authFetch(`${API_BASE}/sites/${siteId}/qa/${id}`, { method: "DELETE" });
      if (!response.ok) { setMessage(await errorMessage(response, "Không thể xóa Q&A.")); return; }
    }
    setQaPairs(qaPairs.filter((item) => item.id !== id));
    setMessage("Đã xóa Q&A.");
  }

  return (
    <div className="site-config-form">
      <header><h2>Dữ liệu huấn luyện</h2><p>Quản lý tài liệu và câu trả lời đã được kiểm duyệt.</p></header>
      <section>
        <h3>Tài liệu</h3>
        <form className="document-upload-form" onSubmit={upload}><input name="files" type="file" multiple accept=".pdf,.doc,.docx,.txt,.md,.csv,.pptx,.xlsx,.html" required /><button className="sites-primary-button">Tải lên</button></form>
        <div className="management-list">
          {documents.map((doc) => <article key={doc.id}><Icon name="document" /><div><strong>{doc.filename}</strong><small>{doc.word_count} từ · {doc.chunks} đoạn · {doc.status}</small></div><button onClick={() => void removeDoc(doc.id)}>Xóa</button></article>)}
          {!documents.length && <p>Chưa có tài liệu.</p>}
        </div>
      </section>
      <section>
        <h3>Câu hỏi & trả lời</h3>
        <form className="qa-add-form" onSubmit={addQA}><label>Câu hỏi<input name="question" required /></label><label>Câu trả lời<textarea name="answer" rows={4} required /></label><button className="sites-primary-button">Thêm Q&A</button></form>
        <div className="qa-list">
          {qaPairs.map((item) => <article key={item.id}><div><strong>{item.question}</strong><p>{item.answer}</p><small>Đã dùng {item.use_count} lần</small></div><label><input type="checkbox" checked={item.enabled} onChange={() => void toggleQA(item)} /> Bật</label><button onClick={() => void removeQA(item.id)}>Xóa</button></article>)}
        </div>
      </section>
      {message && <footer><span>{message}</span></footer>}
    </div>
  );
}

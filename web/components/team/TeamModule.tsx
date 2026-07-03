"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { API_BASE, authFetch, DEV_AUTH_ENABLED, getStoredUser } from "@/lib/auth";

type Member = {
  id: string;
  email: string;
  name: string;
  role: "admin" | "user" | "agent";
  created_at: string;
  assigned_site_ids: string[];
};

type SiteOption = { site_id: string; name?: string | null; url: string };
type TeamTab = "owners" | "agents";

const demoOwners: Member[] = [
  { id: "local-development-user", email: "dev@auralis.local", name: "Auralis Local", role: "admin", created_at: new Date().toISOString(), assigned_site_ids: [] },
  { id: "demo-owner", email: "owner@example.com", name: "Nguyễn Quản lý", role: "user", created_at: new Date(Date.now() - 25 * 86400_000).toISOString(), assigned_site_ids: [] },
];

const demoAgents: Member[] = [
  { id: "demo-agent-1", email: "linh@example.com", name: "Trần Ngọc Linh", role: "agent", created_at: new Date(Date.now() - 12 * 86400_000).toISOString(), assigned_site_ids: ["demo-auralis", "demo-store"] },
  { id: "demo-agent-2", email: "minh@example.com", name: "Lê Minh", role: "agent", created_at: new Date(Date.now() - 5 * 86400_000).toISOString(), assigned_site_ids: ["demo-store"] },
];

async function apiError(response: Response, fallback: string) {
  const data = (await response.json().catch(() => ({}))) as {
    detail?: string | Array<{ msg?: string }>;
  };
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) return data.detail.map((item) => item.msg).filter(Boolean).join(", ");
  return fallback;
}

export function TeamModule() {
  const currentUser = useMemo(() => getStoredUser(), []);
  const isAdmin = currentUser?.role === "admin";
  const [tab, setTab] = useState<TeamTab>(isAdmin ? "owners" : "agents");
  const [owners, setOwners] = useState<Member[]>([]);
  const [agents, setAgents] = useState<Member[]>([]);
  const [sites, setSites] = useState<SiteOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Member | null>(null);
  const [saving, setSaving] = useState(false);

  const loadTeam = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      if (DEV_AUTH_ENABLED) {
        setOwners((current) => (current.length ? current : demoOwners));
        setAgents((current) => (current.length ? current : demoAgents));
        setSites([
          { site_id: "demo-auralis", name: "Auralis Demo", url: "" },
          { site_id: "demo-store", name: "Cửa hàng mẫu", url: "" },
        ]);
        return;
      }
      const requests: Promise<unknown>[] = [
        authFetch(`${API_BASE}/auth/agents`),
        authFetch(`${API_BASE}/sites`),
      ];
      if (isAdmin) requests.push(authFetch(`${API_BASE}/auth/users`));
      const responses = (await Promise.all(requests)) as Response[];
      for (const response of responses) {
        if (!response.ok) throw new Error(await apiError(response, "Không thể tải đội ngũ."));
      }
      setAgents((await responses[0].json()) as Member[]);
      setSites((await responses[1].json()) as SiteOption[]);
      if (isAdmin) {
        const allUsers = (await responses[2].json()) as Member[];
        setOwners(allUsers.filter((member) => member.role !== "agent"));
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Không thể tải đội ngũ.");
    } finally {
      setLoading(false);
    }
  }, [isAdmin]);

  useEffect(() => {
    const frame = requestAnimationFrame(() => void loadTeam());
    return () => cancelAnimationFrame(frame);
  }, [loadTeam]);

  const members = tab === "owners" ? owners : agents;

  function openCreate() {
    setEditing(null);
    setModalOpen(true);
  }

  function openEdit(member: Member) {
    setEditing(member);
    setModalOpen(true);
  }

  async function saveMember(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    const form = new FormData(event.currentTarget);
    const name = String(form.get("name") ?? "").trim();
    const email = String(form.get("email") ?? "").trim();
    const password = String(form.get("password") ?? "");
    const assignedSiteIds = form.getAll("site_ids").map(String);

    try {
      const role: Member["role"] = tab === "agents" ? "agent" : "user";
      const localMember: Member = {
        id: editing?.id || `local-${Date.now()}`,
        email: editing?.email || email,
        name,
        role,
        created_at: editing?.created_at || new Date().toISOString(),
        assigned_site_ids: role === "agent" ? assignedSiteIds : [],
      };

      if (!DEV_AUTH_ENABLED) {
        const base = tab === "agents" ? "agents" : "users";
        const url = editing
          ? `${API_BASE}/auth/${base}/${editing.id}`
          : `${API_BASE}/auth/${base}`;
        const body: Record<string, unknown> = { name };
        if (!editing) body.email = email;
        if (password) body.password = password;
        if (tab === "agents") body.assigned_site_ids = assignedSiteIds;
        const response = await authFetch(url, {
          method: editing ? "PATCH" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        if (!response.ok) throw new Error(await apiError(response, "Không thể lưu thành viên."));
      }

      const setter = tab === "agents" ? setAgents : setOwners;
      setter((current) =>
        editing
          ? current.map((member) => (member.id === editing.id ? localMember : member))
          : [...current, localMember],
      );
      setModalOpen(false);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Không thể lưu thành viên.");
    } finally {
      setSaving(false);
    }
  }

  async function removeMember(member: Member) {
    if (!window.confirm(`Xóa tài khoản “${member.name}”?`)) return;
    try {
      if (!DEV_AUTH_ENABLED) {
        const base = member.role === "agent" ? "agents" : "users";
        const response = await authFetch(`${API_BASE}/auth/${base}/${member.id}`, {
          method: "DELETE",
        });
        if (!response.ok) throw new Error(await apiError(response, "Không thể xóa thành viên."));
      }
      if (member.role === "agent") {
        setAgents((current) => current.filter((item) => item.id !== member.id));
      } else {
        setOwners((current) => current.filter((item) => item.id !== member.id));
      }
    } catch (removeError) {
      setError(removeError instanceof Error ? removeError.message : "Không thể xóa thành viên.");
    }
  }

  const siteNames = (ids: string[]) =>
    ids.map((id) => sites.find((site) => site.site_id === id)?.name || id);

  return (
    <main className="dashboard-content team-module">
      <div className="team-title-row">
        <div className="dashboard-page-heading">
          <span><Icon name="users" /></span>
          <div><h1>Đội ngũ</h1><p>Quản lý thành viên và quyền truy cập website.</p></div>
        </div>
        <button className="sites-primary-button" onClick={openCreate}>
          <span>+</span> {tab === "agents" ? "Thêm nhân viên" : "Thêm chủ website"}
        </button>
      </div>

      {isAdmin && (
        <div className="team-tabs">
          <button className={tab === "owners" ? "active" : ""} onClick={() => setTab("owners")}>
            Chủ website <span>{owners.length}</span>
          </button>
          <button className={tab === "agents" ? "active" : ""} onClick={() => setTab("agents")}>
            Nhân viên hỗ trợ <span>{agents.length}</span>
          </button>
        </div>
      )}

      {error && <div className="sites-alert"><span>{error}</span><button onClick={() => setError("")}>Đóng</button></div>}

      <section className="team-card">
        <header>
          <div>
            <h2>{tab === "agents" ? "Nhân viên hỗ trợ" : "Chủ website"}</h2>
            <p>
              {tab === "agents"
                ? "Nhân viên tiếp nhận handoff trên những website được phân công."
                : "Chủ website có thể quản lý website và nhân viên thuộc tài khoản của họ."}
            </p>
          </div>
          <span>{members.length} thành viên</span>
        </header>

        {loading ? (
          <div className="team-empty"><span className="dashboard-spinner" />Đang tải đội ngũ...</div>
        ) : members.length === 0 ? (
          <div className="team-empty"><Icon name="users" /><h3>Chưa có thành viên</h3><p>Thêm thành viên đầu tiên để bắt đầu cộng tác.</p><button onClick={openCreate}>Thêm thành viên</button></div>
        ) : (
          <div className="team-table-wrap">
            <table className="team-table">
              <thead><tr><th>Thành viên</th><th>Vai trò</th><th>Website được phân công</th><th>Ngày tạo</th><th /></tr></thead>
              <tbody>
                {members.map((member) => (
                  <tr key={member.id}>
                    <td>
                      <span className="team-avatar">{member.name.charAt(0).toUpperCase()}</span>
                      <span><strong>{member.name}</strong><small>{member.email}</small></span>
                    </td>
                    <td><em className={member.role}>{member.role === "admin" ? "Quản trị viên" : member.role === "user" ? "Chủ website" : "Nhân viên"}</em></td>
                    <td>
                      {member.role === "agent" ? (
                        member.assigned_site_ids.length ? (
                          <div className="team-site-tags">
                            {siteNames(member.assigned_site_ids).slice(0, 2).map((name) => <span key={name}>{name}</span>)}
                            {member.assigned_site_ids.length > 2 && <span>+{member.assigned_site_ids.length - 2}</span>}
                          </div>
                        ) : <span className="team-muted">Chưa phân công</span>
                      ) : <span className="team-muted">Theo quyền sở hữu</span>}
                    </td>
                    <td>{new Date(member.created_at).toLocaleDateString("vi-VN")}</td>
                    <td>
                      <div className="team-row-actions">
                        {member.role !== "admin" && <button onClick={() => openEdit(member)}>Chỉnh sửa</button>}
                        {member.id !== currentUser?.id && member.role !== "admin" && <button className="danger" onClick={() => void removeMember(member)}>Xóa</button>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {modalOpen && (
        <div className="sites-modal-layer">
          <button className="sites-modal-backdrop" onClick={() => setModalOpen(false)} aria-label="Đóng" />
          <section className="sites-modal team-modal" role="dialog" aria-modal="true">
            <div className="sites-modal-header">
              <div>
                <h2>{editing ? "Chỉnh sửa thành viên" : tab === "agents" ? "Thêm nhân viên hỗ trợ" : "Thêm chủ website"}</h2>
                <p>{tab === "agents" ? "Phân công website mà nhân viên được phép hỗ trợ." : "Tạo tài khoản quản lý website mới."}</p>
              </div>
              <button onClick={() => setModalOpen(false)}>×</button>
            </div>
            <form onSubmit={saveMember}>
              <label>Họ và tên<input name="name" defaultValue={editing?.name} minLength={2} required autoFocus /></label>
              <label>Email<input name="email" type="email" defaultValue={editing?.email} disabled={Boolean(editing)} required={!editing} placeholder="nhanvien@congty.com" /></label>
              <label>
                {editing ? "Mật khẩu mới" : "Mật khẩu"}
                <small>{editing ? "Để trống nếu không muốn thay đổi" : "Tối thiểu 8 ký tự, gồm chữ hoa, chữ thường và số"}</small>
                <input name="password" type="password" minLength={8} required={!editing} autoComplete="new-password" />
              </label>
              {tab === "agents" && (
                <fieldset className="team-sites-fieldset">
                  <legend>Website được phân công</legend>
                  {sites.length ? sites.map((site) => (
                    <label key={site.site_id}>
                      <input type="checkbox" name="site_ids" value={site.site_id} defaultChecked={editing?.assigned_site_ids.includes(site.site_id)} />
                      <span>{site.name || site.url}</span>
                    </label>
                  )) : <p>Chưa có website để phân công.</p>}
                </fieldset>
              )}
              <div className="sites-modal-actions">
                <button type="button" onClick={() => setModalOpen(false)}>Hủy</button>
                <button className="sites-primary-button" disabled={saving}>{saving ? "Đang lưu..." : editing ? "Lưu thay đổi" : "Tạo tài khoản"}</button>
              </div>
            </form>
          </section>
        </div>
      )}
    </main>
  );
}

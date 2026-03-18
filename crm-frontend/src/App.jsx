import { useState, useEffect } from "react";
import "./index.css";

const API = "";

const getToken = () => localStorage.getItem("client_token");
const getSession = () => { try { return JSON.parse(localStorage.getItem("client_session") || "{}"); } catch { return {}; } };

const authFetch = (url, opts = {}) =>
  fetch(`${API}${url}`, {
    ...opts,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}`, ...(opts.headers || {}) },
  });

function fmt(dt) {
  if (!dt) return "—";
  return new Date(dt).toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function getBadgeClass(state) {
  const s = (state || "").toLowerCase();
  if (s === "active_chat") return "badge badge-active";
  if (s === "normal") return "badge badge-normal";
  if (s === "session_expired") return "badge badge-expired";
  if (s.startsWith("awaiting")) return "badge badge-awaiting";
  return "badge badge-default";
}

// =====================================================
// LOGIN
// =====================================================
function LoginScreen({ onLogin }) {
  const [form, setForm] = useState({ username: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    setLoading(true); setError("");
    try {
      const res = await fetch(`${API}/api/auth/client/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || "Login failed"); return; }
      localStorage.setItem("client_token", data.access_token);
      localStorage.setItem("client_session", JSON.stringify({ client_id: data.client_id, username: form.username, must_change_password: data.must_change_password }));
      onLogin(data);
    } catch { setError("Could not connect to server"); }
    finally { setLoading(false); }
  };

  return (
    <div className="auth-screen">
      <div className="auth-scan" />
      <div className="auth-box">
        <div className="auth-logo-wrap">
          <div className="auth-logo-icon">💬</div>
          <div className="auth-logo">Lakshya CRM</div>
        </div>
        <div className="auth-role">Client Portal</div>
        <div className="auth-title">Sign in to your account</div>
        <div className="auth-sub">Access your leads and appointment dashboard</div>
        <div className="field">
          <label>Username</label>
          <input value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} onKeyDown={e => e.key === "Enter" && handleLogin()} autoComplete="username" />
        </div>
        <div className="field">
          <label>Password</label>
          <input type="password" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} onKeyDown={e => e.key === "Enter" && handleLogin()} autoComplete="current-password" />
        </div>
        <button className="auth-btn" onClick={handleLogin} disabled={loading}>
          {loading ? "Signing in..." : "Sign in →"}
        </button>
        {error && <div className="auth-err">{error}</div>}
      </div>
    </div>
  );
}

// =====================================================
// FORCE CHANGE PASSWORD
// =====================================================
function ForceChangePassword({ onChanged }) {
  const [form, setForm] = useState({ current_password: "", new_password: "", confirm: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handle = async () => {
    if (form.new_password !== form.confirm) { setError("Passwords do not match"); return; }
    if (form.new_password.length < 8) { setError("Minimum 8 characters"); return; }
    setLoading(true); setError("");
    const res = await authFetch("/api/client/change-password", { method: "POST", body: JSON.stringify({ current_password: form.current_password, new_password: form.new_password }) });
    const data = await res.json();
    if (!res.ok) { setError(data.detail || "Failed"); setLoading(false); return; }
    const session = getSession();
    localStorage.setItem("client_session", JSON.stringify({ ...session, must_change_password: false }));
    onChanged();
  };

  return (
    <div className="force-change">
      <div className="force-box">
        <div className="auth-logo-wrap" style={{ marginBottom: 6 }}>
          <div className="auth-logo-icon">🔑</div>
          <div className="auth-logo">Lakshya CRM</div>
        </div>
        <div className="force-title" style={{ marginTop: 8 }}>Set New Password</div>
        <div className="force-sub" style={{ marginTop: 8 }}>⚠️ You are using a temporary password. Please set a new one to continue.</div>
        {error && <div className="auth-err">{error}</div>}
        <div className="field"><label>Current (Temporary) Password</label><input type="password" value={form.current_password} onChange={e => setForm({ ...form, current_password: e.target.value })} /></div>
        <div className="field"><label>New Password</label><input type="password" value={form.new_password} onChange={e => setForm({ ...form, new_password: e.target.value })} /></div>
        <div className="field"><label>Confirm New Password</label><input type="password" value={form.confirm} onChange={e => setForm({ ...form, confirm: e.target.value })} /></div>
        <button className="auth-btn" onClick={handle} disabled={loading}>{loading ? "Updating..." : "Set New Password →"}</button>
      </div>
    </div>
  );
}

// =====================================================
// LEADS VIEW
// =====================================================
function LeadsView({ onSelectLead }) {
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    authFetch("/api/client/leads").then(r => r.json()).then(d => { setLeads(d); setLoading(false); });
  }, []);

  const filtered = leads.filter(l =>
    (l.name || "").toLowerCase().includes(search.toLowerCase()) ||
    (l.phone_number || "").includes(search)
  );

  return (
    <>
      <div className="stats-row">
        <div className="stat-card"><div className="stat-label">Total Leads</div><div className="stat-value">{leads.length}</div><div className="stat-sub">All time</div></div>
        <div className="stat-card"><div className="stat-label">Active Chats</div><div className="stat-value">{leads.filter(l => l.state === "active_chat").length}</div><div className="stat-sub">Currently engaged</div></div>
        <div className="stat-card"><div className="stat-label">Named Leads</div><div className="stat-value">{leads.filter(l => l.name).length}</div><div className="stat-sub">Name captured</div></div>
      </div>
      <div className="card">
        <div className="card-header">
          <span className="card-title">All Leads</span>
          <div className="search-wrap">
            <span className="search-icon">🔍</span>
            <input className="search-input" placeholder="Search name or phone..." value={search} onChange={e => setSearch(e.target.value)} />
          </div>
        </div>
        {loading ? <div className="loading"><div className="spinner" />Loading...</div>
          : filtered.length === 0 ? <div className="empty"><div className="empty-icon">👤</div>No leads yet</div>
          : <table>
              <thead><tr><th>ID</th><th>Name</th><th>Phone</th><th>Interest</th><th>State</th><th>Last Active</th><th></th></tr></thead>
              <tbody>
                {filtered.map(l => (
                  <tr key={l.id} onClick={() => onSelectLead(l.id)}>
                    <td style={{ color: "var(--muted)", fontFamily: "var(--mono)", fontSize: 12 }}>#{l.id.slice(-6)}</td>
                    <td className="cell-name">{l.name || <span style={{ color: "var(--muted)" }}>Unknown</span>}</td>
                    <td className="cell-mono">{l.phone_number}</td>
                    <td>{l.service_interest ? <span className="badge badge-normal">{l.service_interest}</span> : "—"}</td>
                    <td><span className={getBadgeClass(l.state)}>{l.state}</span></td>
                    <td>{fmt(l.last_interaction_at)}</td>
                    <td><button className="btn btn-ghost btn-sm">View →</button></td>
                  </tr>
                ))}
              </tbody>
            </table>}
      </div>
    </>
  );
}

// =====================================================
// LEAD DETAIL
// =====================================================
function LeadDetail({ leadId, onBack }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    authFetch(`/api/client/leads/${leadId}`).then(r => r.json()).then(d => { setData(d); setLoading(false); });
  }, [leadId]);

  if (loading) return <div className="loading"><div className="spinner" />Loading...</div>;
  if (!data) return <div className="empty">Lead not found</div>;
  const { lead, chats } = data;

  return (
    <>
      <button className="back-btn" onClick={onBack}>← Back to Leads</button>
      <div className="detail-grid">
        <div className="info-card">
          <div className="info-avatar">{lead.name?.charAt(0) || "?"}</div>
          <div className="info-name">{lead.name || "Unknown"}</div>
          <div className="info-phone">{lead.phone_number}</div>
          <hr className="info-divider" />
          <div className="info-row"><span className="info-key">State</span><span className={getBadgeClass(lead.state)}>{lead.state}</span></div>
          <div className="info-row"><span className="info-key">Interest</span><span className="info-val">{lead.service_interest || "—"}</span></div>
          <div className="info-row"><span className="info-key">Created</span><span className="info-val" style={{ fontSize: 11 }}>{fmt(lead.created_at)}</span></div>
          <div className="info-row"><span className="info-key">Last Active</span><span className="info-val" style={{ fontSize: 11 }}>{fmt(lead.last_interaction_at)}</span></div>
          <div className="info-row"><span className="info-key">Messages</span><span className="info-val">{chats.length}</span></div>
        </div>
        <div className="chat-card">
          <div className="chat-header">💬 Conversation History</div>
          <div className="chat-body">
            {chats.length === 0
              ? <div className="empty"><div className="empty-icon">💬</div>No messages yet</div>
              : chats.map(m => (
                <div key={m.id} className={`msg-row ${m.direction}`}>
                  <div className={`bubble ${m.direction}`}>
                    {m.text}
                    <div className="bubble-time">{fmt(m.created_at)}</div>
                  </div>
                </div>
              ))}
          </div>
        </div>
      </div>
    </>
  );
}

// =====================================================
// APPOINTMENTS VIEW
// =====================================================
function AppointmentsView() {
  const [appts, setAppts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    authFetch("/api/client/appointments").then(r => r.json()).then(d => { setAppts(d); setLoading(false); });
  }, []);

  const filtered = appts.filter(a =>
    (a.lead_name || "").toLowerCase().includes(search.toLowerCase()) ||
    (a.phone_number || "").includes(search)
  );

  return (
    <>
      <div className="stats-row">
        <div className="stat-card"><div className="stat-label">Total</div><div className="stat-value">{appts.length}</div><div className="stat-sub">All time</div></div>
        <div className="stat-card"><div className="stat-label">Confirmed</div><div className="stat-value" style={{ color: "var(--success)" }}>{appts.filter(a => a.status === "confirmed").length}</div><div className="stat-sub">Scheduled callbacks</div></div>
        <div className="stat-card"><div className="stat-label">Pending</div><div className="stat-value" style={{ color: "var(--warning)" }}>{appts.filter(a => a.status === "pending").length}</div><div className="stat-sub">Awaiting confirmation</div></div>
      </div>
      <div className="card">
        <div className="card-header">
          <span className="card-title">All Appointments</span>
          <div className="search-wrap">
            <span className="search-icon">🔍</span>
            <input className="search-input" placeholder="Search..." value={search} onChange={e => setSearch(e.target.value)} />
          </div>
        </div>
        {loading ? <div className="loading"><div className="spinner" />Loading...</div>
          : filtered.length === 0 ? <div className="empty"><div className="empty-icon">📅</div>No appointments yet</div>
          : <table>
              <thead><tr><th>Name</th><th>Phone</th><th>Requested Time</th><th>Status</th><th>Created</th></tr></thead>
              <tbody>
                {filtered.map(a => (
                  <tr key={a.id}>
                    <td className="cell-name">{a.lead_name || "Unknown"}</td>
                    <td className="cell-mono">{a.phone_number}</td>
                    <td style={{ color: "var(--text)" }}>{a.requested_time}</td>
                    <td><span className={a.status === "confirmed" ? "badge badge-confirmed" : "badge badge-pending"}>{a.status}</span></td>
                    <td>{fmt(a.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>}
      </div>
    </>
  );
}

// =====================================================
// SETTINGS
// =====================================================
function SettingsView() {
  const [form, setForm] = useState({ current_password: "", new_password: "", confirm: "" });
  const [msg, setMsg] = useState(null);
  const [loading, setLoading] = useState(false);

  const handle = async () => {
    if (form.new_password !== form.confirm) { setMsg({ type: "error", text: "Passwords do not match" }); return; }
    if (form.new_password.length < 8) { setMsg({ type: "error", text: "Min 8 characters" }); return; }
    setLoading(true); setMsg(null);
    const res = await authFetch("/api/client/change-password", { method: "POST", body: JSON.stringify({ current_password: form.current_password, new_password: form.new_password }) });
    const data = await res.json();
    setLoading(false);
    if (!res.ok) { setMsg({ type: "error", text: data.detail || "Failed" }); return; }
    setMsg({ type: "success", text: "Password updated successfully" });
    setForm({ current_password: "", new_password: "", confirm: "" });
  };

  return (
    <div className="settings-card">
      <div className="settings-title">🔑 Change Password</div>
      {msg && <div className={`alert alert-${msg.type}`}>{msg.text}</div>}
      <div className="form-group"><label className="form-label">Current Password</label><input className="form-input" type="password" value={form.current_password} onChange={e => setForm({ ...form, current_password: e.target.value })} /></div>
      <div className="form-group"><label className="form-label">New Password</label><input className="form-input" type="password" value={form.new_password} onChange={e => setForm({ ...form, new_password: e.target.value })} /></div>
      <div className="form-group"><label className="form-label">Confirm New Password</label><input className="form-input" type="password" value={form.confirm} onChange={e => setForm({ ...form, confirm: e.target.value })} /></div>
      <button className="btn btn-primary" onClick={handle} disabled={loading}>{loading ? "Updating..." : "Update Password"}</button>
    </div>
  );
}

// =====================================================
// ROOT
// =====================================================
export default function ClientApp() {
  const [authed, setAuthed] = useState(!!getToken());
  const [mustChange, setMustChange] = useState(getSession().must_change_password || false);
  const [view, setView] = useState("leads");
  const [selectedLeadId, setSelectedLeadId] = useState(null);
  const [profile, setProfile] = useState(null);
  const session = getSession();

  useEffect(() => {
    if (authed && !mustChange) {
      authFetch("/api/client/profile").then(r => r.json()).then(setProfile).catch(() => {});
    }
  }, [authed, mustChange]);

  const handleLogin = (data) => { setAuthed(true); setMustChange(data.must_change_password); };
  const handleSelectLead = (id) => { setSelectedLeadId(id); setView("lead-detail"); };

  if (!authed) return <LoginScreen onLogin={handleLogin} />;
  if (mustChange) return <ForceChangePassword onChanged={() => setMustChange(false)} />;

  const pages = {
    leads: { title: "Leads", sub: "All WhatsApp leads and their status" },
    "lead-detail": { title: "Lead Detail", sub: "Conversation history and lead info" },
    appointments: { title: "Appointments", sub: "Scheduled callbacks and status" },
    settings: { title: "Settings", sub: "Account settings" },
  };
  const page = pages[view] || pages.leads;

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-name">Lakshya CRM</div>
          <div className="brand-tag">{profile?.institute_name || session.username}</div>
        </div>
        <nav className="sidebar-nav">
          <div className="nav-label">Menu</div>
          <button className={`nav-btn ${view === "leads" || view === "lead-detail" ? "active" : ""}`} onClick={() => setView("leads")}>👥 Leads</button>
          <button className={`nav-btn ${view === "appointments" ? "active" : ""}`} onClick={() => setView("appointments")}>📅 Appointments</button>
          <div className="nav-label">Account</div>
          <button className={`nav-btn ${view === "settings" ? "active" : ""}`} onClick={() => setView("settings")}>⚙️ Settings</button>
        </nav>
        <div className="sidebar-bottom">
          <span className="sidebar-user">{session.username}</span>
          <button className="logout-btn" onClick={() => { localStorage.removeItem("client_token"); localStorage.removeItem("client_session"); setAuthed(false); }}>Logout</button>
        </div>
      </aside>
      <main className="main">
        <div className="topbar">
          <div>
            <div className="page-title">{page.title}</div>
            <div className="page-sub">{page.sub}</div>
          </div>
          {profile && <div style={{ fontSize: 12, color: "var(--muted)", textAlign: "right" }}>{profile.leads_count} leads · {profile.appointments_count} appointments</div>}
        </div>
        <div className="content">
          {view === "leads" && <LeadsView onSelectLead={handleSelectLead} />}
          {view === "lead-detail" && <LeadDetail leadId={selectedLeadId} onBack={() => setView("leads")} />}
          {view === "appointments" && <AppointmentsView />}
          {view === "settings" && <SettingsView />}
        </div>
      </main>
    </div>
  );
}
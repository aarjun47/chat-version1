import { useState, useEffect } from "react";
import "./index.css";

const API = "https://chatbot-nw9p.onrender.com";

const token = () => localStorage.getItem("master_token");
const authFetch = (url, opts = {}) =>
  fetch(`${API}${url}`, {
    ...opts,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token()}`, ...(opts.headers || {}) },
  });

function fmt(dt) {
  if (!dt) return "—";
  return new Date(dt).toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
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
      const res = await fetch(`${API}/api/auth/master/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || "Login failed"); return; }
      localStorage.setItem("master_token", data.access_token);
      onLogin();
    } catch { setError("Could not connect to server"); }
    finally { setLoading(false); }
  };

  return (
    <div className="auth-screen">
      <div className="auth-scan" />
      <div className="auth-box">
        <div className="auth-logo-wrap">
          <div className="auth-logo-icon">⚡</div>
          <div className="auth-logo">Lakshya CRM</div>
        </div>
        <div className="auth-role">Master Portal</div>
        <div className="auth-title">Sign in</div>
        <div className="auth-sub">Restricted access — authorised personnel only</div>
        <div className="field">
          <label>Username</label>
          <input value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} onKeyDown={e => e.key === "Enter" && handleLogin()} autoComplete="username" />
        </div>
        <div className="field">
          <label>Password</label>
          <input type="password" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} onKeyDown={e => e.key === "Enter" && handleLogin()} autoComplete="current-password" />
        </div>
        <button className="auth-btn" onClick={handleLogin} disabled={loading}>
          {loading ? "Authenticating..." : "Sign in →"}
        </button>
        {error && <div className="auth-err">{error}</div>}
      </div>
    </div>
  );
}

// =====================================================
// DASHBOARD
// =====================================================
function Dashboard({ onSelectClient }) {
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    authFetch("/api/master/clients").then(r => r.json()).then(d => { setClients(d); setLoading(false); });
  };
  useEffect(() => { load(); }, []);

  const totalLeads = clients.reduce((s, c) => s + (c.leads_count || 0), 0);
  const totalAppts = clients.reduce((s, c) => s + (c.appointments_count || 0), 0);

  return (
    <>
      <div className="stats-row">
        <div className="stat-card"><div className="stat-label">Total Clients</div><div className="stat-value">{clients.length}</div><div className="stat-sub">All institutes</div></div>
        <div className="stat-card"><div className="stat-label">Active</div><div className="stat-value" style={{ color: "var(--success)" }}>{clients.filter(c => c.is_active).length}</div><div className="stat-sub">Running</div></div>
        <div className="stat-card"><div className="stat-label">Total Leads</div><div className="stat-value">{totalLeads}</div><div className="stat-sub">Across all clients</div></div>
        <div className="stat-card"><div className="stat-label">Appointments</div><div className="stat-value">{totalAppts}</div><div className="stat-sub">Across all clients</div></div>
      </div>
      <div className="card">
        <div className="card-header"><span className="card-title">All Clients</span></div>
        {loading ? <div className="loading"><div className="spinner" />Loading...</div>
          : clients.length === 0 ? <div className="empty"><div className="empty-icon">🏫</div>No clients yet. Click "Add Client" to get started.</div>
          : <table>
              <thead><tr><th>Institute</th><th>Phone</th><th>Persona</th><th>Leads</th><th>Appointments</th><th>Status</th><th>Created</th><th></th></tr></thead>
              <tbody>
                {clients.map(c => (
                  <tr key={c.id} onClick={() => onSelectClient(c.id)}>
                    <td className="cell-name">{c.institute_name}</td>
                    <td className="cell-mono">{c.twilio_phone_number}</td>
                    <td>{c.persona_name}</td>
                    <td><span className="badge badge-blue">{c.leads_count}</span></td>
                    <td><span className="badge badge-blue">{c.appointments_count}</span></td>
                    <td><span className={c.is_active ? "badge badge-active" : "badge badge-inactive"}>{c.is_active ? "Active" : "Inactive"}</span></td>
                    <td>{fmt(c.created_at)}</td>
                    <td><button className="btn btn-ghost btn-sm" onClick={e => { e.stopPropagation(); onSelectClient(c.id); }}>View →</button></td>
                  </tr>
                ))}
              </tbody>
            </table>}
      </div>
    </>
  );
}

// =====================================================
// ADD CLIENT MODAL
// =====================================================
function AddClientModal({ onClose, onCreated }) {
  const [form, setForm] = useState({
    institute_name: "", twilio_account_sid: "", twilio_auth_token: "",
    twilio_phone_number: "", persona_name: "Arun", system_prompt: "",
    username: "", password: "",
    base_url: "https://chatbot-nw9p.onrender.com"
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleCreate = async () => {
    setSaving(true); setError("");
    try {
      const res = await authFetch("/api/master/clients", { method: "POST", body: JSON.stringify(form) });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || "Failed"); return; }
      onCreated(data);
    } catch { setError("Server error"); }
    finally { setSaving(false); }
  };

  const f = (key, label, type = "text", placeholder = "") => (
    <div className="form-group" key={key}>
      <label className="form-label">{label}</label>
      <input className="form-input" type={type} placeholder={placeholder} value={form[key]} onChange={e => setForm({ ...form, [key]: e.target.value })} />
    </div>
  );

  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-title">Add New Client</div>
        {error && <div className="alert alert-error">{error}</div>}
        <div className="section-divider">Institute Info</div>
        {f("institute_name", "Institute Name", "text", "e.g. Indian Institute of Commerce")}
        <div className="form-row">
          {f("persona_name", "AI Counsellor Name", "text", "e.g. Arun")}
          {f("base_url", "Backend Base URL", "text", "https://your-app.onrender.com")}
        </div>
        <div className="section-divider">Twilio Credentials</div>
        {f("twilio_account_sid", "Account SID", "text", "ACxxxxxxxx")}
        {f("twilio_auth_token", "Auth Token", "password")}
        {f("twilio_phone_number", "WhatsApp Number", "text", "+1415XXXXXXX")}
        <div className="section-divider">Client Login Credentials</div>
        <div className="form-row">
          {f("username", "Username")}
          {f("password", "Temporary Password", "password")}
        </div>
        <div className="section-divider">Custom System Prompt (Optional)</div>
        <div className="form-group">
          <label className="form-label">System Prompt</label>
          <textarea className="form-textarea" placeholder="Leave blank to use default prompt..." value={form.system_prompt} onChange={e => setForm({ ...form, system_prompt: e.target.value })} />
        </div>
        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={handleCreate} disabled={saving}>{saving ? "Creating..." : "Create Client"}</button>
        </div>
      </div>
    </div>
  );
}

// =====================================================
// CLIENT DETAIL
// =====================================================
function ClientDetail({ clientId, onBack }) {
  const [client, setClient] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showResetModal, setShowResetModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [resetForm, setResetForm] = useState({ username: "", password: "" });
  const [editForm, setEditForm] = useState({});
  const [msg, setMsg] = useState(null);

  const load = () => {
    setLoading(true);
    authFetch(`/api/master/clients/${clientId}`).then(r => r.json()).then(d => {
      setClient(d);
      setEditForm({ institute_name: d.institute_name, persona_name: d.persona_name, twilio_account_sid: d.twilio_account_sid, twilio_auth_token: "", twilio_phone_number: d.twilio_phone_number, system_prompt: d.system_prompt || "", is_active: d.is_active, webhook_url: d.webhook_url || "" });
      setLoading(false);
    });
  };
  useEffect(() => { load(); }, [clientId]);

  const handleDelete = async () => {
    if (!confirm("Delete this client and ALL their data? This cannot be undone.")) return;
    await authFetch(`/api/master/clients/${clientId}`, { method: "DELETE" });
    onBack();
  };

  const handleToggleActive = async () => {
    await authFetch(`/api/master/clients/${clientId}`, { method: "PUT", body: JSON.stringify({ is_active: !client.is_active }) });
    load();
  };

  const handleResetCreds = async () => {
    const res = await authFetch(`/api/master/clients/${clientId}/reset-credentials`, { method: "POST", body: JSON.stringify(resetForm) });
    if (res.ok) { setMsg({ type: "success", text: "Credentials reset. Client must change password on next login." }); setShowResetModal(false); }
  };

  const handleSaveEdit = async () => {
    const payload = { ...editForm };
    if (!payload.twilio_auth_token) delete payload.twilio_auth_token;
    const res = await authFetch(`/api/master/clients/${clientId}`, { method: "PUT", body: JSON.stringify(payload) });
    if (res.ok) { setMsg({ type: "success", text: "Client updated." }); setShowEditModal(false); load(); }
  };

  if (loading) return <div className="loading"><div className="spinner" />Loading...</div>;
  if (!client) return <div className="empty"><div className="empty-icon">⚠️</div>Client not found</div>;

  return (
    <>
      <button className="back-btn" onClick={onBack}>← Back to Dashboard</button>
      {msg && <div className={`alert alert-${msg.type}`}>{msg.text}</div>}
      <div className="detail-grid">
        <div className="info-panel">
          <div className="info-avatar">{client.institute_name?.charAt(0)}</div>
          <div className="info-name">{client.institute_name}</div>
          <div className="info-sub">Persona: {client.persona_name}</div>
          <hr className="divider" />
          <div className="info-row"><span className="info-key">Status</span><span className={client.is_active ? "badge badge-active" : "badge badge-inactive"}>{client.is_active ? "Active" : "Inactive"}</span></div>
          <div className="info-row"><span className="info-key">Leads</span><span className="info-val">{client.leads_count}</span></div>
          <div className="info-row"><span className="info-key">Appointments</span><span className="info-val">{client.appointments_count}</span></div>
          <div className="info-row"><span className="info-key">Username</span><span className="info-val cell-mono">{client.username || "—"}</span></div>
          <div className="info-row"><span className="info-key">Created</span><span className="info-val" style={{ fontSize: 11 }}>{fmt(client.created_at)}</span></div>
          <div className="section-divider" style={{ marginTop: 18 }}>Twilio</div>
          <div className="info-row"><span className="info-key">Phone</span><span className="info-val cell-mono">{client.twilio_phone_number}</span></div>
          <div className="info-row"><span className="info-key">SID</span><span className="info-val cell-mono" style={{ fontSize: 10 }}>{client.twilio_account_sid}</span></div>
          <div className="section-divider" style={{ marginTop: 18 }}>Webhook URL</div>
          <div className="webhook-box">{client.webhook_url || `https://your-app.onrender.com/message/${client.id}`}</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 20 }}>
            <button className="btn btn-ghost" onClick={() => setShowEditModal(true)}>✏️ Edit Info</button>
            <button className="btn btn-warning" onClick={() => setShowResetModal(true)}>🔑 Reset Credentials</button>
            <button className="btn btn-ghost" onClick={handleToggleActive}>{client.is_active ? "⏸ Deactivate" : "▶ Activate"}</button>
            <button className="btn btn-danger" onClick={handleDelete}>🗑 Delete Client</button>
          </div>
        </div>
        <div>
          <div className="card">
            <div className="card-header"><span className="card-title">Overview</span></div>
            <div style={{ padding: "24px 26px", color: "var(--text-dim)", fontSize: 13, lineHeight: 1.8 }}>
              <p>Persona: <strong style={{ color: "var(--text)" }}>{client.persona_name}</strong></p>
              <p style={{ marginTop: 8 }}><strong style={{ color: "var(--text)" }}>{client.leads_count}</strong> leads · <strong style={{ color: "var(--text)" }}>{client.appointments_count}</strong> appointments</p>
              <p style={{ marginTop: 8 }}>Custom prompt: <strong style={{ color: "var(--text)" }}>{client.system_prompt ? "Yes" : "No (using default)"}</strong></p>
              {client.system_prompt && <div style={{ marginTop: 12, background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: 8, padding: 12, fontFamily: "var(--mono)", fontSize: 11, color: "var(--muted)", maxHeight: 200, overflowY: "auto", whiteSpace: "pre-wrap" }}>{client.system_prompt}</div>}
            </div>
          </div>
        </div>
      </div>

      {showResetModal && (
        <div className="overlay" onClick={() => setShowResetModal(false)}>
          <div className="modal" style={{ width: 400 }} onClick={e => e.stopPropagation()}>
            <div className="modal-title">Reset Client Credentials</div>
            <div className="form-group"><label className="form-label">New Username</label><input className="form-input" value={resetForm.username} onChange={e => setResetForm({ ...resetForm, username: e.target.value })} /></div>
            <div className="form-group"><label className="form-label">New Temporary Password</label><input className="form-input" type="password" value={resetForm.password} onChange={e => setResetForm({ ...resetForm, password: e.target.value })} /></div>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setShowResetModal(false)}>Cancel</button>
              <button className="btn btn-warning" onClick={handleResetCreds}>Reset</button>
            </div>
          </div>
        </div>
      )}

      {showEditModal && (
        <div className="overlay" onClick={() => setShowEditModal(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-title">Edit Client Info</div>
            {["institute_name", "persona_name", "twilio_account_sid", "twilio_phone_number", "webhook_url"].map(key => (
              <div className="form-group" key={key}>
                <label className="form-label">{key.replace(/_/g, " ")}</label>
                <input className="form-input" value={editForm[key] || ""} onChange={e => setEditForm({ ...editForm, [key]: e.target.value })} />
              </div>
            ))}
            <div className="form-group"><label className="form-label">Auth Token (blank = keep existing)</label><input className="form-input" type="password" placeholder="••••••••" onChange={e => setEditForm({ ...editForm, twilio_auth_token: e.target.value })} /></div>
            <div className="form-group"><label className="form-label">System Prompt</label><textarea className="form-textarea" value={editForm.system_prompt || ""} onChange={e => setEditForm({ ...editForm, system_prompt: e.target.value })} /></div>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setShowEditModal(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={handleSaveEdit}>Save</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// =====================================================
// ROOT
// =====================================================
export default function MasterApp() {
  const [authed, setAuthed] = useState(!!localStorage.getItem("master_token"));
  const [view, setView] = useState("dashboard");
  const [selectedClientId, setSelectedClientId] = useState(null);
  const [showAddModal, setShowAddModal] = useState(false);

  if (!authed) return <LoginScreen onLogin={() => setAuthed(true)} />;

  const handleSelectClient = (id) => { setSelectedClientId(id); setView("client-detail"); };

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-name">Ai Studio</div>
          <div className="brand-tag">Master</div>
        </div>
        <nav className="sidebar-nav">
          <div className="nav-section">Navigation</div>
          <button className={`nav-btn ${view === "dashboard" ? "active" : ""}`} onClick={() => setView("dashboard")}>🏠 Dashboard</button>
          <button className={`nav-btn ${view === "client-detail" ? "active" : ""}`} style={{ opacity: selectedClientId ? 1 : 0.4, pointerEvents: selectedClientId ? "auto" : "none" }}>🏫 Client Detail</button>
          <div className="nav-section">Actions</div>
          <button className="nav-btn" onClick={() => setShowAddModal(true)}>➕ Add Client</button>
        </nav>
        <div className="sidebar-bottom">
          <span className="sidebar-user">Master Admin</span>
          <button className="logout-btn" onClick={() => { localStorage.removeItem("master_token"); setAuthed(false); }}>Logout</button>
        </div>
      </aside>
      <main className="main">
        <div className="topbar">
          <div>
            <div className="page-title">{view === "dashboard" ? "Dashboard" : "Client Detail"}</div>
            <div className="page-sub">{view === "dashboard" ? "All client accounts overview" : "Manage client settings and credentials"}</div>
          </div>
          {view === "dashboard" && <button className="btn btn-primary" onClick={() => setShowAddModal(true)}>+ Add Client</button>}
        </div>
        <div className="content">
          {view === "dashboard" && <Dashboard onSelectClient={handleSelectClient} />}
          {view === "client-detail" && selectedClientId && <ClientDetail clientId={selectedClientId} onBack={() => setView("dashboard")} />}
        </div>
      </main>
      {showAddModal && <AddClientModal onClose={() => setShowAddModal(false)} onCreated={() => { setShowAddModal(false); setView("dashboard"); }} />}
    </div>
  );
}
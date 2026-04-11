import { useEffect, useState } from "react";

const TIMEFRAME_OPTIONS = [
  { value: "all", label: "All Time" },
  { value: "today", label: "Today" },
  { value: "yesterday", label: "Yesterday" },
  { value: "last_7_days", label: "Last 7 Days" },
  { value: "last_30_days", label: "Last 30 Days" },
];

function toIstDate(dateLike) {
  if (!dateLike) return null;
  const date = new Date(dateLike);
  if (Number.isNaN(date.getTime())) return null;
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(date);
  const map = Object.fromEntries(parts.filter(part => part.type !== "literal").map(part => [part.type, part.value]));
  return new Date(`${map.year}-${map.month}-${map.day}T${map.hour}:${map.minute}:${map.second}`);
}

function startOfDay(date) {
  const next = new Date(date);
  next.setHours(0, 0, 0, 0);
  return next;
}

function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function resolveBounds(range) {
  const now = toIstDate(new Date());
  const todayStart = startOfDay(now);
  if (range === "all") return { start: null, end: null };
  if (range === "today") return { start: todayStart, end: addDays(todayStart, 1) };
  if (range === "yesterday") return { start: addDays(todayStart, -1), end: todayStart };
  if (range === "last_7_days") return { start: addDays(todayStart, -6), end: addDays(todayStart, 1) };
  return { start: addDays(todayStart, -29), end: addDays(todayStart, 1) };
}

function filterByRange(items, range) {
  const { start, end } = resolveBounds(range);
  if (!start) return items;
  return items.filter(item => {
    const created = toIstDate(item.created_at);
    return created && created >= start && created < end;
  });
}

function normalizeInterest(value) {
  return (value || "").trim().toUpperCase() || "Unknown";
}

function buildHourlySeries(leads) {
  const counts = Array.from({ length: 24 }, (_, hour) => ({ label: `${String(hour).padStart(2, "0")}:00`, value: 0 }));
  leads.forEach(lead => {
    const created = toIstDate(lead.created_at);
    if (created) counts[created.getHours()].value += 1;
  });
  return counts;
}

function buildDailySeries(leads, days) {
  const { start } = resolveBounds(days === 7 ? "last_7_days" : "last_30_days");
  const counts = Array.from({ length: days }, (_, index) => {
    const current = addDays(start, index);
    return {
      key: current.toDateString(),
      label: current.toLocaleDateString("en-IN", { day: "2-digit", month: "short" }),
      value: 0,
    };
  });
  const byKey = Object.fromEntries(counts.map(item => [item.key, item]));
  leads.forEach(lead => {
    const created = toIstDate(lead.created_at);
    if (!created) return;
    const key = startOfDay(created).toDateString();
    if (byKey[key]) byKey[key].value += 1;
  });
  return counts.map(({ label, value }) => ({ label, value }));
}

function buildAllTimeSeries(leads) {
  if (!leads.length) return [];
  const sortedDays = leads
    .map(lead => toIstDate(lead.created_at))
    .filter(Boolean)
    .map(date => startOfDay(date))
    .sort((a, b) => a - b);
  if (!sortedDays.length) return [];

  const start = sortedDays[0];
  const end = startOfDay(toIstDate(new Date()));
  const counts = {};
  sortedDays.forEach(day => {
    const key = day.toDateString();
    counts[key] = (counts[key] || 0) + 1;
  });

  const points = [];
  let running = 0;
  for (let current = new Date(start); current <= end; current = addDays(current, 1)) {
    const key = current.toDateString();
    running += counts[key] || 0;
    points.push({
      label: current.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }),
      value: running,
    });
  }
  return points;
}

function buildDistribution(leads) {
  const counts = {};
  leads.forEach(lead => {
    const label = normalizeInterest(lead.service_interest);
    counts[label] = (counts[label] || 0) + 1;
  });
  const total = Object.values(counts).reduce((sum, count) => sum + count, 0);
  const breakdown = Object.entries(counts)
    .sort((a, b) => (b[1] - a[1]) || a[0].localeCompare(b[0]))
    .map(([label, count]) => ({
      label,
      count,
      percentage: total ? Number(((count / total) * 100).toFixed(1)) : 0,
    }));
  return { total, top: breakdown.slice(0, 5), breakdown };
}

function buildFrontendAnalytics(leads, appointments, range) {
  const filteredLeads = filterByRange(leads, range);
  const filteredAppointments = filterByRange(appointments, range);
  let leadGrowthDistribution;

  if (range === "all") {
    leadGrowthDistribution = {
      chart_type: "line",
      granularity: "cumulative_daily",
      points: buildAllTimeSeries(filteredLeads),
    };
  } else if (range === "today" || range === "yesterday") {
    leadGrowthDistribution = {
      chart_type: "bar",
      granularity: "hourly",
      points: buildHourlySeries(filteredLeads),
    };
  } else {
    const days = range === "last_7_days" ? 7 : 30;
    leadGrowthDistribution = {
      chart_type: "bar",
      granularity: "daily",
      points: buildDailySeries(filteredLeads, days),
    };
  }

  return {
    range,
    kpis: {
      total_leads: filteredLeads.length,
      total_appointments: filteredAppointments.length,
    },
    lead_growth_distribution: leadGrowthDistribution,
    enquiry_type_distribution: buildDistribution(filteredLeads),
  };
}

function formatNumber(value) {
  return new Intl.NumberFormat("en-IN").format(value || 0);
}

function ChartShell({ title, subtitle, children, action }) {
  return (
    <div className="card analytics-card">
      <div className="card-header analytics-card-header">
        <div>
          <div className="card-title">{title}</div>
          {subtitle && <div className="analytics-card-sub">{subtitle}</div>}
        </div>
        {action}
      </div>
      <div className="analytics-card-body">{children}</div>
    </div>
  );
}

function EmptyChart({ message }) {
  return (
    <div className="analytics-empty">
      <div className="analytics-empty-icon">+</div>
      <div>{message}</div>
    </div>
  );
}

function BarChart({ points }) {
  if (!points.length) return <EmptyChart message="No enquiry activity in this period" />;

  const values = points.map(point => point.value);
  const max = Math.max(...values, 1);

  return (
    <div className="chart-wrap">
      <div className="chart-bars">
        {points.map(point => (
          <div key={point.label} className="chart-bar-item">
            <div className="chart-bar-value">{point.value}</div>
            <div className="chart-bar-track">
              <div
                className="chart-bar-fill"
                style={{ height: `${Math.max((point.value / max) * 100, point.value ? 10 : 0)}%` }}
              />
            </div>
            <div className="chart-bar-label">{point.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function LineChart({ points }) {
  if (!points.length) return <EmptyChart message="No enquiry activity in this period" />;

  const width = 920;
  const height = 300;
  const padding = 24;
  const values = points.map(point => point.value);
  const max = Math.max(...values, 1);
  const stepX = points.length > 1 ? (width - padding * 2) / (points.length - 1) : 0;

  const coords = points.map((point, index) => {
    const x = padding + (stepX * index);
    const y = height - padding - ((point.value / max) * (height - padding * 2));
    return { x, y, value: point.value, label: point.label };
  });

  const path = coords.map((coord, index) => `${index === 0 ? "M" : "L"} ${coord.x} ${coord.y}`).join(" ");
  const lastCoord = coords[coords.length - 1];
  const areaPath = `${path} L ${lastCoord.x} ${height - padding} L ${coords[0].x} ${height - padding} Z`;

  return (
    <div className="chart-wrap line-chart-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} className="line-chart" preserveAspectRatio="none">
        <defs>
          <linearGradient id="leadAreaGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="rgba(217,119,87,0.32)" />
            <stop offset="100%" stopColor="rgba(217,119,87,0)" />
          </linearGradient>
        </defs>
        {[0, 1, 2, 3].map(line => {
          const y = padding + (((height - padding * 2) / 3) * line);
          return <line key={line} x1={padding} x2={width - padding} y1={y} y2={y} className="line-chart-grid" />;
        })}
        <path d={areaPath} fill="url(#leadAreaGradient)" />
        <path d={path} className="line-chart-path" />
        {coords.map(coord => (
          <circle key={coord.label} cx={coord.x} cy={coord.y} r="4" className="line-chart-dot" />
        ))}
      </svg>
      <div className="line-chart-labels">
        {points.map((point, index) => (
          <span key={point.label} className={index % Math.ceil(points.length / 8 || 1) === 0 || index === points.length - 1 ? "line-chart-label show" : "line-chart-label"}>
            {point.label}
          </span>
        ))}
      </div>
    </div>
  );
}

function EnquiryDistribution({ distribution, onOpenDrawer }) {
  const top = distribution?.top || [];

  return (
    <ChartShell
      title="Enquiry Type Distribution"
      subtitle="Top five service interests by lead volume"
      action={<button className="btn btn-ghost" onClick={onOpenDrawer}>View breakdown</button>}
    >
      {!top.length ? (
        <EmptyChart message="No enquiry types recorded for this period" />
      ) : (
        <div className="dist-list">
          {top.map(item => (
            <div key={item.label} className="dist-item">
              <div className="dist-copy">
                <div className="dist-title">{item.label}</div>
                <div className="dist-meta">{item.count} leads</div>
              </div>
              <div className="dist-track">
                <div className="dist-fill" style={{ width: `${item.percentage}%` }} />
              </div>
              <div className="dist-pct">{item.percentage}%</div>
            </div>
          ))}
        </div>
      )}
    </ChartShell>
  );
}

function BreakdownDrawer({ open, onClose, distribution }) {
  const items = distribution?.breakdown || [];

  return (
    <div className={`analytics-drawer-shell ${open ? "open" : ""}`} aria-hidden={!open}>
      <button className={`analytics-drawer-backdrop ${open ? "open" : ""}`} onClick={onClose} aria-label="Close breakdown" />
      <aside className={`analytics-drawer ${open ? "open" : ""}`}>
        <div className="analytics-drawer-head">
          <div>
            <div className="analytics-drawer-eyebrow">Enquiry Type Breakdown</div>
            <div className="analytics-drawer-title">All service interests</div>
          </div>
          <button className="analytics-drawer-close" onClick={onClose}>Close</button>
        </div>
        <div className="analytics-drawer-body">
          {!items.length ? (
            <EmptyChart message="No service-interest data available" />
          ) : (
            items.map(item => (
              <div key={item.label} className="drawer-item">
                <div>
                  <div className="drawer-item-title">{item.label}</div>
                  <div className="drawer-item-meta">{item.count} leads</div>
                </div>
                <div className="drawer-item-right">{item.percentage}%</div>
              </div>
            ))
          )}
        </div>
      </aside>
    </div>
  );
}

export default function AnalyticsView({ authFetch }) {
  const [range, setRange] = useState("all");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadAnalytics() {
      setLoading(true);
      setError("");
      try {
        const res = await authFetch(`/api/client/analytics?range=${range}`);
        const payload = await res.json().catch(() => ({}));
        if (res.ok) {
          if (!cancelled) setData(payload);
          return;
        }

        if (res.status === 404) {
          const [leadsRes, apptsRes] = await Promise.all([
            authFetch("/api/client/leads"),
            authFetch("/api/client/appointments"),
          ]);
          const [leadsPayload, apptsPayload] = await Promise.all([leadsRes.json(), apptsRes.json()]);
          if (!leadsRes.ok || !apptsRes.ok) {
            throw new Error("Failed to load analytics");
          }
          if (!cancelled) setData(buildFrontendAnalytics(leadsPayload, apptsPayload, range));
          return;
        }

        throw new Error(payload.detail || "Failed to load analytics");
      } catch (err) {
        if (!cancelled) setError(err.message || "Failed to load analytics");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadAnalytics();
    return () => {
      cancelled = true;
    };
  }, [authFetch, range]);

  const chart = data?.lead_growth_distribution;
  const kpis = data?.kpis || { total_leads: 0, total_appointments: 0 };
  const enquiry = data?.enquiry_type_distribution || { top: [], breakdown: [], total: 0 };

  return (
    <>
      <div className="analytics-toolbar">
        <div>
          <div className="analytics-toolbar-title">Analytics</div>
          <div className="analytics-toolbar-sub">A live view of enquiry volume, appointments, and interest mix</div>
        </div>
        <div className="analytics-filter-group">
          {TIMEFRAME_OPTIONS.map(option => (
            <button
              key={option.value}
              className={`filter-chip ${range === option.value ? "active" : ""}`}
              onClick={() => setRange(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="stats-row analytics-kpi-row">
        <div className="stat-card stat-card-hero">
          <div className="stat-label">Total Leads</div>
          <div className="stat-value">{loading ? "..." : formatNumber(kpis.total_leads)}</div>
          <div className="stat-sub">Qualified by the selected timeframe</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total Appointments</div>
          <div className="stat-value">{loading ? "..." : formatNumber(kpis.total_appointments)}</div>
          <div className="stat-sub">Callbacks booked in the selected timeframe</div>
        </div>
        <div className="stat-card stat-card-soft">
          <div className="stat-label">Enquiries Captured</div>
          <div className="stat-value">{loading ? "..." : formatNumber(enquiry.total)}</div>
          <div className="stat-sub">Lead records used for distribution analysis</div>
        </div>
      </div>

      <div className="analytics-grid">
        <ChartShell
          title="Leads Growth Distribution"
          subtitle={chart?.chart_type === "line" ? "Cumulative enquiry growth across all time" : "Enquiry volume across the selected period"}
        >
          {loading
            ? <div className="loading"><div className="spinner" />Loading...</div>
            : chart?.chart_type === "line"
              ? <LineChart points={chart.points || []} />
              : <BarChart points={chart?.points || []} />}
        </ChartShell>

        <EnquiryDistribution distribution={enquiry} onOpenDrawer={() => setDrawerOpen(true)} />
      </div>

      <BreakdownDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} distribution={enquiry} />
    </>
  );
}

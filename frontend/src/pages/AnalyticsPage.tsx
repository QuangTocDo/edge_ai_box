import { Activity, Gauge, Radio, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { EmptyState, MetricCard, PageLoader } from "../components/UI";
import { api } from "../services/api";
import type { Analytics } from "../types";
import { readableType } from "../utils";

const COLORS = ["#6366f1", "#06b6d4", "#f43f5e", "#f59e0b", "#10b981", "#8b5cf6"];

export function AnalyticsPage() {
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = () => api.analytics().then(setData).catch((e) => setError(e.message));
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, []);

  if (!data && !error) return <PageLoader />;
  if (error) return <div className="error-banner">{error}</div>;
  if (!data) return null;

  const typeData = Object.entries(data.by_type).map(([name, value]) => ({ name: readableType(name), value }));
  const severityData = Object.entries(data.by_severity).map(([name, count]) => ({ name, count }));
  const empty = data.total_violations === 0;

  return (
    <div className="page-stack">
      <div className="page-heading">
        <div>
          <span className="eyebrow">Deep Intelligence</span>
          <h1>Traffic Analytics & Trends</h1>
          <p>Multi-source violation patterns, velocity telemetry, and temporal hotspot analytics.</p>
        </div>
      </div>

      <section className="metric-grid">
        <MetricCard label="Total Violations" value={data.total_violations} icon={ShieldAlert} tone="red" detail={`${data.live_total} live · ${data.job_total} from video`} />
        <MetricCard label="Average Speed" value={data.avg_speed_kmh != null ? `${data.avg_speed_kmh}` : "—"} icon={Gauge} tone="amber" detail="km/h across speed events" />
        <MetricCard label="Top Speed" value={data.max_speed_kmh != null ? `${data.max_speed_kmh}` : "—"} icon={Activity} tone="gray" detail="km/h peak recorded" />
        <MetricCard label="Live Sources" value={data.live_total} icon={Radio} tone="green" detail="Violations from cameras" />
      </section>

      {empty ? (
        <section className="panel"><EmptyState title="No analytics yet" body="Process a video or run a calibrated live camera to populate trends." /></section>
      ) : (
        <>
          <section className="panel chart-panel">
            <div className="panel-heading"><div><span>Historical Timeline</span><h2>Violations Over the Last 14 Days</h2></div></div>
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={data.daily} margin={{ top: 8, right: 16, left: -18, bottom: 0 }}>
                <defs>
                  <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#6366f1" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--line-subtle)" vertical={false} />
                <XAxis dataKey="date" tickLine={false} axisLine={false} stroke="var(--muted)" fontSize={11} />
                <YAxis allowDecimals={false} tickLine={false} axisLine={false} stroke="var(--muted)" fontSize={11} />
                <Tooltip contentStyle={{ backgroundColor: "var(--surface)", borderColor: "var(--line)", borderRadius: "8px", color: "var(--ink)", boxShadow: "0 8px 24px rgba(0,0,0,0.3)" }} />
                <Area type="monotone" dataKey="count" stroke="#6366f1" strokeWidth={2.5} fill="url(#g)" />
              </AreaChart>
            </ResponsiveContainer>
          </section>

          <section className="overview-grid">
            <article className="panel chart-panel">
              <div className="panel-heading"><div><span>Violation Breakdown</span><h2>By Rule Category</h2></div></div>
              <div className="chart-layout">
                <ResponsiveContainer width="55%" height={230}>
                  <PieChart>
                    <Pie data={typeData} dataKey="value" nameKey="name" innerRadius={58} outerRadius={88} paddingAngle={4}>
                      {typeData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                    </Pie>
                    <Tooltip contentStyle={{ backgroundColor: "var(--surface)", borderColor: "var(--line)", borderRadius: "8px", color: "var(--ink)", boxShadow: "0 8px 24px rgba(0,0,0,0.3)" }} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="chart-legend">
                  {typeData.map((it, i) => (
                    <div key={it.name}>
                      <i style={{ background: COLORS[i % COLORS.length] }} />
                      <span>{it.name}</span>
                      <b>{it.value}</b>
                    </div>
                  ))}
                </div>
              </div>
            </article>

            <article className="panel chart-panel">
              <div className="panel-heading"><div><span>Risk Profile</span><h2>By Severity Rating</h2></div></div>
              <ResponsiveContainer width="100%" height={230}>
                <BarChart data={severityData} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
                  <CartesianGrid stroke="var(--line-subtle)" vertical={false} />
                  <XAxis dataKey="name" tickLine={false} axisLine={false} stroke="var(--muted)" />
                  <YAxis allowDecimals={false} tickLine={false} axisLine={false} stroke="var(--muted)" />
                  <Tooltip contentStyle={{ backgroundColor: "var(--surface)", borderColor: "var(--line)", borderRadius: "8px", color: "var(--ink)", boxShadow: "0 8px 24px rgba(0,0,0,0.3)" }} />
                  <Bar dataKey="count" fill="#f43f5e" radius={[6, 6, 0, 0]} maxBarSize={54} />
                </BarChart>
              </ResponsiveContainer>
            </article>
          </section>

          <section className="overview-grid">
            <article className="panel chart-panel">
              <div className="panel-heading"><div><span>Temporal Heatmap</span><h2>Violations by Hour of Day</h2></div></div>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={data.by_hour} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
                  <CartesianGrid stroke="var(--line-subtle)" vertical={false} />
                  <XAxis dataKey="hour" tickLine={false} axisLine={false} stroke="var(--muted)" fontSize={10} interval={1} />
                  <YAxis allowDecimals={false} tickLine={false} axisLine={false} stroke="var(--muted)" fontSize={11} />
                  <Tooltip contentStyle={{ backgroundColor: "var(--surface)", borderColor: "var(--line)", borderRadius: "8px", color: "var(--ink)", boxShadow: "0 8px 24px rgba(0,0,0,0.3)" }} />
                  <Bar dataKey="count" fill="#06b6d4" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </article>

            <article className="panel chart-panel">
              <div className="panel-heading"><div><span>Speed Telemetry</span><h2>Speed Distribution (km/h)</h2></div></div>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={data.speed_histogram} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
                  <CartesianGrid stroke="var(--line-subtle)" vertical={false} />
                  <XAxis dataKey="bucket" tickLine={false} axisLine={false} stroke="var(--muted)" fontSize={11} />
                  <YAxis allowDecimals={false} tickLine={false} axisLine={false} stroke="var(--muted)" fontSize={11} />
                  <Tooltip contentStyle={{ backgroundColor: "var(--surface)", borderColor: "var(--line)", borderRadius: "8px", color: "var(--ink)", boxShadow: "0 8px 24px rgba(0,0,0,0.3)" }} />
                  <Bar dataKey="count" fill="#f59e0b" radius={[6, 6, 0, 0]} maxBarSize={48} />
                </BarChart>
              </ResponsiveContainer>
            </article>
          </section>

          <section className="panel">
            <div className="panel-heading"><div><span>Camera & Stream Feeds</span><h2>Top Violation Hotspots</h2></div></div>
            {data.top_sources.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Source Name</th><th>Total Incidents Detected</th></tr>
                  </thead>
                  <tbody>
                    {data.top_sources.map((s) => (
                      <tr key={s.name}>
                        <td><strong>{s.name}</strong></td>
                        <td className="mono">{s.count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <EmptyState title="No sources yet" body="Sources appear once violations are recorded." />}
          </section>
        </>
      )}
    </div>
  );
}

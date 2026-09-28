import { AlertTriangle, CheckCircle2, Clock3, Film, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { EmptyState, EventType, MetricCard, PageLoader, SeverityBadge } from "../components/UI";
import { api } from "../services/api";
import type { Overview } from "../types";
import { formatDate, formatDuration, readableType } from "../utils";

const COLORS = ["#6366f1", "#06b6d4", "#f43f5e", "#f59e0b", "#10b981", "#8b5cf6"];

export function OverviewPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.overview().then(setOverview).catch((err) => setError(err.message));
  }, []);

  if (!overview && !error) return <PageLoader />;
  if (error) return <div className="error-banner">{error}</div>;
  if (!overview) return null;

  const violationData = Object.entries(overview.violations_by_type).map(([name, value]) => ({ name: readableType(name), value }));
  const severityData = Object.entries(overview.severity_counts).map(([name, count]) => ({ name, count }));

  return (
    <div className="page-stack">
      <div className="page-heading">
        <div>
          <span className="eyebrow">Smart City Center</span>
          <h1>Network Overview</h1>
          <p>Real-time traffic AI pipeline status, automated detection health, and violation telemetry.</p>
        </div>
        <Link className="button button-primary" to="/jobs">
          <Film size={17} />
          Process video
        </Link>
      </div>

      <section className="metric-grid">
        <MetricCard label="Processed Videos" value={overview.completed_jobs} icon={CheckCircle2} tone="green" detail={`${overview.total_jobs} total jobs`} />
        <MetricCard label="Confirmed Events" value={overview.total_events} icon={ShieldAlert} tone="red" detail="Violations detected" />
        <MetricCard label="Active Queue" value={overview.processing_jobs} icon={Clock3} tone="amber" detail="Queued or processing" />
        <MetricCard label="Failed Jobs" value={overview.failed_jobs} icon={AlertTriangle} tone="gray" detail="Requires inspection" />
      </section>

      <section className="overview-grid">
        <article className="panel chart-panel">
          <div className="panel-heading">
            <div>
              <span>Distribution</span>
              <h2>Events by Rule</h2>
            </div>
          </div>
          {violationData.length ? (
            <div className="chart-layout">
              <ResponsiveContainer width="55%" height={230}>
                <PieChart>
                  <Pie data={violationData} dataKey="value" nameKey="name" innerRadius={58} outerRadius={88} paddingAngle={4}>
                    {violationData.map((_, index) => (
                      <Cell key={index} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "var(--surface)",
                      borderColor: "var(--line)",
                      borderRadius: "8px",
                      color: "var(--ink)",
                      boxShadow: "0 8px 24px rgba(0,0,0,0.3)",
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="chart-legend">
                {violationData.map((item, index) => (
                  <div key={item.name}>
                    <i style={{ background: COLORS[index % COLORS.length] }} />
                    <span>{item.name}</span>
                    <b>{item.value}</b>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <EmptyState title="No events yet" body="Processed violation events will appear here." />
          )}
        </article>

        <article className="panel chart-panel">
          <div className="panel-heading">
            <div>
              <span>Risk Profile</span>
              <h2>Events by Severity</h2>
            </div>
          </div>
          {severityData.length ? (
            <ResponsiveContainer width="100%" height={230}>
              <BarChart data={severityData} margin={{ top: 12, right: 16, left: -18, bottom: 0 }}>
                <CartesianGrid stroke="var(--line-subtle)" vertical={false} />
                <XAxis dataKey="name" tickLine={false} axisLine={false} stroke="var(--muted)" fontSize={11} />
                <YAxis allowDecimals={false} tickLine={false} axisLine={false} stroke="var(--muted)" fontSize={11} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "var(--surface)",
                    borderColor: "var(--line)",
                    borderRadius: "8px",
                    color: "var(--ink)",
                    boxShadow: "0 8px 24px rgba(0,0,0,0.3)",
                  }}
                />
                <Bar dataKey="count" fill="#6366f1" radius={[6, 6, 0, 0]} maxBarSize={48} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState title="No severity data" body="Severity distribution appears after the first detected event." />
          )}
        </article>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <span>Latest Detections</span>
            <h2>Recent Violations & Incidents</h2>
          </div>
          <Link to="/jobs" className="text-link">
            View all jobs
          </Link>
        </div>
        {overview.recent_events.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Event Type</th>
                  <th>Severity</th>
                  <th>Track</th>
                  <th>Timestamp</th>
                  <th>Speed</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {overview.recent_events.map((event) => (
                  <tr key={event.id}>
                    <td>
                      <EventType type={event.type} />
                    </td>
                    <td>
                      <SeverityBadge severity={event.severity} />
                    </td>
                    <td className="mono">ID {event.track_id}</td>
                    <td>{formatDuration(event.time_s)}</td>
                    <td>{event.speed_kmh ? `${event.speed_kmh.toFixed(1)} km/h` : "—"}</td>
                    <td>
                      <Link className="row-link" to={`/events/${event.id}`}>
                        Review Evidence
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="No recent detections" body="Upload and process a traffic video to populate the event review queue." />
        )}
      </section>

      <footer className="page-footnote">AI Vision Engine active · Refreshed {formatDate(new Date().toISOString())}</footer>
    </div>
  );
}

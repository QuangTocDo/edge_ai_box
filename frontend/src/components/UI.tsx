import { Inbox, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { readableType } from "../utils";

export function StatusBadge({ status }: { status: string }) {
  return <span className={`status-badge status-${status.toLowerCase()}`}><i />{status}</span>;
}

export function SeverityBadge({ severity }: { severity: string }) {
  return <span className={`severity severity-${severity.toLowerCase()}`}>{severity}</span>;
}

export function EventType({ type }: { type: string }) {
  return <span className="event-type">{readableType(type)}</span>;
}

export function MetricCard({ label, value, icon: Icon, tone, detail }: {
  label: string;
  value: number | string;
  icon: LucideIcon;
  tone: string;
  detail: string;
}) {
  return (
    <article className="metric-card">
      <div className={`metric-icon metric-${tone}`}><Icon size={20} /></div>
      <div className="metric-copy"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>
    </article>
  );
}

export function EmptyState({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <div className="empty-state">
      <div className="empty-icon"><Inbox size={24} /></div>
      <strong>{title}</strong>
      <p>{body}</p>
      {action}
    </div>
  );
}

export function ProgressBar({ value }: { value: number }) {
  return <div className="progress-track"><span style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></div>;
}

export function PageLoader() {
  return <div className="page-loader"><span /><span /><span /></div>;
}


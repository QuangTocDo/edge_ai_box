import { AlertCircle, ArrowLeft, Download, Film, Filter, Play, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { EmptyState, EventType, PageLoader, ProgressBar, SeverityBadge, StatusBadge } from "../components/UI";
import { api, jobVideoUrl, websocketUrl } from "../services/api";
import type { ProcessingJob, ViolationEvent } from "../types";
import { formatDate, formatDuration, readableType } from "../utils";

export function JobDetailPage() {
  const { jobId = "" } = useParams();
  const [job, setJob] = useState<ProcessingJob | null>(null);
  const [events, setEvents] = useState<ViolationEvent[]>([]);
  const [filter, setFilter] = useState("all");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const nextJob = await api.job(jobId); setJob(nextJob);
      if (nextJob.status === "completed") setEvents(await api.events(jobId));
    } catch (err) { setError(err instanceof Error ? err.message : "Could not load job"); }
  }, [jobId]);

  useEffect(() => { load(); const timer = window.setInterval(load, 2500); return () => window.clearInterval(timer); }, [load]);
  useEffect(() => {
    if (!jobId) return;
    const socket = new WebSocket(websocketUrl(jobId));
    socket.onmessage = () => load();
    return () => socket.close();
  }, [jobId, load]);

  const types = useMemo(() => Array.from(new Set(events.map((event) => event.type))), [events]);
  const filtered = filter === "all" ? events : events.filter((event) => event.type === filter);
  if (!job && !error) return <PageLoader />;
  if (error) return <div className="error-banner">{error}</div>;
  if (!job) return null;

  return (
    <div className="page-stack">
      <Link className="back-link" to="/jobs"><ArrowLeft size={16} />Back to video jobs</Link>
      <div className="page-heading job-heading"><div><span className="eyebrow">Video review</span><h1>{job.original_filename}</h1><div className="inline-meta"><StatusBadge status={job.status} /><span>Created {formatDate(job.created_at)}</span><span className="mono">{job.id.slice(0, 8)}</span></div></div>{job.status === "failed" && <button className="button button-primary" onClick={() => api.process(job.id).then(load)}><RefreshCw size={16} />Retry</button>}</div>

      {(job.status === "queued" || job.status === "processing") && <section className="processing-strip"><div className="processing-copy"><span className="processing-pulse" /><div><strong>{job.status === "queued" ? "Waiting for vision worker" : "Analyzing traffic footage"}</strong><span>{job.current_frame.toLocaleString()} of {job.total_frames ? job.total_frames.toLocaleString() : "—"} frames</span></div></div><div className="processing-progress"><ProgressBar value={job.progress_percent} /><b>{job.progress_percent}%</b></div>{job.status === "queued" && <button className="button button-primary" onClick={() => api.process(job.id).then(load)}><Play size={16} />Start processing</button>}</section>}
      {job.status === "failed" && <div className="error-banner"><AlertCircle size={18} />{job.error_message}</div>}

      <section className="review-grid">
        <article className="video-panel">
          <div className="video-frame">{job.status === "completed" ? <video controls preload="metadata" src={jobVideoUrl(job.id)} /> : <div className="video-placeholder"><Film size={34} /><strong>Annotated video pending</strong><span>The player becomes available after processing completes.</span></div>}</div>
          <div className="video-footer"><div><span>Vision output</span><strong>{job.status === "completed" ? "Annotated H.264 · 1920 × 1080" : "Processing required"}</strong></div>{job.status === "completed" && <a className="button button-secondary" href={jobVideoUrl(job.id)} download><Download size={16} />Video</a>}</div>
        </article>
        <aside className="summary-panel"><span>Job summary</span><dl><div><dt>Confirmed events</dt><dd>{job.event_count}</dd></div><div><dt>Source</dt><dd>Uploaded file</dd></div><div><dt>Frames processed</dt><dd>{job.total_frames || "—"}</dd></div><div><dt>Rules active</dt><dd>3</dd></div></dl>{job.status === "completed" && <div className="download-stack"><a href={`/api/jobs/${job.id}/events.csv`} className="button button-secondary"><Download size={16} />Events CSV</a><a href={`/api/jobs/${job.id}/events.json`} className="button button-secondary"><Download size={16} />Events JSON</a></div>}</aside>
      </section>

      <section className="panel">
        <div className="panel-heading"><div><span>Evidence timeline</span><h2>Detected events</h2></div><label className="filter-control"><Filter size={15} /><select value={filter} onChange={(e) => setFilter(e.target.value)}><option value="all">All event types</option>{types.map((type) => <option key={type} value={type}>{readableType(type)}</option>)}</select></label></div>
        {filtered.length ? <div className="table-wrap"><table><thead><tr><th>Time</th><th>Event</th><th>Severity</th><th>Track</th><th>Speed</th><th>Signal</th><th /></tr></thead><tbody>{filtered.map((event) => <tr key={event.id}><td className="mono">{formatDuration(event.time_s)}</td><td><EventType type={event.type} /></td><td><SeverityBadge severity={event.severity} /></td><td>ID {event.track_id}</td><td>{event.speed_kmh ? `${event.speed_kmh.toFixed(1)} km/h` : "—"}</td><td>{event.light_phase ?? "—"}</td><td><Link className="row-link" to={`/events/${event.id}`}>Evidence</Link></td></tr>)}</tbody></table></div> : <EmptyState title="No matching events" body={job.status === "completed" ? "This video produced no events for the selected rule." : "Events will appear after processing completes."} />}
      </section>
    </div>
  );
}


import { ArrowLeft, Clock3, Gauge, Hash, MapPin, TrafficCone } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { EventType, PageLoader, SeverityBadge } from "../components/UI";
import { api, jobVideoUrl, mediaUrl } from "../services/api";
import type { ViolationEvent } from "../types";
import { formatDuration } from "../utils";

export function EventDetailPage() {
  const { eventId = "" } = useParams();
  const [event, setEvent] = useState<ViolationEvent | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { api.event(Number(eventId)).then(setEvent).catch((err) => setError(err.message)); }, [eventId]);
  if (!event && !error) return <PageLoader />;
  if (error) return <div className="error-banner">{error}</div>;
  if (!event) return null;

  return (
    <div className="page-stack">
      <Link className="back-link" to={`/jobs/${event.job_id}`}><ArrowLeft size={16} />Back to video review</Link>
      <div className="page-heading"><div><span className="eyebrow">Evidence record #{event.id}</span><h1><EventType type={event.type} /></h1><div className="inline-meta"><SeverityBadge severity={event.severity} /><span>Track ID {event.track_id}</span><span>{formatDuration(event.time_s)}</span></div></div></div>

      <section className="evidence-grid">
        <article className="evidence-media"><div className="panel-heading"><div><span>Primary evidence</span><h2>Event screenshot</h2></div></div>{event.screenshot_url ? <img src={mediaUrl(event.screenshot_url)} alt={`${event.type} evidence`} /> : <div className="video-placeholder">No screenshot available</div>}</article>
        <aside className="facts-panel"><span>Event facts</span><div className="fact-row"><Clock3 size={17} /><div><small>Video time</small><strong>{formatDuration(event.time_s)}</strong></div></div><div className="fact-row"><Hash size={17} /><div><small>Frame / track</small><strong>{event.frame} / ID {event.track_id}</strong></div></div><div className="fact-row"><Gauge size={17} /><div><small>Measured speed</small><strong>{event.speed_kmh ? `${event.speed_kmh.toFixed(1)} km/h` : "Not measured"}</strong></div></div><div className="fact-row"><TrafficCone size={17} /><div><small>Lane / signal</small><strong>{event.lane_id ?? "—"} / {event.light_phase ?? "—"}</strong></div></div><div className="fact-row"><MapPin size={17} /><div><small>World position</small><strong>{event.world_x?.toFixed(2) ?? "—"}, {event.world_y?.toFixed(2) ?? "—"} m</strong></div></div></aside>
      </section>

      <section className="review-grid event-review-grid">
        <article className="video-panel"><div className="panel-heading panel-heading-dark"><div><span>Evidence window</span><h2>Violation clip</h2></div></div><div className="video-frame">{event.clip_url ? <video controls src={mediaUrl(event.clip_url)} /> : <div className="video-placeholder">No evidence clip available</div>}</div></article>
        <aside className="summary-panel"><span>Full video context</span><p>Open the complete annotated recording at the event timestamp for broader review.</p><a className="button button-primary" href={`${jobVideoUrl(event.job_id)}#t=${Math.max(0, event.time_s - 2).toFixed(2)}`} target="_blank" rel="noreferrer">Open full video</a><div className="json-block"><small>Measured values</small><pre>{JSON.stringify(event.measured, null, 2)}</pre></div></aside>
      </section>
    </div>
  );
}


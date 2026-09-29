import { ArrowLeft, Play, RefreshCw, Square, SlidersHorizontal } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { EmptyState, PageLoader, SeverityBadge, StatusBadge } from "../components/UI";
import { useAuth } from "../auth/AuthContext";
import { api, cameraStreamUrl, cameraWebsocketUrl } from "../services/api";
import type { Camera, CameraEvent, CameraStatusMessage } from "../types";
import { formatDuration, readableType } from "../utils";

const RUNNING = new Set(["Live", "Connecting", "Reconnecting"]);

export function CameraDetailPage() {
  const { isAdmin } = useAuth();
  const navigate = useNavigate();
  const { cameraId } = useParams<{ cameraId: string }>();
  const [camera, setCamera] = useState<Camera | null>(null);
  const [events, setEvents] = useState<CameraEvent[]>([]);
  const [live, setLive] = useState<CameraStatusMessage | null>(null);
  const [error, setError] = useState("");
  const [streamKey, setStreamKey] = useState(0); // bump to force <img> reload
  const wsRef = useRef<WebSocket | null>(null);

  const loadCamera = () => cameraId && api.camera(cameraId).then(setCamera).catch((e) => setError(e.message));
  const loadEvents = () => cameraId && api.cameraEvents(cameraId).then(setEvents).catch(() => {});

  useEffect(() => {
    if (!cameraId) return;
    loadCamera();
    loadEvents();
    const ws = new WebSocket(cameraWebsocketUrl(cameraId));
    wsRef.current = ws;
    ws.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data) as CameraStatusMessage;
        if (data.type === "status") {
          setLive(data);
          loadEvents();
        }
      } catch {
        /* ignore malformed frames */
      }
    };
    const poll = setInterval(loadCamera, 5000);
    return () => {
      ws.close();
      clearInterval(poll);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameraId]);

  async function control(action: "start" | "stop" | "reconnect") {
    if (!cameraId) return;
    setError("");
    try {
      const fn =
        action === "start" ? api.startCamera : action === "stop" ? api.stopCamera : api.reconnectCamera;
      const updated = await fn(cameraId);
      setCamera(updated);
      setTimeout(() => setStreamKey((k) => k + 1), 500);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  if (!camera && !error) return <PageLoader />;
  if (error && !camera) return <div className="error-banner">{error}</div>;
  if (!camera) return null;

  const status = live?.status ?? camera.status;
  const isRunning = RUNNING.has(status);

  return (
    <div className="page-stack">
      <div className="page-heading">
        <div>
          <Link className="text-link" to="/cameras"><ArrowLeft size={15} /> Back to cameras</Link>
          <h1>{camera.name}</h1>
          <p className="mono">{camera.source_type} · {camera.source_uri}</p>
        </div>
        {isAdmin && (
          <div className="button-row">
            <button className="button button-secondary" onClick={() => navigate(`/cameras/${cameraId}/calibrate`)}>
              <SlidersHorizontal size={16} />Calibrate
            </button>
            {!isRunning ? (
              <button className="button button-primary" onClick={() => control("start")}><Play size={16} />Start</button>
            ) : (
              <button className="button" onClick={() => control("stop")}><Square size={16} />Stop</button>
            )}
            <button className="button" onClick={() => control("reconnect")}><RefreshCw size={16} />Reconnect</button>
          </div>
        )}
      </div>

      {error && <div className="error-banner">{error}</div>}

      {!camera.calibrated && (
        <div className="error-banner" style={{ background: "#fff7e6", color: "#8a5a00" }}>
          This camera is not calibrated. It tracks and draws vehicles but emits no violations until a homography is set.
        </div>
      )}

      <section className="overview-grid">
        <article className="panel">
          <div className="panel-heading"><div><span>Live feed</span><h2>Annotated stream</h2></div><StatusBadge status={status} /></div>
          {isRunning ? (
            <img
              key={streamKey}
              src={`${cameraStreamUrl(camera.id)}?t=${streamKey}`}
              alt="Live annotated feed"
              style={{ width: "100%", borderRadius: 8, background: "#000", display: "block" }}
              onError={() => {
                setTimeout(() => setStreamKey((k) => k + 1), 1000);
              }}
            />
          ) : (
            <EmptyState title="Stream offline" body="Start the camera to view the live annotated feed." />
          )}
          {live?.last_error && <small className="mono">{live.last_error}</small>}
        </article>

        <article className="panel">
          <div className="panel-heading"><div><span>Runtime</span><h2>Telemetry</h2></div></div>
          <div className="system-panel">
            <div className="system-line"><span>Status</span><b>{status}</b></div>
            <div className="system-line"><span>Processing FPS</span><b>{live?.fps ?? camera.fps ?? "—"}</b></div>
            <div className="system-line"><span>Active vehicles</span><b>{live?.active_vehicles ?? camera.active_vehicles ?? "—"}</b></div>
            <div className="system-line"><span>Frames processed</span><b>{live?.processed_frames ?? camera.processed_frames ?? 0}</b></div>
            <div className="system-line"><span>Calibrated</span><b>{camera.calibrated ? "Yes" : "No"}</b></div>
            <div className="system-line"><span>Total events</span><b>{camera.event_count}</b></div>
          </div>
        </article>
      </section>

      <section className="panel">
        <div className="panel-heading"><div><span>Detections</span><h2>Recent violations</h2></div></div>
        {events.length ? (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Event</th><th>Severity</th><th>Track</th><th>Time</th><th>Speed</th><th>Light</th><th>Evidence</th></tr></thead>
              <tbody>
                {events.map((ev) => (
                  <tr key={ev.id}>
                    <td>{readableType(ev.type)}</td>
                    <td><SeverityBadge severity={ev.severity} /></td>
                    <td className="mono">ID {ev.track_id}</td>
                    <td>{formatDuration(ev.time_s)}</td>
                    <td>{ev.speed_kmh ? `${ev.speed_kmh.toFixed(1)} km/h` : "—"}</td>
                    <td>{ev.light_phase ?? "—"}</td>
                    <td>
                      {ev.screenshot_url && <a className="text-link" href={ev.screenshot_url} target="_blank" rel="noreferrer">Image</a>}
                      {ev.clip_url && <> · <a className="text-link" href={ev.clip_url} target="_blank" rel="noreferrer">Clip</a></>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="No violations yet" body="Confirmed live violations will appear here as they are detected." />
        )}
      </section>
    </div>
  );
}

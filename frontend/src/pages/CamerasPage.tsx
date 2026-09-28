import { Plus, Radio, Trash2, Video } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { EmptyState, PageLoader, StatusBadge } from "../components/UI";
import { useAuth } from "../auth/AuthContext";
import { api } from "../services/api";
import type { Camera } from "../types";
import { formatDate } from "../utils";

const SOURCE_TYPES = [
  { value: "rtsp", label: "RTSP (IP camera)", placeholder: "rtsp://user:pass@host:554/stream" },
  { value: "webcam", label: "USB / local webcam", placeholder: "0" },
  { value: "file", label: "File loop (pseudo-camera)", placeholder: "/path/to/clip.mp4" },
  { value: "youtube", label: "YouTube live (detection only)", placeholder: "https://www.youtube.com/watch?v=..." },
  { value: "hls", label: "HLS stream (detection only)", placeholder: "https://.../playlist.m3u8" },
];

export function CamerasPage() {
  const { isAdmin } = useAuth();
  const [cameras, setCameras] = useState<Camera[] | null>(null);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [sourceType, setSourceType] = useState("rtsp");
  const [sourceUri, setSourceUri] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => api.cameras().then(setCameras).catch((e) => setError(e.message));

  useEffect(() => {
    load();
    const timer = setInterval(load, 4000);
    return () => clearInterval(timer);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.createCamera({ name, source_type: sourceType, source_uri: sourceUri });
      setName("");
      setSourceUri("");
      setShowForm(false);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    if (!confirm("Delete this camera and its recorded evidence?")) return;
    try {
      await api.deleteCamera(id);
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  if (!cameras && !error) return <PageLoader />;

  const placeholder = SOURCE_TYPES.find((s) => s.value === sourceType)?.placeholder;

  return (
    <div className="page-stack">
      <div className="page-heading">
        <div>
          <span className="eyebrow">Live sources</span>
          <h1>Live cameras</h1>
          <p>Monitor RTSP and webcam feeds in real time with on-stream violation detection.</p>
        </div>
        {isAdmin && (
          <button className="button button-primary" onClick={() => setShowForm((v) => !v)}>
            <Plus size={17} />Add camera
          </button>
        )}
      </div>

      {error && <div className="error-banner">{error}</div>}

      {showForm && isAdmin && (
        <section className="panel">
          <form className="page-stack" onSubmit={submit}>
            <label>
              <span>Name</span>
              <input value={name} onChange={(e) => setName(e.target.value)} required placeholder="North gate – NB approach" />
            </label>
            <label>
              <span>Source type</span>
              <select value={sourceType} onChange={(e) => setSourceType(e.target.value)}>
                {SOURCE_TYPES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
            </label>
            <label>
              <span>Source URI</span>
              <input value={sourceUri} onChange={(e) => setSourceUri(e.target.value)} required placeholder={placeholder} />
            </label>
            <small>New cameras start uncalibrated — they track and draw but emit no violations until a homography is set.</small>
            <div>
              <button className="button button-primary" type="submit" disabled={busy}>
                {busy ? "Saving…" : "Create camera"}
              </button>
            </div>
          </form>
        </section>
      )}

      <section className="panel">
        <div className="panel-heading"><div><span>Registered feeds</span><h2>All cameras</h2></div></div>
        {cameras && cameras.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Camera</th><th>Source</th><th>Status</th><th>Calibrated</th><th>FPS</th><th>Vehicles</th><th>Events</th><th>Added</th><th /></tr>
              </thead>
              <tbody>
                {cameras.map((cam) => (
                  <tr key={cam.id}>
                    <td><Link className="row-link" to={`/cameras/${cam.id}`}><Video size={15} /> {cam.name}</Link></td>
                    <td className="mono">{cam.source_type} · {cam.source_uri}</td>
                    <td><StatusBadge status={cam.status} /></td>
                    <td>{cam.calibrated ? "Yes" : <span className="severity severity-medium">No</span>}</td>
                    <td>{cam.fps ?? "—"}</td>
                    <td>{cam.active_vehicles ?? "—"}</td>
                    <td>{cam.event_count}</td>
                    <td>{formatDate(cam.created_at)}</td>
                    <td>
                      {isAdmin && (
                        <button className="icon-button" title="Delete camera" onClick={() => remove(cam.id)}>
                          <Trash2 size={16} />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="No cameras yet"
            body="Add an RTSP IP camera, a local webcam, or a file-loop pseudo-camera to start live monitoring."
            action={isAdmin ? <button className="button button-primary" onClick={() => setShowForm(true)}><Radio size={16} />Add your first camera</button> : undefined}
          />
        )}
      </section>
    </div>
  );
}

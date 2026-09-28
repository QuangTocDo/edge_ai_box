import { FileVideo2, Play, RefreshCw, Trash2, UploadCloud } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { EmptyState, PageLoader, ProgressBar, StatusBadge } from "../components/UI";
import { useAuth } from "../auth/AuthContext";
import { api } from "../services/api";
import type { ProcessingJob } from "../types";
import { formatDate } from "../utils";

export function JobsPage() {
  const { isAdmin } = useAuth();
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(() => api.jobs().then(setJobs).finally(() => setLoading(false)), []);
  useEffect(() => { load(); const timer = window.setInterval(load, 3000); return () => window.clearInterval(timer); }, [load]);

  async function upload(file?: File) {
    if (!file) return;
    setBusy(true); setMessage("");
    try { await api.upload(file); setMessage(`${file.name} added to the queue.`); await load(); }
    catch (err) { setMessage(err instanceof Error ? err.message : "Upload failed"); }
    finally { setBusy(false); if (inputRef.current) inputRef.current.value = ""; }
  }

  async function process(id: string) {
    setMessage("");
    try { await api.process(id); await load(); }
    catch (err) { setMessage(err instanceof Error ? err.message : "Could not start processing"); }
  }

  async function remove(id: string) {
    if (!window.confirm("Delete this job and its generated evidence?")) return;
    try { await api.deleteJob(id); await load(); }
    catch (err) { setMessage(err instanceof Error ? err.message : "Delete failed"); }
  }

  return (
    <div className="page-stack">
      <div className="page-heading"><div><span className="eyebrow">Recorded sources</span><h1>Video jobs</h1><p>Upload footage, run the vision pipeline, and review generated evidence.</p></div><button className="button button-secondary" onClick={load}><RefreshCw size={16} />Refresh</button></div>

      <section className="upload-layout">
        {isAdmin ? (
          <button className={`upload-zone ${dragging ? "upload-dragging" : ""}`} onClick={() => inputRef.current?.click()} onDragOver={(e) => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(e) => { e.preventDefault(); setDragging(false); upload(e.dataTransfer.files[0]); }} disabled={busy}>
            <span className="upload-icon"><UploadCloud size={25} /></span><strong>{busy ? "Uploading video…" : "Drop traffic footage here"}</strong><span>or choose an MP4, MOV, AVI, MKV, or M4V file</span><b>Choose video</b>
          </button>
        ) : (
          <div className="upload-zone upload-readonly"><span className="upload-icon"><UploadCloud size={25} /></span><strong>Read-only access</strong><span>Sign in as an administrator to upload and process footage.</span></div>
        )}
        <input ref={inputRef} className="visually-hidden" type="file" accept="video/*,.mkv" onChange={(e) => upload(e.target.files?.[0])} />
        <aside className="pipeline-note"><span>Processing pipeline</span><ol><li><i>1</i>Vehicle detection and tracking</li><li><i>2</i>Signal, speed, and rule evaluation</li><li><i>3</i>Evidence clip and event export</li></ol></aside>
      </section>
      {message && <div className="info-banner">{message}</div>}

      <section className="panel">
        <div className="panel-heading"><div><span>Processing queue</span><h2>All video jobs</h2></div><b className="count-chip">{jobs.length}</b></div>
        {loading ? <PageLoader /> : jobs.length ? (
          <div className="table-wrap"><table className="jobs-table"><thead><tr><th>Video</th><th>Status</th><th>Progress</th><th>Events</th><th>Created</th><th>Actions</th></tr></thead><tbody>{jobs.map((job) => <tr key={job.id}><td><Link className="file-cell file-cell-link" to={`/jobs/${job.id}`} title="Open job and watch annotated video"><span><FileVideo2 size={18} /></span><div><strong>{job.original_filename}</strong><small className="mono">{job.id.slice(0, 8)}</small></div></Link></td><td><StatusBadge status={job.status} /></td><td><div className="progress-cell"><ProgressBar value={job.progress_percent} /><span>{job.progress_percent}%</span></div></td><td>{job.event_count}</td><td>{formatDate(job.created_at)}</td><td><div className="action-row">{isAdmin && (job.status === "queued" || job.status === "failed") && <button className="icon-button" title={job.status === "failed" ? "Retry processing" : "Start processing"} onClick={() => process(job.id)}><Play size={17} /></button>}<Link className="icon-button" title="Open job" to={`/jobs/${job.id}`}><FileVideo2 size={17} /></Link>{isAdmin && <button className="icon-button danger" title="Delete job" disabled={job.status === "processing"} onClick={() => remove(job.id)}><Trash2 size={17} /></button>}</div></td></tr>)}</tbody></table></div>
        ) : <EmptyState title="No video jobs" body="Upload the reference clip or new traffic footage to begin." action={<button className="button button-primary" onClick={() => inputRef.current?.click()}><UploadCloud size={17} />Upload video</button>} />}
      </section>
    </div>
  );
}


import { ArrowLeft, Check, RotateCcw, Undo2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { PageLoader } from "../components/UI";
import {
  api,
  cameraSnapshotUrl,
  type CalibrationRequest,
  type HomographyPreview,
} from "../services/api";
import type { Camera } from "../types";

type Mode = "rect" | "stop" | "lanePoly" | "laneArrow" | "light";
type Lane = { id: string; polygon: number[][]; arrow: number[][]; speed: number };

const STEPS: { mode: Mode; label: string; hint: string }[] = [
  { mode: "rect", label: "1 · Ground rectangle", hint: "Click 4 corners of a known rectangle on the road (e.g. a lane segment): top-left, top-right, bottom-right, bottom-left. Then enter its real size." },
  { mode: "stop", label: "2 · Stop line", hint: "Click the two ends of the stop line across the road." },
  { mode: "lanePoly", label: "3 · Lanes", hint: "Click around a lane to outline it, press “Finish outline”, then click two points (back → front) to show its travel direction, set the speed limit, and Add lane." },
  { mode: "light", label: "4 · Traffic light", hint: "Click two opposite corners of a box around the traffic light lamps." },
];

export function CalibratePage() {
  const { cameraId = "" } = useParams();
  const navigate = useNavigate();
  const [camera, setCamera] = useState<Camera | null>(null);
  const [snapUrl, setSnapUrl] = useState("");
  const [nat, setNat] = useState<{ w: number; h: number } | null>(null);

  const [mode, setMode] = useState<Mode>("rect");
  const [rectPts, setRectPts] = useState<number[][]>([]);
  const [widthM, setWidthM] = useState(3.5);
  const [lengthM, setLengthM] = useState(10);
  const [stopPts, setStopPts] = useState<number[][]>([]);
  const [lanes, setLanes] = useState<Lane[]>([]);
  const [draftPoly, setDraftPoly] = useState<number[][]>([]);
  const [draftArrow, setDraftArrow] = useState<number[][]>([]);
  const [draftSpeed, setDraftSpeed] = useState(50);
  const [lightPts, setLightPts] = useState<number[][]>([]);

  const [preview, setPreview] = useState<HomographyPreview | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!cameraId) return;
    api.camera(cameraId).then(setCamera).catch((e) => setError(e.message));
    setSnapUrl(cameraSnapshotUrl(cameraId));
  }, [cameraId]);

  // Validate the homography whenever the 4 points / dimensions change.
  useEffect(() => {
    if (rectPts.length !== 4 || !widthM || !lengthM) { setPreview(null); return; }
    const t = setTimeout(() => {
      api.homographyPreview(cameraId, { image_points: rectPts, width_m: widthM, length_m: lengthM })
        .then(setPreview).catch(() => setPreview(null));
    }, 250);
    return () => clearTimeout(t);
  }, [rectPts, widthM, lengthM, cameraId]);

  const addPoint = useCallback((p: number[]) => {
    if (mode === "rect") setRectPts((v) => (v.length >= 4 ? v : [...v, p]));
    else if (mode === "stop") setStopPts((v) => (v.length >= 2 ? v : [...v, p]));
    else if (mode === "lanePoly") setDraftPoly((v) => [...v, p]);
    else if (mode === "laneArrow") setDraftArrow((v) => (v.length >= 2 ? v : [...v, p]));
    else if (mode === "light") setLightPts((v) => (v.length >= 2 ? [p] : [...v, p]));
  }, [mode]);

  function onSvgClick(e: React.MouseEvent) {
    if (!nat || !svgRef.current) return;
    const r = svgRef.current.getBoundingClientRect();
    const x = Math.round(((e.clientX - r.left) / r.width) * nat.w);
    const y = Math.round(((e.clientY - r.top) / r.height) * nat.h);
    addPoint([x, y]);
  }

  function undo() {
    if (mode === "rect") setRectPts((v) => v.slice(0, -1));
    else if (mode === "stop") setStopPts((v) => v.slice(0, -1));
    else if (mode === "lanePoly") setDraftPoly((v) => v.slice(0, -1));
    else if (mode === "laneArrow") setDraftArrow((v) => v.slice(0, -1));
    else if (mode === "light") setLightPts((v) => v.slice(0, -1));
  }

  function resetAll() {
    setRectPts([]); setStopPts([]); setLanes([]); setDraftPoly([]); setDraftArrow([]); setLightPts([]); setPreview(null);
    setMode("rect");
  }

  function addLane() {
    if (draftPoly.length < 3 || draftArrow.length !== 2) return;
    setLanes((v) => [...v, { id: `lane-${v.length + 1}`, polygon: draftPoly, arrow: draftArrow, speed: draftSpeed }]);
    setDraftPoly([]); setDraftArrow([]); setMode("lanePoly");
  }

  async function save() {
    setError("");
    if (rectPts.length !== 4) return setError("Place all 4 ground rectangle points (step 1).");
    if (stopPts.length !== 2) return setError("Draw the stop line (step 2).");
    const lightBox = lightPts.length === 2
      ? [Math.min(lightPts[0][0], lightPts[1][0]), Math.min(lightPts[0][1], lightPts[1][1]),
         Math.max(lightPts[0][0], lightPts[1][0]), Math.max(lightPts[0][1], lightPts[1][1])]
      : null;
    const payload: CalibrationRequest = {
      rectangle: { image_points: rectPts, width_m: widthM, length_m: lengthM },
      stop_line: stopPts,
      lanes: lanes.map((l) => ({ id: l.id, polygon: l.polygon, arrow: l.arrow, speed_limit_kmh: l.speed })),
      light_box: lightBox,
    };
    setSaving(true);
    try {
      await api.calibrate(cameraId, payload);
      navigate(`/cameras/${cameraId}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  if (!camera && !error) return <PageLoader />;
  const activeHint = STEPS.find((s) => s.mode === mode || (mode === "laneArrow" && s.mode === "lanePoly"))?.hint;

  return (
    <div className="page-stack">
      <Link className="back-link" to={`/cameras/${cameraId}`}><ArrowLeft size={16} />Back to camera</Link>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Calibration</span>
          <h1>Calibrate {camera?.name}</h1>
          <p>Draw the road geometry on a snapshot. This teaches the camera real-world distances so speed, red-light, and wrong-way detection work.</p>
        </div>
        <button className="button button-primary" onClick={save} disabled={saving}>
          <Check size={16} />{saving ? "Saving…" : "Save & enable detection"}
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="calib-layout">
        <div className="calib-canvas">
          {snapUrl && (
            <div className="calib-stage">
              <img
                src={snapUrl}
                alt="camera snapshot"
                onLoad={(e) => setNat({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
                onError={() => setError("Could not grab a snapshot — make sure the camera source is reachable.")}
              />
              {nat && (
                <svg ref={svgRef} viewBox={`0 0 ${nat.w} ${nat.h}`} preserveAspectRatio="none" onClick={onSvgClick} className="calib-svg">
                  {/* ground rectangle */}
                  {rectPts.length > 1 && <polygon points={rectPts.map((p) => p.join(",")).join(" ")} fill="rgba(47,174,141,.18)" stroke="#2fae8d" strokeWidth={3} />}
                  {rectPts.map((p, i) => <g key={`r${i}`}><circle cx={p[0]} cy={p[1]} r={7} fill="#2fae8d" /><text x={p[0] + 10} y={p[1] - 8} fill="#2fae8d" fontSize={22} fontWeight={700}>{i + 1}</text></g>)}
                  {/* stop line */}
                  {stopPts.length === 2 && <line x1={stopPts[0][0]} y1={stopPts[0][1]} x2={stopPts[1][0]} y2={stopPts[1][1]} stroke="#f0a500" strokeWidth={4} />}
                  {stopPts.map((p, i) => <circle key={`s${i}`} cx={p[0]} cy={p[1]} r={7} fill="#f0a500" />)}
                  {/* committed lanes */}
                  {lanes.map((l, i) => (
                    <g key={`l${i}`}>
                      <polygon points={l.polygon.map((p) => p.join(",")).join(" ")} fill="rgba(80,160,255,.16)" stroke="#4a9bff" strokeWidth={2.5} />
                      <line x1={l.arrow[0][0]} y1={l.arrow[0][1]} x2={l.arrow[1][0]} y2={l.arrow[1][1]} stroke="#4a9bff" strokeWidth={4} />
                      <circle cx={l.arrow[1][0]} cy={l.arrow[1][1]} r={9} fill="#4a9bff" />
                    </g>
                  ))}
                  {/* draft polygon + arrow */}
                  {draftPoly.length > 0 && <polyline points={draftPoly.map((p) => p.join(",")).join(" ")} fill="rgba(80,160,255,.12)" stroke="#7db8ff" strokeWidth={2.5} strokeDasharray="8 6" />}
                  {draftPoly.map((p, i) => <circle key={`dp${i}`} cx={p[0]} cy={p[1]} r={6} fill="#7db8ff" />)}
                  {draftArrow.length === 2 && <line x1={draftArrow[0][0]} y1={draftArrow[0][1]} x2={draftArrow[1][0]} y2={draftArrow[1][1]} stroke="#7db8ff" strokeWidth={4} />}
                  {draftArrow.map((p, i) => <circle key={`da${i}`} cx={p[0]} cy={p[1]} r={7} fill="#7db8ff" />)}
                  {/* light box */}
                  {lightPts.length === 2 && <rect x={Math.min(lightPts[0][0], lightPts[1][0])} y={Math.min(lightPts[0][1], lightPts[1][1])} width={Math.abs(lightPts[1][0] - lightPts[0][0])} height={Math.abs(lightPts[1][1] - lightPts[0][1])} fill="none" stroke="#e0413a" strokeWidth={3} />}
                  {lightPts.map((p, i) => <circle key={`li${i}`} cx={p[0]} cy={p[1]} r={6} fill="#e0413a" />)}
                </svg>
              )}
            </div>
          )}
          <div className="calib-toolbar">
            <button className="button button-secondary" onClick={undo}><Undo2 size={15} />Undo point</button>
            <button className="button button-secondary" onClick={resetAll}><RotateCcw size={15} />Reset all</button>
            <button className="button button-secondary" onClick={() => setSnapUrl(cameraSnapshotUrl(cameraId))}>New snapshot</button>
          </div>
        </div>

        <aside className="calib-panel">
          <div className="calib-steps">
            {STEPS.map((s) => {
              const active = mode === s.mode || (s.mode === "lanePoly" && mode === "laneArrow");
              return (
                <button key={s.mode} className={`calib-step ${active ? "calib-step-active" : ""}`} onClick={() => setMode(s.mode)}>
                  {s.label}
                </button>
              );
            })}
          </div>

          <p className="calib-hint">{activeHint}</p>

          {mode === "rect" && (
            <div className="calib-fields">
              <label><span>Rectangle width (m)</span><input type="number" step="0.1" value={widthM} onChange={(e) => setWidthM(+e.target.value)} /></label>
              <label><span>Rectangle length (m)</span><input type="number" step="0.1" value={lengthM} onChange={(e) => setLengthM(+e.target.value)} /></label>
              <small>Tip: a standard lane is ~3.5 m wide. Pick a rectangle you can measure.</small>
              {preview && (
                <div className={`calib-preview ${preview.ok ? "ok" : "warn"}`}>
                  {preview.ok ? "✓ " : "⚠ "}{preview.message}
                </div>
              )}
              <div className="calib-count">{rectPts.length} / 4 points placed</div>
            </div>
          )}

          {(mode === "lanePoly" || mode === "laneArrow") && (
            <div className="calib-fields">
              {mode === "lanePoly" && (
                <button className="button button-secondary" disabled={draftPoly.length < 3} onClick={() => setMode("laneArrow")}>
                  Finish outline → draw direction
                </button>
              )}
              {mode === "laneArrow" && <div className="calib-count">{draftArrow.length} / 2 direction points</div>}
              <label><span>Speed limit (km/h)</span><input type="number" value={draftSpeed} onChange={(e) => setDraftSpeed(+e.target.value)} /></label>
              <button className="button button-primary" disabled={draftPoly.length < 3 || draftArrow.length !== 2} onClick={addLane}>Add lane</button>
              {lanes.length > 0 && (
                <ul className="calib-lane-list">
                  {lanes.map((l, i) => (
                    <li key={l.id}><span>{l.id} · {l.speed} km/h</span><button onClick={() => setLanes((v) => v.filter((_, j) => j !== i))}>✕</button></li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {mode === "stop" && <div className="calib-count">{stopPts.length} / 2 points placed</div>}
          {mode === "light" && <div className="calib-count">{lightPts.length} / 2 corners placed</div>}

          <div className="calib-summary">
            <div><b>{rectPts.length === 4 ? "✓" : "—"}</b> Ground rectangle</div>
            <div><b>{stopPts.length === 2 ? "✓" : "—"}</b> Stop line</div>
            <div><b>{lanes.length > 0 ? "✓" : "—"}</b> Lanes ({lanes.length})</div>
            <div><b>{lightPts.length === 2 ? "✓" : "—"}</b> Traffic light</div>
          </div>
        </aside>
      </div>
    </div>
  );
}

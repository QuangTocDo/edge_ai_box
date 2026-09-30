import {
  ArrowLeft,
  Check,
  RotateCcw,
  Undo2,
  Gauge,
  TrafficCone,
  Compass,
  Ban,
  CircleSlash,
  Clock,
  Users,
  Eye,
  Trash2,
  FileCode,
  Save,
  Edit3,
  Sliders,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { PageLoader } from "../components/UI";
import {
  api,
  cameraSnapshotUrl,
  type CalibrationRequest,
  type HomographyPreview,
  type RuleZoneConfig,
} from "../services/api";
import type { Camera } from "../types";

type RuleKey =
  | "speeding"
  | "red_light"
  | "wrong_way"
  | "no_uturn"
  | "no_entry_road"
  | "no_parking"
  | "no_gathering";

interface SpeedZone {
  id: string;
  polygon: number[][];
  homography_src?: number[][];
  road_dir?: number[];
  road_dir_points?: number[][];
  width_m: number;
  length_m: number;
  limit_kmh: number;
}

interface RuleMeta {
  key: RuleKey;
  label: string;
  sublabel: string;
  shortcut: string;
  icon: typeof Gauge;
  color: string;
  fill: string;
  hint: string;
}

function computeAllowedVec(p1: number[], p2: number[], allowed_sign: number = 1, len: number = 50) {
  const lx = p2[0] - p1[0];
  const ly = p2[1] - p1[1];
  const n = Math.hypot(lx, ly) || 1;
  let nx = -ly / n;
  let ny = lx / n;
  if (allowed_sign < 0) {
    nx = -nx;
    ny = -ny;
  }
  const mx = (p1[0] + p2[0]) / 2;
  const my = (p1[1] + p2[1]) / 2;
  return {
    start: [mx, my],
    end: [mx + nx * len, my + ny * len],
  };
}

const RULE_METAS: RuleMeta[] = [
  {
    key: "speeding",
    label: "1. Đo tốc độ (Speeding)",
    sublabel: "Hiệu chuẩn H (4 điểm P1..P4)",
    shortcut: "1",
    icon: Gauge,
    color: "#d946ef",
    fill: "rgba(217, 70, 239, 0.18)",
    hint: "Chấm 4 góc chuẩn P1..P4 (màu cánh sen như draw_lines.py) và nhập kích thước mặt đường thực tế (chiều rộng x chiều dài).",
  },
  {
    key: "red_light",
    label: "2. Đèn đỏ & Vạch dừng",
    sublabel: "Stop Line & Signal Box",
    shortcut: "2",
    icon: TrafficCone,
    color: "#f59e0b",
    fill: "rgba(245, 158, 11, 0.18)",
    hint: "Chấm 2 điểm tạo Vạch dừng ngang đường + Khoanh hộp đèn giao thông SIGNAL (viền vàng viền đôi).",
  },
  {
    key: "wrong_way",
    label: "3. Ngược chiều (Wrong Way)",
    sublabel: "Vạch quy định chiều đi",
    shortcut: "3",
    icon: Compass,
    color: "#22c55e",
    fill: "rgba(34, 197, 94, 0.18)",
    hint: "Chấm 2 điểm trên hình để vẽ Vạch kiểm soát chiều đi (Line). Mũi tên vàng chỉ hướng lưu thông hợp pháp (+1 / -1).",
  },
  {
    key: "no_uturn",
    label: "4. Cấm quay đầu (No U-Turn)",
    sublabel: "Vùng cấm quay đầu xe",
    shortcut: "4",
    icon: RotateCcw,
    color: "#8b5cf6",
    fill: "rgba(139, 92, 246, 0.18)",
    hint: "Chấm các điểm bao quanh khu vực cấm hành vi quay đầu xe (tối thiểu 3 điểm).",
  },
  {
    key: "no_entry_road",
    label: "5. Đường cấm (No Entry)",
    sublabel: "Vùng cấm lưu thông [banned]",
    shortcut: "5",
    icon: CircleSlash,
    color: "#ef4444",
    fill: "rgba(239, 68, 68, 0.2)",
    hint: "Chấm các điểm tạo đa giác vùng đường cấm loại [banned] (viền đỏ như draw_lines.py).",
  },
  {
    key: "no_parking",
    label: "6. Cấm dừng đỗ (No Parking)",
    sublabel: "Vùng đỗ xe trái phép [parking]",
    shortcut: "6",
    icon: Clock,
    color: "#6366f1",
    fill: "rgba(99, 102, 241, 0.18)",
    hint: "Chấm đa giác bao quanh lề đường cấm đỗ + Thiết lập thời gian dwell time tối đa cho phép.",
  },
  {
    key: "no_gathering",
    label: "7. Cấm tụ tập (Gathering)",
    sublabel: "Vùng an ninh trật tự",
    shortcut: "7",
    icon: Users,
    color: "#14b8a6",
    fill: "rgba(20, 184, 166, 0.18)",
    hint: "Chấm đa giác giám sát an ninh + Cài đặt số người và thời gian tụ tập tối thiểu.",
  },
];

interface CustomZone {
  id: string;
  rule_type: RuleKey;
  polygon: number[][];
  arrow?: number[][];
  dwell_s?: number;
  min_persons?: number;
  speed_limit_kmh?: number;
}

export function CalibratePage() {
  const { cameraId = "" } = useParams();
  const navigate = useNavigate();
  const [camera, setCamera] = useState<Camera | null>(null);
  const [snapUrl, setSnapUrl] = useState("");
  const [nat, setNat] = useState<{ w: number; h: number } | null>(null);

  const [activeRule, setActiveRule] = useState<RuleKey>("speeding");
  const [drawSubMode, setDrawSubMode] = useState<"poly" | "arrow" | "stop" | "light">("poly");

  // Speeding (Ho tro ve polygon tuy y + hieu chuan 4 diem H + road_dir)
  const [speedZones, setSpeedZones] = useState<SpeedZone[]>([]);
  const [editingSpeedZoneId, setEditingSpeedZoneId] = useState<string | null>(null);
  const [speedSubMode, setSpeedSubMode] = useState<"poly" | "calib" | "arrow">("poly");
  const [speedArrow, setSpeedArrow] = useState<number[][]>([]);
  const [rectPts, setRectPts] = useState<number[][]>([]);
  const [widthM, setWidthM] = useState(3.5);
  const [lengthM, setLengthM] = useState(15.0);
  const [speedLimit, setSpeedLimit] = useState(50);

  const [preview, setPreview] = useState<HomographyPreview | null>(null);

  // Red Light & Stop Lines (Ho tro nhieu vach dung STOP_1, STOP_2... theo tung lan xe)
  const [stopLines, setStopLines] = useState<Array<{ id: string; p1: number[]; p2: number[]; role?: string }>>([]);
  const [stopPts, setStopPts] = useState<number[][]>([]);
  const [lightPts, setLightPts] = useState<number[][]>([]);

  // Committed zones for wrong_way, no_uturn, no_entry, no_parking, no_gathering
  const [customZones, setCustomZones] = useState<CustomZone[]>([]);
  const [existingLines, setExistingLines] = useState<Array<{ id: string; p1: number[]; p2: number[]; allowed_sign?: number; role?: string; signal_id?: string }>>([]);
  const [existingSignals, setExistingSignals] = useState<Array<{ id: string; roi: number[] }>>([]);
  const [existingPairs, setExistingPairs] = useState<Array<{ first: string; second: string; medial?: string }>>([]);
  const [configLoaded, setConfigLoaded] = useState(false);

  // Tabs: Visual canvas vs Raw active.yaml editor
  const [activeTab, setActiveTab] = useState<"visual" | "yaml">("visual");
  const [rawYaml, setRawYaml] = useState("");
  const [rawYamlSuccess, setRawYamlSuccess] = useState("");
  const [rawYamlLoading, setRawYamlLoading] = useState(false);

  // Draft drawing
  const [draftPoly, setDraftPoly] = useState<number[][]>([]);
  const [draftArrow, setDraftArrow] = useState<number[][]>([]);
  const [draftLine, setDraftLine] = useState<number[][]>([]);
  const [lineAllowedSign, setLineAllowedSign] = useState<number>(1);
  const [draftDwell, setDraftDwell] = useState(2.0);
  const [draftMinPersons, setDraftMinPersons] = useState(5);
  const [syncStatus, setSyncStatus] = useState("");

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!cameraId) return;
    api.camera(cameraId).then(setCamera).catch((e) => setError(e.message));
    setSnapUrl(cameraSnapshotUrl(cameraId));

    // Load active.yaml synchronized configuration
    api.cameraConfig(cameraId)
      .then((cfg) => {
        if (!cfg) return;
        if (cfg.raw_yaml) setRawYaml(cfg.raw_yaml);
        if (!cfg) return;

        // 1. Homography / Speeding zones (Nap toan bo cac vung toc do SPEED_1, SPEED_2...)
        const rawSpeedPolys = (cfg.polygons || []).filter(
          (p: any) => p.homography?.src?.length === 4 || p.rules?.speeding || p.id?.startsWith("SPEED_")
        );
        const parsedSpeedZones: SpeedZone[] = rawSpeedPolys.map((p: any, idx: number) => {
          const poly = p.polygon || p.homography?.src || [];
          const src = p.homography?.src || (p.polygon?.length === 4 ? p.polygon : []);
          const dst = p.homography?.dst || [];
          let w = 3.5;
          let l = 15.0;
          if (dst && dst.length === 4) {
            w = Math.round(Math.abs(dst[1][0] - dst[0][0]) * 10) / 10 || 3.5;
            l = Math.round(Math.abs(dst[2][1] - dst[1][1]) * 10) / 10 || 15.0;
          }
          const spLimit = p.rules?.speeding?.limit_kmh || p.rules?.speeding?.speed_limit_kmh || 50;
          return {
            id: p.id || `SPEED_${idx + 1}`,
            polygon: poly,
            homography_src: src,
            road_dir: p.road_dir,
            road_dir_points: p.road_dir_points,
            width_m: w,
            length_m: l,
            limit_kmh: spLimit,
          };
        });
        setSpeedZones(parsedSpeedZones);

        // 2. Stop Lines & Traffic Lines (Nap toan bo vach dung theo tung lan)
        if (cfg.lines) {
          const stops = cfg.lines.filter(
            (ln: any) => ln.id?.toUpperCase().includes("STOP") || ln.role === "stop"
          );
          setStopLines(stops);
          const otherLines = cfg.lines.filter((ln: any) => !stops.includes(ln) && ln.p1 && ln.p2);
          setExistingLines(otherLines);
        }

        // 3. Traffic Light Signals
        if (cfg.signals && cfg.signals.length > 0) {
          const validSigs = cfg.signals
            .filter((s: any) => (s.roi || s.box) && (s.roi || s.box).length === 4)
            .map((s: any) => ({
              id: s.id || "SIGNAL_1",
              roi: s.roi || s.box,
            }));
          setExistingSignals(validSigs);
          if (validSigs.length > 0) {
            const b = validSigs[0].roi;
            setLightPts([[b[0], b[1]], [b[2], b[3]]]);
          }
        } else {
          setExistingSignals([]);
        }

        // 3.5. U-Turn and Medial Pairs
        if (cfg.uturn_pairs && Array.isArray(cfg.uturn_pairs)) {
          setExistingPairs(cfg.uturn_pairs);
        } else {
          setExistingPairs([]);
        }

        // 4. Polygons from active.yaml mapped to customZones
        const zones: CustomZone[] = [];
        cfg.polygons?.forEach((p) => {
          if (!p.polygon || p.polygon.length < 3) return;
          const rules = p.rules || {};

          let matchedRule: RuleKey | null = null;
          if (rules.no_uturn?.enable) matchedRule = "no_uturn";
          else if (rules.no_entry_road?.enable || (p.kind === "banned" && !rules.no_parking?.enable)) matchedRule = "no_entry_road";
          else if (rules.no_parking?.enable) matchedRule = "no_parking";
          else if (rules.no_gathering?.enable) matchedRule = "no_gathering";

          if (matchedRule) {
            let arrow: number[][] | undefined = undefined;
            if (p.road_dir_points && p.road_dir_points.length === 2) {
              arrow = p.road_dir_points;
            } else if (p.road_dir && p.road_dir.length === 2) {
              const cx = p.polygon.reduce((sum, pt) => sum + pt[0], 0) / p.polygon.length;
              const cy = p.polygon.reduce((sum, pt) => sum + pt[1], 0) / p.polygon.length;
              arrow = [
                [Math.round(cx - p.road_dir[0] * 50), Math.round(cy - p.road_dir[1] * 50)],
                [Math.round(cx + p.road_dir[0] * 50), Math.round(cy + p.road_dir[1] * 50)],
              ];
            }

            zones.push({
              id: p.id,
              rule_type: matchedRule,
              polygon: p.polygon,
              arrow,
              dwell_s: rules[matchedRule]?.dwell_s ?? p.dwell_s ?? 2.0,
              min_persons: rules[matchedRule]?.min_persons ?? p.min_persons ?? 5,
              speed_limit_kmh: rules[matchedRule]?.speed_limit_kmh ?? 50,
            });
          }
        });

        if (zones.length > 0) {
          setCustomZones(zones);
        }
        setConfigLoaded(true);
      })
      .catch((err) => {
        console.warn("Could not load camera config from active.yaml:", err);
      });
  }, [cameraId]);

  // Homography preview validation
  useEffect(() => {
    if (rectPts.length !== 4 || !widthM || !lengthM) {
      setPreview(null);
      return;
    }
    const t = setTimeout(() => {
      api
        .homographyPreview(cameraId, {
          image_points: rectPts,
          width_m: widthM,
          length_m: lengthM,
        })
        .then(setPreview)
        .catch(() => setPreview(null));
    }, 250);
    return () => clearTimeout(t);
  }, [rectPts, widthM, lengthM, cameraId]);

  function addPoint(p: number[]) {
    if (activeRule === "speeding") {
      if (speedSubMode === "poly") {
        setDraftPoly((v) => [...v, p]);
      } else if (speedSubMode === "calib") {
        setRectPts((v) => (v.length >= 4 ? v : [...v, p]));
      } else if (speedSubMode === "arrow") {
        setSpeedArrow((v) => (v.length >= 2 ? [p] : [...v, p]));
      }
    } else if (activeRule === "red_light") {
      if (drawSubMode === "stop") {
        setStopPts((v) => (v.length >= 2 ? v : [...v, p]));
      } else {
        setLightPts((v) => (v.length >= 2 ? [p] : [...v, p]));
      }
    } else if (activeRule === "wrong_way") {
      setDraftLine((v) => (v.length >= 2 ? [p] : [...v, p]));
    } else {
      // polygon rules: no_uturn, no_entry_road, no_parking, no_gathering
      setDraftPoly((v) => [...v, p]);
    }
  }

  function onSvgClick(e: React.MouseEvent) {
    if (!nat || !svgRef.current) return;
    const r = svgRef.current.getBoundingClientRect();
    const x = Math.round(((e.clientX - r.left) / r.width) * nat.w);
    const y = Math.round(((e.clientY - r.top) / r.height) * nat.h);
    addPoint([x, y]);
  }

  function undoPoint() {
    if (activeRule === "speeding") {
      if (speedSubMode === "poly") setDraftPoly((v) => v.slice(0, -1));
      else if (speedSubMode === "calib") setRectPts((v) => v.slice(0, -1));
      else if (speedSubMode === "arrow") setSpeedArrow((v) => v.slice(0, -1));
    } else if (activeRule === "red_light") {
      if (drawSubMode === "stop") setStopPts((v) => v.slice(0, -1));
      else setLightPts((v) => v.slice(0, -1));
    } else if (activeRule === "wrong_way") {
      setDraftLine((v) => v.slice(0, -1));
    } else {
      setDraftPoly((v) => v.slice(0, -1));
    }
  }

  function resetCurrentRule() {
    if (activeRule === "speeding") {
      setDraftPoly([]);
      setRectPts([]);
      setSpeedArrow([]);
      setPreview(null);
    } else if (activeRule === "red_light") {
      if (stopPts.length > 0 || lightPts.length > 0) {
        deleteEntireRedLightRule();
      } else {
        setStopPts([]);
        setLightPts([]);
      }
    } else if (activeRule === "wrong_way") {
      setDraftLine([]);
    } else {
      setDraftPoly([]);
      setDraftArrow([]);
    }
  }

  async function commitZone() {
    if (draftPoly.length < 3) return;
    setError("");
    setSyncStatus("");
    const count = customZones.filter((z) => z.rule_type === activeRule).length + 1;
    const zoneId = `${activeRule.toUpperCase()}_${count}`;
    const newZone: CustomZone = {
      id: zoneId,
      rule_type: activeRule,
      polygon: draftPoly,
      dwell_s:
        activeRule === "no_entry_road" || activeRule === "no_parking" || activeRule === "no_gathering"
          ? draftDwell
          : undefined,
      min_persons: activeRule === "no_gathering" ? draftMinPersons : undefined,
    };

    const polyPayload: any = {
      id: zoneId,
      kind: activeRule === "no_entry_road" || activeRule === "no_parking" ? "banned" : "directional",
      polygon: draftPoly,
      rules: {
        [activeRule]: {
          enable: true,
          ...(activeRule === "no_entry_road" || activeRule === "no_parking" || activeRule === "no_gathering"
            ? { dwell_s: draftDwell }
            : {}),
          ...(activeRule === "no_gathering" ? { min_persons: draftMinPersons } : {}),
        },
      },
    };

    try {
      await api.saveCameraPolygon(cameraId, polyPayload);
      setCustomZones((v) => [...v, newZone]);
      setDraftPoly([]);
      setDraftArrow([]);
      setDrawSubMode("poly");
      setSyncStatus(`✓ Đã ghi trực tiếp vùng ${zoneId} vào configs/active.yaml!`);
      const cfg = await api.cameraConfig(cameraId);
      if (cfg?.raw_yaml) setRawYaml(cfg.raw_yaml);
    } catch (err) {
      setError((err as Error).message);
    }
  }





  function startEditSpeedZone(zone: SpeedZone) {
    setEditingSpeedZoneId(zone.id);
    setDraftPoly(zone.polygon || []);
    setRectPts(zone.homography_src && zone.homography_src.length === 4 ? zone.homography_src : (zone.polygon.length === 4 ? zone.polygon : []));
    setSpeedArrow(zone.road_dir_points || []);
    setWidthM(zone.width_m || 3.5);
    setLengthM(zone.length_m || 15.0);
    setSpeedLimit(zone.limit_kmh || 50);
    setActiveRule("speeding");
    setSyncStatus(`Đang chỉnh sửa vùng đo tốc độ: ${zone.id}`);
  }

  function cancelEditSpeedZone() {
    setEditingSpeedZoneId(null);
    setDraftPoly([]);
    setRectPts([]);
    setSpeedArrow([]);
    setSyncStatus("");
  }

  async function removeSpeedZone(id: string) {
    if (!window.confirm(`Xác nhận xóa vùng đo tốc độ ${id} khỏi active.yaml?`)) return;
    try {
      await api.deleteCameraPolygon(cameraId, id);
      setSpeedZones((prev) => prev.filter((z) => z.id !== id));
      if (editingSpeedZoneId === id) {
        setEditingSpeedZoneId(null);
        setRectPts([]);
      }
      setSyncStatus(`✓ Đã xóa vùng tốc độ ${id} khỏi active.yaml!`);
      const cfg = await api.cameraConfig(cameraId);
      if (cfg?.raw_yaml) setRawYaml(cfg.raw_yaml);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function saveSpeedingZone() {
    const finalPoly = draftPoly.length >= 3 ? draftPoly : rectPts;
    if (rectPts.length !== 4) {
      setError("Vui lòng chấm đủ 4 điểm hiệu chuẩn mặt phẳng đường H (Bước 2).");
      return;
    }
    if (finalPoly.length < 3) {
      setError("Vui lòng vẽ đa giác vùng làn đường (Bước 1) hoặc chấm 4 góc hiệu chuẩn.");
      return;
    }
    setError("");
    setSyncStatus("");

    let targetId = editingSpeedZoneId;
    if (!targetId) {
      const usedIds = new Set(speedZones.map((z) => z.id));
      let idx = 1;
      while (usedIds.has(`SPEED_${idx}`)) idx++;
      targetId = `SPEED_${idx}`;
    }

    const world = [
      [0.0, 0.0],
      [widthM, 0.0],
      [widthM, lengthM],
      [0.0, lengthM],
    ];

    let rdir: number[] = [0.0, 1.0];
    let rdirPts: number[][] | undefined = undefined;
    if (speedArrow.length === 2) {
      const dx = speedArrow[1][0] - speedArrow[0][0];
      const dy = speedArrow[1][1] - speedArrow[0][1];
      const mag = Math.hypot(dx, dy) || 1;
      rdir = [Math.round((dx / mag) * 1000) / 1000, Math.round((dy / mag) * 1000) / 1000];
      rdirPts = speedArrow;
    }

    const polyPayload: any = {
      id: targetId,
      kind: "directional",
      polygon: finalPoly,
      road_dir: rdir,
      road_dir_points: rdirPts,
      rules: {
        speeding: {
          enable: true,
          limit_kmh: speedLimit,
        },
      },
      homography: {
        src: rectPts,
        dst: world,
        measured_at: new Date().toISOString(),
      },
    };
    try {
      const res = await api.saveCameraPolygon(cameraId, polyPayload);
      const savedPoly = res?.polygon || polyPayload;
      setSpeedZones((prev) => [
        ...prev.filter((z) => z.id !== targetId),
        {
          id: targetId!,
          polygon: savedPoly.polygon || finalPoly,
          homography_src: savedPoly.homography?.src || rectPts,
          road_dir: savedPoly.road_dir || rdir,
          road_dir_points: savedPoly.road_dir_points || rdirPts,
          width_m: widthM,
          length_m: lengthM,
          limit_kmh: speedLimit,
        },
      ]);
      setRectPts([]);
      setDraftPoly([]);
      setSpeedArrow([]);
      setEditingSpeedZoneId(null);
      setSyncStatus(`✓ Đã ghi vùng tốc độ ${targetId} (${(savedPoly.polygon || finalPoly).length} đỉnh, ${widthM}m x ${lengthM}m, ${speedLimit}km/h) vào active.yaml!`);
      const cfg = await api.cameraConfig(cameraId);
      if (cfg?.raw_yaml) setRawYaml(cfg.raw_yaml);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function saveStopLine() {
    if (stopPts.length !== 2) return;
    setError("");
    setSyncStatus("");
    const used = new Set(stopLines.map((l) => l.id));
    let idx = 1;
    while (used.has(`STOP_${idx}`)) idx++;
    const stopId = `STOP_${idx}`;
    const payload = {
      id: stopId,
      p1: stopPts[0],
      p2: stopPts[1],
      role: "stop",
    };
    try {
      await api.saveCameraLine(cameraId, payload);
      setStopLines((prev) => [...prev.filter((l) => l.id !== stopId), payload]);
      setStopPts([]);
      setSyncStatus(`✓ Đã ghi vạch dừng ${stopId} vào active.yaml!`);
      const cfg = await api.cameraConfig(cameraId);
      if (cfg?.raw_yaml) setRawYaml(cfg.raw_yaml);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function removeStopLine(id: string) {
    if (!window.confirm(`Xác nhận xóa vạch dừng ${id} khỏi active.yaml?`)) return;
    try {
      await api.deleteCameraLine(cameraId, id);
      setStopLines((prev) => prev.filter((l) => l.id !== id));
      setSyncStatus(`✓ Đã xóa vạch dừng ${id} khỏi active.yaml!`);
      const cfg = await api.cameraConfig(cameraId);
      if (cfg?.raw_yaml) setRawYaml(cfg.raw_yaml);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function saveSignalBox() {
    if (lightPts.length !== 2) return;
    setError("");
    setSyncStatus("");
    const used = new Set(existingSignals.map((s) => s.id));
    let idx = 1;
    while (used.has(`SIGNAL_${idx}`)) idx++;
    const sigId = `SIGNAL_${idx}`;
    const box = [
      Math.min(lightPts[0][0], lightPts[1][0]),
      Math.min(lightPts[0][1], lightPts[1][1]),
      Math.max(lightPts[0][0], lightPts[1][0]),
      Math.max(lightPts[0][1], lightPts[1][1]),
    ];
    try {
      await api.saveCameraSignal(cameraId, {
        id: sigId,
        roi: box,
        box: box,
        default: "red",
      });
      setExistingSignals((prev) => [...prev.filter((s) => s.id !== sigId), { id: sigId, roi: box }]);
      setLightPts([]);
      setSyncStatus(`✓ Đã ghi hộp đèn ${sigId} vào active.yaml!`);
      const cfg = await api.cameraConfig(cameraId);
      if (cfg?.raw_yaml) setRawYaml(cfg.raw_yaml);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function removeSignalBox(id: string) {
    if (!window.confirm(`Xác nhận xóa hộp đèn ${id} khỏi active.yaml?`)) return;
    try {
      await api.deleteCameraSignal(cameraId, id);
      setExistingSignals((prev) => prev.filter((s) => s.id !== id));
      setSyncStatus(`✓ Đã xóa hộp đèn tín hiệu ${id} khỏi active.yaml!`);
      const cfg = await api.cameraConfig(cameraId);
      if (cfg?.raw_yaml) setRawYaml(cfg.raw_yaml);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function deleteEntireRedLightRule() {
    if (!window.confirm("Xác nhận xóa TOÀN BỘ cấu hình Vượt đèn đỏ & Đè vạch (tất cả vạch dừng + hộp đèn) khỏi active.yaml?")) return;
    try {
      for (const ln of stopLines) {
        try { await api.deleteCameraLine(cameraId, ln.id); } catch (_) {}
      }
      for (const sig of existingSignals) {
        try { await api.deleteCameraSignal(cameraId, sig.id); } catch (_) {}
      }
      setStopLines([]);
      setExistingSignals([]);
      setStopPts([]);
      setLightPts([]);
      setSyncStatus("✓ Đã xóa hoàn toàn cấu hình Vượt đèn đỏ & Đè vạch khỏi configs/active.yaml!");
      const cfg = await api.cameraConfig(cameraId);
      if (cfg?.raw_yaml) setRawYaml(cfg.raw_yaml);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function saveWrongWayLine() {
    if (draftLine.length !== 2) return;
    setError("");
    setSyncStatus("");
    const used = new Set(existingLines.map((l) => l.id));
    let idx = 1;
    while (used.has(`L${idx}`)) idx++;
    const lid = `L${idx}`;
    const payload = {
      id: lid,
      p1: draftLine[0],
      p2: draftLine[1],
      allowed_sign: lineAllowedSign,
      role: "lane",
    };
    try {
      await api.saveCameraLine(cameraId, payload);
      setExistingLines((v) => [...v.filter((l) => l.id !== lid), payload]);
      setDraftLine([]);
      setSyncStatus(`✓ Đã ghi trực tiếp vạch ngược chiều ${lid} (hướng: ${lineAllowedSign > 0 ? "+1" : "-1"}) vào active.yaml!`);
      const cfg = await api.cameraConfig(cameraId);
      if (cfg?.raw_yaml) setRawYaml(cfg.raw_yaml);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function removeZone(id: string) {
    if (!window.confirm(`Xác nhận xóa vùng ${id} khỏi active.yaml?`)) return;
    try {
      await api.deleteCameraPolygon(cameraId, id);
      setCustomZones((v) => v.filter((z) => z.id !== id));
      const cfg = await api.cameraConfig(cameraId);
      if (cfg?.raw_yaml) setRawYaml(cfg.raw_yaml);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function removeLine(id: string) {
    if (!window.confirm(`Xác nhận xóa vạch kẻ ${id} khỏi active.yaml?`)) return;
    try {
      await api.deleteCameraLine(cameraId, id);
      setExistingLines((v) => v.filter((ln) => ln.id !== id));
      const cfg = await api.cameraConfig(cameraId);
      if (cfg?.raw_yaml) setRawYaml(cfg.raw_yaml);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleSaveRawYaml() {
    setRawYamlLoading(true);
    setRawYamlSuccess("");
    setError("");
    try {
      const res = await api.updateRawConfig(cameraId, rawYaml);
      setRawYamlSuccess(res.message || "Đã lưu active.yaml thành công!");
      // Reload visual calibration from saved YAML
      const cfg = await api.cameraConfig(cameraId);
      if (cfg) {
        if (cfg.raw_yaml) setRawYaml(cfg.raw_yaml);
        if (cfg.lines) {
          const stopLine = cfg.lines.find(
            (ln) => ln.id?.toUpperCase().includes("STOP") || ln.role === "stop"
          );
          if (stopLine && stopLine.p1 && stopLine.p2) setStopPts([stopLine.p1, stopLine.p2]);
          const otherLines = cfg.lines.filter((ln) => ln !== stopLine && ln.p1 && ln.p2);
          setExistingLines(otherLines);
        }
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRawYamlLoading(false);
    }
  }

  async function save() {
    setError("");
    const lightBox =
      lightPts.length === 2
        ? [
            Math.min(lightPts[0][0], lightPts[1][0]),
            Math.min(lightPts[0][1], lightPts[1][1]),
            Math.max(lightPts[0][0], lightPts[1][0]),
            Math.max(lightPts[0][1], lightPts[1][1]),
          ]
        : null;

    const ruleZones: RuleZoneConfig[] = customZones.map((z) => ({
      id: z.id,
      rule_type: z.rule_type,
      polygon: z.polygon,
      arrow: z.arrow,
      dwell_s: z.dwell_s,
      min_persons: z.min_persons,
      speed_limit_kmh: z.speed_limit_kmh,
      enabled: true,
    }));

    const payload: CalibrationRequest = {
      rectangle:
        rectPts.length === 4
          ? { image_points: rectPts, width_m: widthM, length_m: lengthM }
          : undefined,
      stop_line: stopPts.length === 2 ? stopPts : undefined,
      light_box: lightBox,
      lines: existingLines,
      rule_zones: ruleZones.filter((z) => z.rule_type !== "wrong_way"),
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
  const currentMeta = RULE_METAS.find((m) => m.key === activeRule) || RULE_METAS[0];

  function getRuleBadge(key: RuleKey) {
    if (key === "speeding") {
      if (speedZones.length > 0) {
        return { text: `✓ ${speedZones.length} vùng`, color: "#10b981", bg: "rgba(16, 185, 129, 0.15)" };
      }
      if (rectPts.length === 4) {
        return { text: "✓ 4 góc (Homography)", color: "#10b981", bg: "rgba(16, 185, 129, 0.15)" };
      }
      return { text: "Chưa cấu hình", color: "var(--muted)", bg: "var(--surface-raised)" };
    }
    if (key === "red_light") {
      const hasStop = stopPts.length === 2;
      const hasLight = lightPts.length === 2;
      if (hasStop && hasLight) {
        return { text: "✓ Vạch dừng & Đèn", color: "#10b981", bg: "rgba(16, 185, 129, 0.15)" };
      }
      if (hasStop) {
        return { text: "✓ Vạch dừng", color: "#f59e0b", bg: "rgba(245, 158, 11, 0.15)" };
      }
      return { text: "Chưa cấu hình", color: "var(--muted)", bg: "var(--surface-raised)" };
    }
    if (key === "wrong_way") {
      const wwLines = existingLines.filter((ln) => ln.role !== "divider" && !ln.id?.toUpperCase().includes("STOP"));
      if (wwLines.length > 0) {
        return { text: `✓ ${wwLines.length} vạch`, color: "#22c55e", bg: "rgba(34, 197, 94, 0.15)" };
      }
      return { text: "Chưa cấu hình", color: "var(--muted)", bg: "var(--surface-raised)" };
    }
    const count = customZones.filter((z) => z.rule_type === key).length;
    if (count > 0) {
      return { text: `✓ ${count} vùng`, color: "#10b981", bg: "rgba(16, 185, 129, 0.15)" };
    }
    return { text: "Chưa cấu hình", color: "var(--muted)", bg: "var(--surface-raised)" };
  }

  return (
    <div className="page-stack">
      <Link className="back-link" to={`/cameras/${cameraId}`}>
        <ArrowLeft size={16} /> Quay lại camera
      </Link>

      <div className="page-heading" style={{ alignItems: "center", marginBottom: "6px" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <h1 style={{ margin: 0, fontSize: "20px" }}>Hiệu chuẩn Camera: {camera?.name}</h1>
            {configLoaded && (
              <span style={{
                background: "rgba(16, 185, 129, 0.15)",
                color: "#10b981",
                border: "1px solid rgba(16, 185, 129, 0.3)",
                borderRadius: "20px",
                padding: "2px 10px",
                fontSize: "11px",
                fontWeight: 600,
                display: "inline-flex",
                alignItems: "center",
                gap: "5px"
              }}>
                <Check size={13} /> Đồng bộ từ active.yaml: {customZones.length + (rectPts.length ? 1 : 0)} vùng, {existingLines.length + (stopPts.length ? 1 : 0)} vạch kẻ
              </span>
            )}
          </div>
        </div>
        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <div style={{ display: "flex", gap: "6px" }}>
            <button
              className={`button ${activeTab === "visual" ? "button-primary" : "button-secondary"}`}
              onClick={() => setActiveTab("visual")}
              style={{ fontSize: "12px", padding: "6px 12px", display: "flex", alignItems: "center", gap: "6px" }}
            >
              <Edit3 size={14} /> Trực quan (Canvas)
            </button>
            <button
              className={`button ${activeTab === "yaml" ? "button-primary" : "button-secondary"}`}
              onClick={() => setActiveTab("yaml")}
              style={{ fontSize: "12px", padding: "6px 12px", display: "flex", alignItems: "center", gap: "6px" }}
            >
              <FileCode size={14} /> File active.yaml
            </button>
          </div>
          <button className="button button-primary" onClick={save} disabled={saving} style={{ padding: "6px 14px", fontSize: "12.5px" }}>
            <Check size={15} />
            {saving ? "Đang lưu…" : "Lưu & Kích hoạt"}
          </button>
        </div>
      </div>

      {syncStatus && (
        <div style={{
          background: "rgba(16, 185, 129, 0.15)",
          color: "#10b981",
          border: "1px solid rgba(16, 185, 129, 0.35)",
          borderRadius: "var(--radius-sm)",
          padding: "10px 16px",
          marginBottom: "14px",
          fontWeight: 600,
          fontSize: "13.5px",
          display: "flex",
          alignItems: "center",
          gap: "8px"
        }}>
          <Check size={16} /> {syncStatus}
        </div>
      )}

      {error && <div className="error-banner">{error}</div>}

      {activeTab === "yaml" ? (
        <div className="card" style={{ padding: "20px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "12px" }}>
            <div>
              <h3 style={{ margin: 0, display: "flex", alignItems: "center", gap: "8px" }}>
                <FileCode size={20} color="var(--cyan)" /> Tập tin cấu hình: <code style={{ color: "var(--cyan)" }}>configs/active.yaml</code>
              </h3>
              <p style={{ margin: "4px 0 0 0", color: "var(--muted)", fontSize: "13px" }}>
                Cho phép sửa, thêm hoặc xóa trực tiếp các polygon, lines, signals hoặc các thông số quy tắc trực tiếp trên máy chủ.
              </p>
            </div>
            <div style={{ display: "flex", gap: "10px" }}>
              <button
                className="button button-secondary"
                onClick={() => {
                  api.cameraConfig(cameraId).then((cfg) => {
                    if (cfg?.raw_yaml) setRawYaml(cfg.raw_yaml);
                  });
                }}
              >
                <RotateCcw size={16} /> Tải lại từ máy chủ
              </button>
              <button
                className="button button-primary"
                onClick={handleSaveRawYaml}
                disabled={rawYamlLoading}
                style={{ background: "var(--emerald)" }}
              >
                <Save size={16} /> {rawYamlLoading ? "Đang lưu..." : "Lưu tập tin active.yaml"}
              </button>
            </div>
          </div>

          {rawYamlSuccess && (
            <div style={{
              background: "rgba(16, 185, 129, 0.15)",
              color: "#10b981",
              border: "1px solid rgba(16, 185, 129, 0.3)",
              padding: "10px 14px",
              borderRadius: "var(--radius-sm)",
              marginBottom: "14px",
              fontSize: "13px",
              fontWeight: 500
            }}>
              ✓ {rawYamlSuccess}
            </div>
          )}

          <textarea
            value={rawYaml}
            onChange={(e) => setRawYaml(e.target.value)}
            spellCheck={false}
            rows={32}
            style={{
              width: "100%",
              fontFamily: "var(--font-mono, monospace)",
              fontSize: "13px",
              lineHeight: 1.6,
              background: "#090d16",
              color: "#38bdf8",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-md)",
              padding: "16px",
              boxSizing: "border-box",
              resize: "vertical",
            }}
          />
        </div>
      ) : (
      <div className="calib-layout">
        {/* Canvas Area */}
        <div className="calib-canvas">
          {snapUrl && (
            <div className="calib-stage">
              <img
                src={snapUrl}
                alt="camera snapshot"
                onLoad={(e) =>
                  setNat({
                    w: e.currentTarget.naturalWidth,
                    h: e.currentTarget.naturalHeight,
                  })
                }
                onError={() =>
                  setError("Không thể tải ảnh snapshot từ camera. Vui lòng kiểm tra kết nối nguồn video.")
                }
              />

              {nat && (
                <svg
                  ref={svgRef}
                  viewBox={`0 0 ${nat.w} ${nat.h}`}
                  preserveAspectRatio="none"
                  onClick={onSvgClick}
                  className="calib-svg"
                >
                  <defs>
                    <marker
                      id="arrow-emerald"
                      viewBox="0 0 10 10"
                      refX="6"
                      refY="5"
                      markerWidth="6"
                      markerHeight="6"
                      orient="auto-start-reverse"
                    >
                      <path d="M 0 1 L 10 5 L 0 9 z" fill="#10b981" />
                    </marker>
                    <marker
                      id="arrow-cyan"
                      viewBox="0 0 10 10"
                      refX="6"
                      refY="5"
                      markerWidth="6"
                      markerHeight="6"
                      orient="auto-start-reverse"
                    >
                      <path d="M 0 1 L 10 5 L 0 9 z" fill="#06b6d4" />
                    </marker>
                    <marker
                      id="arrow-draft"
                      viewBox="0 0 10 10"
                      refX="6"
                      refY="5"
                      markerWidth="6"
                      markerHeight="6"
                      orient="auto-start-reverse"
                    >
                      <path d="M 0 1 L 10 5 L 0 9 z" fill="#7dd3fc" />
                    </marker>
                    <marker
                      id="arrow-yellow"
                      viewBox="0 0 10 10"
                      refX="6"
                      refY="5"
                      markerWidth="6"
                      markerHeight="6"
                      orient="auto-start-reverse"
                    >
                      <path d="M 0 1 L 10 5 L 0 9 z" fill="#facc15" />
                    </marker>
                    <marker
                      id="arrow-magenta"
                      viewBox="0 0 10 10"
                      refX="6"
                      refY="5"
                      markerWidth="6"
                      markerHeight="6"
                      orient="auto-start-reverse"
                    >
                      <path d="M 0 1 L 10 5 L 0 9 z" fill="#d946ef" />
                    </marker>
                  </defs>

                  {/* 0. HUD Overlay in top-left like draw_lines.py */}
                  <g className="hud-overlay" style={{ pointerEvents: "none" }}>
                    <rect
                      x={14}
                      y={14}
                      width={310}
                      height={34 + existingPairs.length * 22}
                      rx={6}
                      fill="rgba(15, 23, 42, 0.85)"
                      stroke="rgba(255, 255, 255, 0.2)"
                      strokeWidth={1}
                    />
                    <text x={26} y={36} fill="#38bdf8" fontSize={13} fontWeight={700} fontFamily="monospace">
                      [CHẾ ĐỘ]: {currentMeta.label.toUpperCase()} ({currentMeta.shortcut})
                    </text>
                    {existingPairs.map((pr, idx) => (
                      <text key={`hud-pair-${idx}`} x={26} y={58 + idx * 22} fill="#d946ef" fontSize={12} fontWeight={600} fontFamily="monospace">
                        pair{idx}: {pr.first} -&gt; {pr.second} {pr.medial ? `[med=${pr.medial}]` : ""}
                      </text>
                    ))}
                  </g>

                  {/* 1. Saved Speeding Zones (Nhung vung da luu theo tung lan) */}
                  {speedZones.map((z) => {
                    if (editingSpeedZoneId === z.id) return null;
                    const midX = z.polygon.reduce((sum, pt) => sum + pt[0], 0) / (z.polygon.length || 1);
                    const midY = z.polygon.reduce((sum, pt) => sum + pt[1], 0) / (z.polygon.length || 1);
                    return (
                      <g key={`speed-zone-${z.id}`}>
                        {/* Da giac vung lan duong */}
                        <polygon
                          points={z.polygon.map((p) => p.join(",")).join(" ")}
                          fill="rgba(217, 70, 239, 0.14)"
                          stroke="#d946ef"
                          strokeWidth={2.5}
                        />
                        {/* 4 diem hieu chuan Homography mat duong (net dut) */}
                        {z.homography_src && z.homography_src.length === 4 && (
                          <g opacity={0.75}>
                            <polygon
                              points={z.homography_src.map((p) => p.join(",")).join(" ")}
                              fill="none"
                              stroke="#10b981"
                              strokeWidth={1.5}
                              strokeDasharray="4 3"
                            />
                            {z.homography_src.map((pt, idx) => (
                              <circle key={`hz-${z.id}-${idx}`} cx={pt[0]} cy={pt[1]} r={4} fill="#10b981" />
                            ))}
                          </g>
                        )}
                        {/* Mui ten huong xe chay */}
                        {z.road_dir_points && z.road_dir_points.length === 2 ? (
                          <line
                            x1={z.road_dir_points[0][0]}
                            y1={z.road_dir_points[0][1]}
                            x2={z.road_dir_points[1][0]}
                            y2={z.road_dir_points[1][1]}
                            stroke="#facc15"
                            strokeWidth={3}
                            markerEnd="url(#arrow-yellow)"
                          />
                        ) : z.road_dir && z.road_dir.length === 2 ? (
                          <line
                            x1={midX}
                            y1={midY}
                            x2={midX + z.road_dir[0] * 50}
                            y2={midY + z.road_dir[1] * 50}
                            stroke="#facc15"
                            strokeWidth={3}
                            markerEnd="url(#arrow-yellow)"
                          />
                        ) : null}
                        {/* Nhan vung */}
                        <rect
                          x={midX - 48}
                          y={midY - 12}
                          width={96}
                          height={22}
                          fill="rgba(15, 23, 42, 0.88)"
                          stroke="#d946ef"
                          strokeWidth={1}
                          rx={4}
                        />
                        <text
                          x={midX}
                          y={midY + 3}
                          fill="#fdf4ff"
                          fontSize={11}
                          fontWeight={700}
                          textAnchor="middle"
                        >
                          {z.id}: {z.limit_kmh}km/h
                        </text>
                      </g>
                    );
                  })}

                  {/* 1.2. Draft Speeding Components khi activeRule === "speeding" */}
                  {activeRule === "speeding" && (
                    <g>
                      {/* Vung da giac lan duong dang ve */}
                      {draftPoly.length >= 3 ? (
                        <polygon
                          points={draftPoly.map((p) => p.join(",")).join(" ")}
                          fill="rgba(217, 70, 239, 0.2)"
                          stroke="#d946ef"
                          strokeWidth={2.5}
                        />
                      ) : draftPoly.length === 2 ? (
                        <line
                          x1={draftPoly[0][0]}
                          y1={draftPoly[0][1]}
                          x2={draftPoly[1][0]}
                          y2={draftPoly[1][1]}
                          stroke="#d946ef"
                          strokeWidth={2.5}
                          strokeDasharray="5 3"
                        />
                      ) : null}
                      {draftPoly.map((p, i) => (
                        <g key={`sp-poly-${i}`}>
                          <circle cx={p[0]} cy={p[1]} r={6} fill="#d946ef" stroke="#fff" strokeWidth={1.5} />
                          <text x={p[0] + 8} y={p[1] - 8} fill="#d946ef" fontSize={13} fontWeight={700}>
                            {i + 1}
                          </text>
                        </g>
                      ))}

                      {/* 4 diem Homography mat duong dang cham */}
                      {rectPts.length === 4 ? (
                        <polygon
                          points={rectPts.map((p) => p.join(",")).join(" ")}
                          fill="rgba(16, 185, 129, 0.18)"
                          stroke="#10b981"
                          strokeWidth={2}
                        />
                      ) : rectPts.length > 1 ? (
                        <polyline
                          points={rectPts.map((p) => p.join(",")).join(" ")}
                          fill="none"
                          stroke="#10b981"
                          strokeWidth={2}
                          strokeDasharray="4 3"
                        />
                      ) : null}
                      {rectPts.map((p, i) => (
                        <g key={`rect-pt-${i}`}>
                          <circle cx={p[0]} cy={p[1]} r={7} fill="#10b981" stroke="#fff" strokeWidth={2} />
                          <text x={p[0] + 8} y={p[1] - 8} fill="#10b981" fontSize={15} fontWeight={700}>
                            P{i + 1}
                          </text>
                        </g>
                      ))}

                      {/* Mui ten huong xe chay dang cham */}
                      {speedArrow.length === 2 && (
                        <line
                          x1={speedArrow[0][0]}
                          y1={speedArrow[0][1]}
                          x2={speedArrow[1][0]}
                          y2={speedArrow[1][1]}
                          stroke="#facc15"
                          strokeWidth={3.5}
                          markerEnd="url(#arrow-yellow)"
                        />
                      )}
                      {speedArrow.map((p, i) => (
                        <g key={`sp-arr-${i}`}>
                          <circle cx={p[0]} cy={p[1]} r={6} fill="#facc15" stroke="#fff" strokeWidth={2} />
                          <text x={p[0] + 8} y={p[1] - 8} fill="#facc15" fontSize={13} fontWeight={700}>
                            {i === 0 ? "A (Vị trí đến)" : "B (Hướng đi)"}
                          </text>
                        </g>
                      ))}
                    </g>
                  )}

                  {/* 2. Saved Stop Lines (Cac vach dung da luu theo tung lan) */}
                  {stopLines.map((ln) => (
                    <g key={`stop-line-${ln.id}`}>
                      <line
                        x1={ln.p1[0]}
                        y1={ln.p1[1]}
                        x2={ln.p2[0]}
                        y2={ln.p2[1]}
                        stroke="#f59e0b"
                        strokeWidth={4}
                      />
                      <text
                        x={(ln.p1[0] + ln.p2[0]) / 2}
                        y={(ln.p1[1] + ln.p2[1]) / 2 - 8}
                        fill="#f59e0b"
                        fontSize={13}
                        fontWeight={700}
                        textAnchor="middle"
                      >
                        {ln.id}
                      </text>
                    </g>
                  ))}

                  {/* 2.2. Draft Stop Line */}
                  {stopPts.length === 2 && (
                    <line
                      x1={stopPts[0][0]}
                      y1={stopPts[0][1]}
                      x2={stopPts[1][0]}
                      y2={stopPts[1][1]}
                      stroke="#f59e0b"
                      strokeWidth={4}
                    />
                  )}
                  {stopPts.map((p, i) => (
                    <circle key={`stop-pt-${i}`} cx={p[0]} cy={p[1]} r={7} fill="#f59e0b" stroke="#fff" strokeWidth={2} />
                  ))}

                  {/* 2.3. Saved Signals */}
                  {existingSignals.map((sig) => {
                    const b = sig.roi;
                    return (
                      <g key={`signal-${sig.id}`}>
                        <rect
                          x={Math.min(b[0], b[2])}
                          y={Math.min(b[1], b[3])}
                          width={Math.abs(b[2] - b[0])}
                          height={Math.abs(b[3] - b[1])}
                          fill="rgba(239, 68, 68, 0.15)"
                          stroke="#ef4444"
                          strokeWidth={2.5}
                          strokeDasharray="4 2"
                        />
                        <text
                          x={Math.min(b[0], b[2])}
                          y={Math.min(b[1], b[3]) - 6}
                          fill="#ef4444"
                          fontSize={12}
                          fontWeight={700}
                        >
                          {sig.id}
                        </text>
                      </g>
                    );
                  })}

                  {/* 2.4. Draft Signal Box */}
                  {lightPts.length === 2 && (
                    <rect
                      x={Math.min(lightPts[0][0], lightPts[1][0])}
                      y={Math.min(lightPts[0][1], lightPts[1][1])}
                      width={Math.abs(lightPts[1][0] - lightPts[0][0])}
                      height={Math.abs(lightPts[1][1] - lightPts[0][1])}
                      fill="rgba(239, 68, 68, 0.2)"
                      stroke="#ef4444"
                      strokeWidth={3}
                      strokeDasharray="6 4"
                    />
                  )}
                  {lightPts.map((p, i) => (
                    <circle key={`light-pt-${i}`} cx={p[0]} cy={p[1]} r={7} fill="#ef4444" stroke="#fff" strokeWidth={2} />
                  ))}

                  {/* 2.5. Existing Lines with Yellow Arrow allowed_vec exactly like draw_lines.py */}
                  {existingLines.map((ln) => {
                    const isDivider = ln.role === "divider";
                    const col = isDivider ? "#3b82f6" : "#22c55e";
                    const sign = ln.allowed_sign ?? 1;
                    const tag = isDivider
                      ? `${ln.id} [med]`
                      : `${ln.id} ${sign >= 0 ? "+1" : "-1"}${ln.signal_id ? ` [${ln.signal_id}]` : ""}`;
                    const arr = !isDivider ? computeAllowedVec(ln.p1, ln.p2, sign, 50) : null;
                    return (
                      <g key={`existing-line-${ln.id}`}>
                        <line
                          x1={ln.p1[0]}
                          y1={ln.p1[1]}
                          x2={ln.p2[0]}
                          y2={ln.p2[1]}
                          stroke={col}
                          strokeWidth={3}
                        />
                        {arr && (
                          <line
                            x1={arr.start[0]}
                            y1={arr.start[1]}
                            x2={arr.end[0]}
                            y2={arr.end[1]}
                            stroke="#facc15"
                            strokeWidth={3}
                            markerEnd="url(#arrow-yellow)"
                          />
                        )}
                        <text
                          x={ln.p1[0]}
                          y={ln.p1[1] - 8}
                          fill={col}
                          fontSize={14}
                          fontWeight={700}
                        >
                          {tag}
                        </text>
                      </g>
                    );
                  })}

                  {/* 2.6. All Signals (Traffic Light Boxes in Yellow with SIGNAL tag) */}
                  {existingSignals.map((s) => {
                    const x1 = Math.min(s.roi[0], s.roi[2]);
                    const y1 = Math.min(s.roi[1], s.roi[3]);
                    const w = Math.abs(s.roi[2] - s.roi[0]);
                    const h = Math.abs(s.roi[3] - s.roi[1]);
                    return (
                      <g key={`existing-sig-${s.id}`}>
                        <rect
                          x={x1}
                          y={y1}
                          width={w}
                          height={h}
                          fill="rgba(250, 204, 21, 0.15)"
                          stroke="#facc15"
                          strokeWidth={2.5}
                        />
                        <rect x={x1} y={Math.max(0, y1 - 20)} width={90} height={18} fill="#facc15" rx={2} />
                        <text x={x1 + 4} y={Math.max(0, y1 - 6)} fill="#000" fontSize={11} fontWeight={700}>
                          SIGNAL {s.id}
                        </text>
                      </g>
                    );
                  })}

                  {/* 3. Committed Zones */}
                  {customZones.map((z) => {
                    const meta = RULE_METAS.find((m) => m.key === z.rule_type);
                    const strokeCol = meta?.color || "#06b6d4";
                    const fillCol = meta?.fill || "rgba(6, 182, 212, 0.18)";
                    return (
                      <g key={`zone-${z.id}`}>
                        <polygon
                          points={z.polygon.map((p) => p.join(",")).join(" ")}
                          fill={fillCol}
                          stroke={strokeCol}
                          strokeWidth={2.5}
                        />
                        {z.arrow && z.arrow.length === 2 && (
                          <line
                            x1={z.arrow[0][0]}
                            y1={z.arrow[0][1]}
                            x2={z.arrow[1][0]}
                            y2={z.arrow[1][1]}
                            stroke={strokeCol}
                            strokeWidth={4}
                            markerEnd="url(#arrow-cyan)"
                          />
                        )}
                        <text
                          x={z.polygon[0][0] + 6}
                          y={z.polygon[0][1] - 6}
                          fill={strokeCol}
                          fontSize={16}
                          fontWeight={700}
                        >
                          {z.id}
                        </text>
                      </g>
                    );
                  })}

                  {/* 4. Draft Polygon & Arrow (Chi render cho cac rule polygon khac, khong render trung cho speeding) */}
                  {activeRule !== "speeding" && draftPoly.length > 0 && (
                    <polyline
                      points={draftPoly.map((p) => p.join(",")).join(" ")}
                      fill={currentMeta.fill}
                      stroke={currentMeta.color}
                      strokeWidth={2.5}
                      strokeDasharray="8 6"
                    />
                  )}
                  {activeRule !== "speeding" && draftPoly.map((p, i) => (
                    <circle
                      key={`draft-poly-${i}`}
                      cx={p[0]}
                      cy={p[1]}
                      r={6}
                      fill={currentMeta.color}
                      stroke="#fff"
                      strokeWidth={1.5}
                    />
                  ))}

                  {draftArrow.length === 2 && (
                    <line
                      x1={draftArrow[0][0]}
                      y1={draftArrow[0][1]}
                      x2={draftArrow[1][0]}
                      y2={draftArrow[1][1]}
                      stroke="#7dd3fc"
                      strokeWidth={4}
                      markerEnd="url(#arrow-draft)"
                    />
                  )}
                  {draftArrow.map((p, i) => (
                    <circle key={`draft-arr-${i}`} cx={p[0]} cy={p[1]} r={7} fill="#7dd3fc" stroke="#fff" strokeWidth={2} />
                  ))}

                  {/* 5. Draft Wrong-Way Line with Yellow Arrow */}
                  {draftLine.length === 2 && (
                    <g>
                      <line
                        x1={draftLine[0][0]}
                        y1={draftLine[0][1]}
                        x2={draftLine[1][0]}
                        y2={draftLine[1][1]}
                        stroke="#22c55e"
                        strokeWidth={3.5}
                      />
                      {computeAllowedVec(draftLine[0], draftLine[1], lineAllowedSign, 50) && (
                        <line
                          x1={computeAllowedVec(draftLine[0], draftLine[1], lineAllowedSign, 50)!.start[0]}
                          y1={computeAllowedVec(draftLine[0], draftLine[1], lineAllowedSign, 50)!.start[1]}
                          x2={computeAllowedVec(draftLine[0], draftLine[1], lineAllowedSign, 50)!.end[0]}
                          y2={computeAllowedVec(draftLine[0], draftLine[1], lineAllowedSign, 50)!.end[1]}
                          stroke="#facc15"
                          strokeWidth={3.5}
                          markerEnd="url(#arrow-yellow)"
                        />
                      )}
                    </g>
                  )}
                  {draftLine.map((p, i) => (
                    <g key={`draft-line-pt-${i}`}>
                      <circle cx={p[0]} cy={p[1]} r={7} fill="#22c55e" stroke="#fff" strokeWidth={2} />
                      <text x={p[0] + 8} y={p[1] - 8} fill="#22c55e" fontSize={14} fontWeight={700}>
                        P{i + 1}
                      </text>
                    </g>
                  ))}
                </svg>
              )}
            </div>
          )}

          <div className="calib-toolbar">
            <button className="button button-secondary" onClick={undoPoint}>
              <Undo2 size={15} /> Xóa điểm vừa chấm
            </button>
            <button className="button button-secondary" onClick={resetCurrentRule}>
              <RotateCcw size={15} /> Đặt lại bước này
            </button>
            <button className="button button-secondary" onClick={() => setSnapUrl(cameraSnapshotUrl(cameraId))}>
              Chụp ảnh mới
            </button>
          </div>
        </div>

        {/* Sidebar Controls - Clean Rule Selector & Dedicated Inspector */}
        <aside className="calib-panel">
          <div style={{ marginBottom: "2px" }}>
            <div style={{ fontSize: "13.5px", fontWeight: 700, color: "var(--ink)", display: "flex", alignItems: "center", gap: "6px" }}>
              <Sliders size={16} color="var(--brand)" /> Chọn quy tắc hiệu chuẩn
            </div>
            <div style={{ fontSize: "11px", color: "var(--muted)", marginTop: "2px" }}>
              Bấm vào quy tắc để mở bảng điều khiển tọa độ & thiết lập
            </div>
          </div>

          {/* 1. Thanh chọn quy tắc vi phạm (Grid 2 cột) */}
          <div className="calib-rule-selector">
            {RULE_METAS.map((m) => {
              const isSelected = activeRule === m.key;
              const badge = getRuleBadge(m.key);
              return (
                <button
                  key={m.key}
                  type="button"
                  className={`calib-rule-chip ${isSelected ? "selected" : ""}`}
                  style={{
                    borderColor: isSelected ? m.color : undefined,
                    borderLeftWidth: isSelected ? "3.5px" : "1px",
                    background: isSelected ? `${m.color}15` : undefined,
                  }}
                  onClick={() => {
                    setActiveRule(m.key);
                    setDraftPoly([]);
                    setDraftArrow([]);
                    setDrawSubMode("poly");
                  }}
                >
                  <span className="calib-chip-dot" style={{ backgroundColor: m.color }} />
                  <span className="calib-chip-label">{m.label.replace(/^\d+\.\s*/, "")}</span>
                  {badge.text !== "Chưa có" && (
                    <span className="calib-chip-status" style={{ color: badge.color }}>✓</span>
                  )}
                </button>
              );
            })}
          </div>

          {/* 2. Không gian làm việc chuyên biệt cho quy tắc đang chọn */}
          {(() => {
            const m = currentMeta;
            const badge = getRuleBadge(m.key);
            const Icon = m.icon;

            return (
              <div className="calib-workspace-card" style={{ borderTop: `3.5px solid ${m.color}` }}>
                {/* Header quy tắc */}
                <div className="calib-workspace-header">
                  <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                    <div style={{
                      width: 28,
                      height: 28,
                      borderRadius: 6,
                      background: `${m.color}22`,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0
                    }}>
                      <Icon size={16} color={m.color} />
                    </div>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: "13px", color: "var(--ink)" }}>
                        {m.label}
                      </div>
                      <div style={{ color: "var(--muted)", fontSize: "11px" }}>
                        {m.sublabel} (Phím {m.shortcut})
                      </div>
                    </div>
                  </div>
                  <span className="calib-rule-badge" style={{ color: badge.color, background: badge.bg }}>
                    {badge.text}
                  </span>
                </div>

                {/* Hướng dẫn thao tác */}
                <div style={{
                  padding: "6px 8px",
                  background: "rgba(255, 255, 255, 0.03)",
                  borderRadius: "var(--radius-sm)",
                  borderLeft: `2.5px solid ${m.color}`,
                  fontSize: "11px",
                  lineHeight: 1.4,
                  color: "var(--ink-secondary)",
                }}>
                  {m.hint}
                </div>

                {/* Rule Specific Workspace */}
                {m.key === "speeding" && (
                  <div className="calib-fields">
                    {editingSpeedZoneId ? (
                      <div style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        background: "rgba(217, 70, 239, 0.12)",
                        border: "1px solid rgba(217, 70, 239, 0.4)",
                        borderRadius: "var(--radius-sm)",
                        padding: "6px 8px",
                        fontSize: "11.5px",
                      }}>
                        <span style={{ color: "#d946ef", fontWeight: 700 }}>
                          ✎ Đang sửa: {editingSpeedZoneId}
                        </span>
                        <button
                          type="button"
                          className="button button-secondary"
                          style={{ fontSize: "10px", padding: "2px 8px" }}
                          onClick={cancelEditSpeedZone}
                        >
                          Hủy / Vẽ mới
                        </button>
                      </div>
                    ) : (
                      <div style={{ fontSize: "11px", color: "var(--muted)", lineHeight: 1.4 }}>
                        Hiệu chuẩn đo tốc độ theo chuẩn camera: <b>Vẽ làn đường + 4 góc chuẩn Homography (phím c) + Hướng xe chạy (road_dir)</b>.
                      </div>
                    )}

                    {/* 3 Tab chế độ vẽ / hiệu chuẩn */}
                    <div style={{
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr 1fr",
                      gap: "4px",
                      background: "var(--surface-raised)",
                      padding: "3px",
                      borderRadius: "var(--radius-sm)",
                    }}>
                      <button
                        type="button"
                        className={`button ${speedSubMode === "poly" ? "button-primary" : "button-secondary"}`}
                        style={{
                          fontSize: "10.5px",
                          padding: "6px 4px",
                          background: speedSubMode === "poly" ? "#d946ef" : "transparent",
                          color: speedSubMode === "poly" ? "#fff" : "var(--ink-secondary)",
                          fontWeight: speedSubMode === "poly" ? 700 : 500,
                        }}
                        onClick={() => setSpeedSubMode("poly")}
                      >
                        1. Đa giác ({draftPoly.length})
                      </button>
                      <button
                        type="button"
                        className={`button ${speedSubMode === "calib" ? "button-primary" : "button-secondary"}`}
                        style={{
                          fontSize: "10.5px",
                          padding: "6px 4px",
                          background: speedSubMode === "calib" ? "var(--emerald)" : "transparent",
                          color: speedSubMode === "calib" ? "#fff" : "var(--ink-secondary)",
                          fontWeight: speedSubMode === "calib" ? 700 : 500,
                        }}
                        onClick={() => setSpeedSubMode("calib")}
                      >
                        2. 4 góc H ({rectPts.length}/4)
                      </button>
                      <button
                        type="button"
                        className={`button ${speedSubMode === "arrow" ? "button-primary" : "button-secondary"}`}
                        style={{
                          fontSize: "10.5px",
                          padding: "6px 4px",
                          background: speedSubMode === "arrow" ? "#eab308" : "transparent",
                          color: speedSubMode === "arrow" ? "#000" : "var(--ink-secondary)",
                          fontWeight: speedSubMode === "arrow" ? 700 : 500,
                        }}
                        onClick={() => setSpeedSubMode("arrow")}
                      >
                        3. Hướng ({speedArrow.length}/2)
                      </button>
                    </div>

                    {/* Hướng dẫn và thao tác cho từng Bước */}
                    {speedSubMode === "poly" && (
                      <div style={{ fontSize: "11px", color: "var(--ink-secondary)", background: "rgba(217, 70, 239, 0.08)", padding: "8px", borderRadius: "var(--radius-sm)", borderLeft: "3px solid #d946ef", display: "flex", flexDirection: "column", gap: "6px" }}>
                        <div>
                          <b>Bước 1: Vẽ đa giác vùng làn đường</b><br />
                          Click các điểm trên ảnh để vẽ đường viền bao quanh làn đường (thẳng hoặc cong tùy ý).
                        </div>
                        <div style={{ fontSize: "10.5px", color: "var(--muted)" }}>
                          {draftPoly.length === 0 ? "Chưa chấm điểm nào. Click chuột lên khung hình để tạo đỉnh." : `Đã chấm ${draftPoly.length} đỉnh đa giác.`}
                        </div>
                        <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginTop: "2px" }}>
                          {draftPoly.length >= 3 && (
                            <button
                              type="button"
                              className="button button-primary"
                              style={{ fontSize: "11px", padding: "4px 8px", background: "var(--emerald)", flex: "1 1 auto" }}
                              onClick={() => setSpeedSubMode("calib")}
                            >
                              ✓ Chốt đa giác & Sang Bước 2 →
                            </button>
                          )}
                          {draftPoly.length === 0 && (
                            <button
                              type="button"
                              className="button button-secondary"
                              style={{ fontSize: "10.5px", padding: "3px 8px" }}
                              onClick={() => setSpeedSubMode("calib")}
                            >
                              Bỏ qua vẽ đa giác (Dùng 4 góc H) →
                            </button>
                          )}
                          {draftPoly.length > 0 && (
                            <button
                              type="button"
                              className="button button-secondary"
                              style={{ fontSize: "10.5px", padding: "3px 8px" }}
                              onClick={() => setDraftPoly([])}
                            >
                              Xóa vẽ lại đa giác
                            </button>
                          )}
                        </div>
                      </div>
                    )}

                    {speedSubMode === "calib" && (
                      <div style={{ fontSize: "11px", color: "var(--ink-secondary)", background: "rgba(16, 185, 129, 0.08)", padding: "8px", borderRadius: "var(--radius-sm)", borderLeft: "3px solid var(--emerald)", display: "flex", flexDirection: "column", gap: "6px" }}>
                        <div>
                          <b>Bước 2: Hiệu chuẩn 4 điểm mặt đường (Homography - phím c)</b><br />
                          Thứ tự chấm: <b>P1 (đáy trái) → P2 (đáy phải) → P3 (đỉnh phải) → P4 (đỉnh trái)</b>.
                        </div>
                        <div style={{ fontSize: "10.5px" }}>
                          {rectPts.length === 0 && <span style={{ color: "var(--muted)" }}>Hãy click điểm <b>P1 (đáy trái)</b> trên mặt đường.</span>}
                          {rectPts.length === 1 && <span style={{ color: "#38bdf8" }}>Đã có P1. Hãy click điểm <b>P2 (đáy phải)</b>.</span>}
                          {rectPts.length === 2 && <span style={{ color: "#38bdf8" }}>Đã có P1, P2. Hãy click điểm <b>P3 (đỉnh phải)</b>.</span>}
                          {rectPts.length === 3 && <span style={{ color: "#38bdf8" }}>Đã có P1..P3. Hãy click điểm <b>P4 (đỉnh trái)</b>.</span>}
                          {rectPts.length === 4 && <span style={{ color: "var(--emerald)", fontWeight: 700 }}>✓ Đã hoàn tất 4 điểm hiệu chuẩn Homography!</span>}
                        </div>
                        <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginTop: "2px" }}>
                          {rectPts.length === 4 && (
                            <button
                              type="button"
                              className="button button-primary"
                              style={{ fontSize: "11px", padding: "4px 8px", background: "#eab308", color: "#000", fontWeight: 700, flex: "1 1 auto" }}
                              onClick={() => setSpeedSubMode("arrow")}
                            >
                              Sang Bước 3 (Chấm hướng A→B) →
                            </button>
                          )}
                          {rectPts.length > 0 && (
                            <button
                              type="button"
                              className="button button-secondary"
                              style={{ fontSize: "10.5px", padding: "3px 8px" }}
                              onClick={() => setRectPts([])}
                            >
                              Xóa 4 góc H chấm lại
                            </button>
                          )}
                        </div>
                      </div>
                    )}

                    {speedSubMode === "arrow" && (
                      <div style={{ fontSize: "11px", color: "var(--ink-secondary)", background: "rgba(234, 179, 8, 0.08)", padding: "8px", borderRadius: "var(--radius-sm)", borderLeft: "3px solid #eab308", display: "flex", flexDirection: "column", gap: "6px" }}>
                        <div>
                          <b>Bước 3: Xác định hướng xe chạy (road_dir)</b><br />
                          Click 2 điểm: <b>A (vị trí xe đến) → B (hướng xe đi)</b> dọc theo trục làn đường.
                        </div>
                        <div style={{ fontSize: "10.5px" }}>
                          {speedArrow.length === 0 && <span style={{ color: "var(--muted)" }}>Click điểm <b>A</b> (đầu làn xe chạy vào).</span>}
                          {speedArrow.length === 1 && <span style={{ color: "#facc15" }}>Đã có điểm A. Click tiếp điểm <b>B</b> (hướng xe đi ra).</span>}
                          {speedArrow.length === 2 && <span style={{ color: "var(--emerald)", fontWeight: 700 }}>✓ Đã xác định hướng lưu thông A → B!</span>}
                        </div>
                        {speedArrow.length > 0 && (
                          <div style={{ marginTop: "2px" }}>
                            <button
                              type="button"
                              className="button button-secondary"
                              style={{ fontSize: "10.5px", padding: "3px 8px" }}
                              onClick={() => setSpeedArrow([])}
                            >
                              Xóa hướng chấm lại
                            </button>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Kích thước thực tế */}
                    <div className="calib-grid-2">
                      <label>
                        <span>Chiều rộng làn W (m)</span>
                        <input
                          type="number"
                          step="0.1"
                          value={widthM}
                          onChange={(e) => setWidthM(+e.target.value)}
                        />
                      </label>
                      <label>
                        <span>Chiều dài đoạn L (m)</span>
                        <input
                          type="number"
                          step="0.1"
                          value={lengthM}
                          onChange={(e) => setLengthM(+e.target.value)}
                        />
                      </label>
                    </div>

                    {/* Tốc độ giới hạn */}
                    <label>
                      <span>Tốc độ giới hạn tối đa (km/h)</span>
                      <input
                        type="number"
                        value={speedLimit}
                        onChange={(e) => setSpeedLimit(+e.target.value)}
                      />
                    </label>

                    {preview && (
                      <div className={`calib-preview ${preview.ok ? "ok" : "warn"}`} style={{ padding: "5px 8px", fontSize: "11px" }}>
                        {preview.ok ? "✓ " : "⚠️ "}
                        {preview.message}
                      </div>
                    )}

                    {/* Bảng tóm tắt trạng thái các bước */}
                    <div style={{
                      background: "var(--surface-sunken)",
                      padding: "6px 8px",
                      borderRadius: "var(--radius-sm)",
                      fontSize: "11px",
                      display: "flex",
                      flexDirection: "column",
                      gap: "3px",
                    }}>
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <span style={{ color: "var(--muted)" }}>1. Đa giác làn xe:</span>
                        <span style={{ color: draftPoly.length >= 3 ? "var(--emerald)" : "var(--ink-secondary)", fontWeight: 600 }}>
                          {draftPoly.length >= 3 ? `✓ ${draftPoly.length} đỉnh` : (rectPts.length === 4 ? "✓ Dùng 4 góc H" : "Tùy chọn")}
                        </span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <span style={{ color: "var(--muted)" }}>2. Mặt phẳng H:</span>
                        <span style={{ color: rectPts.length === 4 ? "var(--emerald)" : "#f43f5e", fontWeight: 600 }}>
                          {rectPts.length === 4 ? `✓ Đủ 4 góc (${widthM}m x ${lengthM}m)` : `${rectPts.length}/4 góc (Cần đủ 4)`}
                        </span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <span style={{ color: "var(--muted)" }}>3. Hướng di chuyển:</span>
                        <span style={{ color: speedArrow.length === 2 ? "var(--emerald)" : "var(--ink-secondary)", fontWeight: 600 }}>
                          {speedArrow.length === 2 ? "✓ Vector A→B" : "Mặc định [0, 1]"}
                        </span>
                      </div>
                    </div>

                    {/* Nút hành động Lưu / Cập nhật */}
                    <div style={{ marginTop: "4px" }}>
                      <button
                        type="button"
                        className="button button-primary"
                        disabled={rectPts.length !== 4}
                        onClick={saveSpeedingZone}
                        style={{
                          width: "100%",
                          background: rectPts.length === 4 ? "var(--emerald)" : "var(--surface-raised)",
                          padding: "8px 12px",
                          fontSize: "12px",
                          fontWeight: 600,
                          justifyContent: "center",
                          display: "flex",
                          alignItems: "center",
                          gap: "6px",
                        }}
                      >
                        <Check size={14} /> {editingSpeedZoneId ? `Cập nhật vùng ${editingSpeedZoneId}` : `+ Ghi thêm vùng tốc độ (SPEED_${(() => {
                          const used = new Set(speedZones.map(z => z.id));
                          let i = 1; while (used.has(`SPEED_${i}`)) i++; return i;
                        })()})`}
                      </button>
                    </div>

                    {/* Danh sách các vùng tốc độ đã lưu (hỗ trợ nhiều làn xe) */}
                    {speedZones.length > 0 && (
                      <div style={{ marginTop: 6 }}>
                        <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--muted)", marginBottom: 4 }}>
                          Vùng đo tốc độ đã lưu ({speedZones.length}):
                        </div>
                        <ul className="calib-lane-list" style={{ maxHeight: "120px", overflowY: "auto" }}>
                          {speedZones.map((z) => (
                            <li
                              key={z.id}
                              style={{
                                display: "flex",
                                justifyContent: "space-between",
                                alignItems: "center",
                                padding: "4px 8px",
                                background: editingSpeedZoneId === z.id ? "rgba(217, 70, 239, 0.15)" : "var(--surface-sunken)",
                                border: editingSpeedZoneId === z.id ? "1px solid #d946ef" : "1px solid transparent",
                                borderRadius: "4px",
                                marginBottom: "4px",
                              }}
                            >
                              <div style={{ display: "flex", flexDirection: "column" }}>
                                <span style={{ fontSize: "11.5px", fontFamily: "monospace", color: "#d946ef", fontWeight: 700 }}>
                                  {z.id} ({z.limit_kmh} km/h)
                                </span>
                                <span style={{ fontSize: "10px", color: "var(--muted)" }}>
                                  {z.width_m}m x {z.length_m}m
                                </span>
                              </div>
                              <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
                                <button
                                  type="button"
                                  onClick={() => startEditSpeedZone(z)}
                                  title={`Chỉnh sửa ${z.id}`}
                                  style={{
                                    color: "var(--text)",
                                    background: "transparent",
                                    border: "none",
                                    cursor: "pointer",
                                    padding: "2px",
                                    fontSize: "12px",
                                  }}
                                >
                                  ✎
                                </button>
                                <button
                                  type="button"
                                  onClick={() => removeSpeedZone(z.id)}
                                  title={`Xóa vùng ${z.id}`}
                                  style={{
                                    color: "var(--rose)",
                                    background: "transparent",
                                    border: "none",
                                    cursor: "pointer",
                                    padding: "2px",
                                  }}
                                >
                                  <Trash2 size={13} />
                                </button>
                              </div>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}

                {m.key === "red_light" && (
                  <div className="calib-fields">
                    <div style={{ display: "flex", gap: "6px" }}>
                      <button
                        type="button"
                        className={`calib-submode-btn ${drawSubMode === "stop" ? "active" : ""}`}
                        onClick={() => setDrawSubMode("stop")}
                      >
                        1. Vạch dừng ({stopPts.length}/2)
                      </button>
                      <button
                        type="button"
                        className={`calib-submode-btn ${drawSubMode === "light" ? "active" : ""}`}
                        onClick={() => setDrawSubMode("light")}
                      >
                        2. Hộp Đèn tín hiệu ({lightPts.length}/2)
                      </button>
                    </div>
                    <div style={{ fontSize: "11px", color: "var(--muted)" }}>
                      {drawSubMode === "stop"
                        ? "Chấm 2 điểm trên hình để tạo Vạch dừng Stop Line."
                        : "Chấm 2 góc đối diện (góc trên-trái và góc dưới-phải) để khoanh hộp Đèn tín hiệu."}
                    </div>

                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", color: "var(--muted)" }}>
                      <span>Vạch dừng: <b>{stopPts.length}/2</b></span>
                      <span>Hộp đèn: <b>{lightPts.length}/2</b></span>
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px", marginTop: "2px" }}>
                      {drawSubMode === "stop" ? (
                        <button
                          className="button button-primary"
                          disabled={stopPts.length !== 2}
                          onClick={saveStopLine}
                          style={{ background: "var(--amber)", color: "#000", fontWeight: 700, padding: "6px 8px", fontSize: "11.5px", gridColumn: "span 2" }}
                        >
                          + Ghi Vạch dừng STOP_{(() => {
                            const used = new Set(stopLines.map(l => l.id));
                            let i = 1; while (used.has(`STOP_${i}`)) i++; return i;
                          })()}
                        </button>
                      ) : (
                        <button
                          className="button button-primary"
                          disabled={lightPts.length !== 2}
                          onClick={saveSignalBox}
                          style={{ background: "var(--amber)", color: "#000", fontWeight: 700, padding: "6px 8px", fontSize: "11.5px", gridColumn: "span 2" }}
                        >
                          + Ghi Hộp đèn SIGNAL_{(() => {
                            const used = new Set(existingSignals.map(s => s.id));
                            let i = 1; while (used.has(`SIGNAL_${i}`)) i++; return i;
                          })()}
                        </button>
                      )}
                    </div>

                    {/* Danh sách vạch dừng đã lưu theo làn */}
                    {stopLines.length > 0 && (
                      <div style={{ marginTop: 4 }}>
                        <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--muted)", marginBottom: 4 }}>
                          Vạch dừng đã lưu ({stopLines.length}):
                        </div>
                        <ul className="calib-lane-list" style={{ maxHeight: "90px", overflowY: "auto" }}>
                          {stopLines.map((ln) => (
                            <li key={ln.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                              <span style={{ fontSize: "11.5px", fontFamily: "monospace", color: "var(--amber)", fontWeight: 700 }}>
                                {ln.id}
                              </span>
                              <button
                                type="button"
                                onClick={() => removeStopLine(ln.id)}
                                title={`Xóa vạch ${ln.id}`}
                                style={{ color: "var(--rose)", background: "transparent", border: "none", cursor: "pointer", padding: "2px" }}
                              >
                                <Trash2 size={13} />
                              </button>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Danh sách hộp đèn đã lưu */}
                    {existingSignals.length > 0 && (
                      <div style={{ marginTop: 4 }}>
                        <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--muted)", marginBottom: 4 }}>
                          Hộp đèn tín hiệu ({existingSignals.length}):
                        </div>
                        <ul className="calib-lane-list" style={{ maxHeight: "90px", overflowY: "auto" }}>
                          {existingSignals.map((sig) => (
                            <li key={sig.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                              <span style={{ fontSize: "11.5px", fontFamily: "monospace", color: "var(--amber)", fontWeight: 700 }}>
                                {sig.id}
                              </span>
                              <button
                                type="button"
                                onClick={() => removeSignalBox(sig.id)}
                                title={`Xóa hộp đèn ${sig.id}`}
                                style={{ color: "var(--rose)", background: "transparent", border: "none", cursor: "pointer", padding: "2px" }}
                              >
                                <Trash2 size={13} />
                              </button>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}

                {m.key === "wrong_way" && (
                  <div className="calib-fields">
                    <div style={{ fontSize: "11px", color: "var(--muted)", lineHeight: 1.4 }}>
                      Chấm 2 điểm trên hình để tạo <b>Vạch kiểm soát chiều đi (Line)</b>. Mũi tên vàng chỉ hướng lưu thông hợp pháp. Phương tiện cắt qua vạch ngược chiều mũi tên sẽ bị tính lỗi Đi ngược chiều.
                    </div>

                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "11px", color: "var(--muted)" }}>
                      <span>Điểm đã chọn: <b>{draftLine.length} / 2 điểm</b></span>
                      {draftLine.length === 2 && (
                        <span style={{ color: "#22c55e", fontWeight: 600 }}>
                          ✓ Đã sẵn sàng vạch
                        </span>
                      )}
                    </div>

                    {draftLine.length === 2 && (
                      <div
                        style={{
                          background: "rgba(34, 197, 94, 0.08)",
                          border: "1px solid rgba(34, 197, 94, 0.25)",
                          borderRadius: "var(--radius-sm)",
                          padding: "8px",
                          display: "flex",
                          flexDirection: "column",
                          gap: "6px",
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11.5px" }}>
                          <span>Hướng cho phép:</span>
                          <span style={{ color: "#facc15", fontWeight: 700, fontFamily: "monospace" }}>
                            {lineAllowedSign > 0 ? "+1 (Thuận pháp tuyến)" : "-1 (Đảo chiều)"}
                          </span>
                        </div>
                        <button
                          type="button"
                          className="button button-secondary"
                          style={{
                            width: "100%",
                            fontSize: "11.5px",
                            padding: "6px 8px",
                            borderColor: "var(--emerald)",
                            color: "var(--emerald)",
                          }}
                          onClick={() => setLineAllowedSign((s) => (s > 0 ? -1 : 1))}
                        >
                          ⇄ Đảo chiều mũi tên ({lineAllowedSign > 0 ? "+1 ➔ -1" : "-1 ➔ +1"})
                        </button>
                      </div>
                    )}

                    <button
                      type="button"
                      className="button button-primary"
                      disabled={draftLine.length !== 2}
                      onClick={saveWrongWayLine}
                      style={{
                        width: "100%",
                        background: "#22c55e",
                        borderColor: "#22c55e",
                        color: "#fff",
                        fontWeight: 700,
                        padding: "7px 10px",
                        fontSize: "12px",
                      }}
                    >
                      + Ghi vạch ngược chiều vào active.yaml
                    </button>

                    {existingLines.filter((ln) => ln.role !== "divider" && !ln.id?.toUpperCase().includes("STOP")).length > 0 && (
                      <div style={{ marginTop: 6 }}>
                        <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--muted)", marginBottom: 4 }}>
                          Vạch ngược chiều đã cấu hình ({existingLines.filter((ln) => ln.role !== "divider" && !ln.id?.toUpperCase().includes("STOP")).length}):
                        </div>
                        <ul className="calib-lane-list" style={{ maxHeight: "120px", overflowY: "auto" }}>
                          {existingLines
                            .filter((ln) => ln.role !== "divider" && !ln.id?.toUpperCase().includes("STOP"))
                            .map((ln) => (
                              <li
                                key={ln.id}
                                style={{
                                  display: "flex",
                                  justifyContent: "space-between",
                                  alignItems: "center",
                                  padding: "4px 8px",
                                  background: "var(--surface-sunken)",
                                  borderRadius: "4px",
                                  marginBottom: "4px",
                                }}
                              >
                                <span style={{ fontSize: "11.5px", fontFamily: "monospace", display: "flex", alignItems: "center", gap: "6px" }}>
                                  <span style={{ color: "#22c55e", fontWeight: 700 }}>{ln.id}</span>
                                  <span style={{ color: "#facc15", fontSize: "10.5px" }}>
                                    [sign: {ln.allowed_sign ?? 1 > 0 ? "+1" : "-1"}]
                                  </span>
                                </span>
                                <button
                                  type="button"
                                  onClick={() => removeLine(ln.id)}
                                  title={`Xóa vạch ${ln.id}`}
                                  style={{
                                    color: "var(--rose)",
                                    background: "transparent",
                                    border: "none",
                                    cursor: "pointer",
                                    padding: "2px",
                                  }}
                                >
                                  <Trash2 size={13} />
                                </button>
                              </li>
                            ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}

                {(m.key === "no_uturn" ||
                  m.key === "no_entry_road" ||
                  m.key === "no_parking" ||
                  m.key === "no_gathering") && (
                  <div className="calib-fields">
                    {(m.key === "no_entry_road" || m.key === "no_parking" || m.key === "no_gathering") && (
                      <label>
                        <span>
                          {m.key === "no_parking"
                            ? "Thời gian đỗ tối đa cho phép (giây)"
                            : m.key === "no_gathering"
                            ? "Thời gian duy trì tụ tập (giây)"
                            : "Thời gian xe lưu trong vùng cấm (giây)"}
                        </span>
                        <input
                          type="number"
                          step="0.5"
                          value={draftDwell}
                          onChange={(e) => setDraftDwell(+e.target.value)}
                        />
                      </label>
                    )}

                    {m.key === "no_gathering" && (
                      <label>
                        <span>Số lượng người tối thiểu</span>
                        <input
                          type="number"
                          value={draftMinPersons}
                          onChange={(e) => setDraftMinPersons(+e.target.value)}
                        />
                      </label>
                    )}

                    <div className="calib-count">{draftPoly.length} điểm đã chấm (Tối thiểu 3 điểm)</div>

                    <button
                      className="button button-primary"
                      disabled={draftPoly.length < 3}
                      onClick={commitZone}
                      style={{ width: "100%", padding: "7px 10px", fontSize: "12px" }}
                    >
                      + Xác nhận vùng {m.label.replace(/^\d+\.\s*/, "").split("(")[0]?.trim()} ({draftPoly.length} điểm)
                    </button>

                    {customZones.filter((z) => z.rule_type === m.key).length > 0 && (
                      <div style={{ marginTop: 4 }}>
                        <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--muted)", marginBottom: 4 }}>
                          Vùng đã tạo:
                        </div>
                        <ul className="calib-lane-list" style={{ maxHeight: "100px", overflowY: "auto" }}>
                          {customZones
                            .filter((z) => z.rule_type === m.key)
                            .map((z) => (
                              <li key={z.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <span style={{ fontSize: "11px" }}>{z.id} ({z.polygon.length} đỉnh)</span>
                                <button
                                  onClick={() => removeZone(z.id)}
                                  title="Xóa vùng"
                                  style={{ color: "var(--rose)", background: "transparent", border: "none", cursor: "pointer", padding: "2px" }}
                                >
                                  <Trash2 size={12} />
                                </button>
                              </li>
                            ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })()}

          {/* Clean Summary Footer */}
          <div style={{
            padding: "8px 12px",
            background: "var(--surface-raised)",
            borderRadius: "var(--radius-sm)",
            fontSize: "11.5px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            border: "1px solid var(--line)"
          }}>
            <span style={{ color: "var(--muted)" }}>Tổng quan giám sát:</span>
            <span style={{ fontWeight: 600, color: "var(--emerald)" }}>
              {[
                speedZones.length > 0 || rectPts.length === 4,
                stopLines.length > 0 || stopPts.length === 2,
                existingSignals.length > 0 || lightPts.length === 2,
                existingLines.length > 0,
                customZones.length > 0,
              ].filter(Boolean).length} / 5 nhóm quy tắc đã sẵn sàng
            </span>
          </div>
        </aside>
      </div>
      )}
    </div>
  );
}

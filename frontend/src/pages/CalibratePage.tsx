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
  | "lines"
  | "wrong_way"
  | "no_uturn"
  | "no_entry_road"
  | "no_parking"
  | "no_gathering";

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
    key: "wrong_way",
    label: "1. Ngược chiều (Wrong Way)",
    sublabel: "Vạch phân làn & Mũi tên chiều đi",
    shortcut: "1",
    icon: Compass,
    color: "#22c55e",
    fill: "rgba(34, 197, 94, 0.18)",
    hint: "Vẽ vạch phân làn có mũi tên hướng cho phép (+1 / -1) tương tự draw_lines.py. Bấm Space để đảo chiều mũi tên.",
  },
  {
    key: "no_uturn",
    label: "2. Cấm quay đầu (No U-Turn)",
    sublabel: "Vùng cấm quay đầu xe",
    shortcut: "2",
    icon: RotateCcw,
    color: "#8b5cf6",
    fill: "rgba(139, 92, 246, 0.18)",
    hint: "Chấm các điểm bao quanh khu vực cấm hành vi quay đầu xe (tối thiểu 3 điểm).",
  },
  {
    key: "no_entry_road",
    label: "3. Đường cấm (No Entry)",
    sublabel: "Vùng cấm lưu thông [banned]",
    shortcut: "3",
    icon: CircleSlash,
    color: "#ef4444",
    fill: "rgba(239, 68, 68, 0.2)",
    hint: "Chấm các điểm tạo đa giác vùng đường cấm loại [banned] (viền đỏ như draw_lines.py).",
  },
  {
    key: "red_light",
    label: "4. Đèn đỏ & Vạch dừng",
    sublabel: "Stop Line & Signal Box",
    shortcut: "4",
    icon: TrafficCone,
    color: "#f59e0b",
    fill: "rgba(245, 158, 11, 0.18)",
    hint: "Chấm 2 điểm tạo Vạch dừng ngang đường + Khoanh hộp đèn giao thông SIGNAL (viền vàng viền đôi).",
  },
  {
    key: "speeding",
    label: "5. Đo tốc độ (Speeding)",
    sublabel: "Hiệu chuẩn H & road_dir",
    shortcut: "5",
    icon: Gauge,
    color: "#d946ef",
    fill: "rgba(217, 70, 239, 0.18)",
    hint: "Chấm 4 góc chuẩn P1..P4 (màu cánh sen như draw_lines.py) và đường hướng road_dir chiếu theo mặt đường thực tế.",
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
  {
    key: "lines",
    label: "L. Vạch kẻ phân làn (Lines)",
    sublabel: "Vạch L1, L2, dải phân cách",
    shortcut: "L",
    icon: TrafficCone,
    color: "#38bdf8",
    fill: "rgba(56, 189, 248, 0.18)",
    hint: "Chấm 2 điểm tạo vạch phân làn độc lập. Bấm Space để đảo chiều mũi tên hướng cho phép.",
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

  // Speeding
  const [rectPts, setRectPts] = useState<number[][]>([]);
  const [widthM, setWidthM] = useState(3.5);
  const [lengthM, setLengthM] = useState(15.0);
  const [speedLimit, setSpeedLimit] = useState(50);
  const [speedRoadDirPts, setSpeedRoadDirPts] = useState<number[][]>([]);
  const [speedSubMode, setSpeedSubMode] = useState<"corners" | "road_dir">("corners");
  const [preview, setPreview] = useState<HomographyPreview | null>(null);

  // Red Light & Stop Line
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

        // 1. Homography / Speeding rectangle
        const speedPoly = cfg.polygons?.find((p) => p.homography?.src && p.homography.src.length === 4);
        if (speedPoly && speedPoly.homography?.src) {
          setRectPts(speedPoly.homography.src);
          if (speedPoly.homography.dst && speedPoly.homography.dst.length === 4) {
            const dst = speedPoly.homography.dst;
            const w = Math.round(Math.abs(dst[1][0] - dst[0][0]) * 10) / 10;
            const l = Math.round(Math.abs(dst[2][1] - dst[1][1]) * 10) / 10;
            if (w > 0) setWidthM(w);
            if (l > 0) setLengthM(l);
          }
          const spLimit = speedPoly.rules?.speeding?.limit_kmh || speedPoly.rules?.speeding?.speed_limit_kmh;
          if (spLimit) setSpeedLimit(spLimit);
          if (speedPoly.road_dir_points && speedPoly.road_dir_points.length === 2) {
            setSpeedRoadDirPts(speedPoly.road_dir_points);
          } else if (speedPoly.road_dir && speedPoly.road_dir.length === 2 && speedPoly.homography?.src?.length === 4) {
            const src = speedPoly.homography.src;
            const sortedByY = [...src].sort((a: number[], b: number[]) => b[1] - a[1]);
            const nearMid = [(sortedByY[0][0] + sortedByY[1][0]) / 2, (sortedByY[0][1] + sortedByY[1][1]) / 2];
            const farMid = [(sortedByY[2][0] + sortedByY[3][0]) / 2, (sortedByY[2][1] + sortedByY[3][1]) / 2];
            if (speedPoly.road_dir[1] >= 0) {
              setSpeedRoadDirPts([
                [Math.round(nearMid[0]), Math.round(nearMid[1])],
                [Math.round(farMid[0]), Math.round(farMid[1])],
              ]);
            } else {
              setSpeedRoadDirPts([
                [Math.round(farMid[0]), Math.round(farMid[1])],
                [Math.round(nearMid[0]), Math.round(nearMid[1])],
              ]);
            }
          }
        }

        // 2. Stop Line & Traffic Lines
        if (cfg.lines) {
          const stopLine = cfg.lines.find(
            (ln) => ln.id?.toUpperCase().includes("STOP") || ln.role === "stop"
          );
          if (stopLine && stopLine.p1 && stopLine.p2) {
            setStopPts([stopLine.p1, stopLine.p2]);
          }
          const otherLines = cfg.lines.filter((ln) => ln !== stopLine && ln.p1 && ln.p2);
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
          if (rules.wrong_way?.enable) matchedRule = "wrong_way";
          else if (rules.no_uturn?.enable) matchedRule = "no_uturn";
          else if (rules.no_entry_road?.enable || (p.kind === "banned" && !rules.no_parking?.enable)) matchedRule = "no_entry_road";
          else if (rules.no_parking?.enable) matchedRule = "no_parking";
          else if (rules.no_gathering?.enable) matchedRule = "no_gathering";
          else if (rules.speeding?.enable && p !== speedPoly) matchedRule = "speeding";

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

  const addPoint = useCallback(
    (p: number[]) => {
      if (activeRule === "speeding") {
        if (speedSubMode === "road_dir") {
          setSpeedRoadDirPts((v) => (v.length >= 2 ? [p] : [...v, p]));
        } else {
          setRectPts((v) => (v.length >= 4 ? v : [...v, p]));
        }
      } else if (activeRule === "red_light") {
        if (drawSubMode === "stop") {
          setStopPts((v) => (v.length >= 2 ? v : [...v, p]));
        } else {
          setLightPts((v) => (v.length >= 2 ? [p] : [...v, p]));
        }
      } else if (activeRule === "lines") {
        setDraftLine((v) => (v.length >= 2 ? [p] : [...v, p]));
      } else if (activeRule === "wrong_way") {
        if (drawSubMode === "poly") {
          setDraftPoly((v) => [...v, p]);
        } else {
          setDraftArrow((v) => (v.length >= 2 ? v : [...v, p]));
        }
      } else {
        // polygon rules: no_uturn, no_entry_road, no_parking, no_gathering
        setDraftPoly((v) => [...v, p]);
      }
    },
    [activeRule, drawSubMode, speedSubMode]
  );

  function onSvgClick(e: React.MouseEvent) {
    if (!nat || !svgRef.current) return;
    const r = svgRef.current.getBoundingClientRect();
    const x = Math.round(((e.clientX - r.left) / r.width) * nat.w);
    const y = Math.round(((e.clientY - r.top) / r.height) * nat.h);
    addPoint([x, y]);
  }

  function undoPoint() {
    if (activeRule === "speeding") {
      if (speedSubMode === "corners") {
        setRectPts((v) => v.slice(0, -1));
      } else {
        setSpeedRoadDirPts((v) => v.slice(0, -1));
      }
    } else if (activeRule === "lines") {
      setDraftLine((v) => v.slice(0, -1));
    } else if (activeRule === "red_light") {
      if (drawSubMode === "stop") setStopPts((v) => v.slice(0, -1));
      else setLightPts((v) => v.slice(0, -1));
    } else if (activeRule === "wrong_way") {
      if (drawSubMode === "arrow") setDraftArrow((v) => v.slice(0, -1));
      else setDraftPoly((v) => v.slice(0, -1));
    } else {
      setDraftPoly((v) => v.slice(0, -1));
    }
  }

  function resetCurrentRule() {
    if (activeRule === "speeding") {
      setRectPts([]);
      setSpeedRoadDirPts([]);
      setPreview(null);
    } else if (activeRule === "lines") {
      setDraftLine([]);
    } else if (activeRule === "red_light") {
      if (stopPts.length > 0 || lightPts.length > 0) {
        deleteEntireRedLightRule();
      } else {
        setStopPts([]);
        setLightPts([]);
      }
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
      arrow: activeRule === "wrong_way" && draftArrow.length === 2 ? draftArrow : undefined,
      dwell_s:
        activeRule === "no_entry_road" || activeRule === "no_parking" || activeRule === "no_gathering"
          ? draftDwell
          : undefined,
      min_persons: activeRule === "no_gathering" ? draftMinPersons : undefined,
    };

    // Chuẩn bị payload chuẩn theo format draw_lines.py & zones.py
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

    if (activeRule === "wrong_way" && draftArrow.length === 2) {
      const dx = draftArrow[1][0] - draftArrow[0][0];
      const dy = draftArrow[1][1] - draftArrow[0][1];
      const mag = Math.hypot(dx, dy) || 1;
      const unitDx = Math.round((dx / mag) * 1000) / 1000;
      const unitDy = Math.round((dy / mag) * 1000) / 1000;
      polyPayload.road_dir = [unitDx, unitDy];
      polyPayload.road_dir_points = draftArrow;
      const mx = (draftArrow[0][0] + draftArrow[1][0]) / 2;
      const my = (draftArrow[0][1] + draftArrow[1][1]) / 2;
      // Perpendicular vector for allowed_vec(p1, p2, 1) = [unitDx, unitDy]:
      const px = dy / mag;
      const py = -dx / mag;
      polyPayload.lines = [{
        id: `LINE_${zoneId}`,
        p1: [Math.round(mx - px * 60), Math.round(my - py * 60)],
        p2: [Math.round(mx + px * 60), Math.round(my + py * 60)],
        allowed_sign: 1,
      }];
    }

    try {
      // Ghi trực tiếp vào configs/active.yaml trên máy chủ
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

  function loadSampleCam01Calib() {
    // Toa do mat duong chuan tu draw_lines.py (cam_01.yaml)
    setRectPts([[769, 391], [907, 393], [757, 1001], [31, 1003]]);
    setWidthM(7.5);
    setLengthM(50.0);
    setSpeedLimit(50);
    setSpeedRoadDirPts([[838, 392], [394, 1002]]);
    setSyncStatus("✓ Đã nạp tọa độ & kích thước hiệu chuẩn chuẩn xác từ máy (7.5m x 50.0m)!");
  }

  function autoCalculateSpeedRoadDir() {
    if (rectPts.length !== 4) return;
    const sortedByY = [...rectPts].sort((a, b) => b[1] - a[1]);
    const nearMid = [(sortedByY[0][0] + sortedByY[1][0]) / 2, (sortedByY[0][1] + sortedByY[1][1]) / 2];
    const farMid = [(sortedByY[2][0] + sortedByY[3][0]) / 2, (sortedByY[2][1] + sortedByY[3][1]) / 2];
    setSpeedRoadDirPts([
      [Math.round(nearMid[0]), Math.round(nearMid[1])],
      [Math.round(farMid[0]), Math.round(farMid[1])],
    ]);
  }

  async function saveSpeedingZone() {
    if (rectPts.length !== 4) return;
    setError("");
    setSyncStatus("");
    const world = [
      [0.0, 0.0],
      [widthM, 0.0],
      [widthM, lengthM],
      [0.0, lengthM],
    ];

    const polyPayload: any = {
      id: "POLY_1",
      kind: "directional",
      polygon: rectPts,
      road_dir_points: speedRoadDirPts.length === 2 ? speedRoadDirPts : undefined,
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
      await api.saveCameraPolygon(cameraId, polyPayload);
      setSyncStatus("✓ Đã ghi trực tiếp ma trận Homography & vùng tốc độ POLY_1 vào active.yaml!");
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
    try {
      await api.saveCameraLine(cameraId, {
        id: "STOP_1",
        p1: stopPts[0],
        p2: stopPts[1],
        pt1: stopPts[0],
        pt2: stopPts[1],
      });
      setSyncStatus("✓ Đã ghi trực tiếp vạch dừng STOP_1 vào active.yaml!");
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
    const box = [
      Math.min(lightPts[0][0], lightPts[1][0]),
      Math.min(lightPts[0][1], lightPts[1][1]),
      Math.max(lightPts[0][0], lightPts[1][0]),
      Math.max(lightPts[0][1], lightPts[1][1]),
    ];
    try {
      await api.saveCameraSignal(cameraId, {
        id: "SIGNAL_1",
        roi: box,
        box: box,
        default: "red",
      });
      setSyncStatus("✓ Đã ghi trực tiếp hộp đèn SIGNAL_1 vào active.yaml!");
      const cfg = await api.cameraConfig(cameraId);
      if (cfg?.raw_yaml) setRawYaml(cfg.raw_yaml);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function deleteStopLine() {
    if (!window.confirm("Xác nhận xóa vạch dừng STOP_1 khỏi active.yaml?")) return;
    try {
      await api.deleteCameraLine(cameraId, "STOP_1");
      setStopPts([]);
      setSyncStatus("✓ Đã xóa vạch dừng STOP_1 khỏi configs/active.yaml!");
      const cfg = await api.cameraConfig(cameraId);
      if (cfg?.raw_yaml) setRawYaml(cfg.raw_yaml);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function deleteSignalBox() {
    if (!window.confirm("Xác nhận xóa hộp đèn SIGNAL_1 khỏi active.yaml?")) return;
    try {
      await api.deleteCameraSignal(cameraId, "SIGNAL_1");
      setLightPts([]);
      setSyncStatus("✓ Đã xóa hộp đèn tín hiệu SIGNAL_1 khỏi configs/active.yaml!");
      const cfg = await api.cameraConfig(cameraId);
      if (cfg?.raw_yaml) setRawYaml(cfg.raw_yaml);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function deleteEntireRedLightRule() {
    if (!window.confirm("Xác nhận xóa TOÀN BỘ cấu hình Vượt đèn đỏ & Đè vạch (vạch dừng + hộp đèn) khỏi active.yaml?")) return;
    try {
      try { await api.deleteCameraLine(cameraId, "STOP_1"); } catch (_) {}
      try { await api.deleteCameraSignal(cameraId, "SIGNAL_1"); } catch (_) {}
      setStopPts([]);
      setLightPts([]);
      setSyncStatus("✓ Đã xóa hoàn toàn cấu hình Vượt đèn đỏ & Đè vạch khỏi configs/active.yaml!");
      const cfg = await api.cameraConfig(cameraId);
      if (cfg?.raw_yaml) setRawYaml(cfg.raw_yaml);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function saveLaneLine() {
    if (draftLine.length !== 2) return;
    setError("");
    setSyncStatus("");
    const nextNum = existingLines.length + 1;
    const lid = `L${nextNum}`;
    const payload = {
      id: lid,
      p1: draftLine[0],
      p2: draftLine[1],
      allowed_sign: lineAllowedSign,
    };
    try {
      await api.saveCameraLine(cameraId, payload);
      setExistingLines((v) => [...v, payload]);
      setDraftLine([]);
      setSyncStatus(`✓ Đã ghi trực tiếp vạch phân làn ${lid} vào active.yaml!`);
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
      lanes: customZones
        .filter((z) => z.rule_type === "wrong_way")
        .map((z) => ({
          id: z.id,
          polygon: z.polygon,
          arrow: z.arrow || [],
          speed_limit_kmh: speedLimit,
        })),
      rule_zones: ruleZones,
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
    if (key === "lines") {
      if (existingLines.length > 0) {
        return { text: `✓ ${existingLines.length} vạch kẻ`, color: "#38bdf8", bg: "rgba(56, 189, 248, 0.15)" };
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

      <div className="page-heading">
        <div>
          <span className="eyebrow">Cấu hình thông số giám sát</span>
          <div style={{ display: "flex", alignItems: "center", gap: "12px", marginTop: "4px" }}>
            <h1 style={{ margin: 0 }}>Hiệu chuẩn Camera: {camera?.name}</h1>
            {configLoaded && (
              <span style={{
                background: "rgba(16, 185, 129, 0.15)",
                color: "#10b981",
                border: "1px solid rgba(16, 185, 129, 0.3)",
                borderRadius: "20px",
                padding: "3px 12px",
                fontSize: "12px",
                fontWeight: 600,
                display: "inline-flex",
                alignItems: "center",
                gap: "6px"
              }}>
                <Check size={14} /> Đồng bộ từ active.yaml: {customZones.length + (rectPts.length ? 1 : 0)} vùng, {existingLines.length + (stopPts.length ? 1 : 0)} vạch kẻ
              </span>
            )}
          </div>
          <p>
            Vẽ vùng hình học và thiết lập quy tắc cho từng lỗi vi phạm thực tế (Quá tốc độ, Vượt đèn đỏ, Ngược chiều, Cấm dừng đỗ...).
          </p>
        </div>
        <button className="button button-primary" onClick={save} disabled={saving}>
          <Check size={16} />
          {saving ? "Đang lưu cấu hình…" : "Lưu & Kích hoạt giám sát"}
        </button>
      </div>

      {/* Tab Switcher: Visual vs Raw YAML */}
      <div style={{ display: "flex", gap: "10px", marginBottom: "16px" }}>
        <button
          className={`button ${activeTab === "visual" ? "button-primary" : "button-secondary"}`}
          onClick={() => setActiveTab("visual")}
          style={{ display: "flex", alignItems: "center", gap: "8px" }}
        >
          <Edit3 size={16} /> 1. Chỉnh sửa trực quan trên hình ảnh (Visual Canvas)
        </button>
        <button
          className={`button ${activeTab === "yaml" ? "button-primary" : "button-secondary"}`}
          onClick={() => setActiveTab("yaml")}
          style={{ display: "flex", alignItems: "center", gap: "8px" }}
        >
          <FileCode size={16} /> 2. Soạn thảo file cấu hình active.yaml (Raw Editor)
        </button>
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

                  {/* 1. Ground Rectangle & road_dir (Speeding Calib P1..P4 in Magenta like draw_lines.py) */}
                  {rectPts.length > 1 && (
                    <polygon
                      points={rectPts.map((p) => p.join(",")).join(" ")}
                      fill="rgba(217, 70, 239, 0.18)"
                      stroke="#d946ef"
                      strokeWidth={3}
                    />
                  )}
                  {speedRoadDirPts.length === 2 && (
                    <g>
                      <line
                        x1={speedRoadDirPts[0][0]}
                        y1={speedRoadDirPts[0][1]}
                        x2={speedRoadDirPts[1][0]}
                        y2={speedRoadDirPts[1][1]}
                        stroke="#d946ef"
                        strokeWidth={4.5}
                        markerEnd="url(#arrow-magenta)"
                      />
                      <circle cx={speedRoadDirPts[0][0]} cy={speedRoadDirPts[0][1]} r={6} fill="#a21caf" stroke="#fff" strokeWidth={2} />
                      <circle cx={speedRoadDirPts[1][0]} cy={speedRoadDirPts[1][1]} r={7} fill="#d946ef" stroke="#fff" strokeWidth={2} />
                      <text
                        x={(speedRoadDirPts[0][0] + speedRoadDirPts[1][0]) / 2 + 10}
                        y={(speedRoadDirPts[0][1] + speedRoadDirPts[1][1]) / 2 - 10}
                        fill="#d946ef"
                        fontSize={14}
                        fontWeight={700}
                      >
                        road_dir (A-&gt;B)
                      </text>
                    </g>
                  )}
                  {rectPts.map((p, i) => (
                    <g key={`rect-pt-${i}`}>
                      <circle cx={p[0]} cy={p[1]} r={8} fill="#d946ef" stroke="#fff" strokeWidth={2} />
                      <text x={p[0] + 10} y={p[1] - 8} fill="#d946ef" fontSize={20} fontWeight={700}>
                        P{i + 1}
                      </text>
                    </g>
                  ))}

                  {/* 2. Stop Line & Traffic Light */}
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

                  {/* 4. Draft Polygon & Arrow */}
                  {draftPoly.length > 0 && (
                    <polyline
                      points={draftPoly.map((p) => p.join(",")).join(" ")}
                      fill={currentMeta.fill}
                      stroke={currentMeta.color}
                      strokeWidth={2.5}
                      strokeDasharray="8 6"
                    />
                  )}
                  {draftPoly.map((p, i) => (
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

                  {/* 5. Draft Lane Line */}
                  {draftLine.length === 2 && (
                    <g>
                      <line
                        x1={draftLine[0][0]}
                        y1={draftLine[0][1]}
                        x2={draftLine[1][0]}
                        y2={draftLine[1][1]}
                        stroke="#38bdf8"
                        strokeWidth={3.5}
                        markerEnd="url(#arrow-cyan)"
                      />
                    </g>
                  )}
                  {draftLine.map((p, i) => (
                    <circle key={`draft-line-pt-${i}`} cx={p[0]} cy={p[1]} r={6.5} fill="#38bdf8" stroke="#fff" strokeWidth={2} />
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

        {/* Sidebar Controls - Clean Accordion Layout */}
        <aside className="calib-panel">
          <div style={{ marginBottom: "2px" }}>
            <div style={{ fontSize: "14px", fontWeight: 700, color: "var(--ink)", display: "flex", alignItems: "center", gap: "6px" }}>
              <Sliders size={16} color="var(--brand)" /> Cấu hình quy tắc & tọa độ
            </div>
            <div style={{ fontSize: "11.5px", color: "var(--muted)", marginTop: "2px" }}>
              Bấm vào quy tắc bên dưới để mở giao diện chọn điểm góc & thiết lập
            </div>
          </div>

          <div className="calib-accordion-group">
            {RULE_METAS.map((m) => {
              const isOpen = activeRule === m.key;
              const badge = getRuleBadge(m.key);
              const Icon = m.icon;

              return (
                <div
                  key={m.key}
                  className={`calib-accordion-item ${isOpen ? "active" : ""}`}
                  style={{ borderLeft: `3.5px solid ${m.color}` }}
                >
                  <button
                    type="button"
                    className="calib-accordion-header"
                    onClick={() => {
                      if (!isOpen) {
                        setActiveRule(m.key);
                        setDraftPoly([]);
                        setDraftArrow([]);
                        setDrawSubMode("poly");
                      }
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
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
                      <div style={{ minWidth: 0, textAlign: "left" }}>
                        <div style={{ fontWeight: 600, fontSize: "13px", color: isOpen ? "var(--ink)" : "var(--ink-secondary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                          {m.label}
                        </div>
                        <div style={{ color: "var(--muted)", fontSize: "11px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                          {m.sublabel}
                        </div>
                      </div>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
                      <span className="calib-rule-badge" style={{ color: badge.color, background: badge.bg }}>
                        {badge.text}
                      </span>
                      {isOpen ? <ChevronUp size={16} color="var(--muted)" /> : <ChevronDown size={16} color="var(--muted)" />}
                    </div>
                  </button>

                  {isOpen && (
                    <div className="calib-accordion-body">
                      {/* Hint Banner */}
                      <div style={{
                        padding: "8px 10px",
                        background: "rgba(255, 255, 255, 0.03)",
                        borderRadius: "var(--radius-sm)",
                        borderLeft: `2.5px solid ${m.color}`,
                        fontSize: "11.5px",
                        lineHeight: 1.45,
                        color: "var(--ink-secondary)",
                      }}>
                        {m.hint}
                      </div>

                      {/* Rule Specific Workspace */}
                      {m.key === "speeding" && (
                        <div className="calib-fields">
                          <div style={{ display: "flex", gap: "6px" }}>
                            <button
                              type="button"
                              className={`calib-submode-btn ${speedSubMode === "corners" ? "active" : ""}`}
                              onClick={() => setSpeedSubMode("corners")}
                            >
                              1. 4 Điểm góc ({rectPts.length}/4)
                            </button>
                            <button
                              type="button"
                              className={`calib-submode-btn ${speedSubMode === "road_dir" ? "active-emerald" : ""}`}
                              onClick={() => setSpeedSubMode("road_dir")}
                            >
                              2. Hướng xe chạy ({speedRoadDirPts.length}/2)
                            </button>
                          </div>

                          {speedSubMode === "corners" && (
                            <div style={{ fontSize: "11.5px", color: "var(--muted)" }}>
                              Chấm 4 góc theo thứ tự: <b>P1 (đáy trái) → P2 (đáy phải) → P3 (đỉnh phải) → P4 (đỉnh trái)</b>.
                            </div>
                          )}

                          {speedSubMode === "road_dir" && (
                            <div style={{ background: "rgba(16, 185, 129, 0.08)", border: "1px solid rgba(16, 185, 129, 0.25)", borderRadius: "var(--radius-sm)", padding: "8px 10px" }}>
                              <div style={{ fontSize: "11.5px", color: "var(--text)", marginBottom: "6px" }}>
                                <b>Chấm 2 điểm trên hình</b>: Đuôi mũi tên → Đầu mũi tên theo chiều xe chạy.
                              </div>
                              {speedRoadDirPts.length === 2 && (
                                <div style={{ fontSize: "11.5px", color: "#10b981", fontWeight: 600, marginBottom: "6px" }}>
                                  Vector: [{((speedRoadDirPts[1][0] - speedRoadDirPts[0][0]) / (Math.hypot(speedRoadDirPts[1][0] - speedRoadDirPts[0][0], speedRoadDirPts[1][1] - speedRoadDirPts[0][1]) || 1)).toFixed(3)}, {((speedRoadDirPts[1][1] - speedRoadDirPts[0][1]) / (Math.hypot(speedRoadDirPts[1][0] - speedRoadDirPts[0][0], speedRoadDirPts[1][1] - speedRoadDirPts[0][1]) || 1)).toFixed(3)}]
                                </div>
                              )}
                              <div style={{ display: "flex", gap: "6px" }}>
                                <button
                                  type="button"
                                  className="button button-secondary"
                                  style={{ flex: 1, fontSize: "11px", padding: "4px 6px" }}
                                  disabled={speedRoadDirPts.length !== 2}
                                  onClick={() => setSpeedRoadDirPts([speedRoadDirPts[1], speedRoadDirPts[0]])}
                                >
                                  ⇄ Đảo chiều
                                </button>
                                <button
                                  type="button"
                                  className="button button-secondary"
                                  style={{ flex: 1, fontSize: "11px", padding: "4px 6px" }}
                                  disabled={rectPts.length !== 4}
                                  onClick={autoCalculateSpeedRoadDir}
                                >
                                  ⚡ Tự động trục dọc
                                </button>
                              </div>
                            </div>
                          )}

                          <div className="calib-grid-2">
                            <label>
                              <span>Chiều rộng đường (m)</span>
                              <input
                                type="number"
                                step="0.1"
                                value={widthM}
                                onChange={(e) => setWidthM(+e.target.value)}
                              />
                            </label>
                            <label>
                              <span>Chiều dài đoạn đo (m)</span>
                              <input
                                type="number"
                                step="0.1"
                                value={lengthM}
                                onChange={(e) => setLengthM(+e.target.value)}
                              />
                            </label>
                          </div>

                          <label>
                            <span>Tốc độ giới hạn (km/h)</span>
                            <input
                              type="number"
                              value={speedLimit}
                              onChange={(e) => setSpeedLimit(+e.target.value)}
                            />
                          </label>

                          {preview && (
                            <div className={`calib-preview ${preview.ok ? "ok" : "warn"}`} style={{ padding: "6px 10px", fontSize: "11.5px" }}>
                              {preview.ok ? "✓ " : "⚠️ "}
                              {preview.message}
                            </div>
                          )}

                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "11.5px", color: "var(--muted)" }}>
                            <span>Điểm góc: <b>{rectPts.length}/4</b></span>
                            {speedRoadDirPts.length === 2 && <span style={{ color: "#10b981", fontWeight: 600 }}>✓ Đã có hướng road_dir</span>}
                          </div>

                          <button
                            type="button"
                            className="button button-secondary"
                            onClick={loadSampleCam01Calib}
                            style={{ width: "100%", fontSize: "11px", borderColor: "var(--emerald)", color: "var(--emerald)", padding: "6px" }}
                          >
                            🎯 Nạp thông số mẫu chuẩn (cam_01.yaml)
                          </button>

                          <button
                            className="button button-primary"
                            disabled={rectPts.length !== 4}
                            onClick={saveSpeedingZone}
                            style={{ width: "100%", background: "var(--emerald)", padding: "8px" }}
                          >
                            + Ghi trực tiếp Homography vào active.yaml
                          </button>
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
                          <div style={{ fontSize: "11.5px", color: "var(--muted)" }}>
                            Vạch dừng dùng cho cả 2 lỗi: <b>Đè vạch dừng</b> và <b>Vượt đèn đỏ</b>.
                          </div>
                          <div className="calib-grid-2">
                            <button
                              className="button button-primary"
                              disabled={stopPts.length !== 2}
                              onClick={saveStopLine}
                              style={{ fontSize: "11.5px", padding: "7px 4px" }}
                            >
                              + Lưu Vạch dừng
                            </button>
                            <button
                              className="button button-primary"
                              disabled={lightPts.length !== 2}
                              onClick={saveSignalBox}
                              style={{ fontSize: "11.5px", padding: "7px 4px" }}
                            >
                              + Lưu Hộp đèn
                            </button>
                          </div>

                          {/* Status & Deletion Controls */}
                          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                            {stopPts.length === 2 && (
                              <div style={{
                                display: "flex",
                                justifyContent: "space-between",
                                alignItems: "center",
                                background: "rgba(245, 158, 11, 0.12)",
                                border: "1px solid rgba(245, 158, 11, 0.3)",
                                padding: "6px 8px",
                                borderRadius: "var(--radius-sm)"
                              }}>
                                <span style={{ fontSize: "11.5px", color: "#f59e0b", fontWeight: 600 }}>
                                  ✓ Vạch dừng STOP_1
                                </span>
                                <button
                                  type="button"
                                  className="button button-danger"
                                  onClick={deleteStopLine}
                                  style={{ fontSize: "10.5px", padding: "2px 6px" }}
                                >
                                  <Trash2 size={11} /> Xóa
                                </button>
                              </div>
                            )}

                            {lightPts.length === 2 && (
                              <div style={{
                                display: "flex",
                                justifyContent: "space-between",
                                alignItems: "center",
                                background: "rgba(239, 68, 68, 0.12)",
                                border: "1px solid rgba(239, 68, 68, 0.3)",
                                padding: "6px 8px",
                                borderRadius: "var(--radius-sm)"
                              }}>
                                <span style={{ fontSize: "11.5px", color: "#ef4444", fontWeight: 600 }}>
                                  ✓ Hộp đèn SIGNAL_1
                                </span>
                                <button
                                  type="button"
                                  className="button button-danger"
                                  onClick={deleteSignalBox}
                                  style={{ fontSize: "10.5px", padding: "2px 6px" }}
                                >
                                  <Trash2 size={11} /> Xóa
                                </button>
                              </div>
                            )}

                            {(stopPts.length > 0 || lightPts.length > 0) && (
                              <button
                                type="button"
                                className="button button-danger"
                                onClick={deleteEntireRedLightRule}
                                style={{ width: "100%", fontSize: "11.5px", marginTop: "2px", padding: "6px" }}
                              >
                                <Trash2 size={12} /> Xóa sạch cấu hình Đèn đỏ
                              </button>
                            )}
                          </div>
                        </div>
                      )}

                      {m.key === "lines" && (
                        <div className="calib-fields">
                          <label>
                            <span>Hướng được phép lưu thông</span>
                            <select
                              value={lineAllowedSign}
                              onChange={(e) => setLineAllowedSign(+e.target.value)}
                              style={{ width: "100%", padding: "7px", borderRadius: "var(--radius-sm)", background: "var(--surface)", color: "inherit", border: "1px solid var(--line)" }}
                            >
                              <option value={1}>Cùng chiều mũi tên (allowed_sign: +1)</option>
                              <option value={-1}>Ngược chiều mũi tên (allowed_sign: -1)</option>
                            </select>
                          </label>
                          <div className="calib-count">{draftLine.length} / 2 điểm (Điểm đầu → Điểm cuối)</div>
                          <button
                            className="button button-primary"
                            disabled={draftLine.length !== 2}
                            onClick={saveLaneLine}
                            style={{ width: "100%", padding: "8px" }}
                          >
                            + Ghi vạch phân làn vào active.yaml
                          </button>

                          {existingLines.length > 0 && (
                            <div style={{ marginTop: 6 }}>
                              <div style={{ fontSize: "11.5px", fontWeight: 600, color: "var(--muted)", marginBottom: 4 }}>
                                Vạch kẻ hiện có ({existingLines.length}):
                              </div>
                              <ul className="calib-lane-list" style={{ maxHeight: "120px", overflowY: "auto" }}>
                                {existingLines.map((ln) => (
                                  <li key={ln.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                    <span style={{ fontSize: "11px" }}>{ln.id} ([{ln.p1[0]}, {ln.p1[1]}] → [{ln.p2[0]}, {ln.p2[1]}])</span>
                                    <button
                                      onClick={() => removeLine(ln.id)}
                                      title="Xóa vạch kẻ khỏi active.yaml"
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

                      {m.key === "wrong_way" && (
                        <div className="calib-fields">
                          <div style={{ display: "flex", gap: "6px" }}>
                            <button
                              type="button"
                              className={`calib-submode-btn ${drawSubMode === "poly" ? "active" : ""}`}
                              onClick={() => setDrawSubMode("poly")}
                            >
                              1. Viền làn ({draftPoly.length} điểm)
                            </button>
                            <button
                              type="button"
                              className={`calib-submode-btn ${drawSubMode === "arrow" ? "active" : ""}`}
                              disabled={draftPoly.length < 3}
                              onClick={() => setDrawSubMode("arrow")}
                            >
                              2. Mũi tên ({draftArrow.length}/2)
                            </button>
                          </div>

                          <div style={{ fontSize: "11.5px", color: "var(--muted)" }}>
                            {drawSubMode === "poly"
                              ? "Chấm tối thiểu 3 điểm bao quanh làn đường một chiều."
                              : "Chấm 2 điểm tạo mũi tên chỉ chiều xe chạy đúng luật."}
                          </div>

                          <button
                            className="button button-primary"
                            disabled={draftPoly.length < 3 || draftArrow.length !== 2}
                            onClick={commitZone}
                            style={{ width: "100%", padding: "8px" }}
                          >
                            + Thêm làn đường vào active.yaml
                          </button>

                          {customZones.filter((z) => z.rule_type === "wrong_way").length > 0 && (
                            <div style={{ marginTop: 6 }}>
                              <div style={{ fontSize: "11.5px", fontWeight: 600, color: "var(--muted)", marginBottom: 4 }}>
                                Làn đường đã tạo:
                              </div>
                              <ul className="calib-lane-list" style={{ maxHeight: "120px", overflowY: "auto" }}>
                                {customZones
                                  .filter((z) => z.rule_type === "wrong_way")
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
                            style={{ width: "100%", padding: "8px" }}
                          >
                            + Xác nhận vùng {m.label.split(".")[1]?.trim() || ""} ({draftPoly.length} điểm)
                          </button>

                          {customZones.filter((z) => z.rule_type === m.key).length > 0 && (
                            <div style={{ marginTop: 6 }}>
                              <div style={{ fontSize: "11.5px", fontWeight: 600, color: "var(--muted)", marginBottom: 4 }}>
                                Vùng đã tạo:
                              </div>
                              <ul className="calib-lane-list" style={{ maxHeight: "120px", overflowY: "auto" }}>
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
                  )}
                </div>
              );
            })}
          </div>

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
                rectPts.length === 4,
                stopPts.length === 2,
                lightPts.length === 2,
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

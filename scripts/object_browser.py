"""UI duyet object & vi pham giao thong: Modern Cyber Dashboard UI (FastAPI + Tailwind CSS).

Chay: uvicorn scripts.object_browser:app --host 0.0.0.0 --port 8081 --reload
Mo: http://<ip-may>:8081
Doc SQLite read-only (pipeline ghi song song an toan nho WAL) va evidence folder.
Nang cap cao cap:
1. Cyber Grid + Aura Glow atmospheric background
2. Data Visualization KPI Bar (Color Spectrum bar & Violation Breakdown)
3. Micro-interactions & Neon border cards
4. Evidence Theater Modal voi Keyboard Shortcut HUD & Zoom
5. Live Auto-Refresh & Batch Bulk Deletion
"""
import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

DB_PATH = str(REPO_ROOT / "objects.db")
CROP_ROOT = REPO_ROOT / "objects"
EV_ROOT = REPO_ROOT / "evidence"

app = FastAPI(title="Edge Traffic AI - Cyber Operations Dashboard")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _ev_dates():
    out = {}
    if not EV_ROOT.is_dir():
        return out
    for cam_dir in sorted(EV_ROOT.iterdir()):
        if not cam_dir.is_dir():
            continue
        for date_dir in sorted(cam_dir.glob("date=*")):
            d = date_dir.name[5:]
            out[d] = out.get(d, 0) + len(list(date_dir.glob("*/*.json")))
    return out


@app.get("/api/vdates")
def api_vdates():
    return [{"date": d, "count": n}
            for d, n in sorted(_ev_dates().items(), reverse=True)]


@app.get("/api/violations")
def api_violations(date: str = Query(""), camera: str = Query("")):
    out = {}
    if not EV_ROOT.is_dir():
        return []
    cams = [EV_ROOT / camera] if camera else sorted(
        p for p in EV_ROOT.iterdir() if p.is_dir())
    for cam_dir in cams:
        if not cam_dir.is_dir():
            continue
        dates = [cam_dir / f"date={date}"] if date else sorted(cam_dir.glob("date=*"))
        for date_dir in dates:
            if not date_dir.is_dir():
                continue
            for vio_dir in sorted(p for p in date_dir.iterdir() if p.is_dir()):
                mains = {p.stem for p in vio_dir.glob("*.json")}
                n = len(mains)
                if n:
                    out[vio_dir.name] = out.get(vio_dir.name, 0) + n
    return [{"violation": k, "count": v} for k, v in sorted(out.items())]


def _img_rel(p):
    try:
        return f"/img/{p.relative_to(REPO_ROOT)}"
    except ValueError:
        return ""


@app.get("/api/events")
def api_events(date: str = Query(""), violation: str = Query(""),
               camera: str = Query(""), limit: int = Query(60, le=500),
               offset: int = Query(0, ge=0)):
    items = []
    if EV_ROOT.is_dir():
        cams = [EV_ROOT / camera] if camera else sorted(
            p for p in EV_ROOT.iterdir() if p.is_dir())
        for cam_dir in cams:
            if not cam_dir.is_dir():
                continue
            dates = [cam_dir / f"date={date}"] if date else sorted(cam_dir.glob("date=*"))
            for date_dir in dates:
                if not date_dir.is_dir():
                    continue
                vios = [date_dir / violation] if violation else sorted(
                    p for p in date_dir.iterdir() if p.is_dir())
                for vio_dir in vios:
                    if not vio_dir.is_dir():
                        continue
                    for jp in sorted(vio_dir.glob("*.json")):
                        try:
                            meta = json.loads(jp.read_text(encoding="utf-8"))
                        except Exception:
                            continue
                        stem = jp.stem
                        full = vio_dir / f"{stem}.jpg"
                        crop = vio_dir / f"{stem}_crop.jpg"
                        diptych_crop = vio_dir / f"{stem}_diptych_crop.jpg"
                        diptych_full = vio_dir / f"{stem}_diptych.jpg"

                        gallery = []
                        for extra in sorted(vio_dir.glob(f"{stem}_diptych*.jpg")) + \
                                sorted(vio_dir.glob(f"{stem}_triptych*.jpg")):
                            gallery.append(_img_rel(extra))

                        chosen_thumb = ""
                        if diptych_crop.is_file():
                            chosen_thumb = _img_rel(diptych_crop)
                        elif crop.is_file():
                            chosen_thumb = _img_rel(crop)
                        elif full.is_file():
                            chosen_thumb = _img_rel(full)

                        chosen_full = ""
                        if diptych_full.is_file():
                            chosen_full = _img_rel(diptych_full)
                        elif full.is_file():
                            chosen_full = _img_rel(full)

                        items.append({
                            "event_id": meta.get("event_id", stem),
                            "camera_id": meta.get("camera_id", cam_dir.name),
                            "violation": meta.get("violation", vio_dir.name),
                            "date": date_dir.name[5:],
                            "timestamp": meta.get("timestamp", ""),
                            "class": meta.get("class", ""),
                            "confidence": meta.get("confidence", 0),
                            "extra": meta.get("extra", {}),
                            "thumb": chosen_thumb,
                            "crop": _img_rel(crop) if crop.is_file() else (_img_rel(diptych_crop) if diptych_crop.is_file() else chosen_thumb),
                            "full": chosen_full,
                            "gallery": gallery,
                            "raw_meta": meta,
                        })
    items.sort(key=lambda r: r["timestamp"], reverse=True)
    return {"total": len(items), "items": items[offset:offset + limit]}


def _delete_event_impl(camera: str, date: str, violation: str, event_id: str):
    deleted = []
    candidates = []
    if camera and date and violation:
        vio_dir = EV_ROOT / camera / f"date={date}" / violation
        if vio_dir.is_dir():
            candidates = list(vio_dir.glob(f"*{event_id}*"))

    if not candidates and EV_ROOT.is_dir():
        candidates = list(EV_ROOT.glob(f"**/*{event_id}*"))

    for p in candidates:
        try:
            if p.is_file():
                p.unlink()
                deleted.append(p.name)
        except Exception:
            pass

    if not deleted:
        raise HTTPException(404, f"Không tìm thấy file bằng chứng cho event #{event_id}")

    return {"status": "ok", "deleted": deleted}


@app.delete("/api/events")
def api_delete_event(camera: str = Query(""), date: str = Query(""),
                     violation: str = Query(""), event_id: str = Query(...)):
    return _delete_event_impl(camera, date, violation, event_id)


@app.post("/api/events/delete")
def api_delete_event_post(camera: str = Query(""), date: str = Query(""),
                          violation: str = Query(""), event_id: str = Query(...)):
    return _delete_event_impl(camera, date, violation, event_id)


@app.post("/api/events/bulk-delete")
async def api_events_bulk_delete(req: Request):
    data = await req.json()
    items = data.get("items", [])
    count = 0
    for it in items:
        try:
            _delete_event_impl(
                it.get("camera", ""),
                it.get("date", ""),
                it.get("violation", ""),
                it.get("event_id", "")
            )
            count += 1
        except Exception:
            pass
    return {"status": "ok", "deleted_count": count}


def _db():
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5.0)
    con.row_factory = sqlite3.Row
    return con


@app.get("/api/dates")
def api_dates():
    con = _db()
    rows = con.execute(
        "SELECT date, COUNT(*) n FROM objects WHERE low_quality=0 "
        "GROUP BY date ORDER BY date DESC").fetchall()
    con.close()
    return [{"date": r["date"], "count": r["n"]} for r in rows]


@app.get("/api/stats")
def api_stats(date: str = Query("")):
    con = _db()
    d_cond, params = ("", [])
    if date:
        d_cond = "AND date=?"
        params = [date]
    obj_rows = con.execute(
        f"SELECT vehicle_type, COUNT(*) as cnt FROM objects WHERE low_quality=0 {d_cond} GROUP BY vehicle_type",
        params
    ).fetchall()
    total_objects = sum(r["cnt"] for r in obj_rows)
    types_breakdown = {r["vehicle_type"]: r["cnt"] for r in obj_rows}

    color_rows = con.execute(
        f"SELECT color, COUNT(*) as cnt FROM objects WHERE low_quality=0 {d_cond} GROUP BY color ORDER BY cnt DESC",
        params
    ).fetchall()
    colors_breakdown = {r["color"]: r["cnt"] for r in color_rows}
    con.close()

    vio_counts = {}
    if EV_ROOT.is_dir():
        cams = sorted(p for p in EV_ROOT.iterdir() if p.is_dir())
        for cam_dir in cams:
            dates = [cam_dir / f"date={date}"] if date else sorted(cam_dir.glob("date=*"))
            for date_dir in dates:
                if not date_dir.is_dir():
                    continue
                for vio_dir in sorted(p for p in date_dir.iterdir() if p.is_dir()):
                    n = len(list(vio_dir.glob("*.json")))
                    if n:
                        vio_counts[vio_dir.name] = vio_counts.get(vio_dir.name, 0) + n
    total_violations = sum(vio_counts.values())

    return {
        "date": date,
        "total_objects": total_objects,
        "types_breakdown": types_breakdown,
        "colors_breakdown": colors_breakdown,
        "total_violations": total_violations,
        "violations_breakdown": vio_counts,
    }


@app.get("/api/types")
def api_types(date: str = Query("")):
    con = _db()
    cond, params = "", []
    if date:
        cond, params = "AND date=?", [date]
    rows = con.execute(
        "SELECT vehicle_type, COUNT(*) n FROM objects "
        f"WHERE low_quality=0 {cond} GROUP BY vehicle_type ORDER BY n DESC",
        params).fetchall()
    con.close()
    return [{"type": r["vehicle_type"], "count": r["n"]} for r in rows]


@app.get("/api/colors")
def api_colors(date: str = Query(""), type: str = Query("", alias="type")):
    con = _db()
    cond, params = [], []
    if date:
        cond.append("date=?")
        params.append(date)
    if type:
        cond.append("vehicle_type=?")
        params.append(type)
    where = ("WHERE low_quality=0 AND " + " AND ".join(cond)) if cond else "WHERE low_quality=0"
    rows = con.execute(
        f"SELECT color, COUNT(*) n FROM objects {where} "
        "GROUP BY color ORDER BY n DESC", params).fetchall()
    con.close()
    return [{"color": r["color"], "count": r["n"]} for r in rows]


@app.get("/api/objects")
def api_objects(date: str = Query(""), type: str = Query("", alias="type"),
                color: str = Query(""), camera: str = Query(""),
                limit: int = Query(200, le=1000)):
    con = _db()
    cond, params = [], []
    if date:
        cond.append("date=?")
        params.append(date)
    if type:
        cond.append("vehicle_type=?")
        params.append(type)
    if color:
        cond.append("color=?")
        params.append(color)
    if camera:
        cond.append("camera_id=?")
        params.append(camera)
    where = ("WHERE low_quality=0 AND " + " AND ".join(cond)) if cond else "WHERE low_quality=0"
    rows = con.execute(
        "SELECT track_id, camera_id, date, vehicle_type, color, color_conf,"
        " best_conf, best_bbox, crop_path, first_seen, last_seen, frames "
        f"FROM objects {where} ORDER BY first_seen DESC LIMIT ?", (*params, limit)).fetchall()
    con.close()
    out = []
    for r in rows:
        d = dict(r)
        cp = d.get("crop_path") or ""
        try:
            rel = str(Path(cp).relative_to(REPO_ROOT))
        except ValueError:
            rel = cp
        d["img"] = f"/img/{rel}" if rel else ""
        out.append(d)
    return out


def _delete_object_impl(track_id: int, date: str, camera: str):
    con = sqlite3.connect(DB_PATH, timeout=5.0)
    cond = ["track_id = ?"]
    params = [track_id]
    if date:
        cond.append("date = ?")
        params.append(date)
    if camera:
        cond.append("camera_id = ?")
        params.append(camera)
    where = " AND ".join(cond)

    row = con.execute(f"SELECT crop_path FROM objects WHERE {where}", params).fetchone()
    if row and row[0]:
        cp = REPO_ROOT / row[0]
        try:
            if cp.is_file():
                cp.unlink()
        except Exception:
            pass

    cur = con.execute(f"DELETE FROM objects WHERE {where}", params)
    con.commit()
    con.close()
    return {"status": "ok", "rows_deleted": cur.rowcount}


@app.delete("/api/objects")
def api_delete_object(track_id: int = Query(...), date: str = Query(""),
                      camera: str = Query("")):
    return _delete_object_impl(track_id, date, camera)


@app.post("/api/objects/delete")
def api_delete_object_post(track_id: int = Query(...), date: str = Query(""),
                           camera: str = Query("")):
    return _delete_object_impl(track_id, date, camera)


@app.post("/api/objects/bulk-delete")
async def api_objects_bulk_delete(req: Request):
    data = await req.json()
    items = data.get("items", [])
    count = 0
    for it in items:
        try:
            _delete_object_impl(
                int(it.get("track_id")),
                it.get("date", ""),
                it.get("camera", "")
            )
            count += 1
        except Exception:
            pass
    return {"status": "ok", "deleted_count": count}


@app.get("/img/{path:path}")
def serve_img(path: str):
    full = (REPO_ROOT / path).resolve()
    if REPO_ROOT not in full.parents and full != REPO_ROOT:
        raise HTTPException(404)
    if not full.is_file() or full.suffix.lower() not in (".jpg", ".jpeg", ".png"):
        raise HTTPException(404)
    return FileResponse(str(full))


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE


PAGE = """<!DOCTYPE html>
<html lang="vi" class="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Traffic Edge AI - Cyber Operations Dashboard</title>
<!-- Tailwind CSS v3 & FontAwesome Icons -->
<script src="https://cdn.tailwindcss.com"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
<script>
tailwind.config = {
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace']
      },
      colors: {
        dark: { 950: '#06080e', 900: '#090d16', 850: '#0e1422', 800: '#121a2d', 700: '#1e293b', 600: '#334155' },
        brand: { 400: '#60a5fa', 500: '#3b82f6', 600: '#2563eb', 700: '#1d4ed8' }
      }
    }
  }
}
</script>
<style>
/* Atmospheric Dot Matrix & Scrollbars */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #06080e; }
::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #334155; }

.cyber-grid {
  background-image: radial-gradient(rgba(255, 255, 255, 0.07) 1px, transparent 1px);
  background-size: 28px 28px;
}

.glass-panel {
  background: rgba(14, 20, 34, 0.72);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.4);
}

/* Neon Glow Card Hover */
.card-hover {
  transition: all 0.28s cubic-bezier(0.16, 1, 0.3, 1);
}
.card-obj-hover:hover {
  transform: translateY(-4px);
  border-color: rgba(59, 130, 246, 0.55);
  box-shadow: 0 16px 32px -8px rgba(0, 0, 0, 0.8), 0 0 20px rgba(59, 130, 246, 0.25);
}
.card-vio-hover:hover {
  transform: translateY(-4px);
  border-color: rgba(244, 63, 94, 0.6);
  box-shadow: 0 16px 32px -8px rgba(0, 0, 0, 0.8), 0 0 22px rgba(244, 63, 94, 0.3);
}

/* Shimmer Skeleton Placeholder */
@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
.skeleton-bg {
  background: linear-gradient(90deg, #121a2d 25%, #1e293b 50%, #121a2d 75%);
  background-size: 200% 100%;
  animation: shimmer 2s infinite linear;
}

/* Interactive Image Zoom */
.img-zoomable { transition: transform 0.25s ease-out; cursor: zoom-in; }
.img-zoomed { transform: scale(2.2); cursor: grab; }

kbd {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 4px;
  padding: 1px 5px;
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
}
</style>
</head>
<body class="bg-dark-950 text-slate-100 min-h-screen flex flex-col font-sans selection:bg-brand-500 selection:text-white relative overflow-x-hidden pb-24">

<!-- Atmospheric Aurora Glow & Cyber Grid Background -->
<div class="fixed inset-0 pointer-events-none z-0 overflow-hidden">
  <div class="absolute -top-40 left-1/4 w-[650px] h-[450px] bg-brand-600/12 rounded-full blur-[150px]"></div>
  <div class="absolute top-1/4 right-1/4 w-[500px] h-[350px] bg-rose-600/10 rounded-full blur-[150px]"></div>
  <div class="absolute bottom-10 left-1/3 w-[650px] h-[400px] bg-indigo-600/10 rounded-full blur-[160px]"></div>
  <div class="cyber-grid absolute inset-0 opacity-40"></div>
</div>

<!-- Top Navigation Header -->
<header class="sticky top-0 z-40 glass-panel border-b border-slate-800/80 px-4 lg:px-8 py-3">
  <div class="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
    <!-- Brand Title -->
    <div class="flex items-center gap-3.5">
      <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-brand-600 via-indigo-500 to-rose-500 flex items-center justify-center shadow-lg shadow-brand-500/25 ring-1 ring-white/20">
        <i class="fa-solid fa-satellite-dish text-white text-base"></i>
      </div>
      <div>
        <div class="flex items-center gap-2">
          <h1 class="text-base sm:text-lg font-extrabold tracking-tight text-white">DIGITAL CITY</h1>
          <span class="px-2 py-0.5 text-[10px] font-mono font-bold uppercase rounded bg-brand-500/20 text-brand-400 border border-brand-500/30">Cyber Edge AI</span>
        </div>
        <p class="text-xs text-slate-400 font-medium hidden sm:block">Trung Tâm Điều Hành & Xử Lý Vi Phạm Giao Thông Thời Gian Thực</p>
      </div>
    </div>

    <!-- Right Controls: Live Auto-Refresh & Camera Status -->
    <div class="flex items-center gap-2.5">
      <!-- Live Auto-Refresh Toggle -->
      <button id="btnLiveRefresh" onclick="toggleLiveRefresh()"
              class="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-900/80 border border-slate-700/80 text-xs font-semibold text-slate-300 hover:text-white transition">
        <span class="relative flex h-2 w-2">
          <span id="livePing" class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-0"></span>
          <span id="liveDot" class="relative inline-flex rounded-full h-2 w-2 bg-slate-500"></span>
        </span>
        <span id="liveText" class="hidden sm:inline">Auto-Refresh: Tắt</span>
      </button>

      <!-- Camera Node Badge -->
      <div class="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-900/80 border border-slate-700/80 text-xs font-semibold text-slate-300">
        <i class="fa-solid fa-video text-brand-400"></i>
        <span>CAM_TEST_01</span>
      </div>

      <!-- Refresh Button -->
      <button onclick="refreshData()" title="Làm mới dữ liệu" class="p-2 rounded-xl bg-slate-900/80 hover:bg-slate-800 text-slate-300 hover:text-white transition border border-slate-700 text-xs">
        <i class="fa-solid fa-arrows-rotate"></i>
      </button>
    </div>
  </div>
</header>

<!-- Main Container -->
<main class="max-w-7xl mx-auto w-full px-4 lg:px-8 py-5 flex-1 flex flex-col gap-5 relative z-10">

  <!-- KPI Analytics Bar (Focused 2-Card Layout) -->
  <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
    
    <!-- KPI 1: Vehicles & Color Spectrum -->
    <div class="glass-panel p-5 rounded-2xl flex flex-col justify-between relative overflow-hidden group">
      <div class="flex items-center justify-between">
        <span class="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
          <i class="fa-solid fa-car-side text-brand-400"></i>
          Lưu Lượng Phương Tiện
        </span>
        <span id="kpiObjSpeed" class="text-[10px] font-mono text-emerald-400 bg-emerald-950/50 px-2.5 py-0.5 rounded-md border border-emerald-500/30">Active</span>
      </div>
      <div class="my-3">
        <div class="flex items-baseline gap-2">
          <div id="kpiObjects" class="text-3xl sm:text-4xl font-extrabold text-white font-mono tracking-tight">0</div>
          <span class="text-xs text-slate-400 font-medium">xe</span>
        </div>
        <p id="kpiObjectsSub" class="text-xs text-slate-400 mt-1 truncate">Đang phân tích chủng loại...</p>
      </div>
      <!-- Color Spectrum Visual Bar -->
      <div class="mt-1">
        <div class="flex items-center justify-between text-[11px] text-slate-400 mb-1.5">
          <span>Phổ màu phương tiện nhận diện:</span>
          <span id="colorCountLabel" class="font-mono text-slate-300">--</span>
        </div>
        <div id="colorSpectrum" class="h-2.5 w-full rounded-full flex overflow-hidden gap-0.5 bg-slate-800/80"></div>
      </div>
    </div>

    <!-- KPI 2: Violations & Breakdown -->
    <div class="glass-panel p-5 rounded-2xl flex flex-col justify-between relative overflow-hidden group border-rose-950/50">
      <div class="flex items-center justify-between">
        <span class="text-xs font-bold uppercase tracking-wider text-rose-400 flex items-center gap-2">
          <i class="fa-solid fa-triangle-exclamation"></i>
          Sự Kiện Vi Phạm Ghi Nhận
        </span>
        <span class="relative flex h-2 w-2">
          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
          <span class="relative inline-flex rounded-full h-2 w-2 bg-rose-500"></span>
        </span>
      </div>
      <div class="my-3">
        <div class="flex items-baseline gap-2">
          <div id="kpiViolations" class="text-3xl sm:text-4xl font-extrabold text-rose-400 font-mono tracking-tight">0</div>
          <span class="text-xs text-rose-300 font-medium">sự kiện</span>
        </div>
        <p id="kpiViolationsSub" class="text-xs text-slate-400 mt-1 truncate">Đang phân tích lỗi...</p>
      </div>
      <!-- Mini Progress Indicator -->
      <div class="mt-1">
        <div class="flex items-center justify-between text-[11px] text-slate-400 mb-1.5">
          <span>Trạng thái trích xuất bằng chứng:</span>
          <span class="text-rose-400 font-semibold flex items-center gap-1">
            <i class="fa-solid fa-camera text-[10px]"></i>
            Tự động cắt ảnh & lưu trữ
          </span>
        </div>
        <div class="h-2.5 w-full rounded-full bg-slate-800 overflow-hidden">
          <div class="h-full bg-gradient-to-r from-rose-600 via-amber-500 to-brand-500 rounded-full w-full"></div>
        </div>
      </div>
    </div>

  </div>

  <!-- Controls & Tabs Bar -->
  <div class="glass-panel p-3 rounded-2xl flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
    <!-- View Switcher Tabs -->
    <div class="flex items-center gap-1.5 p-1 rounded-xl bg-dark-950/80 border border-slate-800">
      <button id="tabO" onclick="showTab('o')" class="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all text-white bg-brand-600 shadow-md shadow-brand-500/20">
        <i class="fa-solid fa-car-side"></i>
        <span>Duyệt Phương Tiện</span>
        <span id="badgeO" class="px-1.5 py-0.2 rounded-full text-[11px] bg-white/20 text-white font-bold ml-1 font-mono">0</span>
      </button>
      <button id="tabV" onclick="showTab('v')" class="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all text-slate-400 hover:text-slate-200">
        <i class="fa-solid fa-triangle-exclamation text-rose-400"></i>
        <span>Sự Kiện Vi Phạm</span>
        <span id="badgeV" class="px-1.5 py-0.2 rounded-full text-[11px] bg-rose-500/20 text-rose-300 font-bold ml-1 font-mono">0</span>
      </button>
    </div>

    <!-- Batch Selection Mode Button -->
    <div class="flex items-center gap-2.5">
      <button id="btnToggleSelectMode" onclick="toggleSelectionMode()"
              class="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 text-xs font-semibold flex items-center gap-2 transition">
        <i class="fa-solid fa-square-check text-slate-400"></i>
        <span id="txtSelectMode">Chế độ chọn nhiều</span>
      </button>
    </div>
  </div>

  <!-- Filter Controls: Tab Objects -->
  <div id="paneO" class="glass-panel p-4 rounded-2xl flex flex-col gap-3 border border-slate-800/80">
    <div class="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-800">
      <div class="flex items-center gap-3 flex-wrap">
        <div class="flex items-center gap-2 text-sm font-medium text-slate-300">
          <i class="fa-regular fa-calendar-days text-brand-400"></i>
          <span>Ngày:</span>
          <select id="date" class="bg-slate-900 border border-slate-700 text-slate-200 text-sm rounded-xl px-3 py-1.5 focus:ring-2 focus:ring-brand-500 focus:outline-none transition font-mono">
            <option value="">Đang nạp...</option>
          </select>
        </div>
        <span id="count" class="px-3 py-1 rounded-full text-xs font-semibold bg-brand-500/10 text-brand-400 border border-brand-500/20 font-mono">0 xe</span>
      </div>
      <!-- Search Input -->
      <div class="relative w-full sm:w-72">
        <i class="fa-solid fa-magnifying-glass absolute left-3.5 top-1/2 -translate-y-1/2 text-xs text-slate-400"></i>
        <input type="text" id="objSearch" placeholder="Tìm ID #123, loại xe, màu sắc..." oninput="filterObjectsLocal()"
               class="w-full bg-slate-900/90 border border-slate-700 rounded-xl pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-brand-500">
      </div>
    </div>

    <!-- Vehicle Types Filter -->
    <div class="flex items-center gap-2 flex-wrap" id="types">
      <span class="text-xs font-semibold text-slate-400 uppercase tracking-wider mr-1">Chủng loại:</span>
    </div>

    <!-- Vehicle Color Swatches Filter -->
    <div class="flex items-center gap-2 flex-wrap" id="colors">
      <span class="text-xs font-semibold text-slate-400 uppercase tracking-wider mr-1">Màu sắc:</span>
    </div>
  </div>

  <!-- Filter Controls: Tab Violations -->
  <div id="paneV" style="display:none" class="glass-panel p-4 rounded-2xl flex flex-col gap-3 border border-slate-800/80">
    <div class="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-800">
      <div class="flex items-center gap-3 flex-wrap">
        <div class="flex items-center gap-2 text-sm font-medium text-slate-300">
          <i class="fa-regular fa-calendar-days text-rose-400"></i>
          <span>Ngày:</span>
          <select id="vdate" class="bg-slate-900 border border-slate-700 text-slate-200 text-sm rounded-xl px-3 py-1.5 focus:ring-2 focus:ring-rose-500 focus:outline-none transition font-mono">
            <option value="">Đang nạp...</option>
          </select>
        </div>
        <span id="vcount" class="px-3 py-1 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20 font-mono">0 vi phạm</span>
      </div>
      <div class="relative w-full sm:w-72">
        <i class="fa-solid fa-magnifying-glass absolute left-3.5 top-1/2 -translate-y-1/2 text-xs text-slate-400"></i>
        <input type="text" id="vioSearch" placeholder="Lọc mã vi phạm, loại xe..." oninput="filterViolationsLocal()"
               class="w-full bg-slate-900/90 border border-slate-700 rounded-xl pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-rose-500">
      </div>
    </div>

    <!-- Violation Types Pills -->
    <div class="flex items-center gap-2 flex-wrap" id="vios">
      <span class="text-xs font-semibold text-slate-400 uppercase tracking-wider mr-1">Lỗi vi phạm:</span>
    </div>
  </div>

  <!-- Grid Showcase for Cards -->
  <div id="grid" class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4"></div>

  <!-- Empty State -->
  <div id="emptyState" style="display:none" class="glass-panel rounded-2xl p-12 flex flex-col items-center justify-center text-center gap-3 my-8">
    <div class="w-16 h-16 rounded-2xl bg-slate-900/80 flex items-center justify-center text-slate-500 text-2xl border border-slate-800">
      <i class="fa-solid fa-inbox"></i>
    </div>
    <h3 class="text-base font-semibold text-slate-200">Không có dữ liệu phù hợp</h3>
    <p class="text-xs text-slate-400 max-w-sm">Không tìm thấy bản ghi nào với bộ lọc hiện tại. Thử chọn ngày hoặc phân loại khác.</p>
  </div>

  <!-- Load More Button -->
  <div id="vmoreWrap" style="display:none" class="flex justify-center mt-2 mb-6">
    <button id="vmore" onclick="vMore()" class="px-6 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-sm font-semibold text-slate-200 border border-slate-700 shadow-lg transition flex items-center gap-2">
      <i class="fa-solid fa-chevron-down text-xs"></i>
      <span>Xem Thêm Bản Ghi</span>
    </button>
  </div>

</main>

<!-- Floating Bulk Action Toolbar -->
<div id="bulkBar" style="display:none" class="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 glass-panel border border-brand-500/50 px-5 py-3 rounded-2xl shadow-2xl flex items-center gap-4 animate-in slide-in-from-bottom duration-300">
  <div class="flex items-center gap-2 text-xs font-bold text-slate-200">
    <span class="w-2.5 h-2.5 rounded-full bg-brand-500 animate-pulse"></span>
    <span>Đã chọn: <span id="selectedCount" class="text-brand-400 font-mono text-sm">0</span> mục</span>
  </div>
  <div class="h-4 w-px bg-slate-700"></div>
  <button onclick="toggleSelectAll()" class="text-xs font-semibold text-slate-300 hover:text-white transition px-2.5 py-1.5 rounded-lg hover:bg-slate-800">
    <span id="txtSelectAll">Chọn tất cả</span>
  </button>
  <button onclick="bulkDeleteSelected()" class="px-4 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold flex items-center gap-1.5 transition shadow-md shadow-rose-600/30">
    <i class="fa-solid fa-trash-can text-[11px]"></i>
    <span>Xóa các mục đã chọn</span>
  </button>
  <button onclick="clearSelection()" title="Bỏ chọn" class="text-slate-400 hover:text-white text-xs ml-1">
    <i class="fa-solid fa-xmark"></i>
  </button>
</div>

<!-- Evidence Theater Modal with Shortcut HUD & Zoom -->
<div id="modal" style="display:none" class="fixed inset-0 z-50 bg-black/90 backdrop-blur-md flex items-center justify-center p-3 sm:p-4">
  <div class="bg-dark-900 border border-slate-700/80 rounded-2xl max-w-4xl w-full overflow-hidden shadow-2xl flex flex-col max-h-[94vh] animate-in fade-in duration-200 relative" onclick="event.stopPropagation()">
    
    <!-- Modal Header -->
    <div class="flex items-center justify-between px-6 py-3.5 border-b border-slate-800 bg-dark-950/80">
      <div class="flex items-center gap-2.5">
        <span id="mBadge" class="px-2.5 py-1 rounded-md text-xs font-bold uppercase bg-brand-500/20 text-brand-400 border border-brand-500/30">Chi Tiết</span>
        <h2 id="mTitle" class="text-sm sm:text-base font-bold text-white truncate max-w-sm sm:max-w-md">Bằng Chứng Giám Sát</h2>
      </div>

      <!-- Navigation & Close Buttons -->
      <div class="flex items-center gap-2">
        <div class="flex items-center bg-slate-900 border border-slate-700 rounded-xl p-0.5 text-xs">
          <button onclick="navModal(-1)" title="Bản ghi trước (Phím ←)" class="px-2.5 py-1 hover:bg-slate-800 rounded-lg text-slate-300 hover:text-white transition">
            <i class="fa-solid fa-chevron-left"></i>
          </button>
          <span id="mIndex" class="px-2 font-mono text-[11px] text-slate-400 font-semibold">1 / 1</span>
          <button onclick="navModal(1)" title="Bản ghi sau (Phím →)" class="px-2.5 py-1 hover:bg-slate-800 rounded-lg text-slate-300 hover:text-white transition">
            <i class="fa-solid fa-chevron-right"></i>
          </button>
        </div>
        <button onclick="closeModal()" class="w-8 h-8 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-white flex items-center justify-center transition ml-1">
          <i class="fa-solid fa-xmark"></i>
        </button>
      </div>
    </div>

    <!-- Modal Body -->
    <div class="p-5 sm:p-6 overflow-y-auto flex flex-col lg:flex-row gap-5">
      <!-- Media Viewer Column -->
      <div class="flex-1 flex flex-col gap-3">
        <!-- Switch between Crop / Full / Gallery & Zoom Toggle -->
        <div class="flex items-center justify-between flex-wrap gap-2">
          <div id="mediaTabs" class="flex items-center gap-1.5 p-1 rounded-xl bg-dark-950 border border-slate-800 w-fit">
            <button id="btnCrop" onclick="switchMedia('crop')" class="px-3 py-1 rounded-lg text-xs font-semibold bg-brand-600 text-white">Cận Cảnh</button>
            <button id="btnFull" onclick="switchMedia('full')" class="px-3 py-1 rounded-lg text-xs font-semibold text-slate-400 hover:text-slate-200">Toàn Cảnh</button>
            <button id="btnDiptych" onclick="switchMedia('diptych')" style="display:none" class="px-3 py-1 rounded-lg text-xs font-semibold text-slate-400 hover:text-slate-200">Chuỗi Bằng Chứng</button>
          </div>

          <!-- Zoom button -->
          <button onclick="toggleImageZoom()" id="btnZoom" class="px-3 py-1 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-300 text-xs font-semibold border border-slate-700 flex items-center gap-1.5 transition">
            <i class="fa-solid fa-magnifying-glass-plus"></i>
            <span id="txtZoom">Phóng to (Z)</span>
          </button>
        </div>

        <div class="relative rounded-xl overflow-hidden bg-black/80 border border-slate-800 flex items-center justify-center min-h-[300px] max-h-[55vh]">
          <img id="mimg" src="" alt="Evidence" onclick="toggleImageZoom()" class="img-zoomable max-h-[52vh] w-auto object-contain rounded-lg">
        </div>
      </div>

      <!-- Info Column -->
      <div class="w-full lg:w-80 flex flex-col gap-4">
        <div class="bg-dark-950/80 border border-slate-800 rounded-xl p-4 flex flex-col gap-3 text-xs">
          <h4 class="font-bold text-slate-200 uppercase tracking-wider text-[11px] pb-2 border-b border-slate-800 flex items-center gap-2">
            <i class="fa-solid fa-circle-info text-brand-400"></i>
            Thông Số Bản Ghi
          </h4>
          <div class="grid grid-cols-2 gap-y-2.5 text-slate-300">
            <div class="text-slate-500">Mã Track / ID:</div>
            <div id="mTrackId" class="font-mono font-bold text-slate-100 text-right">#--</div>

            <div class="text-slate-500">Camera:</div>
            <div id="mCam" class="font-semibold text-right">--</div>

            <div class="text-slate-500">Thời gian:</div>
            <div id="mTime" class="font-mono text-right text-slate-300 text-[11px]">--</div>

            <div class="text-slate-500">Loại xe:</div>
            <div id="mClass" class="font-semibold text-right text-brand-400">--</div>

            <div class="text-slate-500">Độ tin cậy:</div>
            <div id="mConf" class="font-mono text-right">--</div>

            <div class="text-slate-500">Vùng áp dụng:</div>
            <div id="mZone" class="font-semibold text-right text-amber-400">--</div>
          </div>
        </div>

        <!-- Extra Violation Details -->
        <div id="extraBox" class="bg-dark-950/80 border border-slate-800 rounded-xl p-4 flex flex-col gap-2 text-xs">
          <h4 class="font-bold text-slate-200 uppercase tracking-wider text-[11px] pb-2 border-b border-slate-800 flex items-center gap-2">
            <i class="fa-solid fa-list-check text-rose-400"></i>
            Dữ Liệu Đo Đạc
          </h4>
          <pre id="minfo" class="text-[11px] font-mono text-slate-300 whitespace-pre-wrap break-all max-h-36 overflow-y-auto"></pre>
        </div>

        <!-- Action Buttons -->
        <div class="flex items-center gap-2 mt-auto">
          <a id="mDownload" href="#" download class="flex-1 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-semibold text-xs text-center transition flex items-center justify-center gap-1.5 shadow-md">
            <i class="fa-solid fa-download"></i>
            <span>Tải Ảnh (D)</span>
          </a>
          <button onclick="deleteActiveModalItem()" title="Xóa bản ghi này (Delete)" class="px-3.5 py-2 rounded-xl bg-rose-600/20 hover:bg-rose-600 text-rose-400 hover:text-white border border-rose-500/30 text-xs font-semibold flex items-center gap-1.5 transition">
            <i class="fa-solid fa-trash-can"></i>
            <span>Xóa</span>
          </button>
          <button onclick="copyRawMeta()" title="Sao chép JSON" class="px-3.5 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white text-xs font-semibold border border-slate-700 transition">
            <i class="fa-regular fa-copy"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- Keyboard Shortcut HUD Footer -->
    <div class="px-6 py-2.5 border-t border-slate-800 bg-dark-950 flex flex-wrap items-center justify-center gap-4 text-[11px] text-slate-400">
      <span><kbd>←</kbd> <kbd>→</kbd> Duyệt bản ghi</span>
      <span><kbd>Z</kbd> Phóng to</span>
      <span><kbd>D</kbd> Tải ảnh</span>
      <span><kbd>Del</kbd> Xóa</span>
      <span><kbd>Esc</kbd> Đóng</span>
    </div>
  </div>
</div>

<!-- Toast Notification -->
<div id="toast" style="display:none" class="fixed bottom-6 right-6 z-50 px-4 py-3 rounded-xl bg-dark-900 border border-slate-700 text-slate-200 text-xs font-semibold shadow-2xl flex items-center gap-2.5 animate-in slide-in-from-bottom duration-200">
  <i id="toastIcon" class="fa-solid fa-circle-check text-emerald-400"></i>
  <span id="toastMsg">Thành công</span>
</div>

<script>
// State Management
const S = { date: '', type: '', color: '', rawObjects: [], visibleObjects: [] };
const V = { date: '', vio: '', offset: 0, total: 0, init: false, rawEvents: [], visibleEvents: [] };
let activeModalData = null;
let currentTab = 'o';
let isSelectionMode = false;
const selectedItems = new Map();
let isZoomed = false;
let liveRefreshTimer = null;

const VIOLATION_TRANSLATE = {
  'no_entry_road': { name: 'Đường Cấm', icon: 'fa-ban', color: 'rose' },
  'no_parking': { name: 'Đỗ Xe Trái Phép', icon: 'fa-square-parking', color: 'purple' },
  'speeding': { name: 'Quá Tốc Độ', icon: 'fa-gauge-high', color: 'amber' },
  'wrong_way': { name: 'Đi Ngược Chiều', icon: 'fa-arrows-split-up-and-left', color: 'red' },
  'red_light_running': { name: 'Vượt Đèn Đỏ', icon: 'fa-traffic-light', color: 'red' },
  'stop_line_violation': { name: 'Đè Vạch Dừng', icon: 'fa-minus', color: 'orange' }
};

const MCOLOR = {
  'do': '#ef4444', 'cam': '#f97316', 'vang': '#eab308', 'xanh la': '#22c55e',
  'xanh duong': '#3b82f6', 'tim': '#a855f7', 'trang': '#f8fafc', 'bac': '#94a3b8',
  'den': '#1e293b', 'nau': '#78350f', 'unknown': '#475569'
};

function showToast(msg, isError = false) {
  const t = document.getElementById('toast');
  const ic = document.getElementById('toastIcon');
  const txt = document.getElementById('toastMsg');
  txt.textContent = msg;
  if (isError) {
    ic.className = 'fa-solid fa-triangle-exclamation text-rose-400';
  } else {
    ic.className = 'fa-solid fa-circle-check text-emerald-400';
  }
  t.style.display = 'flex';
  setTimeout(() => { t.style.display = 'none'; }, 3500);
}

async function j(url, options = {}) {
  try {
    const r = await fetch(url, options);
    if (!r.ok) return null;
    return await r.json();
  } catch (e) {
    return null;
  }
}

// ------------------------------------
// KPI ANALYTICS BAR WITH VISUALIZATIONS
// ------------------------------------
async function updateKPIStats(date) {
  const res = await j('/api/stats?date=' + encodeURIComponent(date || ''));
  if (!res) return;
  document.getElementById('kpiObjects').textContent = res.total_objects.toLocaleString();
  
  const typeParts = Object.entries(res.types_breakdown || {}).map(([k, v]) => `${k}: ${v}`);
  document.getElementById('kpiObjectsSub').textContent = typeParts.join(' · ') || 'Chưa có phân loại';

  // Render Color Spectrum Multi-bar
  const specEl = document.getElementById('colorSpectrum');
  specEl.innerHTML = '';
  const colors = Object.entries(res.colors_breakdown || {});
  const totalColored = colors.reduce((acc, [, v]) => acc + v, 0);
  document.getElementById('colorCountLabel').textContent = `${colors.length} tông màu`;

  if (totalColored > 0) {
    colors.forEach(([color, cnt]) => {
      const pct = (cnt / totalColored) * 100;
      const bar = document.createElement('div');
      bar.className = 'h-full transition-all duration-500';
      bar.style.width = `${pct}%`;
      bar.style.backgroundColor = MCOLOR[color] || '#475569';
      bar.title = `${color}: ${cnt} xe (${pct.toFixed(1)}%)`;
      specEl.appendChild(bar);
    });
  }

  document.getElementById('kpiViolations').textContent = res.total_violations.toLocaleString();
  const vioParts = Object.entries(res.violations_breakdown || {}).map(([k, v]) => {
    const name = VIOLATION_TRANSLATE[k]?.name || k;
    return `${name}: ${v}`;
  });
  document.getElementById('kpiViolationsSub').textContent = vioParts.join(' · ') || 'Không có vi phạm';
}

// ------------------------------------
// LIVE AUTO-REFRESH MODE
// ------------------------------------
function toggleLiveRefresh() {
  const ping = document.getElementById('livePing');
  const dot = document.getElementById('liveDot');
  const text = document.getElementById('liveText');
  
  if (liveRefreshTimer) {
    clearInterval(liveRefreshTimer);
    liveRefreshTimer = null;
    ping.classList.add('opacity-0');
    dot.className = 'relative inline-flex rounded-full h-2 w-2 bg-slate-500';
    text.textContent = 'Auto-Refresh: Tắt';
    showToast('Đã dừng chế độ tự động cập nhật');
  } else {
    ping.classList.remove('opacity-0');
    dot.className = 'relative inline-flex rounded-full h-2 w-2 bg-emerald-500';
    text.textContent = 'Auto-Refresh: Bật (6s)';
    showToast('Đã kích hoạt chế độ Live Auto-Refresh (cập nhật mỗi 6 giây)');
    liveRefreshTimer = setInterval(() => {
      if (currentTab === 'o') {
        loadGrid();
        updateKPIStats(S.date);
      } else {
        vLoadGrid(true);
        updateKPIStats(V.date);
      }
    }, 6000);
  }
}

// ------------------------------------
// TAB 1: OBJECTS BROWSER
// ------------------------------------
async function loadDates() {
  const ds = await j('/api/dates') || [];
  const el = document.getElementById('date');
  el.innerHTML = ds.length ? '' : '<option value="">(Chưa có dữ liệu)</option>';
  ds.forEach(d => {
    const o = document.createElement('option');
    o.value = d.date;
    o.textContent = `${d.date} (${d.count} xe)`;
    el.appendChild(o);
  });
  if (ds.length) {
    S.date = ds[0].date;
    el.value = S.date;
    document.getElementById('badgeO').textContent = ds[0].count;
    updateKPIStats(S.date);
    await loadTypes();
  }
}

async function loadTypes() {
  const ts = await j('/api/types?date=' + encodeURIComponent(S.date)) || [];
  const el = document.getElementById('types');
  el.innerHTML = '<span class="text-xs font-semibold text-slate-400 uppercase tracking-wider mr-1">Chủng loại:</span>';
  
  const allBtn = document.createElement('button');
  allBtn.className = 'px-3 py-1 rounded-lg text-xs font-semibold bg-brand-600 text-white transition';
  allBtn.textContent = 'Tất cả';
  allBtn.onclick = () => {
    S.type = '';
    [...el.querySelectorAll('button')].forEach(b => b.className = 'px-3 py-1 rounded-lg text-xs font-semibold bg-slate-900 text-slate-300 hover:bg-slate-800 transition');
    allBtn.className = 'px-3 py-1 rounded-lg text-xs font-semibold bg-brand-600 text-white transition';
    loadColors();
  };
  el.appendChild(allBtn);

  ts.forEach(t => {
    const b = document.createElement('button');
    b.className = 'px-3 py-1 rounded-lg text-xs font-semibold bg-slate-900 text-slate-300 hover:bg-slate-800 transition';
    b.innerHTML = `<i class="fa-solid fa-car text-[10px] mr-1 text-slate-400"></i> ${t.type} <span class="opacity-60 text-[10px] font-mono">(${t.count})</span>`;
    b.onclick = () => {
      S.type = (S.type === t.type ? '' : t.type);
      [...el.querySelectorAll('button')].forEach(x => x.className = 'px-3 py-1 rounded-lg text-xs font-semibold bg-slate-900 text-slate-300 hover:bg-slate-800 transition');
      if (S.type) {
        b.className = 'px-3 py-1 rounded-lg text-xs font-semibold bg-brand-600 text-white transition';
      } else {
        allBtn.className = 'px-3 py-1 rounded-lg text-xs font-semibold bg-brand-600 text-white transition';
      }
      loadColors();
    };
    el.appendChild(b);
  });
  await loadColors();
}

async function loadColors() {
  const q = `?date=${encodeURIComponent(S.date)}&type=${encodeURIComponent(S.type)}`;
  const cs = await j('/api/colors' + q) || [];
  const el = document.getElementById('colors');
  el.innerHTML = '<span class="text-xs font-semibold text-slate-400 uppercase tracking-wider mr-1">Màu sắc:</span>';

  const all = document.createElement('button');
  all.className = 'px-3 py-1 rounded-lg text-xs font-semibold bg-brand-600 text-white transition';
  all.textContent = 'Tất cả';
  all.onclick = () => {
    S.color = '';
    [...el.querySelectorAll('button')].forEach(b => b.classList.remove('ring-2', 'ring-white'));
    all.className = 'px-3 py-1 rounded-lg text-xs font-semibold bg-brand-600 text-white transition';
    loadGrid();
  };
  el.appendChild(all);

  cs.forEach(c => {
    const b = document.createElement('button');
    b.className = 'w-7 h-7 rounded-full border border-slate-700 flex items-center justify-center transition hover:scale-110 shadow-sm';
    b.style.backgroundColor = MCOLOR[c.color] || '#334155';
    b.title = `${c.color} (${c.count})`;
    b.onclick = () => {
      S.color = (S.color === c.color ? '' : c.color);
      [...el.querySelectorAll('button')].forEach(x => x.classList.remove('ring-2', 'ring-white'));
      all.className = 'px-3 py-1 rounded-lg text-xs font-semibold bg-slate-900 text-slate-300 hover:bg-slate-800 transition';
      if (S.color) b.classList.add('ring-2', 'ring-white');
      else all.className = 'px-3 py-1 rounded-lg text-xs font-semibold bg-brand-600 text-white transition';
      loadGrid();
    };
    el.appendChild(b);
  });
  await loadGrid();
}

async function loadGrid() {
  const q = `?date=${encodeURIComponent(S.date)}&type=${encodeURIComponent(S.type)}&color=${encodeURIComponent(S.color)}&limit=250`;
  const rows = await j('/api/objects' + q) || [];
  S.rawObjects = rows;
  S.visibleObjects = rows;
  renderObjects(rows);
}

function renderObjects(rows) {
  S.visibleObjects = rows;
  document.getElementById('count').textContent = rows.length + ' xe';
  const g = document.getElementById('grid');
  const empty = document.getElementById('emptyState');
  g.innerHTML = '';

  if (!rows || rows.length === 0) {
    empty.style.display = 'flex';
    return;
  }
  empty.style.display = 'none';

  rows.forEach((r, idx) => {
    const isSelected = selectedItems.has(`obj-${r.track_id}`);
    const card = document.createElement('div');
    card.id = `card-obj-${r.track_id}`;
    card.className = `glass-panel rounded-2xl overflow-hidden card-hover card-obj-hover border ${isSelected ? 'border-brand-500 ring-2 ring-brand-500/50' : 'border-slate-800/80'} cursor-pointer flex flex-col relative group`;
    const confPct = Math.round(r.best_conf * 100);
    
    card.innerHTML = `
      <div class="relative aspect-[4/3] bg-dark-950 overflow-hidden skeleton-bg">
        <img loading="lazy" src="${r.img}" alt="Track #${r.track_id}"
             class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500 relative z-0"
             onerror="this.src='https://placehold.co/400x300/0f172a/64748b?text=Khong+Co+Anh'">
        
        <!-- Vignette Dark Gradient -->
        <div class="absolute inset-0 bg-gradient-to-t from-dark-950/90 via-transparent to-black/30 pointer-events-none z-1"></div>

        <!-- Selection Checkbox & Vehicle Class -->
        <div class="absolute top-2.5 left-2.5 z-10 flex items-center gap-1.5">
          <input type="checkbox" id="chk-obj-${r.track_id}" ${isSelected ? 'checked' : ''}
                 onchange="event.stopPropagation(); toggleItemSelection('obj', ${r.track_id}, ${JSON.stringify(r).replace(/"/g, '&quot;')})"
                 class="w-4 h-4 rounded border-slate-700 bg-slate-900/90 text-brand-600 focus:ring-brand-500 cursor-pointer ${isSelectionMode ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'} transition-opacity">
          <span class="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase bg-brand-500/80 text-white backdrop-blur-md ring-1 ring-white/20">
            ${r.vehicle_type}
          </span>
        </div>

        <div class="absolute top-2.5 right-2.5 z-10 flex items-center gap-1.5">
          <span class="px-2 py-0.5 rounded-md text-[10px] font-mono font-bold bg-black/70 text-slate-200 border border-white/10 backdrop-blur-md">
            ${confPct}%
          </span>
          <button onclick="event.stopPropagation(); deleteObjectItem(${r.track_id}, '${r.date}', '${r.camera_id}')"
                  title="Xóa đối tượng này"
                  class="w-6 h-6 rounded-md bg-rose-600/90 hover:bg-rose-600 text-white flex items-center justify-center text-[10px] opacity-0 group-hover:opacity-100 transition shadow-sm">
            <i class="fa-solid fa-trash-can"></i>
          </button>
        </div>
      </div>
      <div class="p-3.5 flex flex-col gap-2 flex-1 justify-between text-xs bg-dark-900/40">
        <div>
          <div class="flex items-center justify-between font-bold text-slate-200">
            <span class="font-mono text-brand-400 font-bold">#${r.track_id}</span>
            <span class="text-slate-400 text-[11px] font-mono">${r.camera_id}</span>
          </div>
          <div class="flex items-center gap-1.5 mt-1 text-slate-400">
            <span class="w-2.5 h-2.5 rounded-full border border-slate-600 inline-block shadow-sm" style="background:${MCOLOR[r.color]||'#475569'}"></span>
            <span class="capitalize font-medium text-slate-300">${r.color}</span>
            <span class="text-slate-600">·</span>
            <span class="font-mono">${r.frames} frames</span>
          </div>
        </div>
        <div class="pt-2 border-t border-slate-800/80 text-[11px] text-slate-400 flex items-center justify-between">
          <span class="text-slate-500">Thời gian:</span>
          <span class="font-mono text-slate-300">${Number(r.first_seen).toFixed(1)}s → ${Number(r.last_seen).toFixed(1)}s</span>
        </div>
      </div>
    `;

    card.onclick = () => {
      if (isSelectionMode) {
        const chk = document.getElementById(`chk-obj-${r.track_id}`);
        if (chk) {
          chk.checked = !chk.checked;
          toggleItemSelection('obj', r.track_id, r);
        }
      } else {
        openModalByIndex(idx, 'object');
      }
    };
    g.appendChild(card);
  });
}

function filterObjectsLocal() {
  const kw = document.getElementById('objSearch').value.toLowerCase().trim();
  if (!kw) return renderObjects(S.rawObjects);
  const filtered = S.rawObjects.filter(r => 
    String(r.track_id).includes(kw) ||
    String(r.vehicle_type).toLowerCase().includes(kw) ||
    String(r.color).toLowerCase().includes(kw) ||
    String(r.camera_id).toLowerCase().includes(kw)
  );
  renderObjects(filtered);
}

document.getElementById('date').onchange = (e) => {
  S.date = e.target.value;
  S.type = '';
  S.color = '';
  updateKPIStats(S.date);
  loadTypes();
};

// ------------------------------------
// TAB 2: VIOLATIONS EVIDENCE BROWSER
// ------------------------------------
async function vLoadDates() {
  const ds = await j('/api/vdates') || [];
  const el = document.getElementById('vdate');
  el.innerHTML = ds.length ? '' : '<option value="">(Chưa có vi phạm)</option>';
  ds.forEach(d => {
    const o = document.createElement('option');
    o.value = d.date;
    o.textContent = `${d.date} (${d.count} sự kiện)`;
    el.appendChild(o);
  });
  if (ds.length) {
    V.date = ds[0].date;
    el.value = V.date;
    document.getElementById('badgeV').textContent = ds[0].count;
    await vLoadVios();
  }
}

async function vLoadVios() {
  const vs = await j('/api/violations?date=' + encodeURIComponent(V.date)) || [];
  const el = document.getElementById('vios');
  el.innerHTML = '<span class="text-xs font-semibold text-slate-400 uppercase tracking-wider mr-1">Lỗi vi phạm:</span>';
  
  const allBtn = document.createElement('button');
  allBtn.className = 'px-3 py-1 rounded-lg text-xs font-semibold bg-rose-600 text-white transition';
  allBtn.textContent = 'Tất cả';
  allBtn.onclick = () => {
    V.vio = '';
    [...el.querySelectorAll('button')].forEach(b => b.className = 'px-3 py-1 rounded-lg text-xs font-semibold bg-slate-900 text-slate-300 hover:bg-slate-800 transition');
    allBtn.className = 'px-3 py-1 rounded-lg text-xs font-semibold bg-rose-600 text-white transition';
    vLoadGrid(true);
  };
  el.appendChild(allBtn);

  vs.forEach(v => {
    const info = VIOLATION_TRANSLATE[v.violation] || { name: v.violation, icon: 'fa-triangle-exclamation' };
    const b = document.createElement('button');
    b.className = 'px-3 py-1 rounded-lg text-xs font-semibold bg-slate-900 text-slate-300 hover:bg-slate-800 transition flex items-center gap-1.5';
    b.innerHTML = `<i class="fa-solid ${info.icon} text-[10px] text-rose-400"></i> <span>${info.name}</span> <span class="opacity-60 text-[10px] font-mono">(${v.count})</span>`;
    b.onclick = () => {
      V.vio = (V.vio === v.violation ? '' : v.violation);
      [...el.querySelectorAll('button')].forEach(x => x.className = 'px-3 py-1 rounded-lg text-xs font-semibold bg-slate-900 text-slate-300 hover:bg-slate-800 transition');
      if (V.vio) {
        b.className = 'px-3 py-1 rounded-lg text-xs font-semibold bg-rose-600 text-white transition';
      } else {
        allBtn.className = 'px-3 py-1 rounded-lg text-xs font-semibold bg-rose-600 text-white transition';
      }
      vLoadGrid(true);
    };
    el.appendChild(b);
  });
  vLoadGrid(true);
}

async function vLoadGrid(reset) {
  if (reset) V.offset = 0;
  const q = `?date=${encodeURIComponent(V.date)}&violation=${encodeURIComponent(V.vio)}&limit=60&offset=${V.offset}`;
  const res = await j('/api/events' + q) || { total: 0, items: [] };
  V.total = res.total || 0;
  if (reset) V.rawEvents = [];
  V.rawEvents = V.rawEvents.concat(res.items || []);
  V.visibleEvents = V.rawEvents;
  renderViolations(V.rawEvents, reset);
}

function renderViolations(items, reset) {
  V.visibleEvents = items;
  const g = document.getElementById('grid');
  const empty = document.getElementById('emptyState');
  if (reset) g.innerHTML = '';

  document.getElementById('vcount').textContent = `${V.total} vi phạm`;
  document.getElementById('vmoreWrap').style.display = (V.offset + items.length < V.total) ? 'flex' : 'none';

  if (!items || items.length === 0) {
    empty.style.display = 'flex';
    return;
  }
  empty.style.display = 'none';

  items.forEach((r, idx) => {
    const isSelected = selectedItems.has(`vio-${r.event_id}`);
    const card = document.createElement('div');
    card.id = `card-vio-${r.event_id}`;
    card.className = `glass-panel rounded-2xl overflow-hidden card-hover card-vio-hover border ${isSelected ? 'border-rose-500 ring-2 ring-rose-500/50' : 'border-slate-800/80'} cursor-pointer flex flex-col relative group`;
    const vInfo = VIOLATION_TRANSLATE[r.violation] || { name: r.violation, icon: 'fa-triangle-exclamation' };
    const timeShort = (r.timestamp || '').slice(11, 19);

    card.innerHTML = `
      <div class="relative aspect-[4/3] bg-dark-950 overflow-hidden skeleton-bg">
        <img loading="lazy" src="${r.thumb || r.full}" alt="${r.event_id}"
             class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500 relative z-0"
             onerror="this.src='https://placehold.co/400x300/0f172a/64748b?text=Khong+Co+Anh'">
        
        <!-- Vignette Dark Gradient -->
        <div class="absolute inset-0 bg-gradient-to-t from-dark-950/90 via-transparent to-black/30 pointer-events-none z-1"></div>

        <!-- Selection Checkbox & Violation Badge -->
        <div class="absolute top-2.5 left-2.5 z-10 flex items-center gap-1.5">
          <input type="checkbox" id="chk-vio-${r.event_id}" ${isSelected ? 'checked' : ''}
                 onchange="event.stopPropagation(); toggleItemSelection('vio', '${r.event_id}', ${JSON.stringify(r).replace(/"/g, '&quot;')})"
                 class="w-4 h-4 rounded border-slate-700 bg-slate-900/90 text-rose-600 focus:ring-rose-500 cursor-pointer ${isSelectionMode ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'} transition-opacity">
          <span class="px-2 py-0.5 rounded-md text-[10px] font-bold bg-rose-600/90 text-white backdrop-blur-md flex items-center gap-1 ring-1 ring-white/20 shadow-sm">
            <i class="fa-solid ${vInfo.icon} text-[9px]"></i>
            ${vInfo.name}
          </span>
        </div>

        <div class="absolute top-2.5 right-2.5 z-10 flex items-center gap-1.5">
          <button onclick="event.stopPropagation(); deleteViolationItem('${r.event_id}', '${r.camera_id}', '${r.date}', '${r.violation}')"
                  title="Xóa sự kiện vi phạm này"
                  class="w-6 h-6 rounded-md bg-rose-600/90 hover:bg-rose-600 text-white flex items-center justify-center text-[10px] opacity-0 group-hover:opacity-100 transition shadow-sm">
            <i class="fa-solid fa-trash-can"></i>
          </button>
        </div>
        <div class="absolute bottom-2.5 right-2.5 z-10">
          <span class="px-2 py-0.5 rounded-md text-[10px] font-mono bg-black/70 text-slate-200 backdrop-blur-md">
            ${timeShort}
          </span>
        </div>
      </div>
      <div class="p-3.5 flex flex-col gap-2 flex-1 justify-between text-xs bg-dark-900/40">
        <div>
          <div class="flex items-center justify-between font-bold text-slate-200">
            <span class="font-mono text-rose-400 font-bold">#${r.event_id.slice(0, 8)}</span>
            <span class="text-slate-400 text-[11px] font-mono">${r.camera_id}</span>
          </div>
          <div class="flex items-center gap-1.5 mt-1 text-slate-300">
            <span class="px-2 py-0.5 rounded bg-slate-900 text-[11px] font-medium text-slate-300">${r.class || 'Phương tiện'}</span>
            <span class="text-slate-500">·</span>
            <span class="font-mono text-slate-400">${Math.round((r.confidence||0)*100)}% conf</span>
          </div>
        </div>
        <div class="pt-2 border-t border-slate-800/80 text-[11px] text-slate-400 flex items-center justify-between">
          <span class="text-slate-500">Vùng vi phạm:</span>
          <span class="font-semibold text-amber-400">${(r.extra||{}).zone_id || 'Mặc định'}</span>
        </div>
      </div>
    `;

    card.onclick = () => {
      if (isSelectionMode) {
        const chk = document.getElementById(`chk-vio-${r.event_id}`);
        if (chk) {
          chk.checked = !chk.checked;
          toggleItemSelection('vio', r.event_id, r);
        }
      } else {
        openModalByIndex(idx, 'violation');
      }
    };
    g.appendChild(card);
    V.offset++;
  });
}

function filterViolationsLocal() {
  const kw = document.getElementById('vioSearch').value.toLowerCase().trim();
  if (!kw) return renderViolations(V.rawEvents, true);
  const filtered = V.rawEvents.filter(r => 
    String(r.event_id).toLowerCase().includes(kw) ||
    String(r.violation).toLowerCase().includes(kw) ||
    String(r.class).toLowerCase().includes(kw) ||
    String(r.camera_id).toLowerCase().includes(kw)
  );
  renderViolations(filtered, true);
}

document.getElementById('vdate').onchange = (e) => {
  V.date = e.target.value;
  V.vio = '';
  updateKPIStats(V.date);
  vLoadVios();
};

function vMore() {
  vLoadGrid(false);
}

// ------------------------------------
// TABS SWITCHER
// ------------------------------------
function showTab(t) {
  currentTab = t;
  clearSelection();
  const isO = (t === 'o');
  document.getElementById('paneO').style.display = isO ? 'flex' : 'none';
  document.getElementById('paneV').style.display = isO ? 'none' : 'flex';

  const tabO = document.getElementById('tabO');
  const tabV = document.getElementById('tabV');
  if (isO) {
    tabO.className = 'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all text-white bg-brand-600 shadow-md shadow-brand-500/20';
    tabV.className = 'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all text-slate-400 hover:text-slate-200';
    loadGrid();
  } else {
    tabV.className = 'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all text-white bg-rose-600 shadow-md shadow-rose-500/20';
    tabO.className = 'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all text-slate-400 hover:text-slate-200';
    if (!V.init) {
      V.init = true;
      vLoadDates();
    } else {
      vLoadGrid(true);
    }
  }
}

// ------------------------------------
// MODAL INSPECTION & SHORTCUTS
// ------------------------------------
function openModalByIndex(idx, type) {
  const list = (type === 'violation') ? V.visibleEvents : S.visibleObjects;
  if (!list || idx < 0 || idx >= list.length) return;
  const item = list[idx];
  
  activeModalData = { type, index: idx, item, currentMedia: 'crop' };
  resetZoom();

  // Update index indicator
  document.getElementById('mIndex').textContent = `${idx + 1} / ${list.length}`;

  if (type === 'violation') {
    const vInfo = VIOLATION_TRANSLATE[item.violation] || { name: item.violation };
    document.getElementById('mBadge').textContent = vInfo.name;
    document.getElementById('mBadge').className = 'px-2.5 py-1 rounded-md text-xs font-bold uppercase bg-rose-500/20 text-rose-400 border border-rose-500/30';
    document.getElementById('mTitle').textContent = `Sự Kiện Vi Phạm: ${vInfo.name}`;

    document.getElementById('mTrackId').textContent = `#${item.event_id.slice(0, 8)}`;
    document.getElementById('mCam').textContent = item.camera_id;
    document.getElementById('mTime').textContent = (item.timestamp || '').replace('T', ' ').slice(0, 19);
    document.getElementById('mClass').textContent = item.class || 'Phương tiện';
    document.getElementById('mConf').textContent = `${Math.round((item.confidence || 0) * 100)}%`;
    document.getElementById('mZone').textContent = (item.extra || {}).zone_id || 'Mặc định';

    document.getElementById('mediaTabs').style.display = 'flex';
    const hasDiptych = (item.gallery && item.gallery.length > 0) || (item.full && item.full.includes('diptych'));
    document.getElementById('btnDiptych').style.display = hasDiptych ? 'inline-block' : 'none';
    switchMedia('crop');

    document.getElementById('minfo').textContent = JSON.stringify(item.raw_meta || item.extra || {}, null, 2);
  } else {
    document.getElementById('mBadge').textContent = 'Object Track';
    document.getElementById('mBadge').className = 'px-2.5 py-1 rounded-md text-xs font-bold uppercase bg-brand-500/20 text-brand-400 border border-brand-500/30';
    document.getElementById('mTitle').textContent = `Phương tiện #${item.track_id} (${item.vehicle_type})`;

    document.getElementById('mTrackId').textContent = `#${item.track_id}`;
    document.getElementById('mCam').textContent = item.camera_id;
    document.getElementById('mTime').textContent = `${item.date} (${Number(item.first_seen).toFixed(1)}s → ${Number(item.last_seen).toFixed(1)}s)`;
    document.getElementById('mClass').textContent = `${item.vehicle_type} (${item.color})`;
    document.getElementById('mConf').textContent = `${Math.round(item.best_conf * 100)}%`;
    document.getElementById('mZone').textContent = 'Lưu thông';

    document.getElementById('mediaTabs').style.display = 'none';
    document.getElementById('mimg').src = item.img;
    document.getElementById('mDownload').href = item.img;

    document.getElementById('minfo').textContent = JSON.stringify({
      track_id: item.track_id,
      bbox: item.best_bbox,
      color: item.color,
      frames_tracked: item.frames,
      camera: item.camera_id
    }, null, 2);
  }

  document.getElementById('modal').style.display = 'flex';
}

function navModal(step) {
  if (!activeModalData) return;
  const list = (activeModalData.type === 'violation') ? V.visibleEvents : S.visibleObjects;
  if (!list || list.length === 0) return;
  let newIdx = activeModalData.index + step;
  if (newIdx < 0) newIdx = list.length - 1;
  if (newIdx >= list.length) newIdx = 0;
  openModalByIndex(newIdx, activeModalData.type);
}

// Global Keyboard Navigation (HUD supported)
window.addEventListener('keydown', (e) => {
  const m = document.getElementById('modal');
  if (m && m.style.display !== 'none') {
    if (e.key === 'ArrowLeft') {
      e.preventDefault();
      navModal(-1);
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      navModal(1);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      closeModal();
    } else if (e.key === 'z' || e.key === 'Z') {
      e.preventDefault();
      toggleImageZoom();
    } else if (e.key === 'd' || e.key === 'D') {
      e.preventDefault();
      const dload = document.getElementById('mDownload');
      if (dload && dload.href) dload.click();
    } else if (e.key === 'Delete') {
      e.preventDefault();
      deleteActiveModalItem();
    }
  }
});

function switchMedia(type) {
  if (!activeModalData || !activeModalData.item) return;
  const r = activeModalData.item;
  const imgEl = document.getElementById('mimg');
  const dload = document.getElementById('mDownload');

  const bCrop = document.getElementById('btnCrop');
  const bFull = document.getElementById('btnFull');
  const bDip = document.getElementById('btnDiptych');

  [bCrop, bFull, bDip].forEach(b => b.className = 'px-3 py-1 rounded-lg text-xs font-semibold text-slate-400 hover:text-slate-200');

  resetZoom();
  if (type === 'crop') {
    bCrop.className = 'px-3 py-1 rounded-lg text-xs font-semibold bg-brand-600 text-white';
    imgEl.src = r.crop || r.thumb;
    dload.href = r.crop || r.thumb;
  } else if (type === 'full') {
    bFull.className = 'px-3 py-1 rounded-lg text-xs font-semibold bg-brand-600 text-white';
    imgEl.src = r.full || r.thumb;
    dload.href = r.full || r.thumb;
  } else if (type === 'diptych') {
    bDip.className = 'px-3 py-1 rounded-lg text-xs font-semibold bg-brand-600 text-white';
    const dip = (r.gallery && r.gallery[0]) || r.full;
    imgEl.src = dip;
    dload.href = dip;
  }
}

function toggleImageZoom() {
  const img = document.getElementById('mimg');
  const btn = document.getElementById('btnZoom');
  const txt = document.getElementById('txtZoom');
  isZoomed = !isZoomed;
  if (isZoomed) {
    img.classList.add('img-zoomed');
    img.classList.remove('img-zoomable');
    txt.textContent = 'Thu nhỏ (Z)';
    btn.classList.add('bg-brand-600', 'text-white');
  } else {
    resetZoom();
  }
}

function resetZoom() {
  isZoomed = false;
  const img = document.getElementById('mimg');
  const btn = document.getElementById('btnZoom');
  const txt = document.getElementById('txtZoom');
  if (img) {
    img.classList.remove('img-zoomed');
    img.classList.add('img-zoomable');
  }
  if (txt) txt.textContent = 'Phóng to (Z)';
  if (btn) btn.classList.remove('bg-brand-600', 'text-white');
}

function closeModal() {
  document.getElementById('modal').style.display = 'none';
  resetZoom();
  activeModalData = null;
}

function copyRawMeta() {
  if (!activeModalData) return;
  const text = document.getElementById('minfo').textContent;
  navigator.clipboard.writeText(text).then(() => {
    showToast('Đã sao chép dữ liệu JSON vào bộ nhớ tạm!');
  });
}

// ------------------------------------
// BATCH SELECTION & BULK DELETE
// ------------------------------------
function toggleSelectionMode() {
  isSelectionMode = !isSelectionMode;
  const btn = document.getElementById('btnToggleSelectMode');
  const txt = document.getElementById('txtSelectMode');
  if (isSelectionMode) {
    btn.className = 'px-3.5 py-2 rounded-xl bg-brand-600 text-white border border-brand-500 text-xs font-semibold flex items-center gap-2 transition shadow-md';
    txt.textContent = 'Đang bật chọn nhiều';
    showToast('Đã bật chế độ chọn nhiều. Tích chọn các thẻ để thao tác hàng loạt.');
  } else {
    btn.className = 'px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 text-xs font-semibold flex items-center gap-2 transition';
    txt.textContent = 'Chế độ chọn nhiều';
    clearSelection();
  }
  document.querySelectorAll('#grid input[type="checkbox"]').forEach(c => {
    c.style.opacity = isSelectionMode ? '1' : '';
  });
}

function toggleItemSelection(prefix, id, item) {
  const key = `${prefix}-${id}`;
  const card = document.getElementById(`card-${prefix}-${id}`);
  if (selectedItems.has(key)) {
    selectedItems.delete(key);
    if (card) {
      card.classList.remove('border-brand-500', 'ring-2', 'ring-brand-500/50', 'border-rose-500', 'ring-rose-500/50');
      card.classList.add('border-slate-800/80');
    }
  } else {
    selectedItems.set(key, { prefix, id, item });
    if (card) {
      card.classList.remove('border-slate-800/80');
      if (prefix === 'vio') card.classList.add('border-rose-500', 'ring-2', 'ring-rose-500/50');
      else card.classList.add('border-brand-500', 'ring-2', 'ring-brand-500/50');
    }
  }
  updateBulkBar();
}

function updateBulkBar() {
  const bar = document.getElementById('bulkBar');
  const cnt = document.getElementById('selectedCount');
  cnt.textContent = selectedItems.size;
  bar.style.display = (selectedItems.size > 0) ? 'flex' : 'none';
}

function clearSelection() {
  selectedItems.clear();
  document.querySelectorAll('#grid input[type="checkbox"]').forEach(c => c.checked = false);
  document.querySelectorAll('#grid .card-hover').forEach(c => {
    c.classList.remove('border-brand-500', 'ring-2', 'ring-brand-500/50', 'border-rose-500', 'ring-rose-500/50');
    c.classList.add('border-slate-800/80');
  });
  updateBulkBar();
}

function toggleSelectAll() {
  const list = (currentTab === 'v') ? V.visibleEvents : S.visibleObjects;
  const prefix = (currentTab === 'v') ? 'vio' : 'obj';
  const allSelected = list.every(it => selectedItems.has(`${prefix}-${prefix==='vio'?it.event_id:it.track_id}`));

  if (allSelected) {
    clearSelection();
  } else {
    list.forEach(it => {
      const id = (prefix === 'vio') ? it.event_id : it.track_id;
      const key = `${prefix}-${id}`;
      selectedItems.set(key, { prefix, id, item: it });
      const chk = document.getElementById(`chk-${prefix}-${id}`);
      if (chk) chk.checked = true;
      const card = document.getElementById(`card-${prefix}-${id}`);
      if (card) {
        card.classList.remove('border-slate-800/80');
        if (prefix === 'vio') card.classList.add('border-rose-500', 'ring-2', 'ring-rose-500/50');
        else card.classList.add('border-brand-500', 'ring-2', 'ring-brand-500/50');
      }
    });
    updateBulkBar();
  }
}

async function bulkDeleteSelected() {
  const count = selectedItems.size;
  if (count === 0) return;
  if (!confirm(`Bạn có chắc chắn muốn xóa vĩnh viễn ${count} mục đã chọn?`)) {
    return;
  }

  const itemsToDelete = Array.from(selectedItems.values());
  const objItems = itemsToDelete.filter(x => x.prefix === 'obj').map(x => ({
    track_id: x.item.track_id,
    date: x.item.date,
    camera: x.item.camera_id
  }));
  const vioItems = itemsToDelete.filter(x => x.prefix === 'vio').map(x => ({
    event_id: x.item.event_id,
    camera: x.item.camera_id,
    date: x.item.date,
    violation: x.item.violation
  }));

  try {
    let deletedObj = 0, deletedVio = 0;
    if (objItems.length > 0) {
      const res = await fetch('/api/objects/bulk-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: objItems })
      });
      if (res.ok) {
        const d = await res.json();
        deletedObj = d.deleted_count || 0;
      }
    }

    if (vioItems.length > 0) {
      const res = await fetch('/api/events/bulk-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: vioItems })
      });
      if (res.ok) {
        const d = await res.json();
        deletedVio = d.deleted_count || 0;
      }
    }

    showToast(`Đã xóa thành công ${deletedObj + deletedVio} mục`);
    clearSelection();
    
    if (currentTab === 'o') {
      await loadGrid();
      updateKPIStats(S.date);
    } else {
      await vLoadGrid(true);
      updateKPIStats(V.date);
    }
  } catch (e) {
    showToast('Lỗi khi xóa hàng loạt: ' + e.message, true);
  }
}

// ------------------------------------
// SINGLE DELETE HANDLERS
// ------------------------------------
async function deleteViolationItem(eventId, camera, date, violation) {
  if (!confirm(`Bạn có chắc chắn muốn xóa vĩnh viễn sự kiện vi phạm #${eventId.slice(0, 8)}?`)) {
    return;
  }
  const q = `?camera=${encodeURIComponent(camera||'')}&date=${encodeURIComponent(date||'')}&violation=${encodeURIComponent(violation||'')}&event_id=${encodeURIComponent(eventId)}`;
  try {
    let res = await fetch('/api/events' + q, { method: 'DELETE' });
    if (!res.ok) {
      res = await fetch('/api/events/delete' + q, { method: 'POST' });
    }
    if (res.ok) {
      showToast(`Đã xóa thành công sự kiện #${eventId.slice(0, 8)}`);
      V.rawEvents = V.rawEvents.filter(x => x.event_id !== eventId);
      V.total = Math.max(0, V.total - 1);
      document.getElementById('badgeV').textContent = V.total;
      document.getElementById('vcount').textContent = `${V.total} vi phạm`;
      const card = document.getElementById(`card-vio-${eventId}`);
      if (card) {
        card.style.transition = 'all 0.3s ease';
        card.style.opacity = '0';
        card.style.transform = 'scale(0.8)';
        setTimeout(() => card.remove(), 300);
      }
      if (activeModalData && activeModalData.item && activeModalData.item.event_id === eventId) {
        closeModal();
      }
      updateKPIStats(V.date);
    } else {
      let errDetail = 'Lỗi máy chủ';
      try {
        const err = await res.json();
        errDetail = err.detail || JSON.stringify(err);
      } catch (_) {}
      showToast(errDetail, true);
    }
  } catch (e) {
    console.error('Delete violation error:', e);
    showToast('Lỗi mạng: ' + (e.message || 'Không thể kết nối máy chủ'), true);
  }
}

async function deleteObjectItem(trackId, date, camera) {
  if (!confirm(`Bạn có chắc chắn muốn xóa đối tượng xe #${trackId}?`)) {
    return;
  }
  const q = `?track_id=${trackId}&date=${encodeURIComponent(date||'')}&camera=${encodeURIComponent(camera||'')}`;
  try {
    let res = await fetch('/api/objects' + q, { method: 'DELETE' });
    if (!res.ok) {
      res = await fetch('/api/objects/delete' + q, { method: 'POST' });
    }
    if (res.ok) {
      showToast(`Đã xóa thành công đối tượng #${trackId}`);
      S.rawObjects = S.rawObjects.filter(x => x.track_id !== trackId);
      const countEl = document.getElementById('count');
      const badgeO = document.getElementById('badgeO');
      const newLen = S.rawObjects.length;
      if (countEl) countEl.textContent = newLen + ' xe';
      if (badgeO) badgeO.textContent = newLen;
      const card = document.getElementById(`card-obj-${trackId}`);
      if (card) {
        card.style.transition = 'all 0.3s ease';
        card.style.opacity = '0';
        card.style.transform = 'scale(0.8)';
        setTimeout(() => card.remove(), 300);
      }
      if (activeModalData && activeModalData.item && activeModalData.item.track_id === trackId) {
        closeModal();
      }
      updateKPIStats(S.date);
    } else {
      let errDetail = 'Lỗi máy chủ';
      try {
        const err = await res.json();
        errDetail = err.detail || JSON.stringify(err);
      } catch (_) {}
      showToast(errDetail, true);
    }
  } catch (e) {
    console.error('Delete object error:', e);
    showToast('Lỗi mạng: ' + (e.message || 'Không thể kết nối máy chủ'), true);
  }
}

function deleteActiveModalItem() {
  if (!activeModalData || !activeModalData.item) return;
  const it = activeModalData.item;
  if (activeModalData.type === 'violation') {
    deleteViolationItem(it.event_id, it.camera_id, it.date, it.violation);
  } else {
    deleteObjectItem(it.track_id, it.date, it.camera_id);
  }
}

function refreshData() {
  if (currentTab === 'o') {
    loadDates();
  } else {
    vLoadDates();
  }
  showToast('Đã làm mới dữ liệu');
}

// Initial Kickoff
loadDates();
</script>
</body>
</html>"""

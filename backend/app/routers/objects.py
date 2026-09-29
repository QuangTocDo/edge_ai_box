from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from ..config import PROJECT_ROOT


router = APIRouter(prefix="/api/objects", tags=["objects"])

DB_PATH = PROJECT_ROOT / "var" / "objects.db"
CROP_DIR = PROJECT_ROOT / "var" / "objects"


def get_db_connection() -> Optional[sqlite3.Connection]:
    if not DB_PATH.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        return None


@router.get("/stats")
def get_object_stats(date: Optional[str] = Query(None)) -> Dict[str, Any]:
    conn = get_db_connection()
    if conn is None:
        return {
            "total_objects": 0,
            "types": [],
            "colors": [],
            "dates": [],
        }

    # Normalize if called directly outside FastAPI
    if not isinstance(date, str):
        date = None

    try:
        cur = conn.cursor()

        # Dates list
        date_rows = cur.execute(
            "SELECT date, COUNT(*) as cnt FROM objects WHERE low_quality = 0 GROUP BY date ORDER BY date DESC"
        ).fetchall()
        dates = [{"date": r["date"], "count": r["cnt"]} for r in date_rows]

        # Conditions
        conds = ["low_quality = 0"]
        params: List[Any] = []
        if date:
            conds.append("date = ?")
            params.append(date)
        where_clause = "WHERE " + " AND ".join(conds)

        # Total
        total_row = cur.execute(
            f"SELECT COUNT(*) as cnt FROM objects {where_clause}", params
        ).fetchone()
        total_objects = total_row["cnt"] if total_row else 0

        # Types breakdown
        type_rows = cur.execute(
            f"SELECT vehicle_type, COUNT(*) as cnt FROM objects {where_clause} GROUP BY vehicle_type ORDER BY cnt DESC",
            params,
        ).fetchall()
        types = [{"type": r["vehicle_type"], "count": r["cnt"]} for r in type_rows]

        # Colors breakdown
        color_rows = cur.execute(
            f"SELECT color, COUNT(*) as cnt FROM objects {where_clause} GROUP BY color ORDER BY cnt DESC",
            params,
        ).fetchall()
        colors = [{"color": r["color"], "count": r["cnt"]} for r in color_rows]

        return {
            "total_objects": total_objects,
            "types": types,
            "colors": colors,
            "dates": dates,
        }
    finally:
        conn.close()


@router.get("")
def list_objects(
    date: Optional[str] = Query(None),
    vehicle_type: Optional[str] = Query(None),
    color: Optional[str] = Query(None),
    camera_id: Optional[str] = Query(None),
    limit: int = Query(60, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    conn = get_db_connection()
    if conn is None:
        return {"total": 0, "items": []}

    # Normalize defaults if called directly outside FastAPI
    if not isinstance(date, str):
        date = None
    if not isinstance(vehicle_type, str):
        vehicle_type = None
    if not isinstance(color, str):
        color = None
    if not isinstance(camera_id, str):
        camera_id = None
    if not isinstance(limit, int):
        limit = 60
    if not isinstance(offset, int):
        offset = 0

    try:
        cur = conn.cursor()
        conds = ["low_quality = 0"]
        params: List[Any] = []

        if date:
            conds.append("date = ?")
            params.append(date)
        if vehicle_type:
            conds.append("vehicle_type = ?")
            params.append(vehicle_type)
        if color:
            conds.append("color = ?")
            params.append(color)
        if camera_id:
            conds.append("camera_id = ?")
            params.append(camera_id)

        where_clause = "WHERE " + " AND ".join(conds)

        # Count total matches
        total_row = cur.execute(
            f"SELECT COUNT(*) as cnt FROM objects {where_clause}", params
        ).fetchone()
        total = total_row["cnt"] if total_row else 0

        # Check existing columns
        cols = [
            r["name"]
            for r in cur.execute("PRAGMA table_info(objects)").fetchall()
        ]
        sec_cols = (
            "secondary_color, secondary_conf, "
            if "secondary_color" in cols
            else ""
        )

        query = f"""
            SELECT track_id, camera_id, date, vehicle_type, color, color_conf,
                   {sec_cols}best_conf, best_bbox, crop_path, first_seen, last_seen, frames
            FROM objects {where_clause}
            ORDER BY first_seen DESC
            LIMIT ? OFFSET ?
        """
        rows = cur.execute(query, (*params, limit, offset)).fetchall()

        items = []
        for r in rows:
            d = dict(r)
            raw_bbox = d.get("best_bbox")
            bbox_list = None
            if raw_bbox:
                try:
                    bbox_list = [float(x.strip()) for x in raw_bbox.split(",")]
                except Exception:
                    pass
            crop_path = d.get("crop_path") or ""
            items.append(
                {
                    "track_id": d["track_id"],
                    "camera_id": d["camera_id"],
                    "date": d["date"],
                    "vehicle_type": d["vehicle_type"],
                    "color": d["color"],
                    "color_conf": round(float(d.get("color_conf") or 0.0), 2),
                    "secondary_color": d.get("secondary_color"),
                    "secondary_conf": round(
                        float(d.get("secondary_conf") or 0.0), 2
                    )
                    if d.get("secondary_conf")
                    else None,
                    "best_conf": round(float(d.get("best_conf") or 0.0), 2),
                    "best_bbox": bbox_list,
                    "crop_path": crop_path,
                    "crop_url": f"/api/objects/crop?path={crop_path}"
                    if crop_path
                    else None,
                    "first_seen": round(float(d.get("first_seen") or 0.0), 2),
                    "last_seen": round(float(d.get("last_seen") or 0.0), 2),
                    "frames": d.get("frames", 0),
                }
            )

        return {"total": total, "items": items}
    finally:
        conn.close()


@router.get("/crop")
def get_object_crop(path: str = Query(...)):
    """Safely serve object crop images from var/objects."""
    clean_path = path.strip().lstrip("/")
    target = (PROJECT_ROOT / clean_path).resolve()
    base = (PROJECT_ROOT / "var").resolve()

    if not str(target).startswith(str(base)) or not target.is_file():
        raise HTTPException(status_code=404, detail="Crop image not found")

    return FileResponse(target, media_type="image/jpeg", filename=target.name)


@router.delete("/{track_id}")
def delete_object(
    track_id: int,
    date: Optional[str] = Query(None),
    camera: Optional[str] = Query(None),
):
    if not DB_PATH.is_file():
        raise HTTPException(status_code=404, detail="Database not found")

    try:
        conn = sqlite3.connect(DB_PATH, timeout=5.0)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        conds = ["track_id = ?"]
        params: List[Any] = [track_id]
        if date:
            conds.append("date = ?")
            params.append(date)
        if camera:
            conds.append("camera_id = ?")
            params.append(camera)

        where = " AND ".join(conds)
        rows = cur.execute(
            f"SELECT crop_path FROM objects WHERE {where}", params
        ).fetchall()
        for r in rows:
            cp = r["crop_path"]
            if cp:
                p = PROJECT_ROOT / cp
                if p.is_file():
                    try:
                        p.unlink()
                    except Exception:
                        pass

        cur.execute(f"DELETE FROM objects WHERE {where}", params)
        conn.commit()
        conn.close()
        return {"status": "ok", "deleted": track_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

import {
  AlertCircle,
  Calendar,
  Camera,
  CarFront,
  Clock,
  Filter,
  Layers,
  Palette,
  RefreshCw,
  Search,
  Trash2,
  X,
  ZoomIn,
} from "lucide-react";
import { useEffect, useState } from "react";
import { EmptyState, MetricCard, PageLoader } from "../components/UI";
import { api, cropImageUrl } from "../services/api";
import type { DetectedVehicle, VehicleStats } from "../types";

const COLOR_MAP: Record<string, { label: string; hex: string; textDark?: boolean }> = {
  bac: { label: "Bạc", hex: "#94a3b8" },
  trang: { label: "Trắng", hex: "#f8fafc", textDark: true },
  den: { label: "Đen", hex: "#0f172a" },
  do: { label: "Đỏ", hex: "#ef4444" },
  vang: { label: "Vàng", hex: "#eab308", textDark: true },
  cam: { label: "Cam", hex: "#f97316" },
  "xanh duong": { label: "Xanh dương", hex: "#3b82f6" },
  "xanh la": { label: "Xanh lá", hex: "#22c55e" },
  xam: { label: "Xám", hex: "#64748b" },
  nau: { label: "Nâu", hex: "#78350f" },
};

function getColorInfo(colorKey: string) {
  const norm = colorKey.trim().toLowerCase();
  return COLOR_MAP[norm] || { label: colorKey, hex: "#6366f1" };
}

export function ObjectsPage() {
  const [stats, setStats] = useState<VehicleStats | null>(null);
  const [vehicles, setVehicles] = useState<DetectedVehicle[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [selectedType, setSelectedType] = useState<string>("");
  const [selectedColor, setSelectedColor] = useState<string>("");
  const [searchCam, setSearchCam] = useState<string>("");
  const [page, setPage] = useState(0);
  const limit = 40;

  // Modal inspection
  const [inspectVehicle, setInspectVehicle] = useState<DetectedVehicle | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const loadStats = async () => {
    try {
      const s = await api.vehicleStats(selectedDate || undefined);
      setStats(s);
    } catch (err: any) {
      console.warn("Failed to load vehicle stats:", err);
    }
  };

  const loadVehicles = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.vehicles({
        date: selectedDate || undefined,
        vehicle_type: selectedType || undefined,
        color: selectedColor || undefined,
        camera_id: searchCam.trim() || undefined,
        limit,
        offset: page * limit,
      });
      setVehicles(res.items);
      setTotal(res.total);
    } catch (err: any) {
      setError(err.message || "Failed to load vehicles");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStats();
  }, [selectedDate]);

  useEffect(() => {
    loadVehicles();
  }, [selectedDate, selectedType, selectedColor, searchCam, page]);

  const handleDelete = async (v: DetectedVehicle) => {
    if (!window.confirm(`Delete tracked vehicle #${v.track_id} (${v.vehicle_type} - ${v.color})?`)) {
      return;
    }
    setDeletingId(v.track_id);
    try {
      await api.deleteVehicle(v.track_id, v.date, v.camera_id);
      if (inspectVehicle?.track_id === v.track_id) {
        setInspectVehicle(null);
      }
      await loadVehicles();
      await loadStats();
    } catch (err: any) {
      alert("Delete failed: " + (err.message || String(err)));
    } finally {
      setDeletingId(null);
    }
  };

  const activeFilterCount = [selectedDate, selectedType, selectedColor, searchCam].filter(Boolean).length;
  const totalPages = Math.ceil(total / limit);

  return (
    <div className="page-stack">
      {/* Page Heading */}
      <div className="page-heading">
        <div>
          <span className="eyebrow">
            <CarFront size={14} /> Edge Telemetry
          </span>
          <h1>Vehicle & Color Explorer</h1>
          <p>
            Tracked vehicle database, automated neural color recognition, and high-resolution bounding box crops.
          </p>
        </div>
        <button
          className="button button-secondary"
          onClick={() => {
            loadStats();
            loadVehicles();
          }}
          title="Refresh database"
        >
          <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* KPI Cards */}
      <section className="metric-grid">
        <MetricCard
          label="Tracked Vehicles"
          value={stats ? stats.total_objects.toLocaleString() : total.toLocaleString()}
          icon={CarFront}
          tone="green"
          detail={`${stats?.dates.length || 0} recording dates`}
        />
        <MetricCard
          label="Vehicle Types"
          value={stats?.types.length || 0}
          icon={Layers}
          tone="gray"
          detail="Classes categorized"
        />
        <MetricCard
          label="Recognized Colors"
          value={stats?.colors.length || 0}
          icon={Palette}
          tone="amber"
          detail="Distinct color tags"
        />
        <MetricCard
          label="Filtered Scope"
          value={total.toLocaleString()}
          icon={Filter}
          tone="red"
          detail={activeFilterCount > 0 ? `${activeFilterCount} active filters` : "Showing all records"}
        />
      </section>

      {/* Interactive Filter & Breakdown Panel */}
      <section className="panel">
        <div className="panel-heading">
          <div>
            <span>Telemetry Search & Classification</span>
            <h2>Filter Vehicles & Colors</h2>
          </div>
          <b className="count-chip">{total} vehicles</b>
        </div>

        <div className="explorer-filter-body">
          {/* Vehicle Types Row */}
          <div className="filter-row">
            <span className="filter-row-title">VEHICLE TYPE:</span>
            <div className="filter-pill-group">
              <button
                className={`filter-pill ${!selectedType ? "active" : ""}`}
                onClick={() => {
                  setSelectedType("");
                  setPage(0);
                }}
              >
                All Types
              </button>
              {(stats?.types || []).map((t) => (
                <button
                  key={t.type}
                  className={`filter-pill ${selectedType === t.type ? "active" : ""}`}
                  onClick={() => {
                    setSelectedType(selectedType === t.type ? "" : t.type);
                    setPage(0);
                  }}
                >
                  <span>{t.type.toUpperCase()}</span>
                  <b className="pill-badge">{t.count}</b>
                </button>
              ))}
            </div>
          </div>

          {/* Color Breakdown Row */}
          <div className="filter-row">
            <span className="filter-row-title">COLOR PALETTE:</span>
            <div className="filter-pill-group">
              <button
                className={`filter-pill ${!selectedColor ? "active" : ""}`}
                onClick={() => {
                  setSelectedColor("");
                  setPage(0);
                }}
              >
                All Colors
              </button>
              {(stats?.colors || []).map((c) => {
                const info = getColorInfo(c.color);
                const isSelected = selectedColor === c.color;
                return (
                  <button
                    key={c.color}
                    className={`filter-pill color-pill ${isSelected ? "active" : ""}`}
                    onClick={() => {
                      setSelectedColor(isSelected ? "" : c.color);
                      setPage(0);
                    }}
                  >
                    <span
                      className="swatch-dot"
                      style={{
                        backgroundColor: info.hex,
                        border: c.color === "trang" ? "1px solid #cbd5e1" : "none",
                      }}
                    />
                    <span>{info.label}</span>
                    <b className="pill-badge">{c.count}</b>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Secondary Controls Bar */}
          <div className="filter-controls-bar">
            <div className="control-item">
              <Calendar size={15} />
              <select
                value={selectedDate}
                onChange={(e) => {
                  setSelectedDate(e.target.value);
                  setPage(0);
                }}
              >
                <option value="">All Recording Dates</option>
                {(stats?.dates || []).map((d) => (
                  <option key={d.date} value={d.date}>
                    {d.date} ({d.count} vehicles)
                  </option>
                ))}
              </select>
            </div>

            <div className="control-item">
              <Search size={15} />
              <input
                type="text"
                placeholder="Search Camera ID..."
                value={searchCam}
                onChange={(e) => {
                  setSearchCam(e.target.value);
                  setPage(0);
                }}
              />
            </div>

            {activeFilterCount > 0 && (
              <button
                className="button button-secondary btn-reset-filters"
                onClick={() => {
                  setSelectedDate("");
                  setSelectedType("");
                  setSelectedColor("");
                  setSearchCam("");
                  setPage(0);
                }}
              >
                <X size={14} />
                Clear Filters
              </button>
            )}

            <div className="filter-summary-text">
              Showing <strong>{vehicles.length}</strong> of <strong>{total}</strong> vehicles
            </div>
          </div>
        </div>
      </section>

      {/* Grid Content */}
      {loading ? (
        <PageLoader />
      ) : error ? (
        <div className="error-banner">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      ) : vehicles.length === 0 ? (
        <EmptyState
          title="No vehicles found"
          body="Try selecting another date, vehicle category, or clearing your active filters."
          action={
            activeFilterCount > 0 ? (
              <button
                className="button button-primary"
                onClick={() => {
                  setSelectedDate("");
                  setSelectedType("");
                  setSelectedColor("");
                  setSearchCam("");
                  setPage(0);
                }}
              >
                Clear Filters
              </button>
            ) : undefined
          }
        />
      ) : (
        <section className="vehicle-gallery-grid">
          {vehicles.map((v) => {
            const colorInfo = getColorInfo(v.color);
            const secColorInfo = v.secondary_color ? getColorInfo(v.secondary_color) : null;
            const imgUrl = cropImageUrl(v.crop_path);

            return (
              <article
                key={`${v.camera_id}-${v.date}-${v.track_id}`}
                className="vehicle-gallery-card"
                onClick={() => setInspectVehicle(v)}
              >
                <div className="card-thumb-zone">
                  {v.crop_path ? (
                    <img
                      src={imgUrl}
                      alt={`Track #${v.track_id}`}
                      className="crop-thumb-img"
                      loading="lazy"
                      onError={(e) => {
                        (e.target as HTMLElement).style.display = "none";
                      }}
                    />
                  ) : (
                    <div className="no-crop-fallback">
                      <CarFront size={28} opacity={0.4} />
                      <span>No Crop</span>
                    </div>
                  )}

                  <div className="badge-track-id">#{v.track_id}</div>
                  <div className="badge-conf">{(v.best_conf * 100).toFixed(0)}%</div>

                  <div className="card-zoom-hover">
                    <ZoomIn size={16} />
                  </div>
                </div>

                <div className="card-info-zone">
                  <div className="card-header-line">
                    <span className="tag-vehicle-type">{v.vehicle_type.toUpperCase()}</span>
                    <div className="tag-vehicle-color">
                      <span
                        className="color-dot-indicator"
                        style={{
                          backgroundColor: colorInfo.hex,
                          border: v.color === "trang" ? "1px solid #cbd5e1" : "none",
                        }}
                      />
                      <span>{colorInfo.label}</span>
                      <small>({Math.round(v.color_conf * 100)}%)</small>
                    </div>
                  </div>

                  {secColorInfo && (
                    <div className="card-sec-color-line">
                      <span>Secondary:</span>
                      <span className="dot-mini" style={{ backgroundColor: secColorInfo.hex }} />
                      <span>{secColorInfo.label}</span>
                    </div>
                  )}

                  <div className="card-meta-line">
                    <span title="Camera ID">
                      <Camera size={12} /> {v.camera_id}
                    </span>
                    <span title="Appearance time span">
                      <Clock size={12} /> {v.first_seen.toFixed(1)}s - {v.last_seen.toFixed(1)}s
                    </span>
                    <span title="Tracked frames count">
                      <Layers size={12} /> {v.frames}f
                    </span>
                  </div>
                </div>
              </article>
            );
          })}
        </section>
      )}

      {/* Pagination Bar */}
      {totalPages > 1 && (
        <div className="gallery-pagination">
          <button
            className="button button-secondary"
            disabled={page === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
          >
            Previous
          </button>
          <span className="page-indicator">
            Page <strong>{page + 1}</strong> of <strong>{totalPages}</strong>
          </span>
          <button
            className="button button-secondary"
            disabled={page >= totalPages - 1}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </button>
        </div>
      )}

      {/* Detail Inspection Modal */}
      {inspectVehicle && (
        <div className="modal-backdrop" onClick={() => setInspectVehicle(null)}>
          <div
            className="modal-box modal-vehicle-inspect"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-top">
              <div className="modal-top-title">
                <CarFront size={20} className="modal-title-icon" />
                <h3>Tracked Vehicle Details #{inspectVehicle.track_id}</h3>
              </div>
              <button
                className="icon-button"
                onClick={() => setInspectVehicle(null)}
                title="Close"
              >
                <X size={16} />
              </button>
            </div>

            <div className="modal-split-layout">
              {/* Left Column: Crop Image */}
              <div className="modal-image-column">
                <div className="modal-image-frame">
                  {inspectVehicle.crop_path ? (
                    <img
                      src={cropImageUrl(inspectVehicle.crop_path)}
                      alt={`Track #${inspectVehicle.track_id}`}
                      className="modal-full-crop"
                    />
                  ) : (
                    <div className="modal-empty-crop">No crop image available</div>
                  )}
                </div>
                <div className="modal-caption-text">
                  Optimal detection crop (AI confidence: {(inspectVehicle.best_conf * 100).toFixed(1)}%)
                </div>
              </div>

              {/* Right Column: Properties */}
              <div className="modal-properties-column">
                <div className="prop-section">
                  <h4>Classification & Color</h4>
                  <div className="prop-row">
                    <span className="prop-label">Vehicle Type:</span>
                    <span className="tag-vehicle-type large">{inspectVehicle.vehicle_type.toUpperCase()}</span>
                  </div>
                  <div className="prop-row">
                    <span className="prop-label">Primary Color:</span>
                    <div className="prop-color-val">
                      <span
                        className="color-dot-indicator"
                        style={{
                          backgroundColor: getColorInfo(inspectVehicle.color).hex,
                          border: inspectVehicle.color === "trang" ? "1px solid #cbd5e1" : "none",
                        }}
                      />
                      <strong>{getColorInfo(inspectVehicle.color).label}</strong>
                      <small>({(inspectVehicle.color_conf * 100).toFixed(0)}% conf)</small>
                    </div>
                  </div>
                  {inspectVehicle.secondary_color && (
                    <div className="prop-row">
                      <span className="prop-label">Secondary Color:</span>
                      <div className="prop-color-val">
                        <span
                          className="color-dot-indicator"
                          style={{ backgroundColor: getColorInfo(inspectVehicle.secondary_color).hex }}
                        />
                        <span>{getColorInfo(inspectVehicle.secondary_color).label}</span>
                        {inspectVehicle.secondary_conf && (
                          <small>({(inspectVehicle.secondary_conf * 100).toFixed(0)}%)</small>
                        )}
                      </div>
                    </div>
                  )}
                </div>

                <div className="prop-section">
                  <h4>Tracking Telemetry</h4>
                  <div className="prop-row">
                    <span className="prop-label">Track ID:</span>
                    <span className="mono">#{inspectVehicle.track_id}</span>
                  </div>
                  <div className="prop-row">
                    <span className="prop-label">Camera Source:</span>
                    <span className="mono">{inspectVehicle.camera_id}</span>
                  </div>
                  <div className="prop-row">
                    <span className="prop-label">Recording Date:</span>
                    <span className="mono">{inspectVehicle.date}</span>
                  </div>
                  <div className="prop-row">
                    <span className="prop-label">Time Window:</span>
                    <span className="mono">
                      {inspectVehicle.first_seen.toFixed(2)}s → {inspectVehicle.last_seen.toFixed(2)}s
                    </span>
                  </div>
                  <div className="prop-row">
                    <span className="prop-label">Frame Count:</span>
                    <span className="mono">{inspectVehicle.frames} frames</span>
                  </div>
                  {inspectVehicle.best_bbox && (
                    <div className="prop-row">
                      <span className="prop-label">Bounding Box:</span>
                      <span className="mono" style={{ fontSize: "11px" }}>
                        [{inspectVehicle.best_bbox.map((n) => Math.round(n)).join(", ")}]
                      </span>
                    </div>
                  )}
                </div>

                <div className="modal-footer-action">
                  <button
                    className="button button-secondary danger"
                    disabled={deletingId === inspectVehicle.track_id}
                    onClick={() => handleDelete(inspectVehicle)}
                  >
                    <Trash2 size={15} />
                    <span>{deletingId === inspectVehicle.track_id ? "Deleting..." : "Delete Vehicle Record"}</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

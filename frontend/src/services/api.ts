import type { Analytics, Camera, CameraEvent, DetectedVehicle, Overview, ProcessingJob, VehicleStats, ViolationEvent } from "../types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

let authToken: string | null = null;
export function setAuthToken(token: string | null) {
  authToken = token;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers);
  if (authToken) headers.set("Authorization", `Bearer ${authToken}`);
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(payload.detail ?? "Request failed");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

interface LoginResult { token: string; username: string; name: string; role: string }

export const api = {
  login: (username: string, password: string) =>
    request<LoginResult>("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request<{ status: string }>("/api/auth/logout", { method: "POST" }),
  overview: () => request<Overview>("/api/overview"),
  analytics: () => request<Analytics>("/api/analytics"),
  jobs: () => request<ProcessingJob[]>("/api/jobs"),
  job: (id: string) => request<ProcessingJob>(`/api/jobs/${id}`),
  events: (jobId: string) => request<ViolationEvent[]>(`/api/jobs/${jobId}/events`),
  event: (eventId: number) => request<ViolationEvent>(`/api/events/${eventId}`),
  upload: async (file: File) => {
    const form = new FormData();
    form.append("video", file);
    return request<ProcessingJob>("/api/jobs/upload", {
      method: "POST",
      body: form,
    });
  },
  process: (id: string) => request<ProcessingJob>(`/api/jobs/${id}/process`, { method: "POST" }),
  cancelJob: (id: string) => request<ProcessingJob>(`/api/jobs/${id}/cancel`, { method: "POST" }),
  deleteJob: (id: string) => request<void>(`/api/jobs/${id}`, { method: "DELETE" }),
  cameras: () => request<Camera[]>("/api/cameras"),
  camera: (id: string) => request<Camera>(`/api/cameras/${id}`),
  cameraConfig: (id: string) => request<CameraConfig>(`/api/cameras/${id}/config`),
  createCamera: (body: { name: string; source_type: string; source_uri: string }) =>
    request<Camera>("/api/cameras", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  deleteCamera: (id: string) => request<void>(`/api/cameras/${id}`, { method: "DELETE" }),
  startCamera: (id: string) => request<Camera>(`/api/cameras/${id}/start`, { method: "POST" }),
  stopCamera: (id: string) => request<Camera>(`/api/cameras/${id}/stop`, { method: "POST" }),
  reconnectCamera: (id: string) =>
    request<Camera>(`/api/cameras/${id}/reconnect`, { method: "POST" }),
  cameraEvents: (id: string) => request<CameraEvent[]>(`/api/cameras/${id}/events`),
  homographyPreview: (id: string, rect: CalibrationRectangle) =>
    request<HomographyPreview>(`/api/cameras/${id}/homography_preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(rect),
    }),
  calibrate: (id: string, payload: CalibrationRequest) =>
    request<Camera>(`/api/cameras/${id}/calibrate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  updateRawConfig: (id: string, yaml_content: string) =>
    request<{ status: string; message: string }>(`/api/cameras/${id}/config/raw`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ yaml_content }),
    }),
  deleteCameraPolygon: (id: string, polyId: string) =>
    request<{ status: string; deleted: string }>(`/api/cameras/${id}/config/polygons/${polyId}`, {
      method: "DELETE",
    }),
  deleteCameraLine: (id: string, lineId: string) =>
    request<{ status: string; deleted: string }>(`/api/cameras/${id}/config/lines/${lineId}`, {
      method: "DELETE",
    }),
  saveCameraPolygon: (id: string, poly: any) =>
    request<{ status: string; message: string; polygon: any }>(`/api/cameras/${id}/config/polygons`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(poly),
    }),
  saveCameraLine: (id: string, line: any) =>
    request<{ status: string; message: string; line: any }>(`/api/cameras/${id}/config/lines`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(line),
    }),
  saveCameraSignal: (id: string, sig: any) =>
    request<{ status: string; message: string; signal: any }>(`/api/cameras/${id}/config/signals`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(sig),
    }),
  deleteCameraSignal: (id: string, sigId: string) =>
    request<{ status: string; deleted: string }>(`/api/cameras/${id}/config/signals/${sigId}`, {
      method: "DELETE",
    }),
  vehicleStats: (date?: string) =>
    request<VehicleStats>(`/api/objects/stats${date ? `?date=${encodeURIComponent(date)}` : ""}`),
  vehicles: (params?: {
    date?: string;
    vehicle_type?: string;
    color?: string;
    camera_id?: string;
    limit?: number;
    offset?: number;
  }) => {
    const q = new URLSearchParams();
    if (params?.date) q.set("date", params.date);
    if (params?.vehicle_type) q.set("vehicle_type", params.vehicle_type);
    if (params?.color) q.set("color", params.color);
    if (params?.camera_id) q.set("camera_id", params.camera_id);
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.offset) q.set("offset", String(params.offset));
    const qs = q.toString();
    return request<{ total: number; items: DetectedVehicle[] }>(`/api/objects${qs ? `?${qs}` : ""}`);
  },
  deleteVehicle: (trackId: number, date?: string, camera?: string) => {
    const q = new URLSearchParams();
    if (date) q.set("date", date);
    if (camera) q.set("camera", camera);
    const qs = q.toString();
    return request<{ status: string; deleted: number }>(`/api/objects/${trackId}${qs ? `?${qs}` : ""}`, {
      method: "DELETE",
    });
  },
};

export interface CameraConfig {
  camera_id: string;
  config_path: string;
  raw_yaml?: string;
  polygons: Array<{
    id: string;
    kind?: string;
    polygon?: number[][];
    rules?: Record<string, any>;
    homography?: { src: number[][]; dst: number[][]; measured_at?: string };
    road_dir?: number[];
    dwell_s?: number;
    min_persons?: number;
    banned_classes?: number[];
    lines?: Array<{ id: string; p1: number[]; p2: number[]; allowed_sign?: number }>;
    [key: string]: any;
  }>;
  lines: Array<{
    id: string;
    p1: number[];
    p2: number[];
    allowed_sign?: number;
    signal_id?: string;
    role?: string;
    [key: string]: any;
  }>;
  signals: Array<{
    id: string;
    roi?: number[];
    box?: number[];
    default?: string;
    [key: string]: any;
  }>;
  no_entry_road?: Record<string, any>;
  no_gathering?: Record<string, any>;
  no_parking?: Record<string, any>;
  no_uturn?: Record<string, any>;
  wrong_way?: Record<string, any>;
  uturn_pairs?: Array<{ first: string; second: string; medial?: string; [key: string]: any }>;
}

export interface CalibrationRectangle { image_points: number[][]; width_m: number; length_m: number; road_dir?: number[]; road_dir_points?: number[][] }
export interface CalibrationLane { id: string; polygon: number[][]; arrow: number[][]; speed_limit_kmh: number }
export interface RuleZoneConfig {
  id: string;
  rule_type: string;
  polygon?: number[][];
  line?: number[][];
  box?: number[];
  arrow?: number[][];
  speed_limit_kmh?: number;
  dwell_s?: number;
  min_persons?: number;
  enabled?: boolean;
}
export interface CalibrationRequest {
  rectangle?: CalibrationRectangle;
  stop_line?: number[][];
  lanes?: CalibrationLane[];
  light_box?: number[] | null;
  rule_zones?: RuleZoneConfig[];
  deleted_polygon_ids?: string[];
  deleted_line_ids?: string[];
  deleted_signal_ids?: string[];
}
export interface HomographyPreview { condition_number: number; mean_error_m: number; ok: boolean; message: string }

export function cameraStreamUrl(id: string): string {
  return `${API_BASE}/api/cameras/${id}/stream`;
}

export function cameraSnapshotUrl(id: string): string {
  return `${API_BASE}/api/cameras/${id}/snapshot?t=${Date.now()}`;
}

export function cameraWebsocketUrl(cameraId: string): string {
  const configured = import.meta.env.VITE_WS_BASE;
  if (configured) return `${configured}/ws/cameras/${cameraId}`;
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const host = window.location.port === "5173" ? `${window.location.hostname}:8000` : window.location.host;
  return `${protocol}://${host}/ws/cameras/${cameraId}`;
}

export function mediaUrl(path: string | null): string {
  return path ? `${API_BASE}${path}` : "";
}

export function cropImageUrl(path: string | null): string {
  if (!path) return "";
  return `${API_BASE}/api/objects/crop?path=${encodeURIComponent(path)}`;
}

export function jobVideoUrl(id: string): string {
  return `${API_BASE}/api/jobs/${id}/video`;
}

export function websocketUrl(jobId: string): string {
  const configured = import.meta.env.VITE_WS_BASE;
  if (configured) return `${configured}/ws/jobs/${jobId}`;
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const host = window.location.port === "5173" ? `${window.location.hostname}:8000` : window.location.host;
  return `${protocol}://${host}/ws/jobs/${jobId}`;
}

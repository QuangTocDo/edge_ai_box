import type { Analytics, Camera, CameraEvent, Overview, ProcessingJob, ViolationEvent } from "../types";

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
    return request<ProcessingJob>("/api/jobs/upload", { method: "POST", body: form });
  },
  process: (id: string) => request<ProcessingJob>(`/api/jobs/${id}/process`, { method: "POST" }),
  deleteJob: (id: string) => request<void>(`/api/jobs/${id}`, { method: "DELETE" }),

  cameras: () => request<Camera[]>("/api/cameras"),
  camera: (id: string) => request<Camera>(`/api/cameras/${id}`),
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
};

export interface CalibrationRectangle { image_points: number[][]; width_m: number; length_m: number }
export interface CalibrationLane { id: string; polygon: number[][]; arrow: number[][]; speed_limit_kmh: number }
export interface CalibrationRequest {
  rectangle: CalibrationRectangle;
  stop_line: number[][];
  lanes: CalibrationLane[];
  light_box: number[] | null;
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


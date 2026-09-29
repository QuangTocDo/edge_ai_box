export type JobStatus = "queued" | "processing" | "completed" | "failed";

export interface ProcessingJob {
  id: string;
  original_filename: string;
  source_type: string;
  status: JobStatus;
  progress_percent: number;
  current_frame: number;
  total_frames: number;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  event_count: number;
}

export interface ViolationEvent {
  id: number;
  job_id: string;
  type: string;
  track_id: number | string;
  frame: number;
  time_s: number;
  severity: "low" | "medium" | "high" | string;
  speed_kmh: number | null;
  world_x: number | null;
  world_y: number | null;
  lane_id: string | null;
  light_phase: string | null;
  screenshot_url: string | null;
  clip_url: string | null;
  measured: Record<string, unknown>;
  evidence: Record<string, unknown>;
}

export type CameraStatus =
  | "Offline"
  | "Connecting"
  | "Live"
  | "Reconnecting"
  | "Error";

export interface Camera {
  id: string;
  name: string;
  source_type: string;
  source_uri: string; // masked for RTSP
  calibrated: boolean;
  enabled: boolean;
  status: CameraStatus | string;
  last_error: string | null;
  created_at: string;
  fps: number | null;
  processed_frames: number | null;
  active_vehicles: number | null;
  event_count: number;
}

export interface CameraEvent {
  id: number;
  camera_id: string;
  type: string;
  track_id: number | string;
  frame: number;
  time_s: number;
  severity: "low" | "medium" | "high" | string;
  speed_kmh: number | null;
  world_x: number | null;
  world_y: number | null;
  lane_id: string | null;
  light_phase: string | null;
  screenshot_url: string | null;
  clip_url: string | null;
  measured: Record<string, unknown>;
  evidence: Record<string, unknown>;
  created_at: string;
}

export interface CameraStatusMessage {
  type: "status";
  camera_id: string;
  status: CameraStatus | string;
  last_error: string | null;
  fps: number;
  processed_frames: number;
  active_vehicles: number;
  ts: string;
}

export interface Analytics {
  total_violations: number;
  live_total: number;
  job_total: number;
  avg_speed_kmh: number | null;
  max_speed_kmh: number | null;
  by_type: Record<string, number>;
  by_severity: Record<string, number>;
  speed_histogram: { bucket: string; count: number }[];
  by_hour: { hour: string; count: number }[];
  daily: { date: string; count: number }[];
  top_sources: { name: string; count: number }[];
}

export interface Overview {
  total_jobs: number;
  completed_jobs: number;
  processing_jobs: number;
  failed_jobs: number;
  total_events: number;
  violations_by_type: Record<string, number>;
  severity_counts: Record<string, number>;
  recent_events: ViolationEvent[];
}

export interface DetectedVehicle {
  track_id: number;
  camera_id: string;
  date: string;
  vehicle_type: string;
  color: string;
  color_conf: number;
  secondary_color?: string | null;
  secondary_conf?: number | null;
  best_conf: number;
  best_bbox?: number[] | null;
  crop_path: string;
  crop_url?: string | null;
  first_seen: number;
  last_seen: number;
  frames: number;
}

export interface VehicleStats {
  total_objects: number;
  types: { type: string; count: number }[];
  colors: { color: string; count: number }[];
  dates: { date: string; count: number }[];
}

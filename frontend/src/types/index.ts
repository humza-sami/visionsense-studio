export type CameraSourceType = 'rtsp' | 'webcam' | 'usb';
export type CameraStatus = 'idle' | 'connecting' | 'live' | 'error' | 'stopped';
export type YoloTask = 'detect' | 'segment' | 'pose' | 'obb' | 'classify' | 'semantic';

export interface CameraSource {
  type: CameraSourceType;
  url?: string;
  device_index?: number;
}

export interface PipelineFeatures {
  boxes: boolean;
  masks: boolean;
  keypoints: boolean;
  labels: boolean;
  trails: boolean;
  obb: boolean;
  semantic: boolean;
}

export interface ApplicationConfig {
  type: string;
  enabled: boolean;
  config: Record<string, unknown>;
}

export interface PipelineConfig {
  model: string;
  task: YoloTask;
  open_vocab_prompt: string[];
  tracking: { enabled: boolean; tracker: string };
  thresholds: { confidence: number; iou: number };
  features: PipelineFeatures;
  applications: ApplicationConfig[];
  frame_skip: number;
}

export interface Camera {
  id: string;
  name: string;
  source: CameraSource;
  status: CameraStatus;
  pipeline: PipelineConfig;
  error_message?: string;
}

export interface Telemetry {
  cam_id: string;
  fps: number;
  inference_ms: number;
  counts: Record<string, number>;
  application_outputs: Record<string, unknown>;
  alerts: Array<{ type: string; ts: number; detail: string }>;
}

export interface Alert {
  id: string;
  cam_id: string;
  type: string;
  detail: string;
  ts: number;
}

export interface Device {
  index: number;
  name: string;
}

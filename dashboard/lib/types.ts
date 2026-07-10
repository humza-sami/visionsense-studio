/**
 * Core types for the FrameInsight cloud dashboard.
 *
 * The event vocabulary mirrors the edge runtime (frameinsight backend):
 * every edge box streams Events {ts, site, cam_id, rule, kind, severity, data}
 * plus heartbeats. The dashboard aggregates those into the shapes below.
 * Today the data is simulated (lib/data/*); the shapes are what the Supabase
 * queries will return in production.
 */

export type VerticalId =
  | "education"
  | "retail"
  | "manufacturing"
  | "restaurant"
  | "warehouse";

export type Severity = "alert" | "warning" | "info";

export interface Camera {
  id: string;
  name: string;
  /** pipeline group on the edge box (site.yaml `groups:`) */
  group: string;
  online: boolean;
  /** seconds since the last decoded frame (from heartbeat events) */
  lastFrameAgoS: number;
  /** RTSP link quality 0–100 (derived from read errors / reconnects) */
  signal: number;
  detectFps: number;
}

export interface EdgeHealth {
  serverOnline: boolean;
  lastPingAgoS: number;
  uptimeDays: number;
  gpu: string;
  gpuUtilPct: number;
  nvdecUtilPct: number;
  vramUsedGb: number;
  vramTotalGb: number;
  cpuUtilPct: number;
  uplinkMbps: number;
  diskUsedPct: number;
  runtimeVersion: string;
}

export interface Client {
  id: string;
  name: string;
  vertical: VerticalId;
  city: string;
  country: string;
  sinceMonthYear: string;
  plan: "starter" | "pro" | "enterprise";
  cameras: Camera[];
  edge: EdgeHealth;
  /** total rule events in the last 24 h */
  eventsToday: number;
}

export interface AlertItem {
  id: string;
  clientId: string;
  cameraId: string;
  rule: string;
  kind: string;
  severity: Severity;
  message: string;
  minutesAgo: number;
  acknowledged: boolean;
}

export type InsightCategory = "anomaly" | "optimization" | "trend" | "health";

export interface Insight {
  id: string;
  clientId: string;
  category: InsightCategory;
  impact: "high" | "medium" | "low";
  /** model confidence 0–1 (simulated for now) */
  confidence: number;
  title: string;
  body: string;
  suggestedAction: string;
  hoursAgo: number;
}

/** One point of an hourly series ("06", "07", … local time). */
export interface HourPoint {
  hour: string;
  [series: string]: string | number;
}

/** One point of a daily series ("Mon", …). */
export interface DayPoint {
  day: string;
  [series: string]: string | number;
}

export interface Kpi {
  label: string;
  value: string;
  /** e.g. "+12% vs yesterday" */
  delta?: string;
  deltaDirection?: "up" | "down" | "flat";
  /** whether "up" is good for this KPI (colors the delta) */
  upIsGood?: boolean;
  hint?: string;
}

export interface WeeklyReportRow {
  week: string;
  [metric: string]: string | number;
}

export interface MonthlyReport {
  clientId: string;
  month: string;
  headline: Kpi[];
  weekly: WeeklyReportRow[];
  weeklyColumns: { key: string; label: string }[];
  narrative: string;
}

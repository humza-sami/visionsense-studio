import type { AlertItem, Severity } from "../types";

/**
 * Simulated alert feed — the kinds match the edge runtime's rule kernels
 * (zone_intrusion, headcount/overcrowded, custom kernels) plus the runtime's
 * own health events (camera_stalled).
 */
export const ALERTS: AlertItem[] = [
  {
    id: "a1",
    clientId: "sunrise-textiles",
    cameraId: "line3",
    rule: "ppe_compliance",
    kind: "ppe_violation",
    severity: "alert",
    message: "Worker without helmet on Line 3 for 45 s",
    minutesAgo: 6,
    acknowledged: false,
  },
  {
    id: "a2",
    clientId: "swift-logistics",
    cameraId: "yard2",
    rule: "near_miss",
    kind: "forklift_pedestrian",
    severity: "alert",
    message: "Forklift–pedestrian proximity < 2 m in yard lane B",
    minutesAgo: 14,
    acknowledged: false,
  },
  {
    id: "a3",
    clientId: "metro-mart",
    cameraId: "till4",
    rule: "queue_watch",
    kind: "queue_exceeded",
    severity: "warning",
    message: "Checkout queue above 8 people for 5 min (till 4)",
    minutesAgo: 22,
    acknowledged: false,
  },
  {
    id: "a4",
    clientId: "greenfield-school",
    cameraId: "cooler",
    rule: "cooler_crowd_alert",
    kind: "cooler_crowded",
    severity: "warning",
    message: "6 kids around the water cooler (limit 4), sustained 10 s",
    minutesAgo: 41,
    acknowledged: true,
  },
  {
    id: "a5",
    clientId: "swift-logistics",
    cameraId: "dock4",
    rule: "_system",
    kind: "camera_stalled",
    severity: "alert",
    message: "No frames from dock4 for 31 min (RTSP reconnect failing)",
    minutesAgo: 31,
    acknowledged: false,
  },
  {
    id: "a6",
    clientId: "sunrise-textiles",
    cameraId: "gate2",
    rule: "restricted_zone",
    kind: "intrusion",
    severity: "alert",
    message: "Person in dye storage outside shift hours",
    minutesAgo: 58,
    acknowledged: true,
  },
  {
    id: "a7",
    clientId: "metro-mart",
    cameraId: "aisle3",
    rule: "_system",
    kind: "camera_stalled",
    severity: "warning",
    message: "aisle3 signal degraded — 3 reconnects in the last hour",
    minutesAgo: 75,
    acknowledged: false,
  },
  {
    id: "a8",
    clientId: "kabab-house",
    cameraId: "counter1",
    rule: "queue_watch",
    kind: "queue_exceeded",
    severity: "info",
    message: "Counter queue reached 7 during lunch peak",
    minutesAgo: 204,
    acknowledged: true,
  },
  {
    id: "a9",
    clientId: "greenfield-school",
    cameraId: "gate1",
    rule: "gate_counter",
    kind: "after_hours_entry",
    severity: "info",
    message: "2 entries after 16:00 (staff window)",
    minutesAgo: 55,
    acknowledged: true,
  },
  {
    id: "a10",
    clientId: "swift-logistics",
    cameraId: "dock7",
    rule: "dock_dwell",
    kind: "dwell_exceeded",
    severity: "warning",
    message: "TRK-1408 at Bay 7 for 82 min (SLA 60 min)",
    minutesAgo: 12,
    acknowledged: false,
  },
  {
    id: "a11",
    clientId: "style-hub",
    cameraId: "entry",
    rule: "footfall",
    kind: "anomaly",
    severity: "info",
    message: "Footfall 34% above same weekday average",
    minutesAgo: 128,
    acknowledged: true,
  },
  {
    id: "a12",
    clientId: "sunrise-textiles",
    cameraId: "hall2",
    rule: "headcount",
    kind: "overcrowded",
    severity: "warning",
    message: "Packing hall headcount 26 (limit 20)",
    minutesAgo: 96,
    acknowledged: true,
  },
];

export function alertsForClient(clientId: string): AlertItem[] {
  return ALERTS.filter((a) => a.clientId === clientId);
}

export function openAlertCount(clientId?: string): number {
  return ALERTS.filter(
    (a) => !a.acknowledged && (!clientId || a.clientId === clientId),
  ).length;
}

export const SEVERITY_ORDER: Severity[] = ["alert", "warning", "info"];

import { hashSeed, rng } from "../seed";
import { getClient } from "./clients";
import type { MonthlyReport, WeeklyReportRow } from "../types";

/**
 * Monthly client reports — the billable deliverable. Metric columns differ per
 * vertical; the layout is shared.
 */

const VERTICAL_COLUMNS: Record<
  string,
  { key: string; label: string; base: number; unit?: string }[]
> = {
  education: [
    { key: "entries", label: "Gate entries", base: 2400 },
    { key: "avgAttendance", label: "Avg attendance %", base: 93 },
    { key: "coolerVisits", label: "Cooler visits", base: 1450 },
    { key: "alerts", label: "Alerts", base: 6 },
  ],
  retail: [
    { key: "footfall", label: "Footfall", base: 9800 },
    { key: "peakQueue", label: "Peak queue", base: 11 },
    { key: "avgDwellS", label: "Avg zone dwell (s)", base: 96 },
    { key: "alerts", label: "Alerts", base: 9 },
  ],
  manufacturing: [
    { key: "compliance", label: "PPE compliance %", base: 94 },
    { key: "violations", label: "PPE violations", base: 41 },
    { key: "intrusions", label: "Zone intrusions", base: 12 },
    { key: "alerts", label: "Alerts", base: 18 },
  ],
  restaurant: [
    { key: "guests", label: "Guests", base: 3900 },
    { key: "turnoverMin", label: "Avg turnover (min)", base: 42 },
    { key: "peakQueue", label: "Peak queue", base: 9 },
    { key: "alerts", label: "Alerts", base: 4 },
  ],
  warehouse: [
    { key: "trucks", label: "Trucks processed", base: 210 },
    { key: "avgDwellMin", label: "Avg dock dwell (min)", base: 44 },
    { key: "slaBreaches", label: "SLA breaches", base: 7 },
    { key: "nearMisses", label: "Near-misses", base: 5 },
  ],
};

const NARRATIVES: Record<string, string> = {
  education:
    "Attendance held steady month-over-month. Cooler congestion after PE periods remains the main operational finding; entry counting matched the manual register within 2%.",
  retail:
    "Footfall grew week over week with Friday evenings the strongest window. Checkout queueing improved after week 2's staffing change; the entrance promo zone needs attention.",
  manufacturing:
    "PPE compliance improved 3 points after the shift-change checks introduced in week 2. Loading dock remains the most-violated restricted zone.",
  restaurant:
    "Guest volume peaked in week 4 (Eid weekend). Terrace utilisation is the clearest upside — it turns tables twice as fast as the family hall.",
  warehouse:
    "Truck throughput rose 8% while average dock dwell fell 6 minutes. Bay 7 drove two-thirds of SLA breaches and is flagged for re-routing.",
};

export function monthlyReport(clientId: string): MonthlyReport | undefined {
  const client = getClient(clientId);
  if (!client) return undefined;
  const columns = VERTICAL_COLUMNS[client.vertical];
  const r = rng(hashSeed(clientId + ":report"));
  const weekly: WeeklyReportRow[] = Array.from({ length: 4 }, (_, w) => {
    const row: WeeklyReportRow = { week: `Week ${w + 1} (Jun ${1 + w * 7}–${7 + w * 7})` };
    for (const col of columns) {
      const drift = 1 + (w - 1.5) * 0.03 + (r() - 0.5) * 0.1;
      row[col.key] =
        col.base >= 80 && col.base <= 100
          ? Math.min(100, Math.round(col.base * (1 + (r() - 0.4) * 0.05)))
          : Math.round(col.base * drift);
    }
    return row;
  });

  const totals = columns.map((col) => {
    const values = weekly.map((w) => Number(w[col.key]));
    const isPct = col.base >= 80 && col.base <= 100;
    const value = isPct
      ? Math.round(values.reduce((a, b) => a + b, 0) / values.length)
      : values.reduce((a, b) => a + b, 0);
    const first = values[0];
    const last = values[values.length - 1];
    const dir = last > first ? "up" : last < first ? "down" : "flat";
    return {
      label: col.label,
      value: isPct ? `${value}%` : value.toLocaleString("en-US"),
      delta: `${dir === "up" ? "+" : dir === "down" ? "−" : ""}${Math.abs(
        Math.round(((last - first) / Math.max(1, first)) * 100),
      )}% over the month`,
      deltaDirection: dir as "up" | "down" | "flat",
      upIsGood: !/violation|intrusion|breach|near|queue|alert/i.test(col.label),
    };
  });

  return {
    clientId,
    month: "June 2026",
    headline: totals,
    weekly,
    weeklyColumns: [{ key: "week", label: "Week" }, ...columns],
    narrative: NARRATIVES[client.vertical],
  };
}

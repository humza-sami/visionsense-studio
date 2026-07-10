import type { Insight } from "../types";

/**
 * Simulated AI insights. In production an LLM pipeline will read each
 * client's aggregates + alert history and produce these; the object shape is
 * already final so the UI won't change when the real pipeline lands.
 */
export const INSIGHTS: Insight[] = [
  {
    id: "i1",
    clientId: "metro-mart",
    category: "optimization",
    impact: "high",
    confidence: 0.87,
    title: "Open a second till between 17:00–20:00",
    body:
      "Queue length at till 4 exceeded 8 people on 11 of the last 14 evenings, while tills 5–6 sat idle before 17:00. Footfall peaks at 18:00 with 220 entries/hour.",
    suggestedAction:
      "Shift one floor staffer to checkout duty from 17:00; expected queue-time cut ≈ 40%.",
    hoursAgo: 3,
  },
  {
    id: "i2",
    clientId: "metro-mart",
    category: "trend",
    impact: "medium",
    confidence: 0.78,
    title: "Entrance promo zone is under-performing",
    body:
      "Average dwell in the entrance promo zone fell from 41 s to 25 s after the display change on 2 Jul, while grocery dwell held steady. Visitors are walking past the new layout.",
    suggestedAction: "Revert or reposition the display; re-measure for one week.",
    hoursAgo: 26,
  },
  {
    id: "i3",
    clientId: "sunrise-textiles",
    category: "anomaly",
    impact: "high",
    confidence: 0.91,
    title: "PPE violations cluster at shift change",
    body:
      "63% of this week's helmet violations occurred 13:50–14:20, exactly around the B-shift handover on Lines 2–4. Compliance is 97% mid-shift.",
    suggestedAction:
      "Station the supervisor at the Line 2–4 entry during handover; add a 10-min PPE check window.",
    hoursAgo: 8,
  },
  {
    id: "i4",
    clientId: "sunrise-textiles",
    category: "health",
    impact: "medium",
    confidence: 0.95,
    title: "Line 2 camera has been dark for 2 days",
    body:
      "line2 has produced no frames since Wednesday 15:40. PPE and activity numbers for Line 2 are blind spots until it's restored — this week's compliance % excludes it.",
    suggestedAction: "Check camera power/cabling at Line 2; RTSP reconnects are failing.",
    hoursAgo: 14,
  },
  {
    id: "i5",
    clientId: "greenfield-school",
    category: "trend",
    impact: "low",
    confidence: 0.74,
    title: "Cooler congestion follows PE periods",
    body:
      "Water-cooler crowding alerts fire within 10 minutes after PE slots (10:30, 13:00) on 8 of the last 10 school days. Average stay rises from 23 s to 41 s.",
    suggestedAction: "Stagger PE dismissal by 5 minutes or add a second cooler.",
    hoursAgo: 20,
  },
  {
    id: "i6",
    clientId: "greenfield-school",
    category: "anomaly",
    impact: "medium",
    confidence: 0.82,
    title: "Class 4 attendance gap widening",
    body:
      "Class 4 headcount has averaged 4.2 below enrollment this week (vs 1.1 for other classrooms). The gap concentrates in the first period.",
    suggestedAction: "Share first-period entry times with the class teacher.",
    hoursAgo: 44,
  },
  {
    id: "i7",
    clientId: "swift-logistics",
    category: "optimization",
    impact: "high",
    confidence: 0.85,
    title: "Bay 7 is the turnaround bottleneck",
    body:
      "Bay 7's median dwell is 74 min vs a 41-min site median, and it triggered 6 of 9 SLA breaches this week. Bays 1–3 have 30% idle capacity in the same windows.",
    suggestedAction: "Route refrigerated trucks (the Bay 7 majority) to Bay 2 as overflow.",
    hoursAgo: 5,
  },
  {
    id: "i8",
    clientId: "kabab-house",
    category: "optimization",
    impact: "medium",
    confidence: 0.79,
    title: "Terrace tables turn over 2× faster",
    body:
      "Average stay: terrace 31 min vs family hall 52 min, with equal spend profile per the POS import. Terrace sits 40% empty on weekday evenings.",
    suggestedAction: "Seat walk-ins to the terrace first after 18:00.",
    hoursAgo: 30,
  },
  {
    id: "i9",
    clientId: "style-hub",
    category: "trend",
    impact: "low",
    confidence: 0.71,
    title: "Friday footfall consistently strongest",
    body:
      "Fridays run 34% above the weekday mean for four consecutive weeks — the store's single-staff roster doesn't reflect it.",
    suggestedAction: "Add one floor staffer on Fridays 16:00–21:00.",
    hoursAgo: 50,
  },
];

export function insightsForClient(clientId: string): Insight[] {
  return INSIGHTS.filter((i) => i.clientId === clientId);
}

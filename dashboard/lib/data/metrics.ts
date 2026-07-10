/**
 * Per-vertical simulated metric series — the shapes each vertical skin renders.
 * In production these are Supabase aggregate queries over edge events
 * (line_crossed, dwell_completed, headcount, occupancy, intrusion, …).
 */

import {
  HOURS,
  WEEKDAYS,
  doubleBump,
  eveningRamp,
  hashSeed,
  hourlySeries,
  rng,
  shiftPlateau,
} from "../seed";
import type { DayPoint, HourPoint } from "../types";

// ── Education ─────────────────────────────────────────────────────────────────

export interface ClassroomRow {
  room: string;
  enrolled: number;
  present: number;
  peak: number;
  camera: string;
}

export function educationMetrics(clientId: string) {
  const entries = hourlySeries(clientId + ":in", 130, doubleBump);
  const exits = hourlySeries(clientId + ":out", 25, (t) => 0.1 + 0.9 * t ** 3);
  const gateFlow: HourPoint[] = HOURS.map((hour, i) => ({
    hour,
    entries: entries[i],
    exits: exits[i],
  }));
  const coolerVisits = hourlySeries(clientId + ":cooler", 42, doubleBump, 0.25);
  const cooler: HourPoint[] = HOURS.map((hour, i) => ({
    hour,
    visits: coolerVisits[i],
  }));
  const r = rng(hashSeed(clientId + ":rooms"));
  const classrooms: ClassroomRow[] = Array.from({ length: 5 }, (_, i) => {
    const enrolled = 24 + Math.round(r() * 12);
    const present = enrolled - Math.round(r() * 4);
    return {
      room: `Class ${i + 1}`,
      enrolled,
      present,
      peak: Math.min(enrolled, present + Math.round(r() * 2)),
      camera: `class${i + 1}`,
    };
  });
  const totalIn = entries.reduce((a, b) => a + b, 0);
  const totalOut = exits.reduce((a, b) => a + b, 0);
  return {
    gateFlow,
    cooler,
    classrooms,
    totalIn,
    totalOut,
    onCampus: totalIn - totalOut,
    avgCoolerDwellS: 23,
    attendancePct: Math.round(
      (classrooms.reduce((a, c) => a + c.present, 0) /
        classrooms.reduce((a, c) => a + c.enrolled, 0)) *
        100,
    ),
  };
}

// ── Retail ────────────────────────────────────────────────────────────────────

export interface StoreZoneRow {
  zone: string;
  visitors: number;
  avgDwellS: number;
  share: number;
}

export function retailMetrics(clientId: string) {
  const inSeries = hourlySeries(clientId + ":in", 220, eveningRamp);
  const outSeries = inSeries.map((v, i) => (i === 0 ? Math.round(v * 0.6) : Math.round(v * 0.92)));
  const footfall: HourPoint[] = HOURS.map((hour, i) => ({
    hour,
    in: inSeries[i],
    out: outSeries[i],
  }));
  const queue = hourlySeries(clientId + ":queue", 9, eveningRamp, 0.3);
  const queueByHour: HourPoint[] = HOURS.map((hour, i) => ({
    hour,
    people: queue[i],
  }));
  const r = rng(hashSeed(clientId + ":zones"));
  const names = ["Entrance promo", "Electronics", "Grocery", "Apparel", "Checkout"];
  const zones: StoreZoneRow[] = names.map((zone) => ({
    zone,
    visitors: 250 + Math.round(r() * 900),
    avgDwellS: 25 + Math.round(r() * 200),
    share: 0,
  }));
  const total = zones.reduce((a, z) => a + z.visitors, 0);
  zones.forEach((z) => (z.share = Math.round((z.visitors / total) * 100)));
  const footfallToday = inSeries.reduce((a, b) => a + b, 0);
  const peakHourIdx = inSeries.indexOf(Math.max(...inSeries));
  return {
    footfall,
    queueByHour,
    zones,
    footfallToday,
    peakHour: `${HOURS[peakHourIdx]}:00`,
    queueNow: queue[queue.length - 1],
    avgPromoDwellS: zones[0].avgDwellS,
  };
}

// ── Manufacturing ─────────────────────────────────────────────────────────────

export interface LineRow {
  line: string;
  workers: number;
  activityPct: number;
  ppeViolations: number;
  status: "running" | "idle" | "no coverage";
}

export function manufacturingMetrics(clientId: string) {
  const violations = hourlySeries(clientId + ":ppe", 7, shiftPlateau, 0.5);
  const ppeByHour: HourPoint[] = HOURS.map((hour, i) => ({
    hour,
    violations: violations[i],
  }));
  const r = rng(hashSeed(clientId + ":lines"));
  const compliance7d: DayPoint[] = WEEKDAYS.map((day) => ({
    day,
    compliance: 88 + Math.round(r() * 10),
  })).reverse();
  const lines: LineRow[] = Array.from({ length: 8 }, (_, i) => {
    const noCoverage = i === 1; // line2 camera is the one that's stalled
    return {
      line: `Line ${i + 1}`,
      workers: noCoverage ? 0 : 4 + Math.round(r() * 8),
      activityPct: noCoverage ? 0 : 55 + Math.round(r() * 45),
      ppeViolations: noCoverage ? 0 : Math.round(r() * 5),
      status: noCoverage ? "no coverage" : r() > 0.15 ? "running" : "idle",
    };
  });
  const intrusionsByZone = [
    { zone: "Dye storage", count: 4 },
    { zone: "Boiler room", count: 2 },
    { zone: "Loading dock", count: 7 },
    { zone: "Chemical store", count: 1 },
  ];
  const violationsToday = violations.reduce((a, b) => a + b, 0);
  const workersOnFloor = lines.reduce((a, l) => a + l.workers, 0);
  return {
    ppeByHour,
    compliance7d,
    lines,
    intrusionsByZone,
    violationsToday,
    workersOnFloor,
    compliancePct: compliance7d[compliance7d.length - 1].compliance as number,
    intrusionsToday: intrusionsByZone.reduce((a, z) => a + z.count, 0),
  };
}

// ── Restaurant ────────────────────────────────────────────────────────────────

export interface SectionRow {
  section: string;
  tables: number;
  occupied: number;
  avgStayMin: number;
}

export function restaurantMetrics(clientId: string) {
  const guests = hourlySeries(clientId + ":guests", 95, eveningRamp, 0.25);
  const guestsByHour: HourPoint[] = HOURS.map((hour, i) => ({
    hour,
    guests: guests[i],
  }));
  const occupancy = hourlySeries(clientId + ":occ", 92, eveningRamp, 0.1).map((v) =>
    Math.min(100, v),
  );
  const occupancyByHour: HourPoint[] = HOURS.map((hour, i) => ({
    hour,
    occupancy: occupancy[i],
  }));
  const r = rng(hashSeed(clientId + ":sections"));
  const sections: SectionRow[] = [
    { section: "Dining hall", tables: 14, occupied: 0, avgStayMin: 0 },
    { section: "Family hall", tables: 8, occupied: 0, avgStayMin: 0 },
    { section: "Terrace", tables: 6, occupied: 0, avgStayMin: 0 },
  ].map((s) => ({
    ...s,
    occupied: Math.round(s.tables * (0.5 + r() * 0.5)),
    avgStayMin: 28 + Math.round(r() * 25),
  }));
  const tablesTotal = sections.reduce((a, s) => a + s.tables, 0);
  const tablesOccupied = sections.reduce((a, s) => a + s.occupied, 0);
  return {
    guestsByHour,
    occupancyByHour,
    sections,
    guestsToday: guests.reduce((a, b) => a + b, 0),
    tablesTotal,
    tablesOccupied,
    avgTurnoverMin: Math.round(
      sections.reduce((a, s) => a + s.avgStayMin * s.tables, 0) / tablesTotal,
    ),
    queueNow: 3 + Math.round(rng(hashSeed(clientId + ":q"))() * 6),
  };
}

// ── Warehouse ─────────────────────────────────────────────────────────────────

export interface DockRow {
  bay: string;
  truck: string | "—";
  dwellMin: number;
  status: "loading" | "unloading" | "free" | "over SLA";
}

export function warehouseMetrics(clientId: string) {
  const docksBusy = hourlySeries(clientId + ":docks", 8, shiftPlateau, 0.2).map((v) =>
    Math.min(8, v),
  );
  const dockOccupancy: HourPoint[] = HOURS.map((hour, i) => ({
    hour,
    occupied: docksBusy[i],
  }));
  const r = rng(hashSeed(clientId + ":bays"));
  const nearMiss7d: DayPoint[] = WEEKDAYS.map((day) => ({
    day,
    nearMisses: Math.round(r() * 5),
  })).reverse();
  const docks: DockRow[] = Array.from({ length: 8 }, (_, i) => {
    const free = r() > 0.7;
    const dwell = free ? 0 : 12 + Math.round(r() * 70);
    return {
      bay: `Bay ${i + 1}`,
      truck: free ? "—" : `TRK-${1000 + Math.round(r() * 900)}`,
      dwellMin: dwell,
      status: free ? "free" : dwell > 60 ? "over SLA" : r() > 0.5 ? "loading" : "unloading",
    };
  });
  const trucksToday = 26 + Math.round(rng(hashSeed(clientId + ":trucks"))() * 20);
  const activeDwells = docks.filter((d) => d.dwellMin > 0);
  return {
    dockOccupancy,
    nearMiss7d,
    docks,
    trucksToday,
    avgDockDwellMin: Math.round(
      activeDwells.reduce((a, d) => a + d.dwellMin, 0) / Math.max(1, activeDwells.length),
    ),
    nearMissesToday: nearMiss7d[nearMiss7d.length - 1].nearMisses as number,
    docksOccupied: docks.filter((d) => d.status !== "free").length,
  };
}

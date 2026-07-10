/**
 * Deterministic pseudo-randomness for the simulated data.
 *
 * Everything renders on the server AND hydrates on the client, so the data
 * must be identical on both — no Math.random(), no Date.now(). All series are
 * generated from seeded PRNGs and anchored to a fixed "now".
 */

/** The dashboard's frozen wall clock (PKT evening — sites busy all day). */
export const NOW_LABEL = "Fri 10 Jul 2026, 17:00 PKT";

/** mulberry32 — tiny, fast, good-enough seeded PRNG. */
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function hashSeed(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export const HOURS = Array.from({ length: 12 }, (_, i) =>
  String(i + 6).padStart(2, "0"), // "06" … "17" — the business day so far
);

export const WEEKDAYS = ["Fri", "Sat", "Sun", "Mon", "Tue", "Wed", "Thu"];

/**
 * Hourly values following a shaped daily curve.
 * `shape` maps 0..1 (position in the day) to a 0..1 intensity.
 */
export function hourlySeries(
  seedText: string,
  peak: number,
  shape: (t: number) => number,
  jitter = 0.15,
): number[] {
  const r = rng(hashSeed(seedText));
  return HOURS.map((_, i) => {
    const t = i / (HOURS.length - 1);
    const base = shape(t) * peak;
    return Math.max(0, Math.round(base * (1 + (r() - 0.5) * 2 * jitter)));
  });
}

/** Morning + lunch double bump (schools, offices). */
export const doubleBump = (t: number) =>
  0.15 + 0.85 * Math.exp(-(((t - 0.12) / 0.14) ** 2)) + 0.5 * Math.exp(-(((t - 0.62) / 0.16) ** 2));

/** Builds through the day toward an evening peak (retail, restaurants). */
export const eveningRamp = (t: number) => 0.2 + 0.8 * t ** 1.6;

/** Flat with a mid-day dip (factory shifts, warehouses). */
export const shiftPlateau = (t: number) =>
  0.75 + 0.25 * Math.sin(t * Math.PI) - 0.3 * Math.exp(-(((t - 0.55) / 0.08) ** 2));

export function fmtAgo(minutes: number): string {
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${Math.round(minutes)}m ago`;
  const h = minutes / 60;
  if (h < 24) return `${Math.round(h)}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

export function fmtSecs(seconds: number): string {
  if (seconds < 90) return `${Math.round(seconds)}s`;
  return `${Math.round(seconds / 60)}m`;
}

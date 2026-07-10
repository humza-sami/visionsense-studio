import { hashSeed, rng } from "../seed";
import type { Camera, Client, EdgeHealth, VerticalId } from "../types";

interface ClientSeed {
  id: string;
  name: string;
  vertical: VerticalId;
  city: string;
  plan: Client["plan"];
  sinceMonthYear: string;
  cameraGroups: { group: string; prefix: string; count: number; detectFps: number }[];
  gpu: string;
  eventsToday: number;
  /** indexes of cameras forced offline/stalled (stable, story-driven) */
  downCameras?: number[];
}

const SEEDS: ClientSeed[] = [
  {
    id: "greenfield-school",
    name: "Greenfield School",
    vertical: "education",
    city: "Islamabad",
    plan: "pro",
    sinceMonthYear: "Mar 2026",
    cameraGroups: [
      { group: "entrances", prefix: "gate", count: 2, detectFps: 10 },
      { group: "entrances", prefix: "cooler", count: 1, detectFps: 10 },
      { group: "classrooms", prefix: "class", count: 5, detectFps: 1 },
    ],
    gpu: "RTX 3070 Ti 8GB",
    eventsToday: 1462,
  },
  {
    id: "metro-mart",
    name: "Metro Mart",
    vertical: "retail",
    city: "Karachi",
    plan: "enterprise",
    sinceMonthYear: "Jan 2026",
    cameraGroups: [
      { group: "entrances", prefix: "entry", count: 3, detectFps: 10 },
      { group: "checkouts", prefix: "till", count: 6, detectFps: 5 },
      { group: "aisles", prefix: "aisle", count: 12, detectFps: 2 },
    ],
    gpu: "RTX 4090 24GB",
    eventsToday: 9814,
    downCameras: [14],
  },
  {
    id: "style-hub",
    name: "Style Hub Outlet",
    vertical: "retail",
    city: "Lahore",
    plan: "starter",
    sinceMonthYear: "Jun 2026",
    cameraGroups: [
      { group: "entrances", prefix: "entry", count: 1, detectFps: 10 },
      { group: "floor", prefix: "floor", count: 5, detectFps: 2 },
    ],
    gpu: "RTX 3060 12GB",
    eventsToday: 2137,
  },
  {
    id: "sunrise-textiles",
    name: "Sunrise Textiles",
    vertical: "manufacturing",
    city: "Faisalabad",
    plan: "enterprise",
    sinceMonthYear: "Feb 2026",
    cameraGroups: [
      { group: "safety", prefix: "line", count: 8, detectFps: 10 },
      { group: "perimeter", prefix: "gate", count: 4, detectFps: 5 },
      { group: "floor", prefix: "hall", count: 6, detectFps: 2 },
    ],
    gpu: "L4 24GB",
    eventsToday: 5230,
    downCameras: [9],
  },
  {
    id: "kabab-house",
    name: "Kabab House",
    vertical: "restaurant",
    city: "Lahore",
    plan: "pro",
    sinceMonthYear: "Apr 2026",
    cameraGroups: [
      { group: "front", prefix: "counter", count: 2, detectFps: 10 },
      { group: "dining", prefix: "hall", count: 4, detectFps: 2 },
      { group: "kitchen", prefix: "kitchen", count: 2, detectFps: 2 },
    ],
    gpu: "RTX 3060 12GB",
    eventsToday: 3389,
  },
  {
    id: "swift-logistics",
    name: "Swift Logistics Hub",
    vertical: "warehouse",
    city: "Port Qasim",
    plan: "enterprise",
    sinceMonthYear: "May 2026",
    cameraGroups: [
      { group: "docks", prefix: "dock", count: 8, detectFps: 10 },
      { group: "yard", prefix: "yard", count: 4, detectFps: 5 },
      { group: "aisles", prefix: "rack", count: 8, detectFps: 2 },
    ],
    gpu: "RTX 4090 24GB",
    eventsToday: 4102,
    downCameras: [3, 17],
  },
];

function buildCameras(seed: ClientSeed): Camera[] {
  const r = rng(hashSeed(seed.id + ":cams"));
  const cams: Camera[] = [];
  let idx = 0;
  for (const g of seed.cameraGroups) {
    for (let i = 1; i <= g.count; i++) {
      const down = seed.downCameras?.includes(idx) ?? false;
      cams.push({
        id: g.count > 1 ? `${g.prefix}${i}` : g.prefix,
        name: g.count > 1 ? `${cap(g.prefix)} ${i}` : cap(g.prefix),
        group: g.group,
        online: !down,
        lastFrameAgoS: down ? 900 + Math.round(r() * 5400) : Math.round(r() * 3),
        signal: down ? 0 : 62 + Math.round(r() * 38),
        detectFps: g.detectFps,
      });
      idx++;
    }
  }
  return cams;
}

function cap(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function buildEdge(seed: ClientSeed, cameraCount: number): EdgeHealth {
  const r = rng(hashSeed(seed.id + ":edge"));
  const load = Math.min(0.9, cameraCount / 40);
  return {
    serverOnline: true,
    lastPingAgoS: 10 + Math.round(r() * 45),
    uptimeDays: 4 + Math.round(r() * 60),
    gpu: seed.gpu,
    gpuUtilPct: Math.round(8 + load * 40 + r() * 10),
    nvdecUtilPct: Math.round(15 + load * 70 + r() * 10),
    vramUsedGb: Number((1.5 + cameraCount * 0.03 + r()).toFixed(1)),
    vramTotalGb: Number(seed.gpu.match(/(\d+)GB/)?.[1] ?? 8),
    cpuUtilPct: Math.round(10 + load * 25 + r() * 10),
    uplinkMbps: Math.round(20 + r() * 80),
    diskUsedPct: Math.round(30 + r() * 45),
    runtimeVersion: "frameinsight/edge:0.1.0",
  };
}

export const CLIENTS: Client[] = SEEDS.map((seed) => {
  const cameras = buildCameras(seed);
  return {
    id: seed.id,
    name: seed.name,
    vertical: seed.vertical,
    city: seed.city,
    country: "Pakistan",
    sinceMonthYear: seed.sinceMonthYear,
    plan: seed.plan,
    cameras,
    edge: buildEdge(seed, cameras.length),
    eventsToday: seed.eventsToday,
  };
});

export function getClient(id: string): Client | undefined {
  return CLIENTS.find((c) => c.id === id);
}

export function fleetStats() {
  const totalCams = CLIENTS.reduce((n, c) => n + c.cameras.length, 0);
  const onlineCams = CLIENTS.reduce(
    (n, c) => n + c.cameras.filter((cam) => cam.online).length,
    0,
  );
  const eventsToday = CLIENTS.reduce((n, c) => n + c.eventsToday, 0);
  return { clients: CLIENTS.length, totalCams, onlineCams, eventsToday };
}

import {
  Factory,
  GraduationCap,
  ShoppingCart,
  UtensilsCrossed,
  Warehouse,
  type LucideIcon,
} from "lucide-react";

import type { VerticalId } from "./types";

export interface VerticalMeta {
  id: VerticalId;
  label: string;
  icon: LucideIcon;
  /** what the vertical's rule kernels measure — shown as a subtitle */
  tagline: string;
}

export const VERTICALS: Record<VerticalId, VerticalMeta> = {
  education: {
    id: "education",
    label: "Education",
    icon: GraduationCap,
    tagline: "Gate entries, classroom headcounts, congestion",
  },
  retail: {
    id: "retail",
    label: "Retail",
    icon: ShoppingCart,
    tagline: "Footfall, queue lengths, zone dwell",
  },
  manufacturing: {
    id: "manufacturing",
    label: "Manufacturing",
    icon: Factory,
    tagline: "PPE compliance, restricted zones, line activity",
  },
  restaurant: {
    id: "restaurant",
    label: "Restaurant",
    icon: UtensilsCrossed,
    tagline: "Table occupancy, turnover, counter queues",
  },
  warehouse: {
    id: "warehouse",
    label: "Warehouse & Logistics",
    icon: Warehouse,
    tagline: "Dock dwell, truck turnaround, near-miss safety",
  },
};

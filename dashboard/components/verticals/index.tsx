/**
 * Vertical skin registry — maps a client's vertical to its dashboard layout.
 * Adding a vertical = one skin component + one entry here (+ metrics in
 * lib/data/metrics.ts). Nothing else in the app changes.
 */

import type { ComponentType } from "react";

import type { Client, VerticalId } from "@/lib/types";

import { EducationSkin } from "./education-skin";
import { ManufacturingSkin } from "./manufacturing-skin";
import { RestaurantSkin } from "./restaurant-skin";
import { RetailSkin } from "./retail-skin";
import { WarehouseSkin } from "./warehouse-skin";

export const VERTICAL_SKINS: Record<VerticalId, ComponentType<{ client: Client }>> = {
  education: EducationSkin,
  retail: RetailSkin,
  manufacturing: ManufacturingSkin,
  restaurant: RestaurantSkin,
  warehouse: WarehouseSkin,
};

import { BarsChart, TrendAreaChart } from "@/components/charts";
import { KpiRow } from "@/components/kpi-card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { warehouseMetrics } from "@/lib/data/metrics";
import type { Client } from "@/lib/types";

import { ChartCard } from "./chart-card";

export function WarehouseSkin({ client }: { client: Client }) {
  const m = warehouseMetrics(client.id);
  return (
    <div className="space-y-4">
      <KpiRow
        kpis={[
          {
            label: "Trucks processed",
            value: `${m.trucksToday}`,
            delta: "+8% vs daily avg",
            deltaDirection: "up",
          },
          {
            label: "Avg dock dwell",
            value: `${m.avgDockDwellMin} min`,
            delta: "−6 min this week",
            deltaDirection: "down",
            upIsGood: false,
          },
          {
            label: "Docks occupied",
            value: `${m.docksOccupied}/8`,
            hint: "live",
          },
          {
            label: "Near-misses today",
            value: `${m.nearMissesToday}`,
            hint: "forklift ↔ pedestrian",
          },
        ]}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard
          title="Dock occupancy by hour"
          description="bays with a truck present (zone_dwell per bay)"
        >
          <TrendAreaChart
            data={m.dockOccupancy}
            x="hour"
            series={[{ key: "occupied", label: "Bays occupied", color: 1 }]}
          />
        </ChartCard>
        <ChartCard
          title="Near-misses (7 days)"
          description="forklift–pedestrian proximity events in yard lanes"
        >
          <BarsChart
            data={m.nearMiss7d}
            x="day"
            series={[{ key: "nearMisses", label: "Near-misses", color: 5 }]}
          />
        </ChartCard>
      </div>

      <ChartCard title="Dock bays" description="Live dwell per bay — SLA is 60 min">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Bay</TableHead>
              <TableHead>Truck</TableHead>
              <TableHead className="text-right">Dwell</TableHead>
              <TableHead className="text-right">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {m.docks.map((d) => (
              <TableRow key={d.bay}>
                <TableCell className="font-medium">{d.bay}</TableCell>
                <TableCell className="text-muted-foreground font-mono text-sm">
                  {d.truck}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {d.dwellMin > 0 ? `${d.dwellMin} min` : "—"}
                </TableCell>
                <TableCell className="text-right">
                  <Badge
                    variant={
                      d.status === "over SLA"
                        ? "destructive"
                        : d.status === "free"
                          ? "outline"
                          : "secondary"
                    }
                  >
                    {d.status}
                  </Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </ChartCard>
    </div>
  );
}

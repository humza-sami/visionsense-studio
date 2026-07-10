import { TrendAreaChart, TrendLineChart } from "@/components/charts";
import { KpiRow } from "@/components/kpi-card";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { restaurantMetrics } from "@/lib/data/metrics";
import type { Client } from "@/lib/types";

import { ChartCard } from "./chart-card";

export function RestaurantSkin({ client }: { client: Client }) {
  const m = restaurantMetrics(client.id);
  return (
    <div className="space-y-4">
      <KpiRow
        kpis={[
          {
            label: "Guests today",
            value: m.guestsToday.toLocaleString("en-US"),
            delta: "+6% vs last Friday",
            deltaDirection: "up",
          },
          {
            label: "Tables occupied",
            value: `${m.tablesOccupied}/${m.tablesTotal}`,
            hint: "live occupancy",
          },
          {
            label: "Avg table turnover",
            value: `${m.avgTurnoverMin} min`,
            delta: "−3 min vs last week",
            deltaDirection: "down",
            upIsGood: false,
          },
          {
            label: "Counter queue now",
            value: `${m.queueNow}`,
            hint: "people waiting",
          },
        ]}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="Guests by hour" description="entries counted at the door">
          <TrendAreaChart
            data={m.guestsByHour}
            x="hour"
            series={[{ key: "guests", label: "Guests", color: 1 }]}
          />
        </ChartCard>
        <ChartCard
          title="Table occupancy"
          description="share of tables with sustained presence (zone_dwell per table zone)"
        >
          <TrendLineChart
            data={m.occupancyByHour}
            x="hour"
            series={[{ key: "occupancy", label: "Occupancy %", color: 3 }]}
            yDomain={[0, 100]}
          />
        </ChartCard>
      </div>

      <ChartCard
        title="Sections"
        description="Occupancy and average stay per seating section"
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Section</TableHead>
              <TableHead className="text-right">Tables</TableHead>
              <TableHead className="text-right">Occupied</TableHead>
              <TableHead className="text-right">Avg stay</TableHead>
              <TableHead className="w-48">Utilization</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {m.sections.map((s) => (
              <TableRow key={s.section}>
                <TableCell className="font-medium">{s.section}</TableCell>
                <TableCell className="text-right tabular-nums">{s.tables}</TableCell>
                <TableCell className="text-right tabular-nums">{s.occupied}</TableCell>
                <TableCell className="text-right tabular-nums">{s.avgStayMin} min</TableCell>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <Progress value={(s.occupied / s.tables) * 100} className="h-2" />
                    <span className="text-muted-foreground w-10 text-right text-xs tabular-nums">
                      {Math.round((s.occupied / s.tables) * 100)}%
                    </span>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </ChartCard>
    </div>
  );
}

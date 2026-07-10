import { ShareDonutChart, TrendAreaChart, TrendLineChart } from "@/components/charts";
import { KpiRow } from "@/components/kpi-card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { retailMetrics } from "@/lib/data/metrics";
import { fmtSecs } from "@/lib/seed";
import type { Client } from "@/lib/types";

import { ChartCard } from "./chart-card";

export function RetailSkin({ client }: { client: Client }) {
  const m = retailMetrics(client.id);
  return (
    <div className="space-y-4">
      <KpiRow
        kpis={[
          {
            label: "Footfall today",
            value: m.footfallToday.toLocaleString("en-US"),
            delta: "+9% vs last Friday",
            deltaDirection: "up",
          },
          { label: "Peak hour", value: m.peakHour, hint: "highest entry rate" },
          {
            label: "Checkout queue now",
            value: `${m.queueNow}`,
            delta: "−2 vs 30 min ago",
            deltaDirection: "down",
            upIsGood: false,
          },
          {
            label: "Promo-zone dwell",
            value: fmtSecs(m.avgPromoDwellS),
            hint: "avg per visitor",
          },
        ]}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard
          title="Footfall by hour"
          description="line_crossing at the entrances (in vs out)"
        >
          <TrendAreaChart
            data={m.footfall}
            x="hour"
            series={[
              { key: "in", label: "In", color: 1 },
              { key: "out", label: "Out", color: 2 },
            ]}
          />
        </ChartCard>
        <ChartCard
          title="Checkout queue length"
          description="headcount in the till waiting zones — staffing trigger at 8"
        >
          <TrendLineChart
            data={m.queueByHour}
            x="hour"
            series={[{ key: "people", label: "People in queue", color: 4 }]}
          />
        </ChartCard>
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <ChartCard
          title="Visit share by zone"
          description="Where visitors spend time"
          className="lg:col-span-2"
        >
          <ShareDonutChart data={m.zones} nameKey="zone" valueKey="visitors" />
        </ChartCard>
        <ChartCard
          title="Zone performance"
          description="zone_dwell aggregates per drawn floor zone"
          className="lg:col-span-3"
        >
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Zone</TableHead>
                <TableHead className="text-right">Visitors</TableHead>
                <TableHead className="text-right">Avg dwell</TableHead>
                <TableHead className="text-right">Share</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {m.zones.map((z) => (
                <TableRow key={z.zone}>
                  <TableCell className="font-medium">{z.zone}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {z.visitors.toLocaleString("en-US")}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {fmtSecs(z.avgDwellS)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{z.share}%</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ChartCard>
      </div>
    </div>
  );
}

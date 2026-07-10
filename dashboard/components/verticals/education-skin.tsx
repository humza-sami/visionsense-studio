import { BarsChart, TrendAreaChart } from "@/components/charts";
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
import { educationMetrics } from "@/lib/data/metrics";
import type { Client } from "@/lib/types";

import { ChartCard } from "./chart-card";

export function EducationSkin({ client }: { client: Client }) {
  const m = educationMetrics(client.id);
  return (
    <div className="space-y-4">
      <KpiRow
        kpis={[
          {
            label: "Entries today",
            value: m.totalIn.toLocaleString("en-US"),
            delta: "+4% vs yesterday",
            deltaDirection: "up",
          },
          {
            label: "On campus now",
            value: m.onCampus.toLocaleString("en-US"),
            hint: `${m.totalOut} exits so far`,
          },
          {
            label: "Attendance",
            value: `${m.attendancePct}%`,
            delta: "−1 pt vs last week",
            deltaDirection: "down",
          },
          {
            label: "Avg cooler stay",
            value: `${m.avgCoolerDwellS}s`,
            hint: "per visit, today",
          },
        ]}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard
          title="Gate flow by hour"
          description="line_crossing events at the main gate (entries vs exits)"
        >
          <BarsChart
            data={m.gateFlow}
            x="hour"
            series={[
              { key: "entries", label: "Entries", color: 1 },
              { key: "exits", label: "Exits", color: 2 },
            ]}
            stacked
          />
        </ChartCard>
        <ChartCard
          title="Water-cooler visits"
          description="zone_dwell visits per hour — crowding alerts fire above 4 at once"
        >
          <TrendAreaChart
            data={m.cooler}
            x="hour"
            series={[{ key: "visits", label: "Visits", color: 3 }]}
          />
        </ChartCard>
      </div>

      <ChartCard
        title="Classroom headcounts"
        description="Median-smoothed headcount per room (30 s reporting) vs enrollment"
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Room</TableHead>
              <TableHead>Camera</TableHead>
              <TableHead className="text-right">Enrolled</TableHead>
              <TableHead className="text-right">Present</TableHead>
              <TableHead className="text-right">Peak today</TableHead>
              <TableHead className="w-48">Utilization</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {m.classrooms.map((row) => (
              <TableRow key={row.room}>
                <TableCell className="font-medium">{row.room}</TableCell>
                <TableCell className="text-muted-foreground font-mono text-xs">
                  {row.camera}
                </TableCell>
                <TableCell className="text-right tabular-nums">{row.enrolled}</TableCell>
                <TableCell className="text-right tabular-nums">{row.present}</TableCell>
                <TableCell className="text-right tabular-nums">{row.peak}</TableCell>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <Progress value={(row.present / row.enrolled) * 100} className="h-2" />
                    <span className="text-muted-foreground w-10 text-right text-xs tabular-nums">
                      {Math.round((row.present / row.enrolled) * 100)}%
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

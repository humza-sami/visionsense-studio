import { BarsChart, TrendLineChart } from "@/components/charts";
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
import { manufacturingMetrics } from "@/lib/data/metrics";
import { cn } from "@/lib/utils";
import type { Client } from "@/lib/types";

import { ChartCard } from "./chart-card";

export function ManufacturingSkin({ client }: { client: Client }) {
  const m = manufacturingMetrics(client.id);
  return (
    <div className="space-y-4">
      <KpiRow
        kpis={[
          {
            label: "PPE compliance",
            value: `${m.compliancePct}%`,
            delta: "+3 pts this week",
            deltaDirection: "up",
          },
          {
            label: "PPE violations today",
            value: `${m.violationsToday}`,
            delta: "−12% vs yesterday",
            deltaDirection: "down",
            upIsGood: false,
          },
          {
            label: "Zone intrusions today",
            value: `${m.intrusionsToday}`,
            hint: "restricted areas",
          },
          {
            label: "Workers on floor",
            value: `${m.workersOnFloor}`,
            hint: "live headcount",
          },
        ]}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard
          title="PPE violations by hour"
          description="ppe_compliance kernel — spikes cluster at shift changes"
        >
          <BarsChart
            data={m.ppeByHour}
            x="hour"
            series={[{ key: "violations", label: "Violations", color: 5 }]}
          />
        </ChartCard>
        <ChartCard title="Compliance trend (7 days)" description="daily compliance %">
          <TrendLineChart
            data={m.compliance7d}
            x="day"
            series={[{ key: "compliance", label: "Compliance %", color: 1 }]}
            yDomain={[80, 100]}
          />
        </ChartCard>
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <ChartCard
          title="Intrusions by restricted zone"
          description="zone_intrusion alerts this week"
          className="lg:col-span-2"
        >
          <BarsChart
            data={m.intrusionsByZone}
            x="zone"
            series={[{ key: "count", label: "Intrusions", color: 2 }]}
            className="h-64 w-full"
          />
        </ChartCard>
        <ChartCard
          title="Production lines"
          description="Live worker presence and activity per line camera"
          className="lg:col-span-3"
        >
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Line</TableHead>
                <TableHead className="text-right">Workers</TableHead>
                <TableHead className="text-right">Activity</TableHead>
                <TableHead className="text-right">PPE violations</TableHead>
                <TableHead className="text-right">Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {m.lines.map((line) => (
                <TableRow key={line.line}>
                  <TableCell className="font-medium">{line.line}</TableCell>
                  <TableCell className="text-right tabular-nums">{line.workers}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {line.activityPct}%
                  </TableCell>
                  <TableCell
                    className={cn(
                      "text-right tabular-nums",
                      line.ppeViolations > 3 && "font-medium text-red-500",
                    )}
                  >
                    {line.ppeViolations}
                  </TableCell>
                  <TableCell className="text-right">
                    <Badge
                      variant={
                        line.status === "running"
                          ? "secondary"
                          : line.status === "idle"
                            ? "outline"
                            : "destructive"
                      }
                    >
                      {line.status}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ChartCard>
      </div>
    </div>
  );
}

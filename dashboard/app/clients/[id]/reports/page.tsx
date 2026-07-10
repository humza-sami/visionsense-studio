import { Download, FileText } from "lucide-react";
import { notFound } from "next/navigation";

import { KpiRow } from "@/components/kpi-card";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getClient } from "@/lib/data/clients";
import { monthlyReport } from "@/lib/data/reports";

export default async function ClientReportsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const client = getClient(id);
  const report = monthlyReport(id);
  if (!client || !report) notFound();

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <FileText className="size-5" /> Monthly report — {report.month}
          </h2>
          <p className="text-muted-foreground text-sm">
            The billable client deliverable, generated from event aggregates.
          </p>
        </div>
        <Button variant="outline" disabled>
          <Download className="size-4" /> Export PDF (soon)
        </Button>
      </div>

      <KpiRow kpis={report.headline} />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Week by week</CardTitle>
          <CardDescription>{report.narrative}</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                {report.weeklyColumns.map((col, i) => (
                  <TableHead key={col.key} className={i > 0 ? "text-right" : undefined}>
                    {col.label}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {report.weekly.map((row) => (
                <TableRow key={String(row.week)}>
                  {report.weeklyColumns.map((col, i) => (
                    <TableCell
                      key={col.key}
                      className={
                        i > 0 ? "text-right tabular-nums" : "font-medium whitespace-nowrap"
                      }
                    >
                      {typeof row[col.key] === "number"
                        ? Number(row[col.key]).toLocaleString("en-US")
                        : row[col.key]}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

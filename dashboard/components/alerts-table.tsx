import { Camera } from "lucide-react";

import { SeverityBadge } from "@/components/status";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getClient } from "@/lib/data/clients";
import { fmtAgo } from "@/lib/seed";
import type { AlertItem } from "@/lib/types";

export function AlertsTable({
  alerts,
  showClient = false,
}: {
  alerts: AlertItem[];
  showClient?: boolean;
}) {
  const sorted = [...alerts].sort(
    (a, b) =>
      Number(a.acknowledged) - Number(b.acknowledged) || a.minutesAgo - b.minutesAgo,
  );
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-24">Severity</TableHead>
          {showClient && <TableHead>Client</TableHead>}
          <TableHead>Alert</TableHead>
          <TableHead className="hidden md:table-cell">Camera</TableHead>
          <TableHead className="hidden md:table-cell">Rule</TableHead>
          <TableHead className="text-right">When</TableHead>
          <TableHead className="w-28 text-right">Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((a) => (
          <TableRow key={a.id} className={a.acknowledged ? "opacity-60" : undefined}>
            <TableCell>
              <SeverityBadge severity={a.severity} />
            </TableCell>
            {showClient && (
              <TableCell className="whitespace-nowrap">
                {getClient(a.clientId)?.name ?? a.clientId}
              </TableCell>
            )}
            <TableCell className="max-w-md">{a.message}</TableCell>
            <TableCell className="hidden md:table-cell">
              <span className="text-muted-foreground inline-flex items-center gap-1 text-sm">
                <Camera className="size-3.5" /> {a.cameraId}
              </span>
            </TableCell>
            <TableCell className="text-muted-foreground hidden font-mono text-xs md:table-cell">
              {a.rule}
            </TableCell>
            <TableCell className="text-muted-foreground text-right text-sm whitespace-nowrap">
              {fmtAgo(a.minutesAgo)}
            </TableCell>
            <TableCell className="text-right">
              {a.acknowledged ? (
                <Badge variant="secondary">acked</Badge>
              ) : (
                <Badge>open</Badge>
              )}
            </TableCell>
          </TableRow>
        ))}
        {sorted.length === 0 && (
          <TableRow>
            <TableCell
              colSpan={showClient ? 7 : 6}
              className="text-muted-foreground h-20 text-center"
            >
              No alerts — all quiet.
            </TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  );
}

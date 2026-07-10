import { SignalBars, StatusDot } from "@/components/status";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { fmtSecs } from "@/lib/seed";
import type { Camera } from "@/lib/types";

export function CamerasTable({ cameras }: { cameras: Camera[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Camera</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="hidden md:table-cell">Pipeline group</TableHead>
          <TableHead className="hidden md:table-cell">Detection rate</TableHead>
          <TableHead>Last frame</TableHead>
          <TableHead className="text-right">Signal</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {cameras.map((cam) => (
          <TableRow key={cam.id}>
            <TableCell>
              <div className="font-medium">{cam.name}</div>
              <div className="text-muted-foreground font-mono text-xs">{cam.id}</div>
            </TableCell>
            <TableCell>
              <StatusDot ok={cam.online} label={cam.online ? "online" : "stalled"} />
            </TableCell>
            <TableCell className="hidden md:table-cell">
              <Badge variant="outline">{cam.group}</Badge>
            </TableCell>
            <TableCell className="text-muted-foreground hidden text-sm md:table-cell">
              {cam.detectFps} det/s
            </TableCell>
            <TableCell
              className={
                cam.online ? "text-muted-foreground text-sm" : "text-sm font-medium text-red-500"
              }
            >
              {fmtSecs(cam.lastFrameAgoS)} ago
            </TableCell>
            <TableCell className="text-right">
              <SignalBars value={cam.signal} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

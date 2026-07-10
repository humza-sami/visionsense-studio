import { Cpu, Gauge, HardDrive, MemoryStick, Network, Server } from "lucide-react";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { CamerasTable } from "@/components/cameras-table";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { getClient } from "@/lib/data/clients";

function HealthStat({
  icon,
  label,
  value,
  pct,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  pct?: number;
}) {
  return (
    <div className="space-y-1.5">
      <div className="text-muted-foreground flex items-center gap-1.5 text-xs">
        {icon}
        {label}
      </div>
      <div className="text-sm font-medium tabular-nums">{value}</div>
      {pct !== undefined && <Progress value={pct} className="h-1.5" />}
    </div>
  );
}

export default async function ClientCamerasPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const client = getClient(id);
  if (!client) notFound();
  const e = client.edge;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Server className="size-4" /> Edge server
          </CardTitle>
          <CardDescription>
            {e.gpu} · {e.runtimeVersion} · up {e.uptimeDays} days
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
            <HealthStat
              icon={<Gauge className="size-3.5" />}
              label="GPU util"
              value={`${e.gpuUtilPct}%`}
              pct={e.gpuUtilPct}
            />
            <HealthStat
              icon={<Gauge className="size-3.5" />}
              label="NVDEC (decoder)"
              value={`${e.nvdecUtilPct}%`}
              pct={e.nvdecUtilPct}
            />
            <HealthStat
              icon={<MemoryStick className="size-3.5" />}
              label="VRAM"
              value={`${e.vramUsedGb} / ${e.vramTotalGb} GB`}
              pct={(e.vramUsedGb / e.vramTotalGb) * 100}
            />
            <HealthStat
              icon={<Cpu className="size-3.5" />}
              label="CPU"
              value={`${e.cpuUtilPct}%`}
              pct={e.cpuUtilPct}
            />
            <HealthStat
              icon={<Network className="size-3.5" />}
              label="Uplink"
              value={`${e.uplinkMbps} Mbps`}
            />
            <HealthStat
              icon={<HardDrive className="size-3.5" />}
              label="Disk"
              value={`${e.diskUsedPct}%`}
              pct={e.diskUsedPct}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Cameras ({client.cameras.filter((c) => c.online).length}/{client.cameras.length}{" "}
            online)
          </CardTitle>
          <CardDescription>
            Per-camera stream health from edge heartbeats — a stalled camera raises a
            camera_stalled alert automatically.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <CamerasTable cameras={client.cameras} />
        </CardContent>
      </Card>
    </div>
  );
}

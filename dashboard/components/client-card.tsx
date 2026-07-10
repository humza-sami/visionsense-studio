import { Camera, ChevronRight, MapPin } from "lucide-react";
import Link from "next/link";

import { StatusDot } from "@/components/status";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { fmtAgo } from "@/lib/seed";
import { VERTICALS } from "@/lib/verticals";
import type { Client } from "@/lib/types";

export function ClientCard({
  client,
  openAlerts,
}: {
  client: Client;
  openAlerts: number;
}) {
  const meta = VERTICALS[client.vertical];
  const Icon = meta.icon;
  const online = client.cameras.filter((c) => c.online).length;
  const total = client.cameras.length;
  return (
    <Link href={`/clients/${client.id}`} className="group">
      <Card className="h-full transition-colors group-hover:border-primary/40">
        <CardHeader>
          <div className="flex items-start gap-3">
            <div className="bg-muted flex size-10 shrink-0 items-center justify-center rounded-lg">
              <Icon className="size-5" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-1 font-semibold">
                <span className="truncate">{client.name}</span>
                <ChevronRight className="text-muted-foreground size-4 shrink-0 transition-transform group-hover:translate-x-0.5" />
              </div>
              <div className="text-muted-foreground flex items-center gap-1 text-xs">
                <MapPin className="size-3" /> {client.city} · {meta.label}
              </div>
            </div>
            <Badge variant="outline" className="ml-auto capitalize">
              {client.plan}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Edge server</span>
            <span className="inline-flex items-center gap-1.5">
              <StatusDot ok={client.edge.serverOnline} />
              ping {fmtAgo(client.edge.lastPingAgoS / 60)}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Cameras</span>
            <span className="inline-flex items-center gap-1 tabular-nums">
              <Camera className="text-muted-foreground size-3.5" />
              {online}/{total} online
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Events today</span>
            <span className="tabular-nums">{client.eventsToday.toLocaleString("en-US")}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Open alerts</span>
            {openAlerts > 0 ? (
              <Badge className="tabular-nums">{openAlerts}</Badge>
            ) : (
              <span className="text-muted-foreground">none</span>
            )}
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

import { MapPin } from "lucide-react";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { ClientTabs } from "@/components/client-tabs";
import { ModeToggle } from "@/components/mode-toggle";
import { StatusDot } from "@/components/status";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { CLIENTS, getClient } from "@/lib/data/clients";
import { NOW_LABEL, fmtAgo } from "@/lib/seed";
import { VERTICALS } from "@/lib/verticals";

export function generateStaticParams() {
  return CLIENTS.map((c) => ({ id: c.id }));
}

export default async function ClientLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const client = getClient(id);
  if (!client) notFound();
  const meta = VERTICALS[client.vertical];
  const online = client.cameras.filter((c) => c.online).length;

  return (
    <>
      <header className="bg-background sticky top-0 z-10 border-b">
        <div className="flex items-center gap-2 px-4 py-3 md:px-6">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="mr-1 h-4" />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-base font-semibold md:text-lg">{client.name}</h1>
              <Badge variant="outline">{meta.label}</Badge>
              <Badge variant="secondary" className="capitalize">
                {client.plan}
              </Badge>
            </div>
            <div className="text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs">
              <span className="inline-flex items-center gap-1">
                <MapPin className="size-3" />
                {client.city}, {client.country} · since {client.sinceMonthYear}
              </span>
              <span className="inline-flex items-center gap-1.5">
                <StatusDot ok={client.edge.serverOnline} />
                edge {client.edge.serverOnline ? "online" : "offline"} · ping{" "}
                {fmtAgo(client.edge.lastPingAgoS / 60)}
              </span>
              <span>
                {online}/{client.cameras.length} cameras
              </span>
            </div>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <span className="text-muted-foreground hidden text-xs lg:inline">
              {NOW_LABEL}
            </span>
            <ModeToggle />
          </div>
        </div>
        <ClientTabs clientId={client.id} />
      </header>
      <main className="flex-1 p-4 md:p-6">{children}</main>
    </>
  );
}

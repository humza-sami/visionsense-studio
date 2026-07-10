import { Sparkles } from "lucide-react";
import Link from "next/link";

import { AlertsTable } from "@/components/alerts-table";
import { ClientCard } from "@/components/client-card";
import { InsightCard } from "@/components/insight-card";
import { KpiRow } from "@/components/kpi-card";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ALERTS, openAlertCount } from "@/lib/data/alerts";
import { CLIENTS, fleetStats, getClient } from "@/lib/data/clients";
import { INSIGHTS } from "@/lib/data/insights";

export default function FleetOverviewPage() {
  const stats = fleetStats();
  const recentAlerts = ALERTS.filter((a) => !a.acknowledged).slice(0, 6);
  const topInsights = INSIGHTS.filter((i) => i.impact === "high").slice(0, 2);

  return (
    <>
      <PageHeader
        title="Fleet overview"
        description="Every client site at a glance — edge health, cameras, and what needs attention."
      />
      <main className="flex-1 space-y-6 p-4 md:p-6">
        <KpiRow
          kpis={[
            { label: "Client sites", value: `${stats.clients}`, hint: "5 verticals" },
            {
              label: "Cameras online",
              value: `${stats.onlineCams}/${stats.totalCams}`,
              delta:
                stats.totalCams - stats.onlineCams > 0
                  ? `${stats.totalCams - stats.onlineCams} stalled`
                  : "all healthy",
              deltaDirection: stats.totalCams - stats.onlineCams > 0 ? "down" : "flat",
            },
            {
              label: "Open alerts",
              value: `${openAlertCount()}`,
              hint: "across the fleet",
            },
            {
              label: "Events today",
              value: stats.eventsToday.toLocaleString("en-US"),
              delta: "+11% vs yesterday",
              deltaDirection: "up",
            },
          ]}
        />

        <section>
          <h2 className="text-muted-foreground mb-3 text-sm font-semibold tracking-wide uppercase">
            Clients
          </h2>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {CLIENTS.map((client) => (
              <ClientCard
                key={client.id}
                client={client}
                openAlerts={openAlertCount(client.id)}
              />
            ))}
          </div>
        </section>

        <div className="grid gap-4 xl:grid-cols-5">
          <Card className="xl:col-span-3">
            <CardHeader>
              <CardTitle className="text-base">Needs attention</CardTitle>
              <CardDescription>Unacknowledged alerts across all sites</CardDescription>
            </CardHeader>
            <CardContent>
              <AlertsTable alerts={recentAlerts} showClient />
              <div className="mt-3 text-right">
                <Button variant="outline" size="sm" render={<Link href="/alerts" />}>
                  View all alerts
                </Button>
              </div>
            </CardContent>
          </Card>

          <div className="space-y-4 xl:col-span-2">
            <div className="flex items-center gap-2">
              <Sparkles className="size-4 text-amber-500" />
              <h2 className="text-muted-foreground text-sm font-semibold tracking-wide uppercase">
                Top insights
              </h2>
            </div>
            {topInsights.map((insight) => (
              <InsightCard
                key={insight.id}
                insight={insight}
                clientName={getClient(insight.clientId)?.name}
              />
            ))}
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              render={<Link href="/insights" />}
            >
              All insights
            </Button>
          </div>
        </div>
      </main>
    </>
  );
}

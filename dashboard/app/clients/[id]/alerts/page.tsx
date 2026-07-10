import { notFound } from "next/navigation";

import { AlertsTable } from "@/components/alerts-table";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { alertsForClient } from "@/lib/data/alerts";
import { getClient } from "@/lib/data/clients";

export default async function ClientAlertsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const client = getClient(id);
  if (!client) notFound();
  const alerts = alertsForClient(id);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Alerts</CardTitle>
        <CardDescription>
          Everything this site&apos;s rule kernels and health monitors raised recently.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <AlertsTable alerts={alerts} />
      </CardContent>
    </Card>
  );
}

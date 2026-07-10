import { AlertsTable } from "@/components/alerts-table";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ALERTS } from "@/lib/data/alerts";

export const metadata = { title: "Alerts — FrameInsight" };

export default function AlertsPage() {
  const open = ALERTS.filter((a) => !a.acknowledged);
  const critical = ALERTS.filter((a) => a.severity === "alert");

  return (
    <>
      <PageHeader
        title="Alerts"
        description="Rule-kernel alerts and system-health events from every edge box."
      />
      <main className="flex-1 space-y-4 p-4 md:p-6">
        <Tabs defaultValue="open">
          <TabsList>
            <TabsTrigger value="open">Open ({open.length})</TabsTrigger>
            <TabsTrigger value="critical">Critical ({critical.length})</TabsTrigger>
            <TabsTrigger value="all">All ({ALERTS.length})</TabsTrigger>
          </TabsList>
          <TabsContent value="open">
            <Card>
              <CardContent>
                <AlertsTable alerts={open} showClient />
              </CardContent>
            </Card>
          </TabsContent>
          <TabsContent value="critical">
            <Card>
              <CardContent>
                <AlertsTable alerts={critical} showClient />
              </CardContent>
            </Card>
          </TabsContent>
          <TabsContent value="all">
            <Card>
              <CardContent>
                <AlertsTable alerts={ALERTS} showClient />
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </main>
    </>
  );
}

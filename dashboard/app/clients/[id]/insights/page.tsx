import { Sparkles } from "lucide-react";
import { notFound } from "next/navigation";

import { InsightCard } from "@/components/insight-card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { getClient } from "@/lib/data/clients";
import { insightsForClient } from "@/lib/data/insights";

export default async function ClientInsightsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const client = getClient(id);
  if (!client) notFound();
  const insights = insightsForClient(id);
  return (
    <div className="space-y-4">
      <Alert>
        <Sparkles className="size-4" />
        <AlertTitle>Simulated preview</AlertTitle>
        <AlertDescription>
          Sample output in the final shape — the LLM digest pipeline will replace the
          generator, not the UI.
        </AlertDescription>
      </Alert>
      {insights.length === 0 ? (
        <p className="text-muted-foreground text-sm">
          No insights yet for this site — the weekly digest needs at least one full week
          of events.
        </p>
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {insights.map((insight) => (
            <InsightCard key={insight.id} insight={insight} />
          ))}
        </div>
      )}
    </div>
  );
}

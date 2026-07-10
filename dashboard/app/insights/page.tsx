import { Sparkles } from "lucide-react";

import { InsightCard } from "@/components/insight-card";
import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { INSIGHTS } from "@/lib/data/insights";
import { getClient } from "@/lib/data/clients";

export const metadata = { title: "AI Insights — FrameInsight" };

export default function InsightsPage() {
  const ordered = [...INSIGHTS].sort((a, b) => {
    const rank = { high: 0, medium: 1, low: 2 } as const;
    return rank[a.impact] - rank[b.impact] || a.hoursAgo - b.hoursAgo;
  });

  return (
    <>
      <PageHeader
        title="AI Insights"
        description="What the numbers mean — anomalies, optimizations, and trends distilled from each site's events."
      />
      <main className="flex-1 space-y-4 p-4 md:p-6">
        <Alert>
          <Sparkles className="size-4" />
          <AlertTitle>Simulated preview</AlertTitle>
          <AlertDescription>
            These insights are hand-written samples in the exact shape the upcoming LLM
            pipeline will produce (weekly digest per client, computed from event
            aggregates + alert history). The UI is final; only the generator changes.
          </AlertDescription>
        </Alert>
        <div className="grid gap-4 xl:grid-cols-2">
          {ordered.map((insight) => (
            <InsightCard
              key={insight.id}
              insight={insight}
              clientName={getClient(insight.clientId)?.name}
            />
          ))}
        </div>
      </main>
    </>
  );
}

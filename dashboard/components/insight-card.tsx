import { Activity, Lightbulb, Sparkles, TrendingUp, Wrench } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { fmtAgo } from "@/lib/seed";
import type { Insight, InsightCategory } from "@/lib/types";

const CATEGORY_META: Record<
  InsightCategory,
  { label: string; icon: typeof Sparkles }
> = {
  anomaly: { label: "Anomaly", icon: Activity },
  optimization: { label: "Optimization", icon: Wrench },
  trend: { label: "Trend", icon: TrendingUp },
  health: { label: "System health", icon: Sparkles },
};

export function InsightCard({
  insight,
  clientName,
}: {
  insight: Insight;
  clientName?: string;
}) {
  const meta = CATEGORY_META[insight.category];
  const Icon = meta.icon;
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="gap-1">
            <Icon className="size-3" /> {meta.label}
          </Badge>
          <Badge
            variant="outline"
            className={cn(
              "capitalize",
              insight.impact === "high" &&
                "border-red-500/40 bg-red-500/10 text-red-600 dark:text-red-400",
              insight.impact === "medium" &&
                "border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400",
            )}
          >
            {insight.impact} impact
          </Badge>
          <span className="text-muted-foreground ml-auto text-xs">
            {clientName ? `${clientName} · ` : ""}
            {fmtAgo(insight.hoursAgo * 60)} · confidence{" "}
            {Math.round(insight.confidence * 100)}%
          </span>
        </div>
        <CardTitle className="text-base">{insight.title}</CardTitle>
        <CardDescription>{insight.body}</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="bg-muted/50 flex items-start gap-2 rounded-lg border p-3 text-sm">
          <Lightbulb className="mt-0.5 size-4 shrink-0 text-amber-500" />
          <div>
            <span className="font-medium">Suggested action: </span>
            {insight.suggestedAction}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { Kpi } from "@/lib/types";

export function KpiCard({ kpi }: { kpi: Kpi }) {
  const dir = kpi.deltaDirection ?? "flat";
  const good =
    dir === "flat" ? null : (dir === "up") === (kpi.upIsGood ?? true);
  const DeltaIcon = dir === "up" ? ArrowUpRight : dir === "down" ? ArrowDownRight : Minus;
  return (
    <Card className="py-4">
      <CardContent className="px-4">
        <div className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
          {kpi.label}
        </div>
        <div className="mt-1 text-2xl font-semibold tabular-nums">{kpi.value}</div>
        {kpi.delta ? (
          <div
            className={cn(
              "mt-1 flex items-center gap-1 text-xs",
              good === null
                ? "text-muted-foreground"
                : good
                  ? "text-emerald-600 dark:text-emerald-400"
                  : "text-red-600 dark:text-red-400",
            )}
          >
            <DeltaIcon className="size-3" />
            {kpi.delta}
          </div>
        ) : kpi.hint ? (
          <div className="text-muted-foreground mt-1 text-xs">{kpi.hint}</div>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function KpiRow({ kpis }: { kpis: Kpi[] }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {kpis.map((kpi) => (
        <KpiCard key={kpi.label} kpi={kpi} />
      ))}
    </div>
  );
}

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { Severity } from "@/lib/types";

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "capitalize",
        severity === "alert" &&
          "border-red-500/40 bg-red-500/10 text-red-600 dark:text-red-400",
        severity === "warning" &&
          "border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400",
        severity === "info" && "text-muted-foreground",
      )}
    >
      {severity}
    </Badge>
  );
}

export function StatusDot({
  ok,
  label,
}: {
  ok: boolean;
  label?: string;
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={cn(
          "size-2 rounded-full",
          ok ? "bg-emerald-500" : "bg-red-500 animate-pulse",
        )}
      />
      {label ? <span className="text-sm">{label}</span> : null}
    </span>
  );
}

/** Simple 0–100 signal strength as 4 bars. */
export function SignalBars({ value }: { value: number }) {
  const active = value <= 0 ? 0 : Math.max(1, Math.round((value / 100) * 4));
  return (
    <span className="inline-flex items-end gap-0.5" title={`${value}%`}>
      {[1, 2, 3, 4].map((bar) => (
        <span
          key={bar}
          className={cn(
            "w-1 rounded-sm",
            bar <= active ? "bg-emerald-500" : "bg-muted-foreground/25",
          )}
          style={{ height: `${4 + bar * 3}px` }}
        />
      ))}
    </span>
  );
}

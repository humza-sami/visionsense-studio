"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const TABS = [
  { slug: "", label: "Overview" },
  { slug: "/cameras", label: "Cameras" },
  { slug: "/alerts", label: "Alerts" },
  { slug: "/reports", label: "Reports" },
  { slug: "/insights", label: "Insights" },
];

export function ClientTabs({ clientId }: { clientId: string }) {
  const pathname = usePathname();
  const base = `/clients/${clientId}`;
  return (
    <nav className="flex gap-1 overflow-x-auto border-b px-4 md:px-6">
      {TABS.map((tab) => {
        const href = base + tab.slug;
        const active = pathname === href;
        return (
          <Link
            key={tab.slug}
            href={href}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-sm whitespace-nowrap transition-colors",
              active
                ? "border-primary text-foreground font-medium"
                : "text-muted-foreground hover:text-foreground border-transparent",
            )}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}

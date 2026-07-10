import type { ReactNode } from "react";

import { ModeToggle } from "@/components/mode-toggle";
import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { NOW_LABEL } from "@/lib/seed";

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="bg-background sticky top-0 z-10 flex flex-col gap-1 border-b px-4 py-3 md:px-6">
      <div className="flex items-center gap-2">
        <SidebarTrigger className="-ml-1" />
        <Separator orientation="vertical" className="mr-1 h-4" />
        <h1 className="text-base font-semibold md:text-lg">{title}</h1>
        <div className="ml-auto flex items-center gap-2">
          {actions}
          <span className="text-muted-foreground hidden text-xs md:inline">
            {NOW_LABEL}
          </span>
          <ModeToggle />
        </div>
      </div>
      {description ? (
        <p className="text-muted-foreground pl-8 text-sm">{description}</p>
      ) : null}
    </header>
  );
}

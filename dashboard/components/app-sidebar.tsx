"use client";

import { Bell, Calculator, LayoutDashboard, ScanEye, Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { VERTICALS } from "@/lib/verticals";
import type { Client } from "@/lib/types";

interface AppSidebarProps {
  clients: Pick<Client, "id" | "name" | "vertical">[];
  openAlerts: number;
  openAlertsByClient: Record<string, number>;
}

export function AppSidebar({ clients, openAlerts, openAlertsByClient }: AppSidebarProps) {
  const pathname = usePathname();

  return (
    <Sidebar>
      <SidebarHeader>
        <div className="flex items-center gap-2 px-2 py-1.5">
          <div className="bg-primary text-primary-foreground flex size-8 items-center justify-center rounded-lg">
            <ScanEye className="size-5" />
          </div>
          <div className="leading-tight">
            <div className="text-sm font-semibold">FrameInsight</div>
            <div className="text-muted-foreground text-xs">Analytics Cloud</div>
          </div>
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={pathname === "/"}
                  render={<Link href="/" />}
                >
                  <LayoutDashboard />
                  <span>Fleet overview</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={pathname === "/alerts"}
                  render={<Link href="/alerts" />}
                >
                  <Bell />
                  <span>Alerts</span>
                </SidebarMenuButton>
                {openAlerts > 0 && <SidebarMenuBadge>{openAlerts}</SidebarMenuBadge>}
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={pathname === "/insights"}
                  render={<Link href="/insights" />}
                >
                  <Sparkles />
                  <span>AI Insights</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  render={<a href="/deal-simulator.html" target="_blank" rel="noopener noreferrer" />}
                >
                  <Calculator />
                  <span>Deal Simulator</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel>Clients</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {clients.map((client) => {
                const Icon = VERTICALS[client.vertical].icon;
                const open = openAlertsByClient[client.id] ?? 0;
                return (
                  <SidebarMenuItem key={client.id}>
                    <SidebarMenuButton
                      isActive={pathname.startsWith(`/clients/${client.id}`)}
                      render={<Link href={`/clients/${client.id}`} />}
                    >
                      <Icon />
                      <span>{client.name}</span>
                    </SidebarMenuButton>
                    {open > 0 && <SidebarMenuBadge>{open}</SidebarMenuBadge>}
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <div className="text-muted-foreground flex items-center justify-between px-2 py-1 text-xs">
          <span>v0.1 · simulated data</span>
          <Badge variant="outline" className="text-[10px]">
            demo
          </Badge>
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}

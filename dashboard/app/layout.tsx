import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { AppSidebar } from "@/components/app-sidebar";
import { ThemeProvider } from "@/components/theme-provider";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { CLIENTS } from "@/lib/data/clients";
import { openAlertCount } from "@/lib/data/alerts";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "FrameInsight Analytics Cloud",
  description:
    "Multi-client CCTV analytics: live health, alerts, and per-vertical dashboards on FrameInsight edge events.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const clients = CLIENTS.map(({ id, name, vertical }) => ({ id, name, vertical }));
  const openAlertsByClient = Object.fromEntries(
    clients.map((c) => [c.id, openAlertCount(c.id)]),
  );
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
          <SidebarProvider>
            <AppSidebar
              clients={clients}
              openAlerts={openAlertCount()}
              openAlertsByClient={openAlertsByClient}
            />
            <SidebarInset>{children}</SidebarInset>
          </SidebarProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}

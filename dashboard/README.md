# FrameInsight Analytics Cloud — online dashboard

The multi-client web dashboard for FrameInsight: every client's edge box streams
events (rule alerts, aggregates, heartbeats) to the cloud, and this app turns
them into **per-vertical dashboards, fleet health, alerts, monthly reports, and
AI insights**.

> **Status: fully working UI on simulated data.** Every type in `lib/types.ts`
> mirrors the FrameInsight edge event schema, so wiring Supabase in later
> replaces `lib/data/*` — not the UI.

## Stack

- **Next.js 16** (App Router, TypeScript, all pages statically prerendered)
- **Tailwind CSS v4 + shadcn/ui** (base-nova style, Base UI primitives)
- **Recharts** via shadcn chart wrappers
- Dark/light theme (`next-themes`), responsive, collapsible sidebar

## Run it

```bash
npm install
npm run dev        # http://localhost:3000
npm run build      # type-checks + prerenders every route
```

Requires Node 20+.

## What's inside

| Route | What it shows |
|---|---|
| `/` | Fleet overview — all clients, camera health, open alerts, events/day, top insights |
| `/alerts` | Global alert feed (open / critical / all) |
| `/insights` | AI insights across the fleet (simulated LLM output, final shape) |
| `/clients/[id]` | Client dashboard rendered by that client's **vertical skin** |
| `/clients/[id]/cameras` | Edge-server health (GPU/NVDEC/VRAM/CPU/uplink/disk) + per-camera status |
| `/clients/[id]/alerts` | The client's alert history |
| `/clients/[id]/reports` | Monthly report — the billable deliverable (headline KPIs, week-by-week, narrative) |
| `/clients/[id]/insights` | The client's AI insight digest |

## Verticals = skins

Each industry gets its own dashboard layout ("skin") fed by its own metric
shapes, while alerts/cameras/reports/insights pages are shared:

| Vertical | Demo client | Skin highlights |
|---|---|---|
| Education | Greenfield School | Gate entries/exits, classroom headcounts vs enrollment, water-cooler dwell |
| Retail | Metro Mart, Style Hub | Footfall in/out, checkout queue trigger, zone dwell + visit share |
| Manufacturing | Sunrise Textiles | PPE compliance %, violations by hour (shift-change clusters), restricted-zone intrusions, per-line activity |
| Restaurant | Kabab House | Guests/hour, live table occupancy, turnover by section |
| Warehouse | Swift Logistics | Dock-bay dwell vs SLA, truck turnaround, forklift–pedestrian near-misses |

**Adding a vertical** is three self-contained steps, nothing else changes:

1. `lib/data/metrics.ts` — add a `<vertical>Metrics()` generator (later: a Supabase query)
2. `components/verticals/<vertical>-skin.tsx` — compose `KpiRow` + chart cards + a table
3. Register it in `components/verticals/index.tsx` and `lib/verticals.ts`

## Architecture / where real data plugs in

```
edge boxes ──events──► Supabase (events, aggregates, heartbeats)
                            │
                 lib/data/*  ◄── replace these simulated generators
                            │    with Supabase queries (same return types)
                            ▼
              app/ pages ── components/verticals/* skins ── shadcn charts
```

- `lib/types.ts` — the contract. `Camera`, `EdgeHealth`, `AlertItem`, `Insight`,
  `MonthlyReport` are exactly what the edge runtime + heartbeats provide today
  (`camera_stalled`, per-camera `last_frame_age_s`, GPU/NVDEC/VRAM utilization).
- `lib/seed.ts` — deterministic PRNG + frozen clock so the simulated data is
  identical on server and client (no hydration mismatches). Delete alongside
  the generators when real data lands.
- `lib/data/insights.ts` — hand-written samples of the future **LLM digest**
  (weekly, per client, computed from aggregates + alert history). The
  `Insight` shape (category, impact, confidence, suggested action) is final.

## Roadmap to production

1. **Supabase**: replace `lib/data/*` with queries (`events`, `aggregates_1m`,
   `heartbeats` tables; RLS per client org). Realtime subscription for the
   alerts feed.
2. **Auth**: Supabase Auth — internal staff see the fleet, a client org sees
   only its own site(s). The layout already splits fleet vs client scopes.
3. **LLM insights**: scheduled Edge Function that feeds each client's weekly
   aggregates to an LLM and inserts `Insight` rows.
4. **PDF reports**: render `/clients/[id]/reports` to PDF on a monthly cron —
   the page is already the report layout.

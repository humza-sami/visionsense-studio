"use client";

/**
 * Thin, reusable chart wrappers over shadcn's ChartContainer + recharts.
 * Vertical skins compose these with their own data — no skin talks to
 * recharts directly.
 */

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  XAxis,
  YAxis,
} from "recharts";

import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";

export interface SeriesDef {
  key: string;
  label: string;
  /** chart palette slot 1–5 */
  color?: number;
}

function toConfig(series: SeriesDef[]): ChartConfig {
  return Object.fromEntries(
    series.map((s, i) => [
      s.key,
      { label: s.label, color: `var(--chart-${s.color ?? i + 1})` },
    ]),
  );
}

export function TrendAreaChart<T extends object>({
  data,
  x,
  series,
  className,
}: {
  data: T[];
  x: string;
  series: SeriesDef[];
  className?: string;
}) {
  const config = toConfig(series);
  return (
    <ChartContainer config={config} className={className ?? "h-56 w-full"}>
      <AreaChart data={data} margin={{ left: -12, right: 8, top: 8 }}>
        <CartesianGrid vertical={false} strokeDasharray="3 3" />
        <XAxis dataKey={x} tickLine={false} axisLine={false} tickMargin={6} />
        <YAxis tickLine={false} axisLine={false} width={40} />
        <ChartTooltip content={<ChartTooltipContent />} />
        {series.length > 1 && <ChartLegend content={<ChartLegendContent />} />}
        {series.map((s) => (
          <Area
            key={s.key}
            dataKey={s.key}
            type="monotone"
            fill={`var(--color-${s.key})`}
            fillOpacity={0.25}
            stroke={`var(--color-${s.key})`}
            strokeWidth={2}
          />
        ))}
      </AreaChart>
    </ChartContainer>
  );
}

export function BarsChart<T extends object>({
  data,
  x,
  series,
  stacked = false,
  className,
}: {
  data: T[];
  x: string;
  series: SeriesDef[];
  stacked?: boolean;
  className?: string;
}) {
  const config = toConfig(series);
  return (
    <ChartContainer config={config} className={className ?? "h-56 w-full"}>
      <BarChart data={data} margin={{ left: -12, right: 8, top: 8 }}>
        <CartesianGrid vertical={false} strokeDasharray="3 3" />
        <XAxis dataKey={x} tickLine={false} axisLine={false} tickMargin={6} />
        <YAxis tickLine={false} axisLine={false} width={40} />
        <ChartTooltip content={<ChartTooltipContent />} />
        {series.length > 1 && <ChartLegend content={<ChartLegendContent />} />}
        {series.map((s) => (
          <Bar
            key={s.key}
            dataKey={s.key}
            fill={`var(--color-${s.key})`}
            radius={stacked ? 0 : 4}
            stackId={stacked ? "stack" : undefined}
          />
        ))}
      </BarChart>
    </ChartContainer>
  );
}

export function TrendLineChart<T extends object>({
  data,
  x,
  series,
  yDomain,
  className,
}: {
  data: T[];
  x: string;
  series: SeriesDef[];
  yDomain?: [number, number];
  className?: string;
}) {
  const config = toConfig(series);
  return (
    <ChartContainer config={config} className={className ?? "h-56 w-full"}>
      <LineChart data={data} margin={{ left: -12, right: 8, top: 8 }}>
        <CartesianGrid vertical={false} strokeDasharray="3 3" />
        <XAxis dataKey={x} tickLine={false} axisLine={false} tickMargin={6} />
        <YAxis tickLine={false} axisLine={false} width={40} domain={yDomain} />
        <ChartTooltip content={<ChartTooltipContent />} />
        {series.map((s) => (
          <Line
            key={s.key}
            dataKey={s.key}
            type="monotone"
            stroke={`var(--color-${s.key})`}
            strokeWidth={2}
            dot={false}
          />
        ))}
      </LineChart>
    </ChartContainer>
  );
}

export function ShareDonutChart<T extends object>({
  data,
  nameKey,
  valueKey,
  className,
}: {
  data: T[];
  nameKey: keyof T & string;
  valueKey: keyof T & string;
  className?: string;
}) {
  const config: ChartConfig = Object.fromEntries(
    data.map((d, i) => [
      String(d[nameKey]),
      { label: String(d[nameKey]), color: `var(--chart-${(i % 5) + 1})` },
    ]),
  );
  return (
    <ChartContainer config={config} className={className ?? "h-56 w-full"}>
      <PieChart>
        <ChartTooltip content={<ChartTooltipContent nameKey={nameKey} />} />
        <Pie
          data={data}
          dataKey={valueKey}
          nameKey={nameKey}
          innerRadius={50}
          strokeWidth={4}
        >
          {data.map((d, i) => (
            <Cell key={String(d[nameKey])} fill={`var(--chart-${(i % 5) + 1})`} />
          ))}
        </Pie>
        <ChartLegend content={<ChartLegendContent nameKey={nameKey} />} />
      </PieChart>
    </ChartContainer>
  );
}

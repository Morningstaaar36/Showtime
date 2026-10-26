import { Wind } from "lucide-react";
import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { CountdownOut } from "@/api/types";
import { PanelTitle } from "@/components/ui/misc";
import { fmtHM, fmtNum } from "@/lib/format";
import { t } from "@/i18n";

interface Forecast {
  times?: string[];
  gust_ms?: (number | null)[];
  source?: string;
}

/** Forecast gusts vs the stage wind limit, with event start, hazard and latest-start markers. */
export function WindPanel({ data, eventStart }: { data: CountdownOut | undefined; eventStart?: string | null }) {
  const wind = data?.hazards.find((h) => h.source === "hazard_wind");
  const details = (wind?.details ?? {}) as Record<string, unknown>;
  const fc = details.forecast as Forecast | undefined;
  const limit = Number(details.limit_ms ?? 0);
  if (!fc?.times?.length) return null;
  // key on the full local hour ("2026-10-16T11:00") so a two-day forecast has no duplicate ticks
  const all = fc.times.map((t, i) => ({ t: t.slice(0, 16), g: fc.gust_ms?.[i] ?? null }));
  // show the event day when the forecast covers it (two days squeeze the markers together)
  const day = eventStart?.slice(0, 10);
  const onDay = day ? all.filter((r) => r.t.startsWith(day)) : [];
  const rows = onDay.length >= 12 ? onDay : all;
  const hourKey = (iso: string | null | undefined) => (iso ? `${iso.slice(0, 13)}:00` : null);
  const start = hourKey(eventStart);
  const cd = data?.countdown;
  const hazard = cd?.t_hazard_iso ? fmtHM(cd.t_hazard_iso) : null;
  const latest = cd?.t_latest_iso ? fmtHM(cd.t_latest_iso) : null;
  const peak = Math.max(0, ...rows.map((r) => r.g ?? 0));
  return (
    <section className="space-y-2">
      <PanelTitle>{t("ui.windpanel.wind_on_the_day")}</PanelTitle>
      <figure>
        <figcaption className="sr-only">
          {t("ui.windpanel.summary", { peak: fmtNum(peak, 1), limit: fmtNum(limit, 1) })}
        </figcaption>
        <div className="h-40">
          <ResponsiveContainer>
            <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="gust" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--signal)" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="var(--signal)" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" vertical={false} />
              <XAxis dataKey="t" tick={{ fontSize: 10, fill: "var(--muted)" }} stroke="var(--border)"
                     interval={rows.length > 30 ? 11 : 2} tickFormatter={(v: string) => v.slice(11, 16)} />
              <YAxis tick={{ fontSize: 10, fill: "var(--muted)" }} width={30} stroke="var(--border)" domain={[0, Math.ceil(Math.max(peak, limit) + 3)]} />
              <Tooltip formatter={(v) => [`${fmtNum(Number(v), 1)} m/s`, "Gust"]} labelFormatter={(v) => String(v).replace("T", " ")}
                       contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }} />
              <Area dataKey="g" type="monotone" stroke="none" fill="url(#gust)" isAnimationActive={false} />
              <Line dataKey="g" type="monotone" stroke="var(--signal)" strokeWidth={1.8} dot={false} isAnimationActive={false} />
              {limit > 0 && <ReferenceLine y={limit} stroke="var(--danger)" strokeDasharray="5 3"
                                           label={{ value: `stage limit ${fmtNum(limit, 1)}`, fontSize: 10, fill: "var(--danger)", position: "insideTopLeft" }} />}
              {start && <ReferenceLine x={start} stroke="var(--ink)" strokeDasharray="2 2"
                                       label={{ value: "gates", fontSize: 10, fill: "var(--muted)", position: "insideTop" }} />}
              {latest && <ReferenceLine x={hourKey(cd?.t_latest_iso) ?? undefined} stroke="var(--egress)" strokeWidth={2}
                                        label={{ value: "evacuate", fontSize: 10, fill: "var(--egress)", position: "insideBottom" }} />}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </figure>
      <p className="flex items-start gap-1.5 text-xs text-muted">
        <Wind className="mt-0.5 size-3.5 shrink-0" />
        <span>
          {hazard ? t("ui.windpanel.reach_limit", { at: hazard }) : t("ui.windpanel.below_limit")}
          {latest ? ` ${t("ui.windpanel.start_by", { at: latest })}` : ""} {t("ui.windpanel.source", { source: fc.source ?? "Open-Meteo" })}
        </span>
      </p>
    </section>
  );
}

/** Number, time and unit formatting. Metric by default; imperial is a Settings toggle. */
import { t } from "@/i18n";

export type Units = "metric" | "imperial";

const M_TO_FT = 3.28084;

export function fmtInt(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "–";
  return Math.round(n).toLocaleString("en-US");
}

export function fmtNum(n: number | null | undefined, digits = 1): string {
  if (n == null || Number.isNaN(n)) return "–";
  return n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** Seconds as m:ss (or h:mm:ss). */
export function fmtClock(s: number | null | undefined): string {
  if (s == null || Number.isNaN(s)) return "–:––";
  const sign = s < 0 ? "−" : "";
  const t = Math.abs(Math.round(s));
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const sec = t % 60;
  const mm = h ? String(m).padStart(2, "0") : String(m);
  return `${sign}${h ? `${h}:` : ""}${mm}:${String(sec).padStart(2, "0")}`;
}

/** Seconds as "4 min 12 s" for prose. */
export function fmtDuration(s: number | null | undefined): string {
  if (s == null || Number.isNaN(s)) return "–";
  const secs = Math.round(Math.abs(s));
  if (secs < 60) return t("units.n_s", { n: secs });
  const m = Math.floor(secs / 60);
  const r = secs % 60;
  return r ? t("units.n_min_s", { m, s: r }) : t("units.n_min", { n: m });
}

export function fmtLength(m: number | null | undefined, units: Units, digits = 1): string {
  if (m == null) return "–";
  return units === "imperial" ? t("units.n_ft", { n: fmtNum(m * M_TO_FT, digits) }) : t("units.n_m", { n: fmtNum(m, digits) });
}

/** Density in people per m² (or per 10 ft² in imperial, the common US crowd unit). */
export function fmtDensity(ppm2: number | null | undefined, units: Units): string {
  if (ppm2 == null) return "–";
  if (units === "imperial") return t("units.density_imperial", { n: fmtNum(ppm2 / (M_TO_FT * M_TO_FT) * 10, 1) });
  return t("units.density", { n: fmtNum(ppm2, 1) });
}

export function fmtSpeed(ms: number | null | undefined, units: Units): string {
  if (ms == null) return "–";
  return units === "imperial" ? t("units.speed_imperial", { n: fmtNum(ms * 2.23694, 0) }) : t("units.speed", { n: fmtNum(ms, 1), kmh: fmtNum(ms * 3.6, 0) });
}

export function fmtMoney(usd: number | null | undefined): string {
  if (usd == null) return "$–";
  if (usd === 0) return "$0.00";
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}

export function fmtTokens(n: number | null | undefined): string {
  if (n == null) return "–";
  if (n >= 1_000_000) return `${fmtNum(n / 1_000_000, 1)}M`;
  if (n >= 1000) return `${fmtNum(n / 1000, 1)}k`;
  return String(n);
}

/** "18:49" from an ISO local datetime. */
export function fmtHM(iso: string | null | undefined): string {
  if (!iso) return "–";
  const m = /T(\d{2}):(\d{2})/.exec(iso);
  return m ? `${m[1]}:${m[2]}` : iso;
}

export function fmtRelative(iso: string): string {
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return t("units.just_now");
  if (diff < 3600) return t("units.min_ago", { n: Math.floor(diff / 60) });
  if (diff < 86400) return t("units.h_ago", { n: Math.floor(diff / 3600) });
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

/** The server's "based on" text without internal run ids ("full simulation, run r_20d2…" →
 * "full simulation"); empty when nothing but an id is left. */
export function withoutRunIds(text: string | null | undefined): string {
  return (text ?? "")
    .replace(/,?\s*\brun r_[0-9a-f]{6,}\b/gi, "")
    .replace(/\(\s*\)/g, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

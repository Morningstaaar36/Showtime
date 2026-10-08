/** Number, time and unit formatting. Metric by default; imperial is a Settings toggle. */

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
  const t = Math.round(Math.abs(s));
  if (t < 60) return `${t} s`;
  const m = Math.floor(t / 60);
  const r = t % 60;
  return r ? `${m} min ${r} s` : `${m} min`;
}

export function fmtLength(m: number | null | undefined, units: Units, digits = 1): string {
  if (m == null) return "–";
  return units === "imperial" ? `${fmtNum(m * M_TO_FT, digits)} ft` : `${fmtNum(m, digits)} m`;
}

/** Density in people per m² (or per 10 ft² in imperial, the common US crowd unit). */
export function fmtDensity(ppm2: number | null | undefined, units: Units): string {
  if (ppm2 == null) return "–";
  if (units === "imperial") return `${fmtNum(ppm2 / (M_TO_FT * M_TO_FT) * 10, 1)} per 10 ft²`;
  return `${fmtNum(ppm2, 1)} people per m²`;
}

export function fmtSpeed(ms: number | null | undefined, units: Units): string {
  if (ms == null) return "–";
  return units === "imperial" ? `${fmtNum(ms * 2.23694, 0)} mph` : `${fmtNum(ms, 1)} m/s (${fmtNum(ms * 3.6, 0)} km/h)`;
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
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

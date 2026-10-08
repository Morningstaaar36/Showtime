import { useGlossary } from "@/api/queries";
import { AppHeader } from "@/app/AppHeader";
import { Kbd } from "@/components/ui/misc";
import { t } from "@/i18n";

const SHORTCUTS: [string[], string][] = [
  [["Ctrl", "Z"], "Undo"], [["Ctrl", "Shift", "Z"], "Redo"], [["Space"], "Play or pause the replay"],
  [["R"], "Run stress test"], [["/"], "Type a change"], [["V"], "Select and move"], [["E"], "Add exit"],
  [["B"], "Draw barrier"], [["Z"], "Draw zone"], [["M"], "Measure"], [["X"], "Block or unblock an exit"], [["Esc"], "Cancel the current tool"],
  [["1"], "Plan"], [["2"], "Simulate"], [["3"], "Red Team"], [["4"], "Report"],
];

const NUMBERS: [string, string][] = [
  ["Instant estimate (formula)", "Walking distances on a grid that respects walls, a min-cost flow that assigns people to exits within each exit's capacity (1.3 people per metre of width per second, SFPE), and a queue at every exit. Takes a few milliseconds. Used for 'Break it yourself' and to rank attacks."],
  ["Confirmed by simulation", "Every person is simulated with JuPedSim's collision-free speed model (Δt 0.025–0.05 s) inside an isolated Docker sandbox with no network. Body radius 0.22 m, walking speed 1.34 ± 0.26 m/s (5% slow walkers). Upper floors are simulated first; stairs pass at most 1 person per metre per second."],
  ["Density", "People counted on a 1 m grid, smoothed over about 2–3 m² and divided by the walkable area of each cell. Warning at 3.5, danger at 5 people per m² (sustained for at least 5 s)."],
  ["Evacuation time (95%)", "Seconds until 95% of people have passed an exit, from the moment they start moving. Pre-movement time is added separately in the countdown."],
  ["Stage wind limit", "Pynite frame model of the stage roof with ASCE 7 wind pressure q = 0.613·Kz·Kzt·Kd·V². Gust speed at which ballast stops resisting uplift, sliding or overturning. A screening estimate, not a structural design."],
  ["Latest safe time to start evacuating", "T_hazard − (pre-movement + evacuation time × safety factor). The hazard is the first forecast gust above the wind limit (Open-Meteo) or the scenario time when a route is lost."],
];

export function HelpPage() {
  const glossary = useGlossary();
  return (
    <div className="min-h-full">
      <AppHeader />
      <main id="main" className="mx-auto grid max-w-6xl gap-10 px-4 py-10 lg:grid-cols-[1fr_320px]">
        <div className="space-y-10">
          <section>
            <h1 className="text-2xl font-semibold tracking-tight">{t("help.numbers")}</h1>
            <p className="mt-2 max-w-prose text-muted">Every number in Showtime comes from a formula, the simulator or a sourced dataset. The AI agents choose what to test and what to change; they never invent a measurement.</p>
            <dl className="mt-6 space-y-5">
              {NUMBERS.map(([k, v]) => (
                <div key={k} className="max-w-prose">
                  <dt className="font-semibold">{k}</dt>
                  <dd className="mt-1 text-sm text-muted">{v}</dd>
                </div>
              ))}
            </dl>
          </section>
          <section>
            <h2 className="text-xl font-semibold tracking-tight">{t("help.glossary")}</h2>
            <dl className="mt-4 grid gap-4 sm:grid-cols-2">
              {(glossary.data ?? []).map((g) => (
                <div key={g.term} className="rounded-[10px] border border-border bg-surface p-4">
                  <dt className="font-medium">{g.term}</dt>
                  <dd className="mt-1 text-sm text-muted">{g.definition}</dd>
                </div>
              ))}
            </dl>
          </section>
          <section className="max-w-prose">
            <h2 className="text-xl font-semibold tracking-tight">{t("help.limits")}</h2>
            <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-muted">
              <li>{t("app.disclaimer")} Licensed engineers and authorities sign off on real plans.</li>
              <li>Crowd models simulate walking and queuing, not pushing forces; density is the warning signal for crush risk.</li>
              <li>Stairs are modelled as a queue with a fixed throughput, not as a walkable ramp.</li>
              <li>Weather reanalysis smooths out thunderstorm downbursts; enter a manual gust when storms are possible.</li>
              <li>Templates are illustrative; check dimensions against your real drawings.</li>
            </ul>
          </section>
        </div>
        <aside>
          <h2 className="text-sm font-semibold">{t("help.shortcuts")}</h2>
          <ul className="mt-3 divide-y divide-border rounded-[10px] border border-border bg-surface">
            {SHORTCUTS.map(([keys, label]) => (
              <li key={label} className="flex items-center justify-between gap-3 px-4 py-2 text-sm">
                <span>{label}</span>
                <span className="flex gap-1">{keys.map((k) => <Kbd key={k}>{k}</Kbd>)}</span>
              </li>
            ))}
          </ul>
        </aside>
      </main>
    </div>
  );
}

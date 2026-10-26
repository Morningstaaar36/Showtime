/** "The AI didn't answer, so built-in rules wrote …": the plan says when the rules stood in for
 * an AI agent during an AI test (the session summary's `stood_in`: agent -> why). */
import { t } from "@/i18n";

const PARTS = ["red_team", "blue_team", "judge"] as const;

export function stoodInLine(stoodIn: Record<string, string> | null | undefined): { text: string; why: string } | null {
  const parts = PARTS.filter((a) => stoodIn?.[a]);
  if (!stoodIn || !parts.length) return null;
  const names = parts.map((a) => t(`plan.stood_in_${a}`));
  const list = names.length === 1 ? names[0] : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
  return { text: t("plan.stood_in", { what: list }), why: stoodIn[parts[0]] };
}

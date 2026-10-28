import { CornerDownLeft, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ApiError } from "@/api/client";
import { useTextEdit } from "@/api/queries";
import type { EditOut } from "@/api/types";
import { Kbd, Spinner } from "@/components/ui/misc";
import { t, tItems } from "@/i18n";
import { isTypingTarget } from "@/lib/keyboard";
import { UNDO_TOAST_ID } from "@/lib/utils";

/** "Edit by text": the Venue agent turns a sentence into an edit; Undo is one click away. */
export function CommandBar({ projectId, onUndo }: { projectId: string; onUndo: () => void }) {
  const [text, setText] = useState("");
  const [result, setResult] = useState<EditOut | null>(null);
  const [focused, setFocused] = useState(false);
  const edit = useTextEdit(projectId);
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "/" && !isTypingTarget(e.target)) {
        e.preventDefault();
        ref.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const submit = (value: string) => {
    if (!value.trim() || edit.isPending) return;
    setResult(null);
    edit.mutate({ text: value, apply: true }, {
      onSuccess: (r) => {
        setResult(r);
        if (r.status === "applied") {
          setText("");
          toast.success(r.explanation || t("ui.commandbar.applied"), { id: UNDO_TOAST_ID, action: { label: t("common.undo"), onClick: onUndo } });
        } else if (r.status === "failed") toast.error(r.explanation || t("ui.commandbar.failed"));
      },
      onError: (e) => {
        const err = e as ApiError;
        toast.error(err.status === 404 ? t("ui.commandbar.unavailable") : err.message, { description: err.hint ?? undefined });
      },
    });
  };

  return (
    <div className="pointer-events-auto w-[min(720px,calc(100%-32px))]">
      {result?.status === "questions" && (
        <div className="mb-2 rounded-[var(--radius-panel)] border border-signal/30 bg-surface p-3 text-sm shadow-[var(--shadow-float)]">
          <p className="font-medium">{t("tools.questions")}</p>
          <ul className="mt-1 list-disc pl-5 text-muted">{result.questions.map((q) => <li key={q}>{q}</li>)}</ul>
        </div>
      )}
      <form onSubmit={(e) => { e.preventDefault(); submit(text); }}
            className="flex items-center gap-2 rounded-[var(--radius-panel)] border border-border bg-surface/95 p-1.5 pl-3 shadow-[var(--shadow-float)] backdrop-blur focus-within:border-signal focus-within:ring-2 focus-within:ring-signal/20">
        {edit.isPending ? <Spinner /> : <Sparkles className="size-4 shrink-0 text-signal" />}
        <input ref={ref} value={text} onChange={(e) => setText(e.target.value)} aria-label={t("tools.text")}
               onFocus={() => setFocused(true)} onBlur={() => window.setTimeout(() => setFocused(false), 150)}
               placeholder={edit.isPending ? t("tools.thinking") : t("tools.command_ph")}
               className="min-w-0 flex-1 bg-transparent py-1.5 text-sm outline-none placeholder:text-muted/80" />
        {!text && <span className="hidden items-center gap-1 text-2xs text-muted sm:flex"><Kbd>/</Kbd></span>}
        <button type="submit" disabled={!text.trim() || edit.isPending} aria-label={t("ui.commandbar.apply")}
                className="grid size-8 place-items-center rounded-[var(--radius-control)] bg-signal text-signal-ink disabled:opacity-40">
          <CornerDownLeft className="size-4" />
        </button>
      </form>
      {focused && !text && !edit.isPending && (
        <div className="mt-2 flex flex-wrap justify-center gap-1.5">
          {tItems("ui.commandbar.examples").map(({ text: x }) => (
            <button key={x} type="button" onClick={() => setText(x)}
                    className="rounded-full border border-border bg-surface/90 px-2.5 py-1 text-xs text-muted shadow-sm backdrop-blur hover:border-border-strong hover:text-ink">
              {x}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

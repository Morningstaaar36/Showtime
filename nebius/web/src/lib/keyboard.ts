/** True when a key event's target is a form control or editable text, so global shortcuts should stand down. */
export function isTypingTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el || typeof el.closest !== "function") return false;
  return el.isContentEditable || el.closest("input, textarea, select, [contenteditable]:not([contenteditable='false'])") !== null;
}

/** Saves organizer edits as patches: every change is a new version with Undo one click away. */
import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { usePatchProject, useUndo } from "@/api/queries";
import type { PatchOpIn, ProjectDetail } from "@/api/types";
import { qk } from "@/api/queries";
import { t } from "@/i18n";
import { UNDO_TOAST_ID } from "@/lib/utils";

export function useVenueEdit(projectId: string) {
  const qc = useQueryClient();
  const patch = usePatchProject(projectId);
  const undo = useUndo(projectId);
  const submit = useCallback((ops: PatchOpIn[], message: string, onDone?: () => void, expectedVersion?: number) => {
    const version = expectedVersion ?? qc.getQueryData<ProjectDetail>(qk.project(projectId))?.current_version;
    patch.mutate({ patch: { ops }, message, expected_version: version }, {
      onSuccess: (r) => {
        toast.success(t("check.saved", { what: message, n: r.version.version }), {
          id: UNDO_TOAST_ID,
          action: { label: t("common.undo"), onClick: () => undo.mutate() },
        });
        onDone?.();
      },
      onError: (e) => toast.error(e.message, { description: (e as { hint?: string }).hint ?? undefined }),
    });
  }, [patch, undo, qc, projectId]);
  return { submit, pending: patch.isPending };
}

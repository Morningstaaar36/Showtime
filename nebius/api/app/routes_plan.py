"""Organizer configuration, atomic proposals, and evidence applicability."""

from fastapi import APIRouter, Depends, Query

from api.app.routes_core import get_state
from api.app.routes_projects import _after_edit
from api.app.state import AppState
from api.core.plan import evidence_reference
from api.models.plan import (
    BundlePreview,
    PlanBundle,
    PlanEvidence,
    PlanSnapshot,
    PlanUpdate,
)

router = APIRouter(prefix="/api/v1/projects")


@router.get("/{project_id}/plan", response_model=PlanSnapshot)
def get_plan(
    project_id: str,
    version: int | None = Query(default=None, ge=1),
    st: AppState = Depends(get_state),
) -> PlanSnapshot:
    return st.projects.plan(project_id, version)


@router.put("/{project_id}/plan")
def configure_plan(project_id: str, body: PlanUpdate, st: AppState = Depends(get_state)) -> dict:
    row = st.projects.update_plan(project_id, body)
    return _after_edit(st, project_id, row)


@router.post("/{project_id}/plan/bundles/preview", response_model=BundlePreview)
def preview_bundle(
    project_id: str, body: PlanBundle, st: AppState = Depends(get_state)
) -> BundlePreview:
    return st.projects.preview_bundle(project_id, body)


@router.post("/{project_id}/plan/bundles")
def apply_bundle(project_id: str, body: PlanBundle, st: AppState = Depends(get_state)) -> dict:
    row = st.projects.apply_bundle(project_id, body)
    return _after_edit(st, project_id, row)


@router.get("/{project_id}/plan/evidence", response_model=PlanEvidence)
def evidence(project_id: str, st: AppState = Depends(get_state)) -> PlanEvidence:
    plan = st.projects.plan(project_id)
    refs = []
    for run in st.runs.list(project_id):
        digest = run.request.get("extensions", {}).get("plan_hash")
        refs.append(
            evidence_reference(run.id, run.status, digest, plan.plan_hash, bool(run.fix_id))
        )
    return PlanEvidence(
        project_id=project_id, version=plan.version, plan_hash=plan.plan_hash, runs=refs
    )

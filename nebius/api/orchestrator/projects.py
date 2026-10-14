"""Projects and venue versions: every save is a version; undo/redo; export/import."""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import update
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, col, select

from api.core import trajpack
from api.core.extensions import Registry
from api.core.geometry import validate_venue
from api.core.plan import (
    PLAN_KEY,
    PlanConflict,
    PlanError,
    apply_plan_bundle,
    fail,
    plan_data,
    plan_hash,
    transition_issues,
    validate_plan,
    with_plan,
)
from api.core.templates import get_template
from api.core.venue_ops import PatchError, PatchResult, apply_patch, venue_hash
from api.db.models import (
    AuditEntry,
    Project,
    RedTeamSession,
    Run,
    SessionEventRow,
    VenueVersion,
)
from api.db.queries import project_runs
from api.db.session import db_session
from api.models import Venue, VenuePatch
from api.models.plan import BundlePreview, PlanBundle, PlanSnapshot, PlanUpdate

EXPORT_FORMAT = "showtime-project-v1"
ARTIFACT_FILES = (
    "traj.bin",
    "traj_index.json",
    "density.bin",
    "density_index.json",
    "venue.json",
    "result.json",
)


def _dates(row: dict[str, Any]) -> dict[str, Any]:
    """Parse ISO datetimes from an export back into datetime objects."""
    out = dict(row)
    for k in ("created_at", "finished_at", "updated_at"):
        if isinstance(out.get(k), str):
            out[k] = datetime.fromisoformat(out[k])
    return out


class NotFound(Exception):
    """Unknown project, version or run."""


def new_id(prefix: str) -> str:
    """Short random id with a readable prefix."""
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _now() -> datetime:
    return datetime.now(UTC)


class ProjectService:
    """All project/venue persistence goes through here."""

    def __init__(self, registry: Registry, db_url: str | None = None) -> None:
        self.registry = registry
        self.db_url = db_url

    # -- queries ---------------------------------------------------------------
    def list_projects(self, include_archived: bool = False) -> list[Project]:
        """Projects, most recently updated first."""
        with db_session(self.db_url) as s:
            q = select(Project).order_by(col(Project.updated_at).desc())
            items = list(s.exec(q))
        return [p for p in items if include_archived or not p.archived]

    def get(self, project_id: str) -> Project:
        """One project or NotFound."""
        with db_session(self.db_url) as s:
            p = s.get(Project, project_id)
        if p is None:
            raise NotFound(f"Project {project_id} does not exist.")
        return p

    def version(self, project_id: str, version: int | None = None) -> VenueVersion:
        """A venue version (default: current)."""
        p = self.get(project_id)
        v = p.current_version if version is None else version
        with db_session(self.db_url) as s:
            row = s.exec(
                select(VenueVersion).where(
                    VenueVersion.project_id == project_id, VenueVersion.version == v
                )
            ).first()
        if row is None:
            raise NotFound(f"Version {v} of project {project_id} does not exist.")
        return row

    def venue(self, project_id: str, version: int | None = None) -> Venue:
        """The venue at a version."""
        return Venue.model_validate(self.version(project_id, version).venue)

    def versions(self, project_id: str) -> list[VenueVersion]:
        """All versions, newest first."""
        self.get(project_id)
        with db_session(self.db_url) as s:
            return list(
                s.exec(
                    select(VenueVersion)
                    .where(VenueVersion.project_id == project_id)
                    .order_by(col(VenueVersion.version).desc())
                )
            )

    # -- commands ----------------------------------------------------------------
    def create(
        self,
        name: str,
        template_id: str | None = None,
        venue: Venue | None = None,
        description: str = "",
        sample: bool = False,
        project_id: str | None = None,
    ) -> Project:
        """New project from a template or a venue."""
        if venue is None:
            if template_id is None:
                raise ValueError("Give a template or a venue.")
            venue = get_template(template_id)
        validate_plan(venue, self.registry)
        pid = project_id or new_id("p")
        venue = venue.model_copy(update={"venue_id": pid}, deep=True)
        now = _now()
        proj = Project(
            id=pid,
            name=name.strip() or venue.name,
            description=description,
            template_id=template_id,
            current_version=1,
            sample=sample,
            created_at=now,
            updated_at=now,
        )
        with db_session(self.db_url) as s:
            s.add(proj)
            s.flush()
            s.add(
                VenueVersion(
                    project_id=pid,
                    version=1,
                    venue=venue.model_dump(mode="json"),
                    venue_hash=venue_hash(venue),
                    message="Created",
                    author="system",
                )
            )
            s.commit()
            s.refresh(proj)
        return proj

    def rename(self, project_id: str, name: str, description: str | None = None) -> Project:
        """Change name/description."""
        with db_session(self.db_url) as s:
            p = s.get(Project, project_id)
            if p is None:
                raise NotFound(project_id)
            p.name = name.strip() or p.name
            if description is not None:
                p.description = description
            p.updated_at = _now()
            s.add(p)
            s.commit()
            s.refresh(p)
            return p

    def delete(self, project_id: str) -> None:
        """Delete a project and its versions, runs and sessions (artifacts stay on disk)."""
        with db_session(self.db_url) as s:
            p = s.get(Project, project_id)
            if p is None:
                raise NotFound(project_id)
            sids = list(
                s.exec(select(RedTeamSession.id).where(RedTeamSession.project_id == project_id))
            )
            for ev in s.exec(
                select(SessionEventRow).where(col(SessionEventRow.session_id).in_(sids))
            ):
                s.delete(ev)
            # runs other projects' sessions still use stay, detached from this project
            shared = {
                str((ev.payload or {}).get("run_id"))
                for ev in s.exec(
                    select(SessionEventRow).where(
                        SessionEventRow.type == "run_finished",
                        col(SessionEventRow.session_id).not_in(sids),
                    )
                )
            }
            for run in s.exec(select(Run).where(Run.project_id == project_id)):
                if run.id in shared:
                    run.project_id = None
                    run.session_id = None
                    s.add(run)
                else:
                    s.delete(run)
            for model in (VenueVersion, RedTeamSession, AuditEntry):
                for row in s.exec(select(model).where(model.project_id == project_id)):
                    s.delete(row)
            s.delete(p)
            s.commit()

    def duplicate(self, project_id: str, name: str | None = None) -> Project:
        """Copy the current venue into a new project."""
        p = self.get(project_id)
        return self.create(
            name or f"{p.name} (copy)",
            template_id=p.template_id,
            venue=self.venue(project_id),
            description=p.description,
        )

    def _save_version(
        self,
        s: Session,
        p: Project,
        venue: Venue,
        patch: VenuePatch | None,
        inverse: VenuePatch | None,
        message: str,
        author: str,
        base_version: int | None,
        expected_version: int | None = None,
    ) -> VenueVersion:
        if expected_version is not None:
            try:
                claimed = s.connection().execute(
                    update(Project)
                    .where(
                        col(Project.id) == p.id, col(Project.current_version) == expected_version
                    )
                    .values(current_version=expected_version)
                )
            except OperationalError as exc:
                if "database is locked" not in str(exc).lower():
                    raise
                raise PlanConflict(
                    "Another save is in progress. Reload the project and retry."
                ) from exc
            if claimed.rowcount != 1:
                raise PlanConflict("The project changed. Reload its current version and retry.")
        latest = s.exec(
            select(VenueVersion)
            .where(VenueVersion.project_id == p.id)
            .order_by(col(VenueVersion.version).desc())
        ).first()
        nv = (latest.version if latest else 0) + 1
        row = VenueVersion(
            project_id=p.id,
            version=nv,
            venue=venue.model_dump(mode="json"),
            venue_hash=venue_hash(venue),
            base_version=base_version,
            patch=patch.model_dump(mode="json") if patch else None,
            inverse=inverse.model_dump(mode="json") if inverse else None,
            message=message,
            author=author,
        )
        s.add(row)
        p.current_version = nv
        p.updated_at = _now()
        s.add(p)
        return row

    def _row(self, s: Session, project_id: str, version: int) -> VenueVersion:
        row = s.exec(
            select(VenueVersion).where(
                VenueVersion.project_id == project_id, VenueVersion.version == version
            )
        ).first()
        if row is None:
            raise NotFound(f"Version {version} of project {project_id} does not exist.")
        return row

    def apply(
        self,
        project_id: str,
        patch: VenuePatch,
        message: str = "",
        author: str = "user",
        allow_new_errors: bool = False,
        expected_version: int | None = None,
    ) -> tuple[VenueVersion, PatchResult]:
        """Apply a patch to the current venue and save a new version (clears redo)."""
        base = self.version(project_id)
        if expected_version is not None and base.version != expected_version:
            raise PlanConflict("The proposal is for an older version. Reload and preview again.")
        venue = Venue.model_validate(base.venue)
        result = apply_patch(
            venue,
            patch,
            self.registry,
            allow_new_errors=allow_new_errors,
            organizer_edit=author == "user",
        )
        with db_session(self.db_url) as s:
            p = s.get(Project, project_id)
            assert p is not None
            row = self._save_version(
                s,
                p,
                result.venue,
                patch,
                result.inverse,
                message or _describe(patch),
                author,
                base_version=base.version,
                expected_version=base.version,
            )
            p.redo_stack = []
            s.add(
                AuditEntry(
                    project_id=project_id,
                    kind="edit",
                    agent=author,
                    payload={
                        "version": row.version,
                        "patch": patch.model_dump(mode="json"),
                        "message": row.message,
                    },
                )
            )
            s.commit()
            s.refresh(row)
        return row, result

    def can_undo(self, project_id: str) -> bool:
        """True when the current version has a state to go back to."""
        return self.version(project_id).base_version is not None

    def undo(self, project_id: str) -> VenueVersion:
        """Go back to the state before the current one (saved as a new version)."""
        with db_session(self.db_url) as s:
            p = s.get(Project, project_id)
            if p is None:
                raise NotFound(project_id)
            cur = self._row(s, project_id, p.current_version)
            if cur.base_version is None:
                raise PatchError(["Nothing to undo."])
            base = self._row(s, project_id, cur.base_version)
            row = self._save_version(
                s,
                p,
                Venue.model_validate(base.venue),
                None,
                None,
                f"Undo: {cur.message}",
                "user",
                base_version=base.base_version,
            )
            p.redo_stack = [*p.redo_stack, cur.version]
            s.add(p)
            s.commit()
            s.refresh(row)
            return row

    def redo(self, project_id: str) -> VenueVersion:
        """Re-apply the most recently undone version."""
        with db_session(self.db_url) as s:
            p = s.get(Project, project_id)
            if p is None:
                raise NotFound(project_id)
            if not p.redo_stack:
                raise PatchError(["Nothing to redo."])
            target = self._row(s, project_id, p.redo_stack[-1])
            row = self._save_version(
                s,
                p,
                Venue.model_validate(target.venue),
                None,
                None,
                f"Redo: {target.message.removeprefix('Undo: ')}",
                "user",
                base_version=p.current_version,
            )
            p.redo_stack = p.redo_stack[:-1]
            s.add(p)
            s.commit()
            s.refresh(row)
            return row

    def restore(self, project_id: str, version: int) -> VenueVersion:
        """Make an old version current again (as a new version; undo returns here)."""
        with db_session(self.db_url) as s:
            p = s.get(Project, project_id)
            if p is None:
                raise NotFound(project_id)
            old = self._row(s, project_id, version)
            row = self._save_version(
                s,
                p,
                Venue.model_validate(old.venue),
                None,
                None,
                f"Restored version {version}",
                "user",
                base_version=p.current_version,
            )
            p.redo_stack = []
            s.add(p)
            s.commit()
            s.refresh(row)
            return row

    def replace_venue(
        self,
        project_id: str,
        venue: Venue,
        message: str,
        author: str = "system",
        expected_version: int | None = None,
    ) -> VenueVersion:
        """Save a whole venue (e.g. the red team's fixed plan) as a new version."""
        venue = venue.model_copy(update={"venue_id": project_id}, deep=True)
        base = self.version(project_id)
        before = Venue.model_validate(base.venue)
        problems = transition_issues(before, venue)
        if problems:
            raise PlanError(problems)
        validate_plan(venue, self.registry)
        with db_session(self.db_url) as s:
            p = s.get(Project, project_id)
            if p is None:
                raise NotFound(project_id)
            row = self._save_version(
                s,
                p,
                venue,
                None,
                None,
                message,
                author,
                base_version=base.version,
                expected_version=expected_version if expected_version is not None else base.version,
            )
            p.redo_stack = []
            s.add(p)
            s.commit()
            s.refresh(row)
            return row

    def plan(self, project_id: str, version: int | None = None) -> PlanSnapshot:
        row = self.version(project_id, version)
        venue = Venue.model_validate(row.venue)
        data = validate_plan(venue, self.registry)
        return PlanSnapshot(
            project_id=project_id,
            version=row.version,
            plan_hash=plan_hash(venue),
            configured=PLAN_KEY in venue.extensions,
            venue=venue,
            plan=data,
        )

    def update_plan(self, project_id: str, body: PlanUpdate) -> VenueVersion:
        """Explicit organizer command: replace policy/actions, preserve scene geometry."""
        if not body.plan.enforce_constraints:
            raise PlanError(
                [
                    fail(
                        "constraints_required",
                        "Organizer configuration must enforce constraints. "
                        "Legacy actions must be assigned resources before migration.",
                    )
                ]
            )
        base = self.version(project_id)
        if base.version != body.expected_version:
            raise PlanConflict("The project changed. Reload its current version and retry.")
        candidate = with_plan(Venue.model_validate(base.venue), body.plan)
        validate_plan(candidate, self.registry)
        return self._save_plan(project_id, candidate, base.version, body.message, "user")

    def _bundle_candidate(self, project_id: str, body: PlanBundle) -> Venue:
        base = self.version(project_id)
        if base.version != body.expected_version:
            raise PlanConflict("The project changed. Reload its current version and retry.")
        venue = Venue.model_validate(base.venue)
        if PLAN_KEY not in venue.extensions:
            raise PlanError(
                [
                    fail(
                        "plan_not_configured",
                        "Configure the organizer plan before submitting bundles.",
                    )
                ]
            )
        return apply_plan_bundle(venue, body, self.registry)

    def preview_bundle(self, project_id: str, body: PlanBundle) -> BundlePreview:
        try:
            candidate = self._bundle_candidate(project_id, body)
        except PlanError as exc:
            return BundlePreview(valid=False, issues=exc.issues)
        except PatchError as exc:
            return BundlePreview(
                valid=False, issues=[fail("invalid_edit", p) for p in exc.problems]
            )
        return BundlePreview(
            valid=True,
            candidate=PlanSnapshot(
                project_id=project_id,
                version=body.expected_version,
                plan_hash=plan_hash(candidate),
                configured=True,
                venue=candidate,
                plan=plan_data(candidate),
            ),
        )

    def apply_bundle(self, project_id: str, body: PlanBundle) -> VenueVersion:
        candidate = self._bundle_candidate(project_id, body)
        return self._save_plan(
            project_id, candidate, body.expected_version, body.message, body.source
        )

    def _save_plan(
        self, project_id: str, venue: Venue, expected: int, message: str, author: str
    ) -> VenueVersion:
        with db_session(self.db_url) as s:
            p = s.get(Project, project_id)
            if p is None:
                raise NotFound(project_id)
            row = self._save_version(
                s,
                p,
                venue,
                None,
                None,
                message,
                author,
                base_version=expected,
                expected_version=expected,
            )
            p.redo_stack = []
            s.add(
                AuditEntry(
                    project_id=project_id,
                    kind="plan_edit",
                    agent=author,
                    payload={
                        "version": row.version,
                        "plan_hash": plan_hash(venue),
                        "message": message,
                    },
                )
            )
            s.commit()
            s.refresh(row)
            return row

    # -- export / import ---------------------------------------------------------------
    def export_zip(self, project_id: str, artifacts_from: Path | None = None) -> bytes:
        """`.showtime.zip`: project, all versions, run results and sessions (no artifacts)."""
        p = self.get(project_id)
        with db_session(self.db_url) as s:
            versions = list(
                s.exec(
                    select(VenueVersion)
                    .where(VenueVersion.project_id == project_id)
                    .order_by(col(VenueVersion.version))
                )
            )
            runs = project_runs(s, project_id)
            sessions = list(
                s.exec(select(RedTeamSession).where(RedTeamSession.project_id == project_id))
            )
            events: list[SessionEventRow] = []
            for rs in sessions:
                events.extend(
                    s.exec(
                        select(SessionEventRow)
                        .where(SessionEventRow.session_id == rs.id)
                        .order_by(col(SessionEventRow.seq))
                    )
                )
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(
                "manifest.json",
                json.dumps({"format": EXPORT_FORMAT, "exported_at": _now().isoformat()}),
            )
            z.writestr("project.json", p.model_dump_json())
            z.writestr("versions.json", json.dumps([v.model_dump(mode="json") for v in versions]))
            z.writestr("runs.json", json.dumps([r.model_dump(mode="json") for r in runs]))
            z.writestr("sessions.json", json.dumps([r.model_dump(mode="json") for r in sessions]))
            z.writestr(
                "session_events.json", json.dumps([e.model_dump(mode="json") for e in events])
            )
            if artifacts_from is not None:  # demo packs: include replay artifacts
                for r in runs:
                    d = artifacts_from / r.id
                    if not d.is_dir():
                        continue
                    for name in ARTIFACT_FILES:
                        if name.startswith("traj") and (d / "traj_index.json").exists():
                            continue
                        if (d / name).exists():  # LZMA halves trajectory size vs deflate
                            z.write(d / name, f"runs/{r.id}/{name}", compress_type=zipfile.ZIP_LZMA)
                    if (d / "traj.bin").exists() and (d / "traj_index.json").exists():
                        index = json.loads((d / "traj_index.json").read_text())
                        traj, index = trajpack.coarsen((d / "traj.bin").read_bytes(), index, 3)
                        lz = zipfile.ZIP_LZMA
                        z.writestr(f"runs/{r.id}/traj_index.json", json.dumps(index), lz)
                        z.writestr(
                            f"runs/{r.id}/{trajpack.DELTA_NAME}", trajpack.encode(traj, index), lz
                        )
        return buf.getvalue()

    def import_zip(
        self,
        data: bytes,
        sample: bool = False,
        runs_dir: Path | None = None,
        name: str | None = None,
    ) -> Project:
        """Import a `.showtime.zip` as a new project (new id; history kept)."""
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                manifest = json.loads(z.read("manifest.json"))
                if manifest.get("format") != EXPORT_FORMAT:
                    raise ValueError("This file is not a Showtime project export.")
                proj = json.loads(z.read("project.json"))
                versions = json.loads(z.read("versions.json"))
                names = set(z.namelist())
                runs = json.loads(z.read("runs.json")) if "runs.json" in names else []
                sessions = json.loads(z.read("sessions.json")) if "sessions.json" in names else []
                events = (
                    json.loads(z.read("session_events.json"))
                    if "session_events.json" in names
                    else []
                )
                if runs_dir is not None:
                    for n in names:
                        if n.startswith("runs/") and not n.endswith("/"):
                            target = (runs_dir / n.removeprefix("runs/")).resolve()
                            if runs_dir.resolve() not in target.parents:
                                continue
                            target.parent.mkdir(parents=True, exist_ok=True)
                            blob = z.read(n)
                            if target.name == trajpack.DELTA_NAME:  # delta-coded trajectory
                                ix_name = n.rsplit("/", 1)[0] + "/traj_index.json"
                                blob = trajpack.decode(blob, json.loads(z.read(ix_name)))
                                target = target.with_name("traj.bin")
                            target.write_bytes(blob)
        except (KeyError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
            raise ValueError("This file is not a valid .showtime.zip export.") from exc
        if not versions:
            raise ValueError("The export has no venue versions.")
        pid = new_id("p")
        now = _now()
        with db_session(self.db_url) as s:
            p = Project(
                id=pid,
                name=name or f"{proj.get('name', 'Imported')} (imported)",
                sample=sample,
                description=proj.get("description", ""),
                template_id=proj.get("template_id"),
                current_version=int(proj.get("current_version") or versions[-1]["version"]),
                created_at=now,
                updated_at=now,
            )
            s.add(p)
            s.flush()
            for v in versions:
                venue = Venue.model_validate(v["venue"]).model_copy(update={"venue_id": pid})
                validate_plan(venue, self.registry)
                s.add(
                    VenueVersion(
                        project_id=pid,
                        version=int(v["version"]),
                        venue=venue.model_dump(mode="json"),
                        venue_hash=venue_hash(venue),
                        base_version=v.get("base_version"),
                        patch=v.get("patch"),
                        inverse=v.get("inverse"),
                        message=v.get("message", ""),
                        author=v.get("author", "user"),
                    )
                )
            sid_map: dict[str, str] = {}
            for rs in sessions:
                new_sid = rs["id"] if s.get(RedTeamSession, rs["id"]) is None else new_id("s")
                sid_map[rs["id"]] = new_sid
                rs = {**rs, "id": new_sid, "project_id": pid}
                s.add(RedTeamSession.model_validate(_dates(rs)))
            for ev in events:
                if ev.get("session_id") in sid_map:
                    ev = {k: v for k, v in ev.items() if k != "id"}
                    ev["session_id"] = sid_map[ev["session_id"]]
                    s.add(SessionEventRow.model_validate(ev))
            for r in runs:
                if s.get(Run, r["id"]) is not None:
                    continue  # runs are content-addressed: an identical run already exists
                r = {**r, "project_id": pid, "session_id": sid_map.get(r.get("session_id") or "")}
                s.add(Run.model_validate(_dates(r)))
            s.commit()
            s.refresh(p)
        return p


def _describe(patch: VenuePatch) -> str:
    names = {
        "move": "Moved",
        "resize": "Resized",
        "add_exit": "Added exit",
        "remove_exit": "Removed exit",
        "block_exit": "Changed exit",
        "add_obstacle": "Added object",
        "remove_obstacle": "Removed object",
        "add_barrier_line": "Added barrier",
        "set_people": "Changed headcount",
        "add_zone": "Added zone",
        "remove_zone": "Removed zone",
        "set_stage_param": "Changed stage",
    }
    parts = []
    for op in patch.ops[:3]:
        d = op.model_dump()
        target = (
            d.get("target")
            or d.get("id")
            or d.get("exit_id")
            or d.get("zone_id")
            or d.get("obstacle_id")
            or d.get("param")
            or ""
        )
        parts.append(f"{names.get(op.op, op.op)} {target}".strip())
    more = f" (+{len(patch.ops) - 3} more)" if len(patch.ops) > 3 else ""
    return ", ".join(parts) + more


def validation_for(venue: Venue) -> dict[str, Any]:
    """Validation report as JSON."""
    rep = validate_venue(venue)
    return {"ok": rep.ok, "checks": [c.model_dump() for c in rep.checks]}

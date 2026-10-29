"""Projects and venue versions: every save is a version; undo/redo; export/import."""

from __future__ import annotations

import io
import json
import re
import shutil
import uuid
import zipfile
from collections.abc import Callable
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
from api.core.settings import Settings
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
    "pressure.bin",
    "pressure_index.json",
    "agents.json",
    "venue.json",
    "result.json",
)
RUN_FOLDER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
# what an import reads: the export's own files, and the replay files of its runs
EXPORT_FILES = (
    "manifest.json",
    "project.json",
    "versions.json",
    "runs.json",
    "sessions.json",
    "session_events.json",
)
IMPORT_ARTIFACTS = frozenset({*ARTIFACT_FILES, trajpack.DELTA_NAME})


def _dates(row: dict[str, Any]) -> dict[str, Any]:
    """Parse ISO datetimes from an export back into datetime objects."""
    out = dict(row)
    for k in ("created_at", "finished_at", "updated_at"):
        if isinstance(out.get(k), str):
            out[k] = datetime.fromisoformat(out[k])
    return out


def _setting_default(name: str) -> Any:
    """A setting's declared default (callers that have the settings pass their values)."""
    return Settings.model_fields[name].default


def _optional(z: zipfile.ZipFile, names: set[str], name: str) -> Any:
    return json.loads(z.read(name)) if name in names else []


def _rows(data: Any, name: str) -> list[dict[str, Any]]:
    """A list of JSON objects, else ValueError naming the file."""
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
        raise ValueError(f"{name} is not a list of objects.")
    return data


def _need(row: dict[str, Any], key: str, kind: type, name: str) -> None:
    value = row.get(key)
    # bool is an int in Python, never a version number or an event seq
    if not isinstance(value, kind) or isinstance(value, bool):
        raise ValueError(f"{name}: an entry has no valid '{key}'.")


def _check_versions(proj: dict[str, Any], versions: list[dict[str, Any]]) -> int:
    """The current version number, after checking every version's number and venue."""
    if not versions:
        raise ValueError("The export has no venue versions.")
    numbers: set[int] = set()
    for v in versions:
        _need(v, "version", int, "versions.json")
        _need(v, "venue", dict, "versions.json")
        if v["version"] < 1 or v["version"] in numbers:
            raise ValueError(f"versions.json: version {v['version']} is repeated or below 1.")
        numbers.add(v["version"])
        base = v.get("base_version")
        if base is not None and (not isinstance(base, int) or isinstance(base, bool)):
            raise ValueError("versions.json: a base_version is not a version number.")
    current = proj.get("current_version") or max(numbers)
    if not isinstance(current, int) or isinstance(current, bool) or current not in numbers:
        raise ValueError(f"current_version {current!r} is not one of the versions.")
    return current


def _rekeyer(ids: dict[str, str]) -> Callable[[Any], Any]:
    """Replace every old run id in JSON data (values, keys and paths like runs/<id>/...)."""
    if not ids:
        return lambda data: data
    alternatives = "|".join(re.escape(k) for k in sorted(ids, key=len, reverse=True))
    pattern = re.compile(rf"(?<!\w)({alternatives})(?!\w)")

    def walk(data: Any) -> Any:
        if isinstance(data, str):
            return pattern.sub(lambda m: ids[m.group(1)], data)
        if isinstance(data, list):
            return [walk(x) for x in data]
        if isinstance(data, dict):
            return {walk(k): walk(v) for k, v in data.items()}
        return data

    return walk


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

    def delete(self, project_id: str, runs_dir: Path | None = None) -> list[str]:
        """Delete a project and its versions, runs and sessions; returns the deleted run ids.

        With `runs_dir`, the files of those runs go too. A run another project's session
        still uses is kept (detached from this project), and so are its files."""
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
            deleted: list[str] = []
            for run in s.exec(select(Run).where(Run.project_id == project_id)):
                if run.id in shared:
                    run.project_id = None
                    run.session_id = None
                    s.add(run)
                else:
                    s.delete(run)
                    deleted.append(run.id)
            for model in (VenueVersion, RedTeamSession, AuditEntry):
                for row in s.exec(select(model).where(model.project_id == project_id)):
                    s.delete(row)
            s.delete(p)
            s.commit()
        if runs_dir is not None:
            remove_run_files(runs_dir, deleted)
        return deleted

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
        max_unpacked_bytes: int = _setting_default("import_max_unpacked_bytes"),
        max_entries: int = _setting_default("import_max_entries"),
    ) -> Project:
        """Import a `.showtime.zip` as a new project (new id; history kept).

        Anything malformed raises ValueError before a row is written. Imported runs get new
        ids: a run id is the hash of what the run computes, so a result kept under it would be
        served as the cached answer to anyone's identical request."""
        pid = new_id("p")
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                infos = z.infolist()
                # a few kB of zip can unpack to gigabytes: check the sizes it declares first
                read = [
                    i
                    for i in infos
                    if i.filename in EXPORT_FILES
                    or (runs_dir is not None and i.filename.startswith("runs/"))
                ]
                if len(infos) > max_entries:
                    raise ValueError(f"The file holds more than {max_entries} entries.")
                if sum(i.file_size for i in read) > max_unpacked_bytes:
                    raise ValueError(
                        f"The file unpacks to more than {max_unpacked_bytes // 1_000_000} MB."
                    )
                names = {i.filename for i in infos}
                manifest = json.loads(z.read("manifest.json"))
                if not isinstance(manifest, dict) or manifest.get("format") != EXPORT_FORMAT:
                    raise ValueError("This file is not a Showtime project export.")
                proj = json.loads(z.read("project.json"))
                if not isinstance(proj, dict):
                    raise ValueError("project.json is not an object.")
                versions = _rows(json.loads(z.read("versions.json")), "versions.json")
                runs = _rows(_optional(z, names, "runs.json"), "runs.json")
                sessions = _rows(_optional(z, names, "sessions.json"), "sessions.json")
                events = _rows(_optional(z, names, "session_events.json"), "session_events.json")
                current = _check_versions(proj, versions)
                for r in runs:
                    _need(r, "id", str, "runs.json")
                for rs in sessions:
                    _need(rs, "id", str, "sessions.json")
                for ev in events:
                    _need(ev, "seq", int, "session_events.json")
                    _need(ev, "type", str, "session_events.json")
                rekey = _rekeyer({r["id"]: new_id("r") for r in runs})
                versions, runs, sessions, events = rekey([versions, runs, sessions, events])
                venues = []
                for v in versions:
                    venue = Venue.model_validate(v["venue"]).model_copy(update={"venue_id": pid})
                    validate_plan(venue, self.registry)
                    venues.append(venue)
                if runs_dir is not None:
                    self._unpack_artifacts(z, runs_dir, rekey, {r["id"] for r in runs})
        except PlanError as exc:
            raise ValueError(f"A venue in the file is not valid: {exc}") from exc
        except (KeyError, TypeError, ValueError, zipfile.BadZipFile) as exc:
            # json and pydantic errors are ValueErrors; a missing file is a KeyError
            detail = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
            raise ValueError(f"This file is not a valid .showtime.zip export ({detail}).") from exc
        now = _now()
        with db_session(self.db_url) as s:
            p = Project(
                id=pid,
                name=name or f"{proj.get('name') or 'Imported'} (imported)",
                sample=sample,
                description=str(proj.get("description") or ""),
                template_id=proj.get("template_id"),
                current_version=current,
                created_at=now,
                updated_at=now,
            )
            s.add(p)
            s.flush()
            for v, venue in zip(versions, venues, strict=True):
                s.add(
                    VenueVersion(
                        project_id=pid,
                        version=v["version"],
                        venue=venue.model_dump(mode="json"),
                        venue_hash=venue_hash(venue),
                        base_version=v.get("base_version"),
                        patch=v.get("patch"),
                        inverse=v.get("inverse"),
                        message=str(v.get("message") or ""),
                        author=str(v.get("author") or "user"),
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
                r = {**r, "project_id": pid, "session_id": sid_map.get(r.get("session_id") or "")}
                s.add(Run.model_validate(_dates(r)))
            s.commit()
            s.refresh(p)
        return p

    @staticmethod
    def _unpack_artifacts(
        z: zipfile.ZipFile, runs_dir: Path, rekey: Callable[[Any], Any], run_ids: set[str]
    ) -> None:
        """Replay files of the imported runs, under their new ids (other files are skipped)."""
        for n in z.namelist():
            parts = n.split("/")
            if len(parts) != 3 or parts[0] != "runs" or parts[2] not in IMPORT_ARTIFACTS:
                continue
            rid = rekey(parts[1])
            if rid not in run_ids:
                continue  # not a run of this export: never written
            target = (runs_dir / rid / parts[2]).resolve()
            if runs_dir.resolve() not in target.parents:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            blob = z.read(n)
            if target.name == trajpack.DELTA_NAME:  # delta-coded trajectory
                index = json.loads(z.read(f"runs/{parts[1]}/traj_index.json"))
                blob = trajpack.decode(blob, index)
                target = target.with_name("traj.bin")
            elif target.suffix == ".json":  # result.json names its run and artifact paths
                blob = json.dumps(rekey(json.loads(blob))).encode()
            target.write_bytes(blob)


def remove_run_files(runs_dir: Path, run_ids: list[str]) -> None:
    """Delete the folders of these runs under `runs_dir` (ids that are not plain names, or
    folders outside it, are left alone)."""
    root = runs_dir.resolve()
    for rid in run_ids:
        folder = (runs_dir / rid).resolve()
        if RUN_FOLDER_RE.match(rid) and folder.parent == root and folder.is_dir():
            shutil.rmtree(folder, ignore_errors=True)


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

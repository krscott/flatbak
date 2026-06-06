from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from flatbak.config import ConfigEntry, append_root_entries, load_config
from flatbak.flatpak import Flatpak, InstalledApp
from flatbak.state import State, TrackedApp, load_state, save_state


@dataclass(kw_only=True, frozen=True)
class Options:
    dry_run: bool = False


@dataclass(kw_only=True, frozen=True)
class Paths:
    config_dir: Path
    data_dir: Path


@dataclass(kw_only=True, frozen=True)
class ReconcileResult:
    adopted: list[str]
    installed: list[str]
    removed: list[str]
    tracked: list[str]

    @property
    def changed(self) -> bool:
        return bool(self.adopted or self.installed or self.removed or self.tracked)


def reconcile(
    opts: Options, paths: Paths, flatpak: Flatpak | None = None
) -> ReconcileResult:
    client = flatpak if flatpak is not None else Flatpak()
    config = load_config(paths.config_dir, create=not opts.dry_run)
    state = load_state(paths.data_dir / "state.json")
    installed = client.list_installed_apps()

    client.validate_entries(config.entries)

    desired_entries = list(config.entries)
    tracked_app_ids = {app.app_id for app in state.tracked_apps}

    adopted_entries: list[str] = []
    tracked_apps = {app.app_id: app for app in state.tracked_apps}

    for app in installed:
        if app.app_id in tracked_app_ids or _installed_matches_any(
            app, desired_entries
        ):
            continue
        value = _adoption_value(app)
        entry = ConfigEntry.parse(value, source=paths.config_dir / "root.txt")
        adopted_entries.append(value)
        desired_entries.append(entry)
        tracked_apps[app.app_id] = _tracked_from_installed(app, source=value)

    removed: list[str] = []
    installed_after_removals = list(installed)
    for tracked in list(tracked_apps.values()):
        tracked_installs = _tracked_installed_apps(tracked, installed_after_removals)
        if not tracked_installs:
            tracked_apps.pop(tracked.app_id, None)
            continue
        for installed_app in tracked_installs:
            if _installed_matches_any(installed_app, desired_entries):
                continue
            removed.append(installed_app.ref)
            if not opts.dry_run:
                client.uninstall(installed_app.ref)
            installed_after_removals.remove(installed_app)
        if not any(app.app_id == tracked.app_id for app in installed_after_removals):
            tracked_apps.pop(tracked.app_id, None)
    installs: list[str] = []
    for entry in desired_entries:
        if _entry_matches_any(entry, installed_after_removals):
            continue
        installs.append(entry.value)
        if not opts.dry_run:
            client.install(entry)
            tracked_apps[entry.app_id] = TrackedApp(
                app_id=entry.app_id,
                installed_ref=entry.ref,
                source=entry.value,
            )

    newly_tracked: list[str] = []
    for app in installed_after_removals:
        matching = _matching_entry(app, desired_entries)
        if matching is None or app.app_id in tracked_apps:
            continue
        newly_tracked.append(app.app_id)
        tracked_apps[app.app_id] = _tracked_from_installed(app, source=matching.value)

    if not opts.dry_run:
        if adopted_entries:
            append_root_entries(paths.config_dir, adopted_entries)
        save_state(
            paths.data_dir / "state.json",
            State(tracked=sorted(tracked_apps.values(), key=lambda app: app.app_id)),
        )

    return ReconcileResult(
        adopted=adopted_entries,
        installed=installs,
        removed=removed,
        tracked=newly_tracked,
    )


def _installed_matches_any(app: InstalledApp, entries: list[ConfigEntry]) -> bool:
    return _matching_entry(app, entries) is not None


def _matching_entry(
    app: InstalledApp, entries: list[ConfigEntry]
) -> ConfigEntry | None:
    for entry in entries:
        if entry.matches(app):
            return entry
    return None


def _entry_matches_any(entry: ConfigEntry, apps: list[InstalledApp]) -> bool:
    return any(entry.matches(app) for app in apps)


def _tracked_installed_apps(
    tracked: TrackedApp, apps: list[InstalledApp]
) -> list[InstalledApp]:
    if tracked.installed_ref:
        return [
            app
            for app in apps
            if app.app_id == tracked.app_id and app.ref == tracked.installed_ref
        ]
    return [app for app in apps if app.app_id == tracked.app_id]


def _adoption_value(app: InstalledApp) -> str:
    if app.remote in {"", "flathub"} and app.branch in {"", "stable"}:
        return app.app_id
    if app.ref:
        return f"{app.remote}:{app.ref}" if app.remote else app.ref
    return app.app_id


def _tracked_from_installed(app: InstalledApp, source: str) -> TrackedApp:
    return TrackedApp(app_id=app.app_id, installed_ref=app.ref, source=source)

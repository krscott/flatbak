from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

Scope = Literal["user", "system"]
SCOPES: tuple[Scope, Scope] = ("user", "system")


@dataclass(kw_only=True, frozen=True)
class InstalledApp:
    app_id: str
    remote: str
    scope: Scope = "user"
    kind: str = "app"
    arch: str = ""
    branch: str = ""

    @property
    def ref(self) -> str:
        if self.arch and self.branch:
            return f"{self.kind}/{self.app_id}/{self.arch}/{self.branch}"
        return self.app_id

    @staticmethod
    def from_ref(ref: str, remote: str, scope: Scope) -> InstalledApp:
        parts = ref.split("/")
        if len(parts) == 4:
            kind, app_id, arch, branch = parts
            return InstalledApp(
                scope=scope,
                app_id=app_id,
                remote=remote,
                kind=kind,
                arch=arch,
                branch=branch,
            )
        return InstalledApp(scope=scope, app_id=ref, remote=remote)


class Flatpak:
    def list_installed_apps(self) -> list[InstalledApp]:
        apps: list[InstalledApp] = []
        for scope in SCOPES:
            apps.extend(self._list_installed_apps(scope))
        return apps

    def _list_installed_apps(self, scope: Scope) -> list[InstalledApp]:
        output = self._run(
            ["list", f"--{scope}", "--app", "--columns=application,origin,ref"],
            capture=True,
        )
        apps: list[InstalledApp] = []
        for line in output.splitlines():
            if not line.strip():
                continue
            columns = line.split("\t")
            if len(columns) == 3:
                app_id, remote, ref = columns
                app = InstalledApp.from_ref(ref, remote, scope)
                if app.app_id == app_id and app.kind == "app":
                    apps.append(app)
                continue
            columns = line.split()
            if len(columns) >= 3:
                app_id, remote, ref = columns[0], columns[1], columns[2]
                app = InstalledApp.from_ref(ref, remote, scope)
                if app.app_id == app_id and app.kind == "app":
                    apps.append(app)
        return apps

    def remotes(self, scope: Scope) -> set[str]:
        output = self._run(["remotes", f"--{scope}", "--columns=name"], capture=True)
        return {line.strip() for line in output.splitlines() if line.strip()}

    def validate_entries(self, entries: Sequence[object]) -> None:
        from flatbak.config import ConfigEntry

        for entry in entries:
            if not isinstance(entry, ConfigEntry):
                raise ValueError("Invalid config entry")
            remotes = self.remotes(entry.scope)
            required_remote = entry.effective_remote
            if required_remote not in remotes:
                raise ValueError(
                    f"Flatpak remote '{required_remote}' is required for '{entry.scope}:{entry.value}' but is not configured in {entry.scope} scope"
                )
            self.resolve(entry)

    def resolve(self, entry: object) -> InstalledApp:
        from flatbak.config import ConfigEntry

        if not isinstance(entry, ConfigEntry):
            raise ValueError("Invalid config entry")

        output = self._run(
            [
                "remote-ls",
                f"--{entry.scope}",
                "--app",
                "--columns=application,ref",
                entry.effective_remote,
            ],
            capture=True,
        )
        for app in _parse_remote_apps(output, entry.effective_remote, entry.scope):
            if entry.matches(app):
                return app
            if not entry.qualified and app.app_id == entry.app_id:
                return app
        raise ValueError(f"No such ref: {entry.value}")

    def install(self, entry: object) -> None:
        from flatbak.config import ConfigEntry

        if not isinstance(entry, ConfigEntry):
            raise ValueError("Invalid config entry")
        remote = entry.effective_remote
        self._run(
            ["install", f"--{entry.scope}", "--noninteractive", remote, entry.ref],
            capture=False,
        )

    def uninstall(self, scope: Scope, ref: str) -> None:
        self._run(["uninstall", f"--{scope}", "--noninteractive", ref], capture=False)

    def _run(self, args: list[str], *, capture: bool) -> str:
        command = ["flatpak", *args]
        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=capture,
                text=True,
            )
        except FileNotFoundError as error:
            raise ValueError("flatpak executable was not found") from error
        except subprocess.CalledProcessError as error:
            message = error.stderr.strip() if isinstance(error.stderr, str) else ""
            raise ValueError(
                message or f"Command failed: {' '.join(command)}"
            ) from error
        return result.stdout if capture else ""


def _parse_remote_apps(output: str, remote: str, scope: Scope) -> list[InstalledApp]:
    apps: list[InstalledApp] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        columns = line.split("\t")
        if len(columns) != 2:
            columns = line.split()
        if len(columns) < 2:
            continue
        app_id, ref = columns[0], columns[1]
        app = InstalledApp.from_ref(ref, remote, scope)
        if app.app_id == app_id and app.kind == "app":
            apps.append(app)
    return apps

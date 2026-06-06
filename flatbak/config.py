from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

from flatbak.flatpak import SCOPES, InstalledApp, Scope

APP_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*(?:\.[A-Za-z0-9][A-Za-z0-9_-]*)+$")


@dataclass(kw_only=True, frozen=True)
class Config:
    entries: list[ConfigEntry]


@dataclass(kw_only=True, frozen=True)
class ConfigEntry:
    scope: Scope
    value: str
    app_id: str
    remote: str
    kind: str
    arch: str
    branch: str
    source: Path | None = None

    @property
    def qualified(self) -> bool:
        return (
            self.kind != "" or self.arch != "" or self.branch != "" or self.remote != ""
        )

    @property
    def ref(self) -> str:
        if not self.kind:
            return self.app_id
        return f"{self.kind}/{self.app_id}/{self.arch}/{self.branch}"

    @property
    def effective_remote(self) -> str:
        return self.remote if self.remote else "flathub"

    @property
    def match_key(self) -> tuple[str, str, str, str, str, str]:
        if not self.qualified:
            return (self.scope, "app-id", self.app_id, "", "", "")
        return (
            self.scope,
            self.effective_remote,
            self.kind,
            self.app_id,
            self.arch,
            self.branch,
        )

    @staticmethod
    def parse(value: str, scope: Scope, source: Path | None = None) -> ConfigEntry:
        remote = ""
        ref = value
        if ":" in value:
            remote, ref = value.split(":", 1)

        parts = ref.split("/")
        if len(parts) == 1:
            app_id = parts[0]
            if not APP_ID_RE.match(app_id):
                raise ValueError(f"Invalid Flatpak app ID: {value}")
            return ConfigEntry(
                scope=scope,
                value=value,
                app_id=app_id,
                remote=remote,
                kind="",
                arch="",
                branch="",
                source=source,
            )

        if len(parts) != 4:
            raise ValueError(f"Invalid Flatpak ref: {value}")
        kind, app_id, arch, branch = parts
        if kind != "app":
            raise ValueError(f"Only Flatpak app refs are supported: {value}")
        if not APP_ID_RE.match(app_id) or not arch or not branch:
            raise ValueError(f"Invalid Flatpak ref: {value}")
        return ConfigEntry(
            scope=scope,
            value=value,
            app_id=app_id,
            remote=remote,
            kind=kind,
            arch=arch,
            branch=branch,
            source=source,
        )

    def matches(self, app: InstalledApp) -> bool:
        if self.scope != app.scope:
            return False
        if not self.qualified:
            return self.app_id == app.app_id
        return (
            self.app_id == app.app_id
            and self.effective_remote == app.remote
            and self.kind == app.kind
            and self.arch == app.arch
            and self.branch == app.branch
        )


def default_config_dir() -> Path:
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home) / "flatbak"
    return Path.home() / ".config" / "flatbak"


def load_config(config_dir: Path, *, create: bool) -> Config:
    if create:
        ensure_root_config(config_dir)

    entries_by_key: dict[tuple[str, str, str, str, str, str], ConfigEntry] = {}
    if not config_dir.exists():
        return Config(entries=[])
    paths = sorted([*config_dir.glob("*.yml"), *config_dir.glob("*.yaml")])
    for path in paths:
        for scope, value in parse_yaml_config(path).items():
            for item in value:
                entry = ConfigEntry.parse(item, scope=scope, source=path)
                entries_by_key.setdefault(entry.match_key, entry)
    return Config(entries=list(entries_by_key.values()))


def parse_yaml_config(path: Path) -> dict[Scope, list[str]]:
    result: dict[Scope, list[str]] = {"user": [], "system": []}

    data: object = yaml.safe_load(path.read_text())
    if data is None:
        return result
    if not isinstance(data, dict):
        raise ValueError(
            f"Invalid config {path}: top-level YAML value must be a mapping"
        )

    mapping = cast(dict[object, object], data)
    for key, value in mapping.items():
        if key == "user":
            scope: Scope = "user"
        elif key == "system":
            scope = "system"
        else:
            raise ValueError(f"Invalid config {path}: unknown top-level key '{key}'")
        if value is None:
            continue
        if not isinstance(value, list):
            raise ValueError(f"Invalid config {path}: expected list value for {scope}")
        items = cast(list[object], value)
        for item in items:
            if not isinstance(item, str):
                raise ValueError(
                    f"Invalid config {path}: entries under {scope} must be strings"
                )
            result[scope].append(item)
    return result


def append_root_entries(config_dir: Path, entries: list[ConfigEntry]) -> None:
    ensure_root_config(config_dir)
    root = config_dir / "root.yml"
    existing = parse_yaml_config(root)
    for entry in entries:
        existing[entry.scope].append(entry.value)
    root.write_text(format_yaml_config(existing))


def format_yaml_config(entries: dict[Scope, list[str]]) -> str:
    lines: list[str] = []
    for scope in SCOPES:
        values = entries[scope]
        if not values:
            lines.append(f"{scope}: []")
            continue
        lines.append(f"{scope}:")
        for value in values:
            lines.append(f"  - {value}")
    return "\n".join(lines) + "\n"


def ensure_root_config(config_dir: Path) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    root = config_dir / "root.yml"
    if not root.exists() or root.read_text() == "":
        root.write_text(format_yaml_config({"user": [], "system": []}))

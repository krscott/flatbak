from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from flatbak.flatpak import InstalledApp

APP_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*(?:\.[A-Za-z0-9][A-Za-z0-9_-]*)+$")


@dataclass(kw_only=True, frozen=True)
class Config:
    entries: list[ConfigEntry]


@dataclass(kw_only=True, frozen=True)
class ConfigEntry:
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
    def match_key(self) -> tuple[str, str, str, str, str]:
        if not self.qualified:
            return ("app-id", self.app_id, "", "", "")
        return (self.effective_remote, self.kind, self.app_id, self.arch, self.branch)

    @staticmethod
    def parse(value: str, source: Path | None = None) -> ConfigEntry:
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
            value=value,
            app_id=app_id,
            remote=remote,
            kind=kind,
            arch=arch,
            branch=branch,
            source=source,
        )

    def matches(self, app: InstalledApp) -> bool:
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
        config_dir.mkdir(parents=True, exist_ok=True)
        root = config_dir / "root.txt"
        root.touch(exist_ok=True)

    entries_by_value: dict[str, ConfigEntry] = {}
    if not config_dir.exists():
        return Config(entries=[])
    for path in sorted(config_dir.glob("*.txt")):
        for line in path.read_text().splitlines():
            value = parse_config_line(line)
            if value is None:
                continue
            entries_by_value.setdefault(value, ConfigEntry.parse(value, source=path))
    return Config(entries=list(entries_by_value.values()))


def parse_config_line(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    comment_start = stripped.find(" #")
    if comment_start != -1:
        stripped = stripped[:comment_start].rstrip()
    return stripped or None


def append_root_entries(config_dir: Path, entries: list[str]) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    root = config_dir / "root.txt"
    existing = root.read_text() if root.exists() else ""
    prefix = "" if existing == "" or existing.endswith("\n") else "\n"
    root.write_text(existing + prefix + "\n".join(entries) + "\n")

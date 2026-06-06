from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, cast

from flatbak.flatpak import Scope

SCHEMA_VERSION = 1


@dataclass(kw_only=True, frozen=True)
class TrackedApp:
    app_id: str
    scope: Scope = "user"
    installed_ref: str | None = None
    source: str | None = None


@dataclass(kw_only=True, frozen=True)
class State:
    schema_version: int = SCHEMA_VERSION
    tracked: list[TrackedApp] | None = None

    @property
    def tracked_apps(self) -> list[TrackedApp]:
        return self.tracked or []

    def to_dict(self) -> dict[str, Any]:
        assert is_dataclass(self)
        data = asdict(self)
        data["tracked"] = data["tracked"] or []
        return data

    @staticmethod
    def from_dict(data: dict[str, Any]) -> State:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported state schema version: {version}")
        raw_tracked = data.get("tracked", [])
        if not isinstance(raw_tracked, list):
            raise ValueError("Invalid state: tracked must be a list")
        tracked_data = cast(list[object], raw_tracked)
        tracked: list[TrackedApp] = []
        for item in tracked_data:
            if not isinstance(item, dict):
                raise ValueError("Invalid state: tracked app missing app_id")
            tracked_item = cast(dict[str, object], item)
            app_id = tracked_item.get("app_id")
            if not isinstance(app_id, str):
                raise ValueError("Invalid state: tracked app missing app_id")
            scope = tracked_item.get("scope")
            if scope == "user":
                tracked_scope: Scope = "user"
            elif scope == "system":
                tracked_scope = "system"
            else:
                raise ValueError("Invalid state: tracked app missing scope")
            installed_ref = tracked_item.get("installed_ref")
            source = tracked_item.get("source")
            tracked.append(
                TrackedApp(
                    scope=tracked_scope,
                    app_id=app_id,
                    installed_ref=(
                        installed_ref if isinstance(installed_ref, str) else None
                    ),
                    source=source if isinstance(source, str) else None,
                )
            )
        return State(tracked=tracked)


def default_data_dir() -> Path:
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home) / "flatbak"
    return Path.home() / ".local" / "share" / "flatbak"


def load_state(path: Path) -> State:
    if not path.exists():
        return State(tracked=[])
    raw = cast(object, json.loads(path.read_text()))
    if not isinstance(raw, dict):
        raise ValueError("Invalid state: expected JSON object")
    return State.from_dict(cast(dict[str, Any], raw))


def save_state(path: Path, state: State) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n")

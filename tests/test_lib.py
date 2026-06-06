from __future__ import annotations

import json
from pathlib import Path

import pytest

from flatbak.config import ConfigEntry, load_config
from flatbak.flatpak import Flatpak, InstalledApp, Scope
from flatbak.lib import Options, Paths, reconcile
from flatbak.state import State, TrackedApp, load_state, save_state


class FakeFlatpak(Flatpak):
    def __init__(
        self,
        apps: list[InstalledApp],
        remotes: dict[Scope, set[str]] | None = None,
    ) -> None:
        self.apps = apps
        self.available_remotes = remotes or {"user": {"flathub"}, "system": {"flathub"}}
        self.installs: list[str] = []
        self.uninstalls: list[str] = []

    def list_installed_apps(self) -> list[InstalledApp]:
        return list(self.apps)

    def remotes(self, scope: Scope) -> set[str]:
        return self.available_remotes[scope]

    def resolve(self, entry: object) -> InstalledApp:
        assert isinstance(entry, ConfigEntry)
        if entry.effective_remote not in self.available_remotes[entry.scope]:
            raise ValueError(f"No such ref: {entry.value}")
        if entry.qualified:
            return InstalledApp(
                scope=entry.scope,
                app_id=entry.app_id,
                remote=entry.effective_remote,
                kind=entry.kind,
                arch=entry.arch,
                branch=entry.branch,
            )
        return InstalledApp(
            scope=entry.scope,
            app_id=entry.app_id,
            remote=entry.effective_remote,
            arch="x86_64",
            branch="stable",
        )

    def install(self, entry: object) -> None:
        assert isinstance(entry, ConfigEntry)
        self.installs.append(f"{entry.scope} {entry.effective_remote} {entry.ref}")
        installed = self.resolve(entry)
        if not any(entry.matches(app) for app in self.apps):
            self.apps.append(installed)

    def uninstall(self, scope: Scope, ref: str) -> None:
        self.uninstalls.append(f"{scope} {ref}")


def test_installed_app_parses_flatpak_list_ref_without_kind() -> None:
    app = InstalledApp.from_ref(
        "org.audacityteam.Audacity/x86_64/stable",
        remote="flathub",
        scope="system",
    )

    assert app == InstalledApp(
        scope="system",
        app_id="org.audacityteam.Audacity",
        remote="flathub",
        arch="x86_64",
        branch="stable",
    )


def test_load_config_merges_yaml_files_and_deduplicates_by_scope(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "root.yml").write_text("user:\n  - org.mozilla.firefox\n")
    (config_dir / "shared.yaml").write_text(
        "user:\n  - org.mozilla.firefox\n"
        "system:\n  - org.mozilla.firefox\n  - org.gnome.Calculator\n"
    )
    (config_dir / "ignored.txt").write_text("user:\n  - org.example.Ignored\n")

    config = load_config(config_dir, create=True)

    assert [(entry.scope, entry.value) for entry in config.entries] == [
        ("user", "org.mozilla.firefox"),
        ("system", "org.mozilla.firefox"),
        ("system", "org.gnome.Calculator"),
    ]
    assert (config_dir / "root.yml").exists()


def test_load_config_rejects_unknown_top_level_yaml_key(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "bad.yml").write_text("apps:\n  - org.mozilla.firefox\n")

    with pytest.raises(ValueError, match="unknown top-level key 'apps'"):
        load_config(config_dir, create=False)


def test_load_config_accepts_standard_yaml_forms(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "root.yml").write_text(
        "user: [org.mozilla.firefox]\n"
        "system: # apps installed by Software may land here\n"
        "  - 'org.audacityteam.Audacity'\n"
    )

    config = load_config(config_dir, create=False)

    assert [(entry.scope, entry.value) for entry in config.entries] == [
        ("user", "org.mozilla.firefox"),
        ("system", "org.audacityteam.Audacity"),
    ]


def test_load_config_treats_empty_scope_as_empty_list(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "root.yml").write_text(
        "user:\n" "system:\n" "  - org.audacityteam.Audacity\n"
    )

    config = load_config(config_dir, create=False)

    assert [(entry.scope, entry.value) for entry in config.entries] == [
        ("system", "org.audacityteam.Audacity"),
    ]


def test_load_config_rejects_non_list_scope_value(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "bad.yml").write_text("user: org.mozilla.firefox\n")

    with pytest.raises(ValueError, match="user"):
        load_config(config_dir, create=False)


def test_load_config_rejects_non_string_entries(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "bad.yml").write_text("user:\n  - 123\n")

    with pytest.raises(ValueError, match="user"):
        load_config(config_dir, create=False)


def test_state_round_trip_includes_scope(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    save_state(
        state_path,
        State(
            tracked=[
                TrackedApp(
                    scope="system",
                    app_id="org.mozilla.firefox",
                    installed_ref="app/org.mozilla.firefox/x86_64/stable",
                    source="org.mozilla.firefox",
                )
            ]
        ),
    )

    assert load_state(state_path).tracked_apps == [
        TrackedApp(
            scope="system",
            app_id="org.mozilla.firefox",
            installed_ref="app/org.mozilla.firefox/x86_64/stable",
            source="org.mozilla.firefox",
        )
    ]


def test_reconcile_adopts_user_and_system_apps_under_actual_scope(
    tmp_path: Path,
) -> None:
    paths = Paths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    flatpak = FakeFlatpak(
        [
            InstalledApp(scope="user", app_id="org.mozilla.firefox", remote="flathub"),
            InstalledApp(
                scope="system", app_id="org.gnome.Calculator", remote="flathub"
            ),
        ]
    )

    result = reconcile(Options(), paths, flatpak)

    assert result.adopted == [
        "user:org.mozilla.firefox",
        "system:org.gnome.Calculator",
    ]
    assert (paths.config_dir / "root.yml").read_text() == (
        "user:\n" "  - org.mozilla.firefox\n" "system:\n" "  - org.gnome.Calculator\n"
    )
    state = json.loads((paths.data_dir / "state.json").read_text())
    assert {(item["scope"], item["app_id"]) for item in state["tracked"]} == {
        ("user", "org.mozilla.firefox"),
        ("system", "org.gnome.Calculator"),
    }


def test_reconcile_installs_missing_apps_in_configured_scope(tmp_path: Path) -> None:
    paths = Paths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    paths.config_dir.mkdir()
    (paths.config_dir / "root.yml").write_text(
        "user:\n  - org.mozilla.firefox\nsystem:\n  - org.gnome.Calculator\n"
    )
    flatpak = FakeFlatpak([])

    result = reconcile(Options(), paths, flatpak)

    assert result.installed == [
        "user:org.mozilla.firefox",
        "system:org.gnome.Calculator",
    ]
    assert flatpak.installs == [
        "user flathub org.mozilla.firefox",
        "system flathub org.gnome.Calculator",
    ]


def test_bare_app_id_matching_is_scope_aware(tmp_path: Path) -> None:
    paths = Paths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    paths.config_dir.mkdir()
    (paths.config_dir / "root.yml").write_text("system:\n  - org.mozilla.firefox\n")
    flatpak = FakeFlatpak(
        [InstalledApp(scope="user", app_id="org.mozilla.firefox", remote="flathub")]
    )

    result = reconcile(Options(), paths, flatpak)

    assert result.adopted == ["user:org.mozilla.firefox"]
    assert result.installed == ["system:org.mozilla.firefox"]


def test_qualified_ref_matching_requires_scope_remote_and_branch(
    tmp_path: Path,
) -> None:
    paths = Paths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    paths.config_dir.mkdir()
    (paths.config_dir / "root.yml").write_text(
        "user:\n  - testremote:app/org.mozilla.firefox/x86_64/stable\n"
    )
    save_state(
        paths.data_dir / "state.json",
        State(
            tracked=[
                TrackedApp(
                    scope="user",
                    app_id="org.mozilla.firefox",
                    installed_ref="app/org.mozilla.firefox/x86_64/stable",
                )
            ]
        ),
    )
    flatpak = FakeFlatpak(
        [
            InstalledApp(
                scope="user",
                app_id="org.mozilla.firefox",
                remote="flathub",
                arch="x86_64",
                branch="stable",
            )
        ],
        remotes={"user": {"flathub", "testremote"}, "system": {"flathub"}},
    )

    result = reconcile(Options(), paths, flatpak)

    assert result.removed == ["user:app/org.mozilla.firefox/x86_64/stable"]
    assert result.installed == ["user:testremote:app/org.mozilla.firefox/x86_64/stable"]
    assert flatpak.uninstalls == ["user app/org.mozilla.firefox/x86_64/stable"]
    assert flatpak.installs == ["user testremote app/org.mozilla.firefox/x86_64/stable"]


def test_removal_uses_tracked_scope_and_stale_ref_falls_back_to_app_id(
    tmp_path: Path,
) -> None:
    paths = Paths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    paths.config_dir.mkdir()
    (paths.config_dir / "root.yml").write_text("")
    save_state(
        paths.data_dir / "state.json",
        State(
            tracked=[
                TrackedApp(
                    scope="system",
                    app_id="org.mozilla.firefox",
                    installed_ref="app/org.mozilla.firefox/x86_64/stable",
                )
            ]
        ),
    )
    flatpak = FakeFlatpak(
        [
            InstalledApp(scope="user", app_id="org.mozilla.firefox", remote="flathub"),
            InstalledApp(
                scope="system",
                app_id="org.mozilla.firefox",
                remote="flathub",
                arch="x86_64",
                branch="beta",
            ),
        ]
    )

    result = reconcile(Options(), paths, flatpak)

    assert result.removed == ["system:app/org.mozilla.firefox/x86_64/beta"]
    assert result.adopted == ["user:org.mozilla.firefox"]
    assert flatpak.uninstalls == ["system app/org.mozilla.firefox/x86_64/beta"]


def test_preflight_validation_happens_before_writes_or_mutations(
    tmp_path: Path,
) -> None:
    paths = Paths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    paths.config_dir.mkdir()
    (paths.config_dir / "wanted.yml").write_text("system:\n  - org.mozilla.firefox\n")
    flatpak = FakeFlatpak([], remotes={"user": {"flathub"}, "system": set()})

    with pytest.raises(ValueError, match="system scope"):
        reconcile(Options(), paths, flatpak)

    assert not (paths.config_dir / "root.yml").exists()
    assert not paths.data_dir.exists()
    assert flatpak.installs == []
    assert flatpak.uninstalls == []


def test_post_install_verification_rejects_wrong_scope(tmp_path: Path) -> None:
    paths = Paths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    paths.config_dir.mkdir()
    (paths.config_dir / "root.yml").write_text("system:\n  - org.mozilla.firefox\n")

    class WrongScopeAfterInstallFlatpak(FakeFlatpak):
        def install(self, entry: object) -> None:
            assert isinstance(entry, ConfigEntry)
            self.installs.append(f"{entry.scope} {entry.effective_remote} {entry.ref}")
            self.apps.append(
                InstalledApp(scope="user", app_id=entry.app_id, remote="flathub")
            )

    flatpak = WrongScopeAfterInstallFlatpak([])

    with pytest.raises(ValueError, match="not reported"):
        reconcile(Options(), paths, flatpak)

    assert not paths.data_dir.exists()


def test_post_install_verification_rejects_wrong_branch_for_qualified_ref(
    tmp_path: Path,
) -> None:
    paths = Paths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    paths.config_dir.mkdir()
    (paths.config_dir / "root.yml").write_text(
        "user:\n  - app/org.mozilla.firefox/x86_64/stable\n"
    )

    class WrongBranchAfterInstallFlatpak(FakeFlatpak):
        def install(self, entry: object) -> None:
            assert isinstance(entry, ConfigEntry)
            self.installs.append(f"{entry.scope} {entry.effective_remote} {entry.ref}")
            self.apps.append(
                InstalledApp(
                    scope=entry.scope,
                    app_id=entry.app_id,
                    remote=entry.effective_remote,
                    arch="x86_64",
                    branch="beta",
                )
            )

    flatpak = WrongBranchAfterInstallFlatpak([])

    with pytest.raises(ValueError, match="not reported"):
        reconcile(Options(), paths, flatpak)

    assert not paths.data_dir.exists()


def test_dry_run_does_not_write_or_call_mutations_and_reports_scope(
    tmp_path: Path,
) -> None:
    paths = Paths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    flatpak = FakeFlatpak(
        [InstalledApp(scope="system", app_id="org.mozilla.firefox", remote="flathub")]
    )

    result = reconcile(Options(dry_run=True), paths, flatpak)

    assert result.adopted == ["system:org.mozilla.firefox"]
    assert not paths.config_dir.exists()
    assert not paths.data_dir.exists()
    assert flatpak.installs == []
    assert flatpak.uninstalls == []

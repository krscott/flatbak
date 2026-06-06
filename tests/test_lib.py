from __future__ import annotations

import json
from pathlib import Path

import pytest

from flatbak.config import ConfigEntry, load_config, parse_config_line
from flatbak.flatpak import Flatpak, InstalledApp
from flatbak.lib import Options, Paths, reconcile
from flatbak.state import State, TrackedApp, load_state, save_state


class FakeFlatpak(Flatpak):
    def __init__(
        self, apps: list[InstalledApp], remotes: set[str] | None = None
    ) -> None:
        self.apps = apps
        self.available_remotes = remotes if remotes is not None else {"flathub"}
        self.installs: list[str] = []
        self.uninstalls: list[str] = []

    def list_installed_apps(self) -> list[InstalledApp]:
        return list(self.apps)

    def remotes(self) -> set[str]:
        return self.available_remotes

    def resolve(self, entry: object) -> InstalledApp:
        assert isinstance(entry, ConfigEntry)
        if entry.effective_remote not in self.available_remotes:
            raise ValueError(f"No such ref: {entry.value}")
        if entry.qualified:
            return InstalledApp(
                app_id=entry.app_id,
                remote=entry.effective_remote,
                kind=entry.kind,
                arch=entry.arch,
                branch=entry.branch,
            )
        return InstalledApp(
            app_id=entry.app_id,
            remote=entry.effective_remote,
            arch="x86_64",
            branch="stable",
        )

    def install(self, entry: object) -> None:
        assert isinstance(entry, ConfigEntry)
        self.installs.append(f"{entry.remote or 'flathub'} {entry.ref}")
        installed = self.resolve(entry)
        if not any(entry.matches(app) for app in self.apps):
            self.apps.append(installed)

    def uninstall(self, ref: str) -> None:
        self.uninstalls.append(ref)


def test_parse_config_line() -> None:
    assert parse_config_line(" org.mozilla.firefox  ") == "org.mozilla.firefox"
    assert parse_config_line("org.example.App#channel") == "org.example.App#channel"
    assert parse_config_line("org.example.App # comment") == "org.example.App"
    assert parse_config_line("# comment") is None
    assert parse_config_line("  ") is None


def test_load_config_merges_txt_files_and_deduplicates(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "root.txt").write_text("org.mozilla.firefox\n")
    (config_dir / "shared.txt").write_text(
        "org.mozilla.firefox\norg.gnome.Calculator\n"
    )
    (config_dir / "ignored.md").write_text("org.example.Ignored\n")

    config = load_config(config_dir, create=True)

    assert [entry.value for entry in config.entries] == [
        "org.mozilla.firefox",
        "org.gnome.Calculator",
    ]


def test_state_round_trip(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    save_state(
        state_path,
        State(
            tracked=[
                TrackedApp(
                    app_id="org.mozilla.firefox",
                    installed_ref="app/org.mozilla.firefox/x86_64/stable",
                    source="org.mozilla.firefox",
                )
            ]
        ),
    )

    assert load_state(state_path) == State(
        tracked=[
            TrackedApp(
                app_id="org.mozilla.firefox",
                installed_ref="app/org.mozilla.firefox/x86_64/stable",
                source="org.mozilla.firefox",
            )
        ]
    )


def test_reconcile_adopts_untracked_installed_app(tmp_path: Path) -> None:
    paths = Paths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    flatpak = FakeFlatpak(
        [
            InstalledApp(
                app_id="org.mozilla.firefox",
                remote="flathub",
                arch="x86_64",
                branch="stable",
            )
        ]
    )

    result = reconcile(Options(), paths, flatpak)

    assert result.adopted == ["org.mozilla.firefox"]
    assert (paths.config_dir / "root.txt").read_text() == "org.mozilla.firefox\n"
    state = json.loads((paths.data_dir / "state.json").read_text())
    assert state["tracked"][0]["app_id"] == "org.mozilla.firefox"


def test_reconcile_installs_missing_configured_app(tmp_path: Path) -> None:
    paths = Paths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    paths.config_dir.mkdir()
    (paths.config_dir / "root.txt").write_text("org.mozilla.firefox\n")
    flatpak = FakeFlatpak([])

    result = reconcile(Options(), paths, flatpak)

    assert result.installed == ["org.mozilla.firefox"]
    assert flatpak.installs == ["flathub org.mozilla.firefox"]


def test_reconcile_persists_resolved_ref_after_install(tmp_path: Path) -> None:
    paths = Paths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    paths.config_dir.mkdir()
    (paths.config_dir / "root.txt").write_text("org.mozilla.firefox\n")

    class ResolvingFlatpak(FakeFlatpak):
        def install(self, entry: object) -> None:
            super().install(entry)
            assert isinstance(entry, ConfigEntry)
            self.apps.append(
                InstalledApp(
                    app_id=entry.app_id,
                    remote=entry.effective_remote,
                    arch="x86_64",
                    branch="stable",
                )
            )

    flatpak = ResolvingFlatpak([])

    reconcile(Options(), paths, flatpak)

    state = load_state(paths.data_dir / "state.json")
    assert state.tracked_apps == [
        TrackedApp(
            app_id="org.mozilla.firefox",
            installed_ref="app/org.mozilla.firefox/x86_64/stable",
            source="org.mozilla.firefox",
        )
    ]


def test_qualified_ref_without_remote_matches_flathub_install(tmp_path: Path) -> None:
    paths = Paths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    paths.config_dir.mkdir()
    (paths.config_dir / "root.txt").write_text(
        "app/org.mozilla.firefox/x86_64/stable\n"
    )
    flatpak = FakeFlatpak(
        [
            InstalledApp(
                app_id="org.mozilla.firefox",
                remote="flathub",
                arch="x86_64",
                branch="stable",
            )
        ]
    )

    result = reconcile(Options(), paths, flatpak)

    assert not result.installed
    assert not result.removed
    assert result.tracked == ["org.mozilla.firefox"]


def test_reconcile_removes_tracked_app_no_longer_configured(tmp_path: Path) -> None:
    paths = Paths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    paths.config_dir.mkdir()
    (paths.config_dir / "root.txt").write_text("")
    save_state(
        paths.data_dir / "state.json",
        State(tracked=[TrackedApp(app_id="org.mozilla.firefox")]),
    )
    flatpak = FakeFlatpak(
        [InstalledApp(app_id="org.mozilla.firefox", remote="flathub")]
    )

    result = reconcile(Options(), paths, flatpak)

    assert result.removed == ["org.mozilla.firefox"]
    assert flatpak.uninstalls == ["org.mozilla.firefox"]
    assert load_state(paths.data_dir / "state.json").tracked_apps == []


def test_reconcile_removes_mismatched_branch_before_installing_configured_ref(
    tmp_path: Path,
) -> None:
    paths = Paths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    paths.config_dir.mkdir()
    (paths.config_dir / "root.txt").write_text(
        "app/org.mozilla.firefox/x86_64/stable\n"
    )
    save_state(
        paths.data_dir / "state.json",
        State(
            tracked=[
                TrackedApp(
                    app_id="org.mozilla.firefox",
                    installed_ref="app/org.mozilla.firefox/x86_64/beta",
                )
            ]
        ),
    )
    flatpak = FakeFlatpak(
        [
            InstalledApp(
                app_id="org.mozilla.firefox",
                remote="flathub",
                arch="x86_64",
                branch="beta",
            )
        ]
    )

    result = reconcile(Options(), paths, flatpak)

    assert result.removed == ["app/org.mozilla.firefox/x86_64/beta"]
    assert result.installed == ["app/org.mozilla.firefox/x86_64/stable"]
    assert flatpak.uninstalls == ["app/org.mozilla.firefox/x86_64/beta"]
    assert flatpak.installs == ["flathub app/org.mozilla.firefox/x86_64/stable"]


def test_reconcile_removes_tracked_app_when_stored_ref_is_stale(
    tmp_path: Path,
) -> None:
    paths = Paths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    paths.config_dir.mkdir()
    (paths.config_dir / "root.txt").write_text("")
    save_state(
        paths.data_dir / "state.json",
        State(
            tracked=[
                TrackedApp(
                    app_id="org.mozilla.firefox",
                    installed_ref="app/org.mozilla.firefox/x86_64/stable",
                )
            ]
        ),
    )
    flatpak = FakeFlatpak(
        [
            InstalledApp(
                app_id="org.mozilla.firefox",
                remote="flathub",
                arch="x86_64",
                branch="beta",
            )
        ]
    )

    result = reconcile(Options(), paths, flatpak)

    assert result.removed == ["app/org.mozilla.firefox/x86_64/beta"]
    assert flatpak.uninstalls == ["app/org.mozilla.firefox/x86_64/beta"]
    assert load_state(paths.data_dir / "state.json").tracked_apps == []


def test_reconcile_does_not_remove_before_unresolvable_install(
    tmp_path: Path,
) -> None:
    paths = Paths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    paths.config_dir.mkdir()
    (paths.config_dir / "root.txt").write_text(
        "app/org.mozilla.firefox/x86_64/stable\n"
    )
    save_state(
        paths.data_dir / "state.json",
        State(
            tracked=[
                TrackedApp(
                    app_id="org.mozilla.firefox",
                    installed_ref="app/org.mozilla.firefox/x86_64/beta",
                )
            ]
        ),
    )

    class InstallFailsFlatpak(FakeFlatpak):
        def resolve(self, entry: object) -> InstalledApp:
            raise ValueError("No such ref")

    flatpak = InstallFailsFlatpak(
        [
            InstalledApp(
                app_id="org.mozilla.firefox",
                remote="flathub",
                arch="x86_64",
                branch="beta",
            )
        ]
    )

    with pytest.raises(ValueError, match="No such ref"):
        reconcile(Options(), paths, flatpak)

    assert flatpak.uninstalls == []
    state = load_state(paths.data_dir / "state.json")
    assert state.tracked_apps == [
        TrackedApp(
            app_id="org.mozilla.firefox",
            installed_ref="app/org.mozilla.firefox/x86_64/beta",
        )
    ]


def test_reconcile_does_not_write_config_before_unresolvable_install(
    tmp_path: Path,
) -> None:
    paths = Paths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    paths.config_dir.mkdir()
    (paths.config_dir / "wanted.txt").write_text("org.mozilla.firefox\n")

    class ResolveFailsFlatpak(FakeFlatpak):
        def resolve(self, entry: object) -> InstalledApp:
            raise ValueError("No such ref")

    flatpak = ResolveFailsFlatpak([])

    with pytest.raises(ValueError, match="No such ref"):
        reconcile(Options(), paths, flatpak)

    assert not (paths.config_dir / "root.txt").exists()
    assert not paths.data_dir.exists()
    assert flatpak.installs == []
    assert flatpak.uninstalls == []


def test_reconcile_fails_if_installed_app_is_not_reported_after_install(
    tmp_path: Path,
) -> None:
    paths = Paths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    paths.config_dir.mkdir()
    (paths.config_dir / "root.txt").write_text("org.mozilla.firefox\n")

    class InstallNotReportedFlatpak(FakeFlatpak):
        def install(self, entry: object) -> None:
            assert isinstance(entry, ConfigEntry)
            self.installs.append(f"{entry.remote or 'flathub'} {entry.ref}")

    flatpak = InstallNotReportedFlatpak([])

    with pytest.raises(ValueError, match="not reported"):
        reconcile(Options(), paths, flatpak)

    assert not paths.data_dir.exists()


def test_reconcile_rejects_wrong_branch_after_qualified_install(
    tmp_path: Path,
) -> None:
    paths = Paths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    paths.config_dir.mkdir()
    (paths.config_dir / "root.txt").write_text(
        "app/org.mozilla.firefox/x86_64/stable\n"
    )

    class WrongBranchAfterInstallFlatpak(FakeFlatpak):
        def install(self, entry: object) -> None:
            assert isinstance(entry, ConfigEntry)
            self.installs.append(f"{entry.remote or 'flathub'} {entry.ref}")
            self.apps.append(
                InstalledApp(
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


def test_reconcile_removes_mismatched_remote_before_installing_configured_ref(
    tmp_path: Path,
) -> None:
    paths = Paths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    paths.config_dir.mkdir()
    (paths.config_dir / "root.txt").write_text(
        "testremote:app/org.mozilla.firefox/x86_64/stable\n"
    )
    save_state(
        paths.data_dir / "state.json",
        State(
            tracked=[
                TrackedApp(
                    app_id="org.mozilla.firefox",
                    installed_ref="app/org.mozilla.firefox/x86_64/stable",
                )
            ]
        ),
    )
    flatpak = FakeFlatpak(
        [
            InstalledApp(
                app_id="org.mozilla.firefox",
                remote="flathub",
                arch="x86_64",
                branch="stable",
            )
        ],
        remotes={"flathub", "testremote"},
    )

    result = reconcile(Options(), paths, flatpak)

    assert result.removed == ["app/org.mozilla.firefox/x86_64/stable"]
    assert result.installed == ["testremote:app/org.mozilla.firefox/x86_64/stable"]
    assert flatpak.uninstalls == ["app/org.mozilla.firefox/x86_64/stable"]
    assert flatpak.installs == ["testremote app/org.mozilla.firefox/x86_64/stable"]


def test_reconcile_dry_run_does_not_write_or_call_mutations(tmp_path: Path) -> None:
    paths = Paths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    flatpak = FakeFlatpak(
        [InstalledApp(app_id="org.mozilla.firefox", remote="flathub")]
    )

    result = reconcile(Options(dry_run=True), paths, flatpak)

    assert result.adopted == ["org.mozilla.firefox"]
    assert not paths.config_dir.exists()
    assert not paths.data_dir.exists()
    assert flatpak.installs == []
    assert flatpak.uninstalls == []


def test_missing_required_remote_fails(tmp_path: Path) -> None:
    paths = Paths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    paths.config_dir.mkdir()
    (paths.config_dir / "root.txt").write_text("org.mozilla.firefox\n")
    flatpak = FakeFlatpak([], remotes=set())

    with pytest.raises(ValueError, match="flathub"):
        reconcile(Options(), paths, flatpak)

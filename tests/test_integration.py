from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


def fake_flatpak(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "flatpak.log"
    executable = bin_dir / "flatpak"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        "import sys\n"
        f"log = Path({str(log)!r})\n"
        "args = sys.argv[1:]\n"
        "if args[:4] == ['list', '--user', '--app', '--columns=application,origin,ref']:\n"
        "    print('org.mozilla.firefox\\tflathub\\torg.mozilla.firefox/x86_64/stable')\n"
        "elif args[:4] == ['list', '--system', '--app', '--columns=application,origin,ref']:\n"
        "    pass\n"
        "elif args[:3] == ['remotes', '--user', '--columns=name']:\n"
        "    print('flathub')\n"
        "elif args[:3] == ['remotes', '--system', '--columns=name']:\n"
        "    print('flathub')\n"
        "elif args[:4] == ['remote-ls', '--user', '--app', '--columns=application,ref']:\n"
        "    print('org.mozilla.firefox\\tapp/org.mozilla.firefox/x86_64/stable')\n"
        "elif args[:4] == ['remote-ls', '--system', '--app', '--columns=application,ref']:\n"
        "    print('org.mozilla.firefox\\tapp/org.mozilla.firefox/x86_64/stable')\n"
        "elif args and args[0] in {'install', 'uninstall'}:\n"
        "    log.write_text(log.read_text() + ' '.join(args) + '\\n' if log.exists() else ' '.join(args) + '\\n')\n"
        "else:\n"
        "    print('unexpected flatpak args: ' + ' '.join(args), file=sys.stderr)\n"
        "    raise SystemExit(2)\n"
    )
    executable.chmod(0o755)
    return bin_dir


@pytest.mark.integration
def test_cli_adopts_installed_app(tmp_path: Path) -> None:
    bin_dir = fake_flatpak(tmp_path)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config-home")
    env["XDG_DATA_HOME"] = str(tmp_path / "data-home")

    result = subprocess.run(["flatbak"], capture_output=True, text=True, env=env)

    assert result.returncode == 0
    assert "adopt user:org.mozilla.firefox" in result.stdout
    assert (tmp_path / "config-home" / "flatbak" / "root.yml").read_text() == (
        "user:\n  - org.mozilla.firefox\nsystem: []\n"
    )


@pytest.mark.integration
def test_cli_dry_run_does_not_write(tmp_path: Path) -> None:
    bin_dir = fake_flatpak(tmp_path)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config-home")
    env["XDG_DATA_HOME"] = str(tmp_path / "data-home")

    result = subprocess.run(
        ["flatbak", "--dry-run"], capture_output=True, text=True, env=env
    )

    assert result.returncode == 0
    assert "Would adopt user:org.mozilla.firefox" in result.stdout
    assert not (tmp_path / "config-home").exists()
    assert not (tmp_path / "data-home").exists()


@pytest.mark.integration
def test_module_dry_run_invokes_cli(tmp_path: Path) -> None:
    bin_dir = fake_flatpak(tmp_path)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config-home")
    env["XDG_DATA_HOME"] = str(tmp_path / "data-home")

    result = subprocess.run(
        [sys.executable, "-m", "flatbak", "--dry-run"],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0
    assert "Would adopt user:org.mozilla.firefox" in result.stdout


@pytest.mark.integration
def test_cli_verbose_flag(tmp_path: Path) -> None:
    bin_dir = fake_flatpak(tmp_path)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config-home")
    env["XDG_DATA_HOME"] = str(tmp_path / "data-home")

    result = subprocess.run(
        ["flatbak", "--verbose"], capture_output=True, text=True, env=env
    )

    assert result.returncode == 0

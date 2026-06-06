# flatbak

Synchronize your Flatpak apps from YAML config files.

`flatbak` keeps user and system Flatpak app installs aligned with a config
directory. It is designed for people who want reproducible Flatpak installs
without needing to care whether a software center installed an app for the user
or system.

## Quick Start

Preview what flatbak would do:

```sh
flatbak --dry-run
```

Apply changes:

```sh
flatbak
```

On the first run, flatbak creates `root.yml` and adopts your already installed
Flatpak apps into the scope where they are installed.

## Config

flatbak reads config from:

```txt
~/.config/flatbak/*.yml
~/.config/flatbak/*.yaml
```

If `XDG_CONFIG_HOME` is set, it uses `$XDG_CONFIG_HOME/flatbak` instead.

Config files are YAML mappings with `user` and `system` sections:

```yaml
user:
  - org.mozilla.firefox
  - org.gnome.Calculator

system:
  - org.audacityteam.Audacity
```

Bare app IDs install from `flathub` by default.

If you need a specific remote, architecture, or branch, use a qualified ref:

```yaml
user:
  - flathub:app/org.gnome.Calculator/x86_64/stable
```

`root.yml` is machine-local and is the only config file flatbak writes. You can
move entries from `root.yml` into other `.yml` or `.yaml` files, including
symlinked files shared across machines.

## What It Does

On each run, flatbak:

- Adds installed but unmanaged user apps under `user:` in `root.yml`.
- Adds installed but unmanaged system apps under `system:` in `root.yml`.
- Installs configured apps into their configured scope.
- Removes tracked apps that are no longer configured in their tracked scope.
- Tracks installed apps that are already present in config.
- Leaves runtimes and extensions to Flatpak.

## Safety

flatbak only removes apps that it has tracked. An app installed outside flatbak is
first adopted into `root.yml` and tracked, rather than removed.

Before changing installs, flatbak validates configured remotes and app refs where
possible. If `flathub` is required but missing for a scope, flatbak fails with an
error instead of adding the remote automatically.

## Options

Enable verbose logging:

```sh
flatbak --verbose
```

`FLATBAK_VERBOSE=1` also enables verbose logging.

## Development

State is stored in:

```txt
~/.local/share/flatbak/state.json
```

If `XDG_DATA_HOME` is set, state is stored in
`$XDG_DATA_HOME/flatbak/state.json` instead.

Start the Nix development shell:

```sh
nix develop
```

Install the package in editable mode with development dependencies:

```sh
pip install -e '.[dev]'
```

Run checks:

```sh
python -m pytest
python -m pyright
python -m mypy .
```

Update Nix dependencies:

```sh
nix flake update
```

See `DESIGN.md` for detailed requirements and `AGENTS.md` for repository
workflow guidance.

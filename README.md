# flatbak

Synchronize your Flatpak apps from simple text files.

`flatbak` keeps your user-installed Flatpak apps aligned with a config directory.
It is designed for people who want Flatpak installs to be reproducible while
still being able to install apps normally from a software center.

## Quick Start

Preview what flatbak would do:

```sh
flatbak --dry-run
```

Apply changes:

```sh
flatbak
```

On the first run, flatbak creates a config file and adopts your already installed
user Flatpak apps into it.

## Config

flatbak reads config from:

```txt
~/.config/flatbak/*.txt
```

If `XDG_CONFIG_HOME` is set, it uses `$XDG_CONFIG_HOME/flatbak/*.txt` instead.

Config files are plain text. Put one app on each line:

```txt
org.mozilla.firefox
org.gnome.Calculator
```

Bare app IDs install from `flathub` by default.

If you need a specific remote, architecture, or branch, use a qualified ref:

```txt
flathub:app/org.gnome.Calculator/x86_64/stable
```

Parsing rules:

- Only `.txt` files are loaded.
- Empty lines are ignored.
- Lines starting with `#` are ignored.
- Inline comments start with ` #`.
- A `#` without leading whitespace is parsed as part of the value.
- Duplicate entries are treated as one desired app.

`root.txt` is machine-local and is the only config file flatbak writes. You can
move entries from `root.txt` into other `.txt` files, including symlinked files
shared across machines.

## What It Does

On each run, flatbak:

- Adds installed but unmanaged apps to `root.txt`.
- Installs configured apps that are missing.
- Removes tracked apps that are no longer configured.
- Tracks installed apps that are already present in config.
- Leaves runtimes and extensions to Flatpak.

flatbak manages user Flatpak installs by default. It does not manage system
Flatpak installs.

## Safety

flatbak only removes apps that it has tracked. An app installed outside flatbak is
first adopted into `root.txt` and tracked, rather than removed.

Before changing installs, flatbak validates configured remotes and app refs where
possible. If `flathub` is required but missing, flatbak fails with an error
instead of adding the remote automatically.

## Options

Enable verbose logging:

```sh
flatbak --verbose
```

`FLATBAK_VERBOSE=1` also enables verbose logging.

## Development

flatbak treats configured apps as desired state. On each run it compares config,
current user-installed Flatpak apps, and its own tracked state, then reconciles
the differences.

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

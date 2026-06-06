# Design Document

Software requirements for `flatbak`

## Overview

This software synchronizes user Flatpak app installs from text config files.

## Normative Language

The key words `MUST`, `MUST NOT`, `SHOULD`, `SHOULD NOT`, and `MAY` in this
document are to be interpreted as described in RFC 2119.

## Design Methodology

In descending order, this project optimizes for:

1. Correctness - ops MUST result in a good state
2. Reliability - ops SHOULD be reproducible
3. User-friendly - ops SHOULD have a minimal interface and useful error messages
4. Speed - ops SHOULD be efficient

User-visible requirements listed in this document MUST have corresponding
integration tests. Wherever possible, tests SHOULD be implemented first
(Red-Green-Refactor).

## Requirements

### Flatpak install scope

By default, the software manages user Flatpak installs only. Flatpak commands MUST
operate on the user installation unless the user explicitly selects another scope.

### Config files

The software uses `$XDG_CONFIG_HOME/flatbak` as its config directory. If
`XDG_CONFIG_HOME` is unset, it uses `~/.config/flatbak`.

The config directory MUST be created if missing before writing config files.

#### Format

- Config files MUST use a `.txt` extension.
- Each non-empty line contains one desired Flatpak app.
- Leading and trailing whitespace is stripped.
- Empty lines are ignored.
- Lines starting with `#` are ignored.
- Inline comments starting with ` #` are ignored after the desired app value.
  A `#` character without leading whitespace is treated as part of the value.

Config entries MAY be either bare Flatpak app IDs or qualified Flatpak refs.

Examples:

```txt
org.mozilla.firefox
flathub:app/org.mozilla.firefox/x86_64/stable
```

Bare app IDs MUST install from the `flathub` remote by default. Qualified refs
MAY specify an alternate remote when needed, and SHOULD preserve remote, kind,
architecture, and branch details.

#### Multi-config

All `.txt` config files in this software's config dir are merged when evaluated.
Duplicate entries are treated as one desired app.

#### Root config

A `root.txt` config is required, and created if missing. `root.txt` is the only
config file the software writes during automatic adoption of installed apps.
`root.txt` represents machine-local desired state. Users MAY move app entries
from `root.txt` into other config files, including symlinked config files shared
across machines.

### Persist state

The software manages its persistent state in `$XDG_DATA_HOME/flatbak`. If
`XDG_DATA_HOME` is unset, it uses `~/.local/share/flatbak`.

State data manages known Flatpaks ("tracked").

#### Format

- State MUST be stored in `state.json`.
- State files MUST use JSON.
- State files MUST include a schema version.
- Tracked apps MUST include the app ID.
- Tracked apps SHOULD include the resolved installed ref when available.
- Tracked apps SHOULD include the source config entry when available.

### Standard operation

The software performs these actions on a standard invocation

#### Dry run

The CLI MUST provide a `--dry-run` option. Dry runs MUST report the changes that
would be made without installing apps, uninstalling apps, writing config, or
writing state.

#### Preflight validation

Before making changes, the software SHOULD validate configured apps well enough
to identify likely failures, such as invalid app IDs, invalid qualified refs, and
missing remotes. If the `flathub` remote is missing and required for a bare app
ID, the software MUST fail with a clear message rather than adding the remote
automatically.

#### App-only management

The software manages Flatpak apps only. Runtime and extension installs SHOULD be
left to Flatpak dependency resolution and MUST NOT be treated as desired config
entries during automatic adoption.

#### Adopt untracked installed Flatpaks

If a user-installed Flatpak app is not tracked and not present in config, it is
added to `root.txt` and tracked. Automatically adopted apps SHOULD be written as
bare app IDs unless a qualified ref is required to reproduce the install.

#### Install missing flatpaks

If config includes a Flatpak app that is not installed, install it into the user
installation.

Bare app IDs match by app ID. Qualified refs match by their qualified details,
including remote and branch. If a different remote or branch is installed for a
qualified config entry, it is not considered a match.

#### Remove tracked apps no longer in config

If a user-installed Flatpak app is tracked but not present in config, uninstall
it from the user installation and untrack it. This removal is automatic and MUST
only apply to tracked user-installed apps.

Removals SHOULD happen before installs after preflight validation succeeds. This
keeps branch or remote changes simple: a tracked app whose installed qualified
ref no longer matches config can be removed first, then installed from the
configured ref.

#### Track new Flatpaks

If an installed Flatpak app is present in config but not tracked in state, track
it.

Standard operation MUST be idempotent. Running the software repeatedly with the
same installed apps and config MUST result in no additional changes after the
first successful reconciliation.

Failures MUST be reported to the user. If an individual operation fails partway
through reconciliation, the resulting state MUST allow a later successful rerun
to reach the same final state as a fully successful first run. Implementations
SHOULD derive the next reconciliation from actual Flatpak state and config, and
SHOULD persist state only after successful operations that the state describes.

## Architecture

The application follows a clean separation of concerns:

- `__main__.py`: Entry point. Handles CLI interaction and argument parsing
- `lib.py`: Library entry point. Handles general logic.
- `config.py`: Handles reading/writing config files
- `state.py`: Handles reading/writing data file
- `flatpak.py`: Handles installing/uninstalling flatpaks

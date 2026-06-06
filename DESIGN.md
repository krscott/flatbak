# Design Document

Software requirements for `flatbak`

## Overview

This software synchronizes user and system Flatpak app installs from YAML config
files.

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

### Install Scopes

The software manages both user and system Flatpak installs.

- `user` scope maps to Flatpak commands using `--user`.
- `system` scope maps to Flatpak commands using `--system`.

Users SHOULD NOT need to know whether a software center installed an app in user
or system scope. During adoption, the software MUST preserve the scope where the
app is actually installed.

### Config Paths

The software uses `$XDG_CONFIG_HOME/flatbak` as its config directory. If
`XDG_CONFIG_HOME` is unset, it uses `~/.config/flatbak`.

The config directory MUST be created if missing before writing config files.

### Config File Selection

- Config files MUST use a `.yml` or `.yaml` extension.
- All YAML config files in this software's config dir are merged when evaluated.
- Duplicate entries in the same scope are treated as one desired app.

### Config Format

Config files MUST be YAML mappings. The supported top-level keys are `user` and
`system`. Each key maps to a list of desired Flatpak apps for that install scope.
The implementation MUST use a standard YAML parser library for config parsing.

Example:

```yaml
user:
  - org.mozilla.firefox
  - flathub:app/org.gnome.Calculator/x86_64/stable

system:
  - org.audacityteam.Audacity
```

Missing `user` or `system` keys are treated as empty lists. A `user:` or
`system:` key with no value is treated as an empty list. A completely empty YAML
file is treated as an empty mapping. Unknown top-level keys MUST fail validation
with a clear message.

Values under `user` and `system` MUST be YAML lists. Each list item MUST be a
string. Non-list section values and non-string list items MUST fail validation
with a clear message.

### Config Entry Forms

Config entries in each scope MAY be either bare Flatpak app IDs or qualified
Flatpak refs.

Examples:

```yaml
user:
  - org.mozilla.firefox
  - flathub:app/org.mozilla.firefox/x86_64/stable
```

Bare app IDs MUST install from the `flathub` remote by default. Qualified refs
MAY specify an alternate remote when needed, and SHOULD preserve remote, kind,
architecture, and branch details.

### Root Config

A `root.yml` config is required, and created if missing. `root.yml` is the only
config file the software writes during automatic adoption of installed apps.
`root.yml` represents machine-local desired state. Users MAY move app entries
from `root.yml` into other YAML config files, including symlinked config files
shared across machines.

Automatically adopted user-scope apps MUST be written under the `user` key.
Automatically adopted system-scope apps MUST be written under the `system` key.

### State Path

The software manages its persistent state in `$XDG_DATA_HOME/flatbak`. If
`XDG_DATA_HOME` is unset, it uses `~/.local/share/flatbak`.

State data manages known Flatpaks ("tracked").

### State Format

- State MUST be stored in `state.json`.
- State files MUST use JSON.
- State files MUST include a schema version.
- Tracked apps MUST include the app ID.
- Tracked apps MUST include the install scope.
- Tracked apps SHOULD include the resolved installed ref when available.
- Tracked apps SHOULD include the source config entry when available.

### CLI Dry Run

The CLI MUST provide a `--dry-run` option. Dry runs MUST report the changes that
would be made without installing apps, uninstalling apps, writing config, or
writing state.

The application MUST support both the installed `flatbak` console script and
`python -m flatbak` as equivalent CLI entry points.

### CLI Edit

The CLI MUST provide an `-e`/`--edit` option. Edit mode MUST ensure `root.yml`
exists, then open it with the command from the `EDITOR` environment variable. If
`EDITOR` is unset, edit mode MUST fall back to `xdg-open`. Edit mode MUST NOT
perform reconciliation.

### Flatpak App Discovery

The software manages Flatpak apps only. Runtime and extension installs SHOULD be
left to Flatpak dependency resolution and MUST NOT be treated as desired config
entries during automatic adoption.

Installed app discovery MUST accept Flatpak refs reported both as
`app/<app-id>/<arch>/<branch>` and `<app-id>/<arch>/<branch>`. Both forms
describe the same installed app identity.

### Matching Rules

Bare app IDs match by scope and app ID.

Qualified refs match by scope and their qualified details, including remote and
branch. If a different scope, remote, or branch is installed for a qualified
config entry, it is not considered a match.

### Preflight Validation

Before making changes, the software SHOULD validate configured apps in each scope
well enough to identify likely failures, such as invalid app IDs, invalid
qualified refs, and missing remotes. If the `flathub` remote is missing in a
scope and required for a bare app ID in that scope, the software MUST fail with a
clear message rather than adding the remote automatically.

Preflight validation SHOULD verify that configured apps can be resolved by their
configured remote before uninstalling tracked apps. If a configured app cannot be
resolved, reconciliation SHOULD fail before making install, uninstall, config, or
state changes.

### Standard Reconciliation

The software performs these actions on a standard invocation

#### Adopt Untracked Installed Flatpaks

If an installed Flatpak app is not tracked in its install scope and not present in
config for that scope, it is added to `root.yml` under that scope and tracked.
Automatically adopted apps SHOULD be written as bare app IDs unless a qualified
ref is required to reproduce the install.

#### Remove Tracked Apps No Longer In Config

If an installed Flatpak app is tracked but not present in config for its tracked
scope, uninstall it from that install scope and untrack it. This removal is
automatic and MUST only apply to tracked apps in the tracked scope.

If state is stale and the tracked installed ref does not match actual Flatpak
state, the implementation MUST still use the tracked scope and app ID to identify
installed apps that are eligible for removal. Stale state MUST NOT cause tracked
installed apps to be silently untracked while leaving them installed.

Removals SHOULD happen before installs after preflight validation succeeds. This
keeps branch or remote changes simple: a tracked app whose installed qualified
ref no longer matches config can be removed first, then installed from the
configured ref.

#### Install Missing Flatpaks

If config includes a Flatpak app that is not installed in its configured scope,
install it into that scope.

#### Track Existing Configured Flatpaks

If an installed Flatpak app is present in config for its install scope but not
tracked in state for that scope, track it.

### Post-Install State

After installing a Flatpak app, persisted state MUST describe the actual
installed app as reported by Flatpak, including the resolved installed ref when
available. Persisted state MUST NOT assume that the configured value is identical
to the resolved installed ref.

Post-install verification MUST use the same matching semantics as normal
reconciliation. Bare app IDs match by scope and app ID. Qualified refs MUST match
their scope and qualified details, including remote and branch. A reported app
with the same app ID but a different scope, remote, or branch MUST NOT be
accepted as a successful install for a qualified config entry.

### Idempotency And Failure Handling

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

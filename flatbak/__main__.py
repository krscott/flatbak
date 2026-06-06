import argparse
import logging
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import find_dotenv, load_dotenv
from setproctitle import setproctitle

from flatbak.config import default_config_dir, ensure_root_config
from flatbak.lib import Options, Paths, ReconcileResult, reconcile
from flatbak.state import default_data_dir


def main() -> None:
    setproctitle("flatbak")
    load_dotenv(find_dotenv(usecwd=True))

    cli_opts = CliOpts.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if cli_opts.verbose else logging.INFO,
        format="%(message)s",
    )

    paths = Paths(config_dir=default_config_dir(), data_dir=default_data_dir())

    if cli_opts.edit:
        try:
            edit_root_config(paths.config_dir)
        except ValueError as error:
            raise SystemExit(f"flatbak: {error}") from error
        return

    try:
        result = reconcile(
            cli_opts.app_opts,
            paths,
        )
    except ValueError as error:
        raise SystemExit(f"flatbak: {error}") from error
    print_result(result, dry_run=cli_opts.app_opts.dry_run)


def print_result(result: ReconcileResult, *, dry_run: bool) -> None:
    prefix = "Would " if dry_run else ""
    for app in result.removed:
        print(f"{prefix}remove {app}")
    for app in result.adopted:
        print(f"{prefix}adopt {app}")
    for app in result.installed:
        print(f"{prefix}install {app}")
    for app in result.tracked:
        print(f"{prefix}track {app}")
    if not result.changed:
        print("No changes")


def edit_root_config(config_dir: Path) -> None:
    ensure_root_config(config_dir)
    root = config_dir / "root.yml"
    editor = os.environ.get("EDITOR")
    command = [*shlex.split(editor), str(root)] if editor else ["xdg-open", str(root)]
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError as error:
        raise ValueError(f"editor command was not found: {command[0]}") from error
    except subprocess.CalledProcessError as error:
        raise ValueError(f"editor command failed: {' '.join(command)}") from error


@dataclass(kw_only=True, frozen=True)
class CliOpts:
    app_opts: Options
    verbose: bool
    edit: bool

    @staticmethod
    def parse_args() -> "CliOpts":
        parser = argparse.ArgumentParser()

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="report changes without installing, uninstalling, or writing files",
        )
        parser.add_argument(
            "-e",
            "--edit",
            action="store_true",
            help="open root.yml in EDITOR, or xdg-open if EDITOR is unset",
        )

        # CLI-specific options
        parser.add_argument(
            "-v",
            "--verbose",
            action=EnvAction,
            env_var="FLATBAK_VERBOSE",
            nargs=0,
            help="show more detailed log messages",
        )

        args = parser.parse_args()

        return CliOpts(
            app_opts=Options(dry_run=bool(args.dry_run)),
            verbose=bool(args.verbose),
            edit=bool(args.edit),
        )


class EnvAction(argparse.Action):
    """ArgumentParser Action for options with an env var fallback"""

    def __init__(
        self,
        help: str,
        env_var: str = "",
        required: bool = True,
        default: Any = None,
        nargs: str | int | None = None,
        **kwargs: Any,
    ) -> None:
        if default is not None and env_var:
            help += f" (default: {default}, env: {env_var})"
        elif default is not None:
            help += f" (default: {default})"
        elif env_var:
            help += f" (env: {env_var})"

        if env_var and env_var in os.environ:
            default = os.environ[env_var]
            if default == "":
                default = None
            elif nargs == 0:
                default = default.lower() not in {"0", "false", "no", "off"}

        if default is not None or nargs == 0:
            required = False

        super(EnvAction, self).__init__(
            help=help,
            default=default,
            required=required,
            nargs=nargs,
            **kwargs,
        )

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        _ = parser
        _ = option_string
        if self.nargs == 0:
            setattr(namespace, self.dest, True)
        else:
            setattr(namespace, self.dest, values)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Bootstrap pinned benchmark environments on a Linux CUDA worker."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Sequence


PROJECT_ROOT: Final = Path(__file__).resolve().parents[1]
LOCK_PATH: Final = PROJECT_ROOT / "configs" / "sources.lock.json"
SOURCE_ROOT: Final = PROJECT_ROOT / "vendor" / "src"
FREEZE_ROOT: Final = PROJECT_ROOT / ".cache" / "bootstrap" / "freezes"


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    revision: str

    @property
    def path(self) -> Path:
        return SOURCE_ROOT / self.name


class BootstrapError(RuntimeError):
    pass


def display_command(command: Sequence[object]) -> str:
    return shlex.join(str(part) for part in command)


def project_environment() -> dict[str, str]:
    env = os.environ.copy()
    cache = PROJECT_ROOT / ".cache"
    values = {
        "ROBOT_BENCHMARK_ROOT": PROJECT_ROOT,
        "UV_CACHE_DIR": cache / "uv",
        "PIP_CACHE_DIR": cache / "pip",
        "XDG_CACHE_HOME": cache / "xdg",
        "HF_HOME": cache / "huggingface",
        "HUGGINGFACE_HUB_CACHE": cache / "huggingface" / "hub",
        "TORCH_HOME": cache / "torch",
        "JAX_COMPILATION_CACHE_DIR": cache / "jax",
        "TMPDIR": cache / "tmp",
    }
    env.update({name: str(value) for name, value in values.items()})
    env["PYTHONNOUSERSITE"] = "1"
    env["HF_HUB_DISABLE_TELEMETRY"] = "1"
    env.setdefault("MUJOCO_GL", "egl")
    return env


def run(
    command: Sequence[object],
    *,
    dry_run: bool,
    env: dict[str, str],
    input_text: str | None = None,
    capture: bool = False,
) -> str:
    printable = display_command(command)
    print(f"+ {printable}")
    if input_text is not None:
        print("  (automated confirmation supplied to this explicitly requested stage)")
    if dry_run:
        return ""
    completed = subprocess.run(
        [str(part) for part in command],
        cwd=PROJECT_ROOT,
        env=env,
        input=input_text,
        text=True,
        check=False,
        stdout=subprocess.PIPE if capture else None,
    )
    if completed.returncode:
        raise BootstrapError(f"command failed ({completed.returncode}): {printable}")
    return completed.stdout or ""


def load_sources() -> list[Source]:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    repositories = lock["repositories"]
    expected = {
        "robocasa": "456174f62b89b8fca99eaaf33949c29fec9cfc2a",
        "robosuite": "5ce6643f3092639d08f7b0f90ed1c6a84f50552c",
        "groot": "9d7d7a9eb7ad30bd8ce30448d9ab53a918b45b10",
        "openpi": "5a6beda9ff99da30b4e1b59320f6a32971d7c397",
    }
    sources: list[Source] = []
    for name, revision in expected.items():
        entry = repositories[name]
        if entry["revision"] != revision:
            raise BootstrapError(
                f"unexpected {name} revision in {LOCK_PATH}: {entry['revision']}"
            )
        sources.append(Source(name, entry["url"], revision))
    return sources


def preflight(args: argparse.Namespace, env: dict[str, str]) -> None:
    print(f"project root: {PROJECT_ROOT}")
    print(f"host: {platform.system()} {platform.machine()}")
    if args.dry_run:
        if platform.system() != "Linux":
            print("dry-run note: actual bootstrap requires Linux; this host was not modified")
    elif platform.system() != "Linux":
        raise BootstrapError("actual bootstrap requires a Linux worker")

    for program in ("git", "uv"):
        path = shutil.which(program, path=env.get("PATH"))
        if not path:
            raise BootstrapError(f"required command is not available: {program}")
        print(f"{program}: {path}")

    free_gib = shutil.disk_usage(PROJECT_ROOT).free / 1024**3
    print(f"project filesystem free: {free_gib:.1f} GiB")
    if free_gib < args.min_free_gib:
        message = (
            f"project filesystem has {free_gib:.1f} GiB free; "
            f"bootstrap requires at least {args.min_free_gib:.1f} GiB"
        )
        if args.dry_run:
            print(f"dry-run warning: {message}")
        else:
            raise BootstrapError(message)

    if args.skip_gpu_check:
        print("GPU preflight skipped by request")
        return
    nvidia_smi = shutil.which("nvidia-smi", path=env.get("PATH"))
    if not nvidia_smi:
        if args.dry_run:
            print("dry-run warning: nvidia-smi is not available on this host")
            return
        raise BootstrapError("nvidia-smi is required (or pass --skip-gpu-check intentionally)")
    run(
        [
            nvidia_smi,
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader",
        ],
        dry_run=args.dry_run,
        env=env,
    )


def prepare_directories(env: dict[str, str], dry_run: bool) -> None:
    directories = {
        SOURCE_ROOT,
        FREEZE_ROOT,
        *(Path(env[name]) for name in (
            "UV_CACHE_DIR",
            "PIP_CACHE_DIR",
            "XDG_CACHE_HOME",
            "HF_HOME",
            "HUGGINGFACE_HUB_CACHE",
            "TORCH_HOME",
            "JAX_COMPILATION_CACHE_DIR",
            "TMPDIR",
        )),
    }
    for directory in sorted(directories):
        print(f"+ mkdir -p {shlex.quote(str(directory))}")
        if not dry_run:
            directory.mkdir(parents=True, exist_ok=True)


def checkout_source(source: Source, args: argparse.Namespace, env: dict[str, str]) -> None:
    if args.dry_run:
        run(["git", "init", source.path], dry_run=True, env=env)
        run(
            ["git", "-C", source.path, "remote", "add", "origin", source.url],
            dry_run=True,
            env=env,
        )
        run(
            ["git", "-C", source.path, "fetch", "--depth", "1", "origin", source.revision],
            dry_run=True,
            env=env,
        )
        run(
            ["git", "-C", source.path, "checkout", "--detach", source.revision],
            dry_run=True,
            env=env,
        )
        return

    if source.path.exists():
        if not (source.path / ".git").is_dir():
            raise BootstrapError(f"source path exists but is not a git checkout: {source.path}")
        head = run(
            ["git", "-C", source.path, "rev-parse", "HEAD"],
            dry_run=False,
            env=env,
            capture=True,
        ).strip()
        if head != source.revision:
            raise BootstrapError(
                f"existing {source.name} checkout is {head}, expected {source.revision}; "
                "move it aside and rerun"
            )
        tracked_changes = run(
            ["git", "-C", source.path, "status", "--porcelain", "--untracked-files=no"],
            dry_run=False,
            env=env,
            capture=True,
        ).strip()
        if tracked_changes:
            raise BootstrapError(
                f"existing {source.name} checkout has modified tracked files; move it aside and rerun"
            )
        print(f"verified source {source.name}@{head}")
        return

    run(["git", "init", source.path], dry_run=False, env=env)
    run(
        ["git", "-C", source.path, "remote", "add", "origin", source.url],
        dry_run=False,
        env=env,
    )
    run(
        ["git", "-C", source.path, "fetch", "--depth", "1", "origin", source.revision],
        dry_run=False,
        env=env,
    )
    run(
        ["git", "-C", source.path, "checkout", "--detach", source.revision],
        dry_run=False,
        env=env,
    )


def ensure_venv(path: Path, args: argparse.Namespace, env: dict[str, str]) -> Path:
    python = path / "bin" / "python"
    if args.dry_run or not python.exists():
        run(["uv", "venv", "--python", "3.11", path], dry_run=args.dry_run, env=env)
    run(
        [
            python,
            "-c",
            "import sys; assert sys.version_info[:2] == (3, 11), sys.version",
        ],
        dry_run=args.dry_run,
        env=env,
    )
    return python


def install_environment(
    name: str,
    venv: Path,
    requirements: Path | None,
    editables: list[Path],
    import_check: str,
    args: argparse.Namespace,
    env: dict[str, str],
) -> Path:
    python = ensure_venv(venv, args, env)
    if requirements is not None:
        run(
            ["uv", "pip", "install", "--python", python, "-r", requirements],
            dry_run=args.dry_run,
            env=env,
        )
    editable_command: list[object] = ["uv", "pip", "install", "--python", python, "--no-deps"]
    for path in editables:
        editable_command.extend(["-e", path])
    run(editable_command, dry_run=args.dry_run, env=env)
    run([python, "-c", import_check], dry_run=args.dry_run, env=env)
    freeze = run(
        ["uv", "pip", "freeze", "--python", python],
        dry_run=args.dry_run,
        env=env,
        capture=True,
    )
    freeze_path = FREEZE_ROOT / f"{name}.txt"
    print(f"+ write resolved environment to {freeze_path}")
    if not args.dry_run:
        freeze_path.write_text(freeze, encoding="utf-8")
    return python


def setup_robocasa_macros(args: argparse.Namespace) -> None:
    source = SOURCE_ROOT / "robocasa" / "robocasa" / "macros.py"
    destination = source.with_name("macros_private.py")
    if args.dry_run:
        print(f"+ copy {source} -> {destination} (only if absent)")
    elif not destination.exists():
        shutil.copyfile(source, destination)
        print(f"created {destination.relative_to(PROJECT_ROOT)}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print the full plan without writes")
    parser.add_argument(
        "--include-pi05",
        action="store_true",
        help="prepare the unqualified .venv-pi05 fallback",
    )
    parser.add_argument(
        "--download-checkpoint",
        action="store_true",
        help="download and verify the ~7.1 GiB GR00T inference checkpoint",
    )
    parser.add_argument(
        "--download-pi05-checkpoint",
        action="store_true",
        help="download and verify the ~11.6 GiB pi0.5 fallback parameters",
    )
    parser.add_argument(
        "--download-assets",
        action="store_true",
        help="confirm the official RoboCasa ~10 GB asset download non-interactively",
    )
    parser.add_argument(
        "--skip-gpu-check",
        action="store_true",
        help="allow environment preparation when nvidia-smi is intentionally unavailable",
    )
    parser.add_argument(
        "--min-free-gib",
        type=float,
        default=80.0,
        help="minimum free project-filesystem space (default: 80)",
    )
    args = parser.parse_args(argv)
    if args.min_free_gib <= 0:
        parser.error("--min-free-gib must be positive")
    if args.download_pi05_checkpoint and not args.include_pi05:
        parser.error("--download-pi05-checkpoint requires --include-pi05")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        env = project_environment()
        sources = load_sources()
        preflight(args, env)
        prepare_directories(env, args.dry_run)
        for source in sources:
            checkout_source(source, args, env)

        # Create RoboCasa's private macro file before the first import check so
        # the environment is initialized exactly once without warning-driven setup.
        setup_robocasa_macros(args)

        core_python = install_environment(
            "core",
            PROJECT_ROOT / ".venv",
            None,
            [PROJECT_ROOT],
            "import robot_benchmark",
            args,
            env,
        )
        sim_python = install_environment(
            "sim",
            PROJECT_ROOT / ".venv-sim",
            PROJECT_ROOT / "configs" / "requirements-sim.txt",
            [SOURCE_ROOT / "robosuite", SOURCE_ROOT / "robocasa", PROJECT_ROOT],
            "import robocasa, robosuite, robot_benchmark",
            args,
            env,
        )
        install_environment(
            "groot",
            PROJECT_ROOT / ".venv-groot",
            PROJECT_ROOT / "configs" / "requirements-groot.txt",
            [SOURCE_ROOT / "groot", PROJECT_ROOT],
            (
                "import robot_benchmark; "
                "from gr00t.model.policy import Gr00tPolicy; "
                "from gr00t.experiment.data_config import PandaOmronDataConfig"
            ),
            args,
            env,
        )

        if args.include_pi05:
            install_environment(
                "pi05",
                PROJECT_ROOT / ".venv-pi05",
                PROJECT_ROOT / "configs" / "requirements-pi05.txt",
                [SOURCE_ROOT / "openpi" / "packages" / "openpi-client", SOURCE_ROOT / "openpi", PROJECT_ROOT],
                "import openpi, robot_benchmark",
                args,
                env,
            )

        if args.download_checkpoint:
            run(
                [core_python, PROJECT_ROOT / "scripts" / "download_checkpoint.py"],
                dry_run=args.dry_run,
                env=env,
            )

        if args.download_pi05_checkpoint:
            run(
                [core_python, PROJECT_ROOT / "scripts" / "download_checkpoint.py", "--backend", "pi05"],
                dry_run=args.dry_run,
                env=env,
            )

        if args.download_assets:
            run(
                [
                    sim_python,
                    "-m",
                    "robocasa.scripts.download_kitchen_assets",
                    "--type",
                    "all",
                ],
                dry_run=args.dry_run,
                env=env,
                input_text="y\n",
            )

        if args.dry_run:
            print("dry run complete: no project files, environments, downloads, or sources were created")
        else:
            print("bootstrap complete; resolved package snapshots are under .cache/bootstrap/freezes")
        return 0
    except (BootstrapError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

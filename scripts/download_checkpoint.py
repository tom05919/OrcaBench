#!/usr/bin/env python3
"""Download a pinned inference checkpoint without optimizer or training state."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Final


PROJECT_ROOT: Final = Path(__file__).resolve().parents[1]
LOCK_PATH: Final = PROJECT_ROOT / "configs" / "sources.lock.json"
DEFAULT_OUTPUTS: Final = {
    "groot": PROJECT_ROOT / "checkpoints" / "groot" / "checkpoint-120000",
    "pi05": PROJECT_ROOT / "checkpoints" / "pi05" / "75000",
}
MIN_HEADROOM_BYTES: Final = 2 * 1024**3
CHUNK_BYTES: Final = 8 * 1024**2

# These are content hashes at the immutable revision in sources.lock.json.
# The large-file hashes are the Hugging Face LFS object IDs; the three small
# file hashes were computed from their resolved content at the same revision.
GROOT_FILES: Final = {
    "config.json": {
        "size": 1_706,
        "sha256": "6713ae6e9ee07ebf30f18a231bedcf9c06f8c64595d62529b6eb175498ef0526",
    },
    "experiment_cfg/metadata.json": {
        "size": 14_140,
        "sha256": "8be0fc606c9220356bad497feefc4ae4daaa05670acccc31caecaa7ae5590b69",
    },
    "model-00001-of-00002.safetensors": {
        "size": 4_999_367_032,
        "sha256": "08f1891947973e2e5ec2422201cd90261806f77f2634f9ec0477c27aa5a4fe42",
    },
    "model-00002-of-00002.safetensors": {
        "size": 2_586_705_312,
        "sha256": "deb9c9cf40cd8983a7779af85341f6344db15f65bf3307073a0e3c3085450435",
    },
    "model.safetensors.index.json": {
        "size": 104_606,
        "sha256": "bec674fcd06f1c6c29e5ab0f057d148a5c76e7ef92d1688d6b4b8f838afc9746",
    },
}

# Orbax parameter tree plus normalization stats; train_state is deliberately
# excluded. Hashes for LFS files are the immutable LFS SHA-256 object IDs.
PI05_FILES: Final = {
    "_CHECKPOINT_METADATA": {"size": 426, "sha256": "c15b833bd5b285c426ac1eb078ddfa334140a6661c61515e3bfd304ec87bdc70"},
    "assets/norm_stats.json": {"size": 3208, "sha256": "4aed1af411bd0e0f49d2b0e6d6832b11b8682917231a07173fbc30fd493bbdee"},
    "params/_METADATA": {"size": 23544, "sha256": "f27d21952e602528615298c668b588ba14ae8268e03e94598ea0235eaea52a5f"},
    "params/_sharding": {"size": 12797, "sha256": "7e65c8b63fafedfedb52bf416d6bfde394c1c88fd28dc02f18a7911f2581c183"},
    "params/array_metadatas/process_0": {"size": 9162, "sha256": "b6f4c56c01a8b73c9db955c4c68dd0b74d7fdda723831715dcbcd18ba5ddd4ab"},
    "params/d/35c0b41e13ddb0a578456230f51a3416": {"size": 2138, "sha256": "97ee62c8ea97e9d8460dfa4cac06a73755d61c290c8aa6b046ba33f90f515041"},
    "params/manifest.ocdbt": {"size": 117, "sha256": "e0d7c903d80c8ed959cb0428463be3a85406e82b170dbae2c5ca0004f81f0839"},
    "params/ocdbt.process_0/d/16a296efc9531f413b90c15199e43385": {"size": 538931200, "sha256": "dc757fa844af3d94c8eaaa07194417a7c482bb52edf6e8d86e577f81816c5bae"},
    "params/ocdbt.process_0/d/28b537f74e118c2c1c44f72e8b0e00b7": {"size": 2240151552, "sha256": "f209dd91be421638fea6261cc63a34a2004ee145eb30cb6ba38a99654f9af305"},
    "params/ocdbt.process_0/d/471d6e9b709ec1a579f83c8b4914e1ed": {"size": 30384128, "sha256": "3ce8fe59c2e2b636d434e02c985a02916d88d2b129189b529d24c3e6099baed4"},
    "params/ocdbt.process_0/d/5cf1127d4e3fcd6e80a66ebba54dc32d": {"size": 2799407104, "sha256": "bacba2b2609a43ca79324669efc844756779f69a4d8c7cd10c7762683fd32deb"},
    "params/ocdbt.process_0/d/6292e633c11b8f6931cac6ab824f3279": {"size": 35061760, "sha256": "96aa01bc6b8323995e711fbd80ca0f52f24d472194b4bd61cd0cc9c64cf2b4a2"},
    "params/ocdbt.process_0/d/65f82551b4d64f31f6bb1cdcf17945e1": {"size": 70041600, "sha256": "e1f92637f1d9e85c6da42b7cc315fdd98ff1f8786baf31bc93728df8c99c9b4a"},
    "params/ocdbt.process_0/d/7f76f4974bbb6946ff46b5dbcd4d44f8": {"size": 2529587200, "sha256": "e4282ee9762ef7bd9a27972e42f0a10e110b27e4a9d4123610cd8a0e47266754"},
    "params/ocdbt.process_0/d/b627c21812ded6c524507187a8526a3e": {"size": 1956962304, "sha256": "2a36a95461e1b67ea66240045be0b2011d7ade7ed2237a8bf95a3f117010e734"},
    "params/ocdbt.process_0/d/b808ab91bab1b5805b381e09b7fc0a85": {"size": 5367, "sha256": "0c06d6434c9c6937e4804d6cfd0ab3e91eb982c71e8464880ef8e156a9f91d03"},
    "params/ocdbt.process_0/d/d71893b153190783845eb3aabec57214": {"size": 1098, "sha256": "c32792c5ea2f6ea460915854df63ce59f0135e6fb8f6bd716642550d8802e8df"},
    "params/ocdbt.process_0/d/d76149c5c280cb9da59fd2f948d9cdda": {"size": 213, "sha256": "fff2f8b328c86ab34912c01d5758210df1805bcd73e3709be401d1989b9b18c3"},
    "params/ocdbt.process_0/d/fb6f9dae6d90f1b488a3d4ebf79278ed": {"size": 2240278528, "sha256": "c91af421dfea08263fa55d6cd904fb7a909925447c448cebeee8bc140fb5a340"},
    "params/ocdbt.process_0/manifest.ocdbt": {"size": 486, "sha256": "619bbfc24075a6e9055ec5e160a0d1e5d1900e2b7edcc2286ca432997f0d58e4"},
}

EXPECTED_BY_BACKEND: Final = {"groot": GROOT_FILES, "pi05": PI05_FILES}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def inside_project(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError(f"path must be inside project root {PROJECT_ROOT}: {resolved}") from exc
    return resolved


def load_source(backend: str) -> tuple[str, str, str]:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    checkpoint = lock["checkpoint"]
    repo_id = checkpoint["repo_id"]
    revision = checkpoint["revision"]
    subdir = checkpoint[f"{backend}_subdir"]
    if revision != "c484448aba1a9b60a04c9b0ca117241518ea69f3":
        raise ValueError(f"unexpected checkpoint revision in {LOCK_PATH}: {revision}")
    return repo_id, revision, subdir


def download_url(repo_id: str, revision: str, source_path: str) -> str:
    repo = urllib.parse.quote(repo_id, safe="/")
    revision_part = urllib.parse.quote(revision, safe="")
    path_part = urllib.parse.quote(source_path, safe="/")
    return f"https://huggingface.co/{repo}/resolve/{revision_part}/{path_part}?download=true"


def validate_existing(path: Path, expected: dict[str, object]) -> tuple[bool, str | None]:
    if not path.is_file():
        return False, None
    expected_size = int(expected["size"])
    if path.stat().st_size != expected_size:
        return False, f"size {path.stat().st_size} != {expected_size}"
    actual_hash = sha256_file(path)
    if actual_hash != expected["sha256"]:
        return False, f"sha256 {actual_hash} != {expected['sha256']}"
    return True, actual_hash


def download_one(
    url: str,
    destination: Path,
    expected: dict[str, object],
    token: str | None,
    force: bool,
) -> str:
    valid, digest = validate_existing(destination, expected)
    if valid:
        print(f"verified existing {destination.relative_to(PROJECT_ROOT)}")
        return str(digest)
    if destination.exists() and not force:
        _, reason = validate_existing(destination, expected)
        raise ValueError(f"existing file failed verification ({reason}): {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    expected_size = int(expected["size"])
    if partial.exists() and partial.stat().st_size > expected_size:
        if not force:
            raise ValueError(f"oversized partial download; rerun with --force: {partial}")
        partial.unlink()

    offset = partial.stat().st_size if partial.exists() else 0
    headers = {"User-Agent": "robot-policy-benchmark/0.1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if offset:
        headers["Range"] = f"bytes={offset}-"

    request = urllib.request.Request(url, headers=headers)
    try:
        response = urllib.request.urlopen(request, timeout=60)
    except urllib.error.HTTPError as exc:
        if exc.code == 416 and offset == expected_size:
            response = None
        else:
            raise

    if response is not None:
        status = getattr(response, "status", response.getcode())
        append = offset > 0 and status == 206
        if offset and not append:
            print(f"server did not honor resume for {destination.name}; restarting")
            offset = 0
        mode = "ab" if append else "wb"
        downloaded = offset
        last_report = time.monotonic()
        with response, partial.open(mode) as stream:
            while chunk := response.read(CHUNK_BYTES):
                stream.write(chunk)
                downloaded += len(chunk)
                now = time.monotonic()
                if now - last_report >= 5:
                    percent = 100 * downloaded / expected_size
                    print(f"  {destination.name}: {downloaded / 1024**3:.2f} GiB ({percent:.1f}%)")
                    last_report = now

    if not partial.is_file() or partial.stat().st_size != expected_size:
        actual_size = partial.stat().st_size if partial.exists() else 0
        raise ValueError(
            f"downloaded size mismatch for {destination.name}: {actual_size} != {expected_size}"
        )
    actual_hash = sha256_file(partial)
    if actual_hash != expected["sha256"]:
        raise ValueError(
            f"downloaded sha256 mismatch for {destination.name}: "
            f"{actual_hash} != {expected['sha256']}"
        )
    partial.replace(destination)
    print(f"downloaded and verified {destination.relative_to(PROJECT_ROOT)}")
    return actual_hash


def validate_index(output: Path, backend: str) -> None:
    if backend == "pi05":
        # Loading the Orbax tree is the runtime integrity check. The file-level
        # allowlist above ensures the checkpoint contains no train_state tree.
        return
    index = json.loads((output / "model.safetensors.index.json").read_text(encoding="utf-8"))
    referenced = set(index["weight_map"].values())
    expected = {
        "model-00001-of-00002.safetensors",
        "model-00002-of-00002.safetensors",
    }
    if referenced != expected:
        raise ValueError(f"unexpected safetensor shards in index: {sorted(referenced)}")


def manifest_path(output: Path) -> Path:
    return output.with_name(output.name + ".manifest.json")


def write_manifest(
    output: Path,
    repo_id: str,
    revision: str,
    subdir: str,
    hashes: dict[str, str],
    expected_files: dict[str, dict[str, object]],
) -> None:
    manifest = {
        "schema_version": 1,
        "repo_id": repo_id,
        "revision": revision,
        "subdir": subdir,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files": [
            {
                "path": name,
                "size": expected_files[name]["size"],
                "sha256": hashes[name],
            }
            for name in sorted(expected_files)
        ],
    }
    target = manifest_path(output)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    print(f"wrote {target.relative_to(PROJECT_ROOT)}")


def verify(output: Path, backend: str, expected_files: dict[str, dict[str, object]]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    failures: list[str] = []
    for name, expected in expected_files.items():
        valid, digest = validate_existing(output / name, expected)
        if valid:
            hashes[name] = str(digest)
        else:
            failures.append(f"{name}: missing or invalid")
    if failures:
        raise ValueError("checkpoint verification failed:\n  " + "\n  ".join(failures))
    validate_index(output, backend)
    return hashes


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=sorted(EXPECTED_BY_BACKEND), default="groot")
    parser.add_argument(
        "--output",
        type=Path,
        help="checkpoint directory (default is project checkpoints/<backend>/...)",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the immutable download plan")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="verify local files and rewrite the manifest without network access",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an invalid destination or partial file",
    )
    args = parser.parse_args(argv)
    if args.dry_run and args.verify_only:
        parser.error("--dry-run and --verify-only are mutually exclusive")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        output = inside_project(args.output or DEFAULT_OUTPUTS[args.backend])
        repo_id, revision, subdir = load_source(args.backend)
        expected_files = EXPECTED_BY_BACKEND[args.backend]
        print(f"source: {repo_id}@{revision}")
        print(f"subdir: {subdir}")
        print(f"destination: {output}")
        for name, expected in expected_files.items():
            print(f"  {name} ({int(expected['size']) / 1024**3:.3f} GiB)")

        if args.dry_run:
            print("dry run: no directories or network requests were made")
            return 0

        if args.verify_only:
            hashes = verify(output, args.backend, expected_files)
            write_manifest(output, repo_id, revision, subdir, hashes, expected_files)
            return 0

        missing_bytes = 0
        for name, expected in expected_files.items():
            valid, _ = validate_existing(output / name, expected)
            if not valid:
                partial = output / (name + ".part")
                partial_size = partial.stat().st_size if partial.exists() else 0
                missing_bytes += max(0, int(expected["size"]) - partial_size)
        free_bytes = shutil.disk_usage(PROJECT_ROOT).free
        if free_bytes < missing_bytes + MIN_HEADROOM_BYTES:
            raise OSError(
                f"insufficient project filesystem space: need "
                f"{(missing_bytes + MIN_HEADROOM_BYTES) / 1024**3:.1f} GiB, "
                f"have {free_bytes / 1024**3:.1f} GiB"
            )

        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        hashes: dict[str, str] = {}
        for name, expected in expected_files.items():
            source_path = f"{subdir}/{name}"
            hashes[name] = download_one(
                download_url(repo_id, revision, source_path),
                output / name,
                expected,
                token,
                args.force,
            )
        validate_index(output, args.backend)
        write_manifest(output, repo_id, revision, subdir, hashes, expected_files)
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError, urllib.error.URLError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Durably recover the byte-validated WXC implementation package from Git objects.

The script writes an auditable inventory even when reconstruction is impossible. It
only installs the overlay after the full ZIP SHA-256, CRCs, and internal SHA256SUMS
all pass.
"""
from __future__ import annotations

import base64
import hashlib
import itertools
import json
import os
import struct
import urllib.request
import zipfile
from pathlib import Path

EXPECTED = "d0576b193c2fcaf041e10dfc4fb83a185b935f88d83a0e05a71518384006f294"
OBJECTS = [
    "fc718a9dfc299134a7624eb8fd91df57292c3ad9",
    "05708d1f95a7d790b0fd4f57b1b077c1796a1128",
    "c9535cf3ca7500f27f388b667c916ca8e78bfcca",
    "b1d5c47e8d7b8d0a1a0b4c964714ee5d89732394",
    "b3752e84c0f6d3fd13f6280d33a7f11ef4ead75b",
    "b79f72c8473cdb216b8aa196612923fed83514e4",
    "abac9a3a8da92e4aa068d6c732655c872964036d",
    "9d30d1384cadb4b757c316b9808c554c5e32130d",
    "6fed7f1dd15de5cd51f2a2c98c514ecff6aae256",
    "b85c173e7631787f4dab51ce927dbc6c86e0f677",
    "a25411e43a7b1b0f3888fcd1aa90be4b4accebd7",
]
REPORT = Path("anhui_zsb_data/reports/wxc_package_recovery_diagnostic_v2.json")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(repo: str, token: str, object_sha: str) -> bytes:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/git/blobs/{object_sha}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "anhui-zsb-data-wxc-durable-recovery",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("encoding") != "base64":
        raise RuntimeError(f"Unexpected Git blob encoding: {payload.get('encoding')}")
    return base64.b64decode(payload["content"])


def archive_size(data: bytes) -> int | None:
    offset = data.rfind(b"PK\x05\x06")
    if offset < 0 or offset + 22 > len(data):
        return None
    fields = struct.unpack_from("<4s4H2LH", data, offset)
    comment_length = fields[7]
    if offset + 22 + comment_length > len(data):
        return None
    return fields[6] + fields[5] + 22 + comment_length


def reconstruct(candidates: dict[str, bytes]) -> tuple[bytes | None, tuple[str, ...]]:
    for name, data in candidates.items():
        if digest(data) == EXPECTED:
            return data, (name,)

    starts = [name for name, data in candidates.items() if data.startswith(b"PK\x03\x04")]
    ends = [(name, size) for name, data in candidates.items()
            if (size := archive_size(data)) is not None]
    all_names = tuple(candidates)
    for first in starts:
        for last, expected_size in ends:
            if first == last:
                continue
            middle_size = expected_size - len(candidates[first]) - len(candidates[last])
            if middle_size < 0:
                continue
            pool = [name for name in all_names if name not in {first, last}]
            matching_subsets: list[tuple[str, ...]] = []
            for count in range(len(pool) + 1):
                for subset in itertools.combinations(pool, count):
                    if sum(len(candidates[name]) for name in subset) == middle_size:
                        matching_subsets.append(subset)
            for subset in matching_subsets:
                for middle in itertools.permutations(subset):
                    order = (first, *middle, last)
                    hasher = hashlib.sha256()
                    for name in order:
                        hasher.update(candidates[name])
                    if hasher.hexdigest() == EXPECTED:
                        return b"".join(candidates[name] for name in order), order
    return None, ()


def main() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GH_TOKEN"]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    candidates: dict[str, bytes] = {}
    errors: list[str] = []

    transfer = Path(".github/wxc-p0")
    if transfer.exists():
        for path in sorted(transfer.rglob("*")):
            if path.is_file():
                try:
                    candidates[f"file:{path}"] = path.read_bytes()
                except Exception as exc:
                    errors.append(f"file:{path}:{exc!r}")

    for object_sha in OBJECTS:
        try:
            candidates[f"blob:{object_sha}"] = fetch(repo, token, object_sha)
        except Exception as exc:
            errors.append(f"blob:{object_sha}:{exc!r}")

    inventory = [
        {
            "name": name,
            "size": len(data),
            "sha256": digest(data),
            "zip_start": data.startswith(b"PK\x03\x04"),
            "archive_size": archive_size(data),
        }
        for name, data in candidates.items()
    ]
    package, order = reconstruct(candidates)
    diagnostic = {
        "expected_package_sha256": EXPECTED,
        "candidate_count": len(candidates),
        "inventory": inventory,
        "errors": errors,
        "recovered": package is not None,
        "order": list(order),
    }
    REPORT.write_text(json.dumps(diagnostic, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(diagnostic, ensure_ascii=False, indent=2))
    if package is None:
        return 2
    if digest(package) != EXPECTED:
        raise AssertionError("Reconstructed ZIP SHA-256 mismatch")

    zip_path = Path("/tmp/wxc-p0-durable-recovery.zip")
    extract_root = Path("/tmp/wxc-p0-durable-recovery")
    zip_path.write_bytes(package)
    with zipfile.ZipFile(zip_path) as archive:
        bad = archive.testzip()
        if bad:
            raise AssertionError(f"ZIP CRC failure: {bad}")
        archive.extractall(extract_root)

    package_root = extract_root / "anhui-zsb-wxc-p0-implementation"
    for line in (package_root / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        expected_hash, relative = line.split(maxsplit=1)
        relative = relative.lstrip("*")
        path = package_root / relative
        if digest(path.read_bytes()) != expected_hash:
            raise AssertionError(f"Internal package hash mismatch: {relative}")

    overlay = package_root / "repo-overlay"
    for source in overlay.rglob("*"):
        if source.is_file():
            destination = Path(source.relative_to(overlay))
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

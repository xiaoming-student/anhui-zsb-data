#!/usr/bin/env python3
"""Recover the validated WXC implementation ZIP from exact Git objects or branch chunks."""
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

EXPECTED_PACKAGE = "d0576b193c2fcaf041e10dfc4fb83a185b935f88d83a0e05a71518384006f294"
OBJECT_SHAS = [
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


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_blob(repo: str, token: str, sha: str) -> bytes:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/git/blobs/{sha}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "anhui-zsb-data-wxc-recovery-fallback",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("encoding") != "base64":
        raise RuntimeError(f"unexpected encoding for {sha}: {payload.get('encoding')}")
    return base64.b64decode(payload["content"])


def expected_archive_size(data: bytes) -> int | None:
    position = data.rfind(b"PK\x05\x06")
    if position < 0 or position + 22 > len(data):
        return None
    fields = struct.unpack_from("<4s4H2LH", data, position)
    comment_length = fields[7]
    if position + 22 + comment_length > len(data):
        return None
    return fields[6] + fields[5] + 22 + comment_length


def reconstruct(candidates: dict[str, bytes]) -> tuple[bytes | None, tuple[str, ...] | None]:
    for name, data in candidates.items():
        if digest(data) == EXPECTED_PACKAGE:
            return data, (name,)

    starts = [name for name, data in candidates.items() if data.startswith(b"PK\x03\x04")]
    ends = [(name, size) for name, data in candidates.items()
            if (size := expected_archive_size(data)) is not None]
    names = tuple(candidates)
    for first in starts:
        for last, total_size in ends:
            if first == last:
                continue
            middle_size = total_size - len(candidates[first]) - len(candidates[last])
            if middle_size < 0:
                continue
            pool = [name for name in names if name not in {first, last}]
            for count in range(len(pool) + 1):
                for subset in itertools.combinations(pool, count):
                    if sum(len(candidates[name]) for name in subset) != middle_size:
                        continue
                    for middle in itertools.permutations(subset):
                        order = (first, *middle, last)
                        hasher = hashlib.sha256()
                        for name in order:
                            hasher.update(candidates[name])
                        if hasher.hexdigest() == EXPECTED_PACKAGE:
                            return b"".join(candidates[name] for name in order), order
    return None, None


def main() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GH_TOKEN"]
    candidates: dict[str, bytes] = {}
    errors: list[str] = []

    transfer_root = Path(".github/wxc-p0")
    if transfer_root.exists():
        for path in sorted(transfer_root.rglob("*")):
            if not path.is_file():
                continue
            try:
                data = path.read_bytes()
            except Exception as exc:
                errors.append(f"file {path}: {exc!r}")
                continue
            candidates[f"file:{path}"] = data

    for sha in OBJECT_SHAS:
        try:
            candidates[f"blob:{sha}"] = fetch_blob(repo, token, sha)
        except Exception as exc:
            errors.append(f"blob {sha}: {exc!r}")

    inventory = [
        {
            "name": name,
            "size": len(data),
            "sha256": digest(data),
            "zip_start": data.startswith(b"PK\x03\x04"),
            "archive_size_from_eocd": expected_archive_size(data),
        }
        for name, data in candidates.items()
    ]
    package, order = reconstruct(candidates)
    diagnostic = {
        "expected_package_sha256": EXPECTED_PACKAGE,
        "candidate_count": len(candidates),
        "inventory": inventory,
        "errors": errors,
        "recovered": package is not None,
        "order": list(order or ()),
    }
    Path("anhui_zsb_data/reports").mkdir(parents=True, exist_ok=True)
    Path("anhui_zsb_data/reports/wxc_package_recovery_diagnostic.json").write_text(
        json.dumps(diagnostic, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if package is None:
        print(json.dumps(diagnostic, ensure_ascii=False, indent=2))
        return 2

    package_path = Path("/tmp/wxc-p0-recovered.zip")
    package_path.write_bytes(package)
    if digest(package) != EXPECTED_PACKAGE:
        raise AssertionError("recovered package SHA mismatch")
    with zipfile.ZipFile(package_path) as archive:
        bad = archive.testzip()
        if bad:
            raise AssertionError(f"ZIP CRC failure: {bad}")
        archive.extractall("/tmp/wxc-p0-recovered")
    root = Path("/tmp/wxc-p0-recovered/anhui-zsb-wxc-p0-implementation")
    for line in (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        expected, relative = line.split(maxsplit=1)
        path = root / relative.lstrip("*")
        if digest(path.read_bytes()) != expected:
            raise AssertionError(f"manifest mismatch: {relative}")
    overlay = root / "repo-overlay"
    for source in overlay.rglob("*"):
        if source.is_file():
            target = Path(source.relative_to(overlay))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
    print(json.dumps(diagnostic, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

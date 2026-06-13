"""Product integrity verification (REQ-ING-03).

Computes a deterministic sha256 over a downloaded product and compares it against
an expected digest before the product is registered. A product is either a single
file or a SAFE **folder**; for a folder the hash spans every file in a stable,
path-sorted order (relative paths are folded into the digest so renames/moves are
detected). A corrupt or incomplete product fails verification and is rejected.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK = 1 << 20  # 1 MiB streaming read.


def compute_sha256(path: str | Path) -> str:
    """Return the hex sha256 of a file or, recursively, of a SAFE folder.

    For a directory the digest covers each contained file's relative path and
    bytes in path-sorted order, so it is stable across machines and detects both
    content corruption and missing/extra files.
    """
    target = Path(path)
    digest = hashlib.sha256()
    if target.is_dir():
        files = sorted(p for p in target.rglob("*") if p.is_file())
        for file_path in files:
            rel = file_path.relative_to(target).as_posix()
            digest.update(rel.encode("utf-8"))
            digest.update(b"\0")
            _update_with_file(digest, file_path)
            digest.update(b"\0")
    else:
        _update_with_file(digest, target)
    return digest.hexdigest()


def _update_with_file(digest: hashlib._Hash, file_path: Path) -> None:
    with open(file_path, "rb") as handle:
        while True:
            chunk = handle.read(_CHUNK)
            if not chunk:
                break
            digest.update(chunk)


def product_size_bytes(path: str | Path) -> int:
    """Return the total size in bytes of a file or SAFE folder."""
    target = Path(path)
    if target.is_dir():
        return sum(p.stat().st_size for p in target.rglob("*") if p.is_file())
    return target.stat().st_size


def verify_integrity(path: str | Path, expected_sha256: str) -> bool:
    """Return ``True`` iff the product at ``path`` matches ``expected_sha256``.

    Comparison is case-insensitive on the hex digest. A missing path returns
    ``False`` (treated as a failed/incomplete download), never raising.
    """
    target = Path(path)
    if not target.exists():
        return False
    return compute_sha256(target).lower() == expected_sha256.strip().lower()

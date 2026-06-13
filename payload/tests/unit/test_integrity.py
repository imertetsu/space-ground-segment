"""Unit tests for product integrity verification (REQ-ING-03)."""

from __future__ import annotations

from pathlib import Path

from pdgs.ingestion.integrity import (
    compute_sha256,
    product_size_bytes,
    verify_integrity,
)


def test_verify_accepts_matching_file(tmp_path: Path) -> None:
    product = tmp_path / "product.bin"
    product.write_bytes(b"sentinel-3 slstr fixture bytes")
    digest = compute_sha256(product)
    assert verify_integrity(product, digest) is True


def test_verify_rejects_corrupted_file(tmp_path: Path) -> None:
    product = tmp_path / "product.bin"
    product.write_bytes(b"original payload")
    digest = compute_sha256(product)
    # Corrupt the product after the digest was computed.
    product.write_bytes(b"corrupted payload")
    assert verify_integrity(product, digest) is False


def test_verify_is_case_insensitive(tmp_path: Path) -> None:
    product = tmp_path / "p.bin"
    product.write_bytes(b"abc")
    digest = compute_sha256(product)
    assert verify_integrity(product, digest.upper()) is True


def test_verify_missing_path_returns_false(tmp_path: Path) -> None:
    assert verify_integrity(tmp_path / "does_not_exist.bin", "deadbeef") is False


def test_folder_hash_detects_changed_file(tmp_path: Path) -> None:
    safe = tmp_path / "PRODUCT.SAFE"
    safe.mkdir()
    (safe / "a.nc").write_bytes(b"alpha")
    (safe / "b.nc").write_bytes(b"beta")
    digest = compute_sha256(safe)
    assert verify_integrity(safe, digest) is True
    # Mutate one file -> the folder digest must change (corruption detected).
    (safe / "b.nc").write_bytes(b"gamma")
    assert verify_integrity(safe, digest) is False


def test_folder_hash_detects_missing_file(tmp_path: Path) -> None:
    safe = tmp_path / "PRODUCT.SAFE"
    safe.mkdir()
    (safe / "a.nc").write_bytes(b"alpha")
    (safe / "b.nc").write_bytes(b"beta")
    digest = compute_sha256(safe)
    (safe / "b.nc").unlink()
    assert verify_integrity(safe, digest) is False


def test_product_size_bytes_folder(tmp_path: Path) -> None:
    safe = tmp_path / "PRODUCT.SAFE"
    safe.mkdir()
    (safe / "a.nc").write_bytes(b"12345")
    (safe / "b.nc").write_bytes(b"678")
    assert product_size_bytes(safe) == 8

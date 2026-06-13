"""Dead-letter inspection + on-demand reprocessing (REQ-OPS-01, REQ-OPS-02).

The operator actions behind the ``dead-letter`` and ``reprocess`` CLI subcommands,
factored out of :mod:`pdgs.cli` so they can be unit-tested without the argparse
layer:

* :func:`list_dead_letter` — list catalogue products in the ``FAILED`` dead-letter
  state (REQ-OPS-01).
* :func:`resolve_source_l1_dir` — given a product id, resolve the source L1 SAFE
  folder to reprocess: a derived ``SST_L2_DERIVED`` product resolves through its
  provenance ``input_product_ids`` to the registered L1 record; an L1 product
  resolves to its own ``local_path``; a ``FAILED`` product is re-attempted the same
  way. Raises :class:`ReprocessError` on an unknown/unresolvable id.
* :func:`reprocess_product` — re-run :func:`~pdgs.processing.product.process_scene`
  for the resolved source (refreshing the catalogue record in place via
  INSERT-OR-REPLACE), optionally re-validating against an L2 reference (REQ-OPS-02).

This is the ``operations`` layer: it composes ``processing`` and ``validation``
(both lower layers) and never imports ``cli``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pdgs.catalogue.models import Product, ProductStatus
from pdgs.catalogue.repository import Catalogue
from pdgs.config.paths import default_reports_dir
from pdgs.config.processing import ProcessingConfig
from pdgs.ingestion.readers import read_l2_wst
from pdgs.processing.product import DerivedSstProduct, process_scene
from pdgs.validation.orchestrate import validate_product
from pdgs.validation.result import ValidationResult

# Catalogue product_type values this layer reasons about.
_DERIVED_PRODUCT_TYPE = "SST_L2_DERIVED"
_L1_PRODUCT_TYPE = "SL_1_RBT"


class ReprocessError(RuntimeError):
    """Raised when a reprocess request cannot be resolved or carried out.

    Covers an unknown product id, a derived product with no resolvable L1 source,
    and a source whose L1 SAFE folder is missing on disk (e.g. a dead-lettered
    ingestion that never produced a local product).
    """


@dataclass(frozen=True)
class ReprocessOutcome:
    """Result of an on-demand reprocess (REQ-OPS-02).

    ``source_l1_id`` is the L1 product the derived SST was rebuilt from; ``derived``
    is the refreshed in-memory product. ``validation`` is populated only when
    reprocessing was asked to re-validate (``--validate``); otherwise ``None``.
    """

    source_l1_id: str
    derived: DerivedSstProduct
    validation: ValidationResult | None


def list_dead_letter(catalogue: Catalogue) -> list[Product]:
    """Return catalogue products in the ``FAILED`` dead-letter state (REQ-OPS-01)."""
    return catalogue.list(status=ProductStatus.FAILED)


def _resolve_l1_record(catalogue: Catalogue, product: Product) -> Product:
    """Resolve the L1 catalogue record to reprocess ``product`` from.

    A derived ``SST_L2_DERIVED`` product is resolved through its provenance
    ``input_product_ids``; an L1 product resolves to itself. Raises
    :class:`ReprocessError` when no L1 source can be determined.
    """
    if product.product_type == _DERIVED_PRODUCT_TYPE:
        prov = product.provenance
        if prov is None or not prov.input_product_ids:
            raise ReprocessError(
                f"derived product {product.product_id!r} has no provenance input "
                "product ids; cannot resolve its source L1"
            )
        source_id = prov.input_product_ids[0]
        source = catalogue.get(source_id)
        if source is not None:
            return source
        # The L1 source is not separately catalogued (e.g. processed without a
        # prior ingest). Fall back to a synthetic record carrying the id so the
        # caller can still resolve a SAFE folder by other means.
        raise ReprocessError(
            f"source L1 {source_id!r} for derived {product.product_id!r} is not in "
            "the catalogue; ingest it before reprocessing"
        )
    if product.level == "L1" or product.product_type == _L1_PRODUCT_TYPE:
        return product
    raise ReprocessError(
        f"product {product.product_id!r} (type {product.product_type!r}) is neither a "
        "derived SST nor an L1 product; nothing to reprocess"
    )


def resolve_source_l1_dir(catalogue: Catalogue, product_id: str) -> tuple[str, Path]:
    """Resolve ``product_id`` to its source L1 ``(id, SAFE folder)`` to reprocess.

    Looks the product up in the catalogue, resolves the L1 source record (see
    :func:`_resolve_l1_record` — derived products route through provenance; L1
    products resolve to themselves; ``FAILED`` products are re-attempted the same
    way), and returns the L1 product id plus its ``local_path`` as a folder.

    Raises :class:`ReprocessError` if the id is unknown, the L1 source cannot be
    resolved, or the resolved L1 SAFE folder is missing/empty on disk.
    """
    product = catalogue.get(product_id)
    if product is None:
        raise ReprocessError(f"unknown product id: {product_id!r}")

    l1 = _resolve_l1_record(catalogue, product)
    if not l1.local_path:
        raise ReprocessError(
            f"L1 source {l1.product_id!r} has no local path on record "
            "(e.g. a dead-lettered ingestion); re-ingest it before reprocessing"
        )
    l1_dir = Path(l1.local_path)
    if not l1_dir.is_dir():
        raise ReprocessError(
            f"L1 source SAFE folder for {l1.product_id!r} not found on disk: {l1_dir}"
        )
    return l1.product_id, l1_dir


def reprocess_product(
    catalogue: Catalogue,
    product_id: str,
    cfg: ProcessingConfig,
    out_dir: str | Path,
    *,
    reference_l2_dir: str | Path | None = None,
    reports_dir: str | Path | None = None,
    synthetic_inputs: bool = False,
) -> ReprocessOutcome:
    """Reprocess the product selected by ``product_id`` on demand (REQ-OPS-02).

    Resolves the source L1 (:func:`resolve_source_l1_dir`), re-runs
    :func:`~pdgs.processing.product.process_scene` (refreshing the derived record in
    place via the catalogue's INSERT-OR-REPLACE), and — when ``reference_l2_dir`` is
    given — re-validates the refreshed product against that L2 reference, writing the
    report under ``reports_dir`` and setting the derived status to ``VALIDATED`` on a
    PASS. Returns a :class:`ReprocessOutcome`. Raises :class:`ReprocessError` on an
    unknown/unresolvable id.
    """
    source_l1_id, l1_dir = resolve_source_l1_dir(catalogue, product_id)
    derived = process_scene(l1_dir, cfg, catalogue, out_dir)

    validation: ValidationResult | None = None
    if reference_l2_dir is not None:
        ref_dir = Path(reference_l2_dir)
        if not ref_dir.is_dir():
            raise ReprocessError(f"L2 reference SAFE folder not found: {ref_dir}")
        reference = read_l2_wst(ref_dir)
        report_out = (
            Path(reports_dir)
            if reports_dir is not None
            else default_reports_dir(derived.product_id)
        )
        validation = validate_product(
            derived,
            reference,
            cfg.validation,
            report_out,
            config_version=cfg.config_version,
            synthetic_inputs=synthetic_inputs,
        )
        if validation.passed:
            catalogue.update_status(derived.product_id, ProductStatus.VALIDATED)

    return ReprocessOutcome(
        source_l1_id=source_l1_id,
        derived=derived,
        validation=validation,
    )

"""Filesystem path defaults for the PDGS payload chain.

The foundation ``config`` layer owns path conventions so higher layers do not
hard-code locations. Everything lives under a single, gitignored ``data/`` root
(see the repo ``.gitignore``) unless overridden via the ``PDGS_DATA_DIR``
environment variable.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Environment variable that overrides the data-root location.
DATA_DIR_ENV = "PDGS_DATA_DIR"


def data_dir() -> Path:
    """Return the (gitignored) data-root directory, creating it if needed.

    Defaults to ``<cwd>/data``; override with the ``PDGS_DATA_DIR`` env var.
    """
    root = Path(os.environ.get(DATA_DIR_ENV, "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def default_catalogue_path() -> Path:
    """Return the default sqlite catalogue file path under the data root."""
    return data_dir() / "catalogue.sqlite"


def default_download_dir() -> Path:
    """Return the default directory ingested products are downloaded into."""
    dest = data_dir() / "products"
    dest.mkdir(parents=True, exist_ok=True)
    return dest

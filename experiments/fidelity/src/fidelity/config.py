"""Machine-specific paths, read from the environment rather than hardcoded.

Only the paths that genuinely vary by machine (raw credentialed data, local
tool installs) are declared here -- a missing one fails loudly and
immediately, naming exactly what to set, rather than silently resolving to
someone else's home directory. This experiment's own generated output and
results are not machine-specific and live under this experiment's own
directory instead (see `paths.py`).

Setup: copy .env.example to .env, fill in the paths for your own
environment, then `source .env` before running any script directly, or
`sbatch --export=ALL <script>.sbatch` after sourcing it once in your shell.
"""

import os
from pathlib import Path


def _require(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Required environment variable {name} is not set. "
            f"Copy .env.example to .env, fill in your own paths, and `source .env` first."
        )
    return Path(value).expanduser()


# Raw eICU-CRD download (PhysioNet) -- the extraction step's dataset source.
EICU_CRD_RAW_PATH = _require("EICU_CRD_RAW_PATH")

# Per-file symlinks into the raw eICU-CRD download, in ricu's own expected
# source-directory layout -- kept separate from the credentialed PhysioNet
# directory so ricu's own cache never writes there.
RICU_DATA_PATH = _require("RICU_DATA_PATH")

# Local clone of georginapetr/openicu-yaib, needed as an actual checkout for
# resource files (e.g. scripts/datasets/export_ricu_eicu-crd.R) run directly.
OPENICU_YAIB_REPO_ROOT = _require("OPENICU_YAIB_REPO_ROOT")

# conda's own binary and the R environment name ricu/arrow/data.table are installed into.
CONDA_BIN = _require("CONDA_BIN")
RICU_CONDA_ENV = os.environ.get("RICU_CONDA_ENV", "yaib-cohorts2")

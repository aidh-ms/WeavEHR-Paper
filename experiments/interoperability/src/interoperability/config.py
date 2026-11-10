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

# Raw eICU-CRD patient table -- used directly for fields WeavEHR's own
# pipeline can't provide for this task (sex, death_icu, hospital_id; see
# each script's own docstring for why).
EICU_RAW_PATIENT_CSV = EICU_CRD_RAW_PATH / "patient.csv.gz"

# Local clone of the official YAIB training codebase (rvandewater/YAIB).
YAIB_REPO_ROOT = _require("YAIB_REPO_ROOT")

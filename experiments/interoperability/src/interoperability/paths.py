"""This experiment's own directory layout -- not machine-specific, so no env vars."""

from pathlib import Path

EXPERIMENT_ROOT = Path(__file__).parent.parent.parent
CONFIG_DIR = EXPERIMENT_ROOT / "config"
PROJECT_PATH = EXPERIMENT_ROOT / "output" / "project"
RESULTS_DIR = EXPERIMENT_ROOT / "results"

AKI_TASK_DIR = RESULTS_DIR / "aki" / "eicu-crd"
MORTALITY24_TASK_DIR = RESULTS_DIR / "mortality24" / "eicu-crd"

AKI_TRAINING_LOGS_DIR = EXPERIMENT_ROOT / "aki_training_logs"
MORTALITY24_TRAINING_LOGS_DIR = EXPERIMENT_ROOT / "mortality24_training_logs"

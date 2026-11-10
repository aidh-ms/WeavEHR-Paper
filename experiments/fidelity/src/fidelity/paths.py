"""This experiment's own directory layout -- not machine-specific, so no env vars."""

from pathlib import Path

EXPERIMENT_ROOT = Path(__file__).parent.parent.parent
CONFIG_DIR = EXPERIMENT_ROOT / "config"
PROJECT_PATH = EXPERIMENT_ROOT / "output" / "project"
RESULTS_DIR = EXPERIMENT_ROOT / "results"

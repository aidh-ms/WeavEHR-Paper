"""Regression tests for each experiment's path-resolution modules.

Exists because of a real bug found while building the interoperability
experiment: moving `config.py`/`paths.py`/`render_config.py` into a
per-experiment package (to fix a `ty` module-name collision between
experiments) silently broke `paths.py`'s `EXPERIMENT_ROOT` calculation --
the extra package-nesting level meant it resolved one directory too
shallow, and every downstream read/write landed in a nonexistent
`<experiment>/src/output/` instead of `<experiment>/output/`. It was only
caught by actually re-running a SLURM job and watching it fail. These
tests catch that same class of bug before any job has to run at all.

Each experiment's `src/` is a self-contained script directory (run with
`PYTHONPATH=<experiment>/src`, not as part of this repo's own top-level
`src/` package), so these tests insert it onto `sys.path` directly rather
than relying on the `pythonpath` pytest config, which only covers the
top-level package.
"""

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
EXPERIMENTS = ["fidelity", "interoperability"]


@pytest.fixture
def experiment_module(request, monkeypatch):
    """Import `<experiment>.paths` fresh, with its src/ on sys.path only
    for the duration of the test, and the env vars its config.py needs."""
    experiment = request.param
    src_dir = REPO_ROOT / "experiments" / experiment / "src"
    monkeypatch.syspath_prepend(str(src_dir))
    monkeypatch.setenv("EICU_CRD_RAW_PATH", "/fake/eicu-crd")
    if experiment == "interoperability":
        monkeypatch.setenv("YAIB_REPO_ROOT", "/fake/yaib-repo")
    else:
        for name in ("RICU_DATA_PATH", "OPENICU_YAIB_REPO_ROOT", "CONDA_BIN"):
            monkeypatch.setenv(name, "/fake/path")

    for mod_name in list(sys.modules):
        if mod_name == experiment or mod_name.startswith(f"{experiment}."):
            del sys.modules[mod_name]

    paths = importlib.import_module(f"{experiment}.paths")
    yield experiment, paths


@pytest.mark.parametrize("experiment_module", EXPERIMENTS, indirect=True)
def test_experiment_root_is_the_experiment_directory(experiment_module):
    """EXPERIMENT_ROOT must be <repo>/experiments/<name>, not one level off
    in either direction -- confirmed by checking it contains that
    experiment's own, real README.md rather than trusting the computed
    path's string value alone."""
    experiment, paths = experiment_module
    expected_root = REPO_ROOT / "experiments" / experiment

    assert paths.EXPERIMENT_ROOT == expected_root
    assert (paths.EXPERIMENT_ROOT / "README.md").is_file()


@pytest.mark.parametrize("experiment_module", EXPERIMENTS, indirect=True)
def test_derived_paths_are_under_experiment_root(experiment_module):
    _, paths = experiment_module
    assert paths.CONFIG_DIR == paths.EXPERIMENT_ROOT / "config"
    assert paths.PROJECT_PATH == paths.EXPERIMENT_ROOT / "output" / "project"
    assert paths.RESULTS_DIR == paths.EXPERIMENT_ROOT / "results"


@pytest.mark.parametrize("experiment_module", EXPERIMENTS, indirect=True)
def test_render_config_substitutes_the_real_raw_path(experiment_module, tmp_path, monkeypatch):
    """render_extraction_config() must replace the committed placeholder
    with the real, env-provided path -- and fail loudly if the template's
    placeholder text ever drifts from what the module expects, rather than
    silently writing out an unrendered config."""
    experiment, paths = experiment_module
    render_config = importlib.import_module(f"{experiment}.render_config")

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "extraction.yml.example").write_text("path: /path/to/physionet.org/files/eicu-crd/2.0\n")
    monkeypatch.setattr(paths, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(render_config, "CONFIG_DIR", config_dir)

    render_config.render_extraction_config()

    rendered = (config_dir / "extraction.yml").read_text()
    assert "/fake/eicu-crd" in rendered
    assert "/path/to/physionet.org" not in rendered


@pytest.mark.parametrize("experiment_module", EXPERIMENTS, indirect=True)
def test_render_config_raises_if_placeholder_missing(experiment_module, tmp_path, monkeypatch):
    experiment, paths = experiment_module
    render_config = importlib.import_module(f"{experiment}.render_config")

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "extraction.yml.example").write_text("path: already-a-real-looking-value\n")
    monkeypatch.setattr(paths, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(render_config, "CONFIG_DIR", config_dir)

    with pytest.raises(RuntimeError, match="Placeholder"):
        render_config.render_extraction_config()

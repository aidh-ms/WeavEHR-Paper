import argparse
import runpy
import sys
import tempfile
from pathlib import Path

import yaml

import weavehr
from weavehr import ConceptStep, WeavEHRProject
from weavehr.logging import configure_logging
from weavehr.utils.loader import auto_load_configs

from src import conf

parser = argparse.ArgumentParser()
parser.add_argument("--src", choices=["hirid", "aumc"], required=True)
args = parser.parse_args()

root = Path.home() / "output/yaib-cohorts"
src = args.src
version = {"hirid": "1.1.1", "aumc": "1.5.0"}[src]

conf["weavehr_project_path"] = str(
    root / "weavehr-projects-aki-combined/{src}"
)
conf["out_dir"] = str(root / "weavehr-aki-combined")

project_path = Path(
    conf["weavehr_project_path"].format(src=src)
)

assert (project_path / "datasets/extraction/.complete").is_file()
assert not (project_path / "datasets/concept/.complete").exists()
assert not (Path(conf["out_dir"]) / "aki" / src).exists()

print("WeavEHR:", weavehr.__file__, flush=True)
print("Project:", project_path, flush=True)
print("Output:", conf["out_dir"], flush=True)

assert str(Path.home() / "workspace/WeavEHR-aki/src") in str(
    Path(weavehr.__file__).resolve()
)

configure_logging(level="INFO")
auto_load_configs()

step = {
    "name": "Concept",
    "version": "1.0.0",
    "overwrite": False,
    "config": {
        "extraction_step": "Extraction",
        "mapping_configs": [
            {"name": src, "version": version}
        ],
    },
}

with tempfile.TemporaryDirectory() as tmp:
    config_path = Path(tmp) / "concept.yml"
    config_path.write_text(yaml.safe_dump(step))

    with WeavEHRProject(project_path) as project:
        ConceptStep.load(project, config_path).run()

assert (project_path / "datasets/concept/.complete").is_file()

for concept in ("aki", "aki_creatinine"):
    path = (
        project_path / "datasets/concept/data"
        / concept / "1.0.0" / src / f"{version}.parquet"
    )
    assert path.is_file(), f"Missing concept: {path}"

sys.argv = ["aki.py", "--src", src]
runpy.run_path("aki.py", run_name="__main__")

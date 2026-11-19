import argparse
import tempfile
from pathlib import Path

import yaml
import weavehr

from weavehr import ConceptStep, WeavEHRProject
from weavehr.logging import configure_logging
from weavehr.utils.loader import auto_load_configs

parser = argparse.ArgumentParser()
parser.add_argument(
    "--src",
    required=True,
    choices=["eicu-crd-ricu", "mimic-iv-ricu"],
)
args = parser.parse_args()

src = args.src

version = {
    "eicu-crd-ricu": "2.0",
    "mimic-iv-ricu": "3.1",
}[src]

root = Path.home() / "output/yaib-cohorts"
project_path = root / "weavehr-projects-ricu-fix" / src

assert (project_path / "datasets/extraction/.complete").is_file()
assert not (project_path / "datasets/concept").exists()

assert str(
    Path.home() / "workspace/WeavEHR-ricu-fix/src"
) in str(Path(weavehr.__file__).resolve())

print("WeavEHR:", weavehr.__file__, flush=True)
print("Project:", project_path, flush=True)

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

print("CONCEPT_FIX_COMPLETE:", src, flush=True)

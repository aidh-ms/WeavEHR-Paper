import tempfile
from pathlib import Path

import yaml
import weavehr

from weavehr import ConceptStep, WeavEHRProject
from weavehr.logging import configure_logging
from weavehr.utils.loader import auto_load_configs

root = Path.home() / "output/yaib-cohorts"

project_path = (
    root / "weavehr-projects-hirid-fix/hirid"
)

assert (project_path / "datasets/extraction/.complete").is_file()
assert not (project_path / "datasets/concept").exists()

assert str(
    Path.home() / "workspace/WeavEHR-hirid-fix/src"
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
            {"name": "hirid", "version": "1.1.1"}
        ],
    },
}

with tempfile.TemporaryDirectory() as tmp:
    config_path = Path(tmp) / "concept.yml"
    config_path.write_text(yaml.safe_dump(step))

    with WeavEHRProject(project_path) as project:
        ConceptStep.load(project, config_path).run()

assert (project_path / "datasets/concept/.complete").is_file()

for concept in (
    "oxygen_saturation",
    "arterial_oxygen_saturation",
    "neutrophils",
    "neutrophils_absolute",
):
    path = (
        project_path / "datasets/concept/data"
        / concept / "1.0.0" / "hirid/1.1.1.parquet"
    )
    assert path.is_file(), f"Missing concept: {path}"
    print("Validated output:", path, flush=True)

print("CONCEPT_FIX_COMPLETE", flush=True)

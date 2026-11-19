import sys
import runpy
from pathlib import Path
from src import conf

root = Path.home() / "output/yaib-cohorts"

src = sys.argv[1]

assert src in ("eicu-crd-ricu", "mimic-iv-ricu")

project = root / "weavehr-projects-ricu-fix" / src
output = root / "weavehr-ricu-fix"

assert (project / "datasets/concept/.complete").is_file()
assert not (output / "los" / src / "dyn.parquet").exists()

conf["weavehr_project_path"] = str(
    root / "weavehr-projects-ricu-fix/{src}"
)
conf["out_dir"] = str(output)

sys.argv = ["los.py", "--src", src]

runpy.run_path("los.py", run_name="__main__")

assert (output / "los" / src / "dyn.parquet").is_file()

print("LOS_COMPLETE:", src, flush=True)

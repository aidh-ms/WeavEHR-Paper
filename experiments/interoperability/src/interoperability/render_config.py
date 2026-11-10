"""Render extraction.yml from its committed template plus the local raw-data path.

WeavEHR's config loader (`BaseConfig.load`) reads a YAML file as-is -- no
environment-variable interpolation -- so the dataset path can't be a
`${VAR}` placeholder inside a file we commit. Instead the committed file is
`extraction.yml.example` with a placeholder path (the project's established
`.env`/`.env.example` pattern, applied to this one YAML field); this module
renders the real, gitignored `extraction.yml` from it.
"""

from interoperability.config import EICU_CRD_RAW_PATH
from interoperability.paths import CONFIG_DIR

PLACEHOLDER = "/path/to/physionet.org/files/eicu-crd/2.0"


def render_extraction_config() -> None:
    template = (CONFIG_DIR / "extraction.yml.example").read_text()
    if PLACEHOLDER not in template:
        raise RuntimeError(
            f"Placeholder {PLACEHOLDER!r} not found in extraction.yml.example -- "
            f"has the template changed? Update PLACEHOLDER in render_config.py to match."
        )
    rendered = template.replace(PLACEHOLDER, str(EICU_CRD_RAW_PATH))
    (CONFIG_DIR / "extraction.yml").write_text(rendered)


if __name__ == "__main__":
    render_extraction_config()
    print(f"Wrote {CONFIG_DIR / 'extraction.yml'}")

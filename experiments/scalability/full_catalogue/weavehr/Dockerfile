# Build context: experiments/scalability
FROM python:3.14.8-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /bin/
# weavehr and all its dependencies, pinned with hashes (exported from the
# repository's uv.lock; see the file header to regenerate it).
COPY common/weavehr-requirements.txt /tmp/requirements.txt
RUN uv pip install --system --no-cache --require-hashes -r /tmp/requirements.txt

ENV PYTHONUNBUFFERED=1 \
    TMPDIR=/output/tmp \
    POLARS_TEMP_DIR=/output/tmp

COPY common/measure.sh /bench/
COPY full_catalogue/weavehr/run.py /bench/run.py

ENTRYPOINT ["/bench/measure.sh"]
CMD ["python", "/bench/run.py"]

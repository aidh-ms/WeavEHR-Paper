# Build context: experiments/scalability
FROM python:3.14.8-slim-trixie

ARG WEAVEHR_VERSION=0.0.1
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /bin/
RUN uv pip install --system --no-cache "weavehr==${WEAVEHR_VERSION}"

ENV PYTHONUNBUFFERED=1 \
    TMPDIR=/output/tmp \
    POLARS_TEMP_DIR=/output/tmp

COPY common/measure.sh common/common_concepts.csv /bench/
COPY common_concepts/weavehr/run.py /bench/run.py

ENTRYPOINT ["/bench/measure.sh"]
CMD ["python", "/bench/run.py"]

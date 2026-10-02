# Build context: experiments/scalability
FROM python:3.14-slim

ARG WEAVEHR_VERSION=0.0.1
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /bin/
RUN uv pip install --system --no-cache "weavehr==${WEAVEHR_VERSION}"

ENV PYTHONUNBUFFERED=1 \
    TMPDIR=/output/tmp \
    POLARS_TEMP_DIR=/output/tmp

COPY common/measure.sh /bench/
COPY full_catalogue/weavehr/run.py /bench/run.py

ENTRYPOINT ["/bench/measure.sh"]
CMD ["python", "/bench/run.py"]

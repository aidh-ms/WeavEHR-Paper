# Build context: experiments/scalability
FROM python:3.13.16-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /bin/
# reprodICU at the evaluated commit, the packages it imports without declaring
# them, and all dependencies, pinned with hashes (compiled from requirements.in;
# see the file header to regenerate it).
COPY full_catalogue/reprodicu/requirements.txt /tmp/requirements.txt
RUN uv pip install --system --no-cache --require-hashes -r /tmp/requirements.txt

ENV PYTHONUNBUFFERED=1 \
    TMPDIR=/output/tmp \
    POLARS_TEMP_DIR=/output/tmp

COPY common/measure.sh /bench/
COPY full_catalogue/reprodicu/run.py /bench/run.py

ENTRYPOINT ["/bench/measure.sh"]
CMD ["python", "/bench/run.py"]

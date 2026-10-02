# Build context: experiments/scalability
FROM python:3.13-slim

# reprodICU has no releases; pin the commit that was evaluated.
ARG REPRODICU_COMMIT=c5a017f3e0a71753196f945daebfe177e3adf573
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /bin/
# Extra packages are imported by reprodICU but not declared as dependencies.
RUN uv pip install --system --no-cache \
    "reprodICU @ https://github.com/CUB-CORR/reprodICU/archive/${REPRODICU_COMMIT}.tar.gz" \
    pyyaml numpy tqdm scikit-learn matplotlib seaborn altair

ENV PYTHONUNBUFFERED=1 \
    TMPDIR=/output/tmp \
    POLARS_TEMP_DIR=/output/tmp

COPY common/measure.sh /bench/
COPY full_catalogue/reprodicu/run.py /bench/run.py

ENTRYPOINT ["/bench/measure.sh"]
CMD ["python", "/bench/run.py"]

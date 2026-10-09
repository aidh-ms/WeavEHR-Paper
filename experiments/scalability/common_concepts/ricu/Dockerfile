# Build context: experiments/scalability
FROM rocker/r-ver:4.6.1

ARG RICU_VERSION=0.6.3
# units is only suggested by ricu but needed for its unit-converting concepts.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libudunits2-dev \
    && rm -rf /var/lib/apt/lists/*
RUN install2.r --error --skipinstalled ricu arrow units \
    && Rscript -e "stopifnot(packageVersion('ricu') == '${RICU_VERSION}')"

# ricu imports the raw CSVs into its data dir, so it gets a symlinked copy of
# the (read-only) input under /output/work instead of the input itself.
ENV RICU_DATA_PATH=/output/work/ricu \
    RICU_SRC_LOAD="" \
    TMPDIR=/output/tmp

COPY common/measure.sh common/common_concepts.csv /bench/
COPY common_concepts/ricu/run.R /bench/run.R

ENTRYPOINT ["/bench/measure.sh"]
CMD ["Rscript", "/bench/run.R"]

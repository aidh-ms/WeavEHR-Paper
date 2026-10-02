# Build context: experiments/scalability
FROM rocker/r-ver:4.6.1

ARG RICU_VERSION=0.6.3
RUN install2.r --error --skipinstalled ricu arrow \
    && Rscript -e "stopifnot(packageVersion('ricu') == '${RICU_VERSION}')"

# ricu imports the raw CSVs into its data dir, so it gets a symlinked copy of
# the (read-only) input under /output/work instead of the input itself.
ENV RICU_DATA_PATH=/output/work/ricu \
    RICU_SRC_LOAD="" \
    TMPDIR=/output/tmp

COPY common/measure.sh /bench/
COPY full_catalogue/ricu/run.R /bench/run.R

ENTRYPOINT ["/bench/measure.sh"]
CMD ["Rscript", "/bench/run.R"]

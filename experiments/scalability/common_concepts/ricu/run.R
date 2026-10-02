# ricu on the common concept subset (one dataset per run: MIMIC-IV or eICU-CRD).
#
# Import the raw CSVs (ricu's one-off setup step), then load every concept in
# common_concepts.csv and write it to /output/data/<src>/<concept>.parquet.
# Step timings are written to /output/steps.csv.

suppressPackageStartupMessages(library(ricu))
data.table::setDTthreads(0L)

# One dataset per run; the demos use the same ricu sources as the full data.
src <- c("mimic-iv" = "miiv", eicu = "eicu")[[Sys.getenv("DATASET")]]
concepts <- read.csv("/bench/common_concepts.csv")$ricu
out_dir <- "/output/data"
steps_file <- "/output/steps.csv"
cat("step,seconds,status\n", file = steps_file)

timed <- function(step, expr) {
  start <- Sys.time()
  status <- "error"
  on.exit({
    secs <- as.numeric(difftime(Sys.time(), start, units = "secs"))
    cat(sprintf("%s,%.3f,%s\n", step, secs, status), file = steps_file, append = TRUE)
    message(sprintf("[%s] %.1fs %s", step, secs, status))
  })
  res <- expr
  status <- "ok"
  invisible(res)
}

write_tbl <- function(x, file) {
  cols <- lapply(x, function(col) {
    if (inherits(col, "difftime")) as.numeric(col, units = "hours") else col
  })
  arrow::write_parquet(as.data.frame(cols, check.names = FALSE), file)
}

src_dir <- file.path(Sys.getenv("RICU_DATA_PATH"), src)
dir.create(dirname(src_dir), recursive = TRUE, showWarnings = FALSE)
stopifnot(system2("cp", c("-rs", "/input", src_dir)) == 0L)

timed(paste0(src, "/import"), import_src(src))
attach_src(src)

dir.create(file.path(out_dir, src), recursive = TRUE)
for (cncpt in concepts) {
  timed(paste0(src, "/", cncpt), {
    res <- load_concepts(cncpt, src, interval = mins(1L), verbose = FALSE)
    write_tbl(res, file.path(out_dir, src, paste0(cncpt, ".parquet")))
  })
}

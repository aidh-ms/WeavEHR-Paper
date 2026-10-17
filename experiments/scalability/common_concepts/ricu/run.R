# ricu on the common concept subset (one dataset per run: MIMIC-IV or eICU-CRD).
#
# Import the raw CSVs (ricu's one-off setup step), then load every concept in
# common_concepts.csv and write it to /output/data/<src>/<concept>.parquet.
# Step timings are written to /output/steps.csv.

suppressPackageStartupMessages(library(ricu))
data.table::setDTthreads(0L)

# One dataset per run. ricu ships an `eicu_demo` source (the demo CSVs differ
# from the full ones, e.g. respiratorycare.apneaparams vs apneaparms) but no
# MIMIC-IV demo source, so the demo is imported as `miiv` with an overriding
# config: without the table partitioning (the 100 demo patients leave some
# partitions empty, which ricu cannot merge) and without the full-data row counts.
demo <- Sys.getenv("DEMO") == "1"
src <- c("mimic-iv" = "miiv", eicu = if (demo) "eicu_demo" else "eicu")[[
  Sys.getenv("DATASET")
]]

if (demo && src == "miiv") {
  cfg_dir <- "/output/work/ricu-config"
  cfg <- get_config("data-sources")
  cfg <- Filter(function(x) x$name == "miiv", cfg)
  cfg[[1L]]$tables <- lapply(cfg[[1L]]$tables, function(tbl) {
    tbl$partitioning <- NULL
    tbl$num_rows <- NULL
    tbl
  })
  set_config(cfg, "data-sources", cfg_dir, digits = NA)
  # ricu merges the concept dictionaries of all config dirs and fails on a dir
  # without one, so add an empty dictionary.
  writeLines("{}", file.path(cfg_dir, "concept-dict.json"))
  Sys.setenv(RICU_CONFIG_PATH = cfg_dir)
}

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

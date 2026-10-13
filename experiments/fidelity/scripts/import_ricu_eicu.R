# One-time import of the raw eICU-CRD PhysioNet download into ricu's own
# cached format, needed before any ricu::load_concepts() call can work.
#
# RICU_DATA_PATH/eicu/ must contain the raw PhysioNet files under their
# original filenames -- set up as per-file symlinks into the actual raw
# eICU-CRD download (see this repo's README), not a copy, so this can
# never drift from or duplicate the credentialed source data, and never
# write ricu's own cache into that credentialed directory itself.
if (Sys.getenv("RICU_DATA_PATH") == "") {
  stop("RICU_DATA_PATH is not set. Copy .env.example to .env, fill in your own paths, and `source .env` first.")
}

suppressPackageStartupMessages(library(ricu))

cat("RICU_DATA_PATH:", Sys.getenv("RICU_DATA_PATH"), "\n")
cat("Availability before import:\n")
print(src_data_avail("eicu"))

import_src("eicu", verbose = TRUE)

cat("\nAvailability after import:\n")
print(src_data_avail("eicu"))

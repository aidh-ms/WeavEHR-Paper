Sys.unsetenv("RICU_CONFIG_PATH")

setwd("/home/q039tl/yaib/YAIB-cohorts-ricu/R")

lines <- readLines("sepsis.R")

cut1 <- grep("^# Define observation times", lines)
cut2 <- grep("^# Prepare data", lines)

stopifnot(length(cut1) == 1L, length(cut2) == 1L)

# Execute the original reference setup and outcome.
invisible(eval(
    parse(text = lines[seq_len(cut1 - 1L)]),
    envir = .GlobalEnv
))

cat("\n========== RAW SEPSIS AUDIT ==========\n")

raw <- load_step(dict["sep3_alt"], cache = TRUE)
cases <- summary_step(raw, "exists")
hosp <- load_step(dict["hospital_id"])

id <- id_vars(cases)
var <- data_var(cases)

cat("Source:", src, "\n")
cat("Raw outcome rows:", nrow(raw), "\n")
cat("Sepsis case stays:", nrow(cases), "\n")
cat("Base cohort stays:", nrow(patients), "\n")
cat("Hospital mapping rows:", nrow(hosp), "\n")
cat("Unique hospital IDs:", uniqueN(hosp$hospital_id), "\n")
cat("Missing hospital IDs:", sum(is.na(hosp$hospital_id)), "\n")

cat(
    "Duplicate hospital stay mappings:",
    nrow(hosp) - uniqueN(hosp[[id]]),
    "\n"
)

joined <- cases[hosp]

joined[, positive := !is.na(get(var)) & get(var)]

by_hosp <- joined[, .(
    stays = .N,
    cases = sum(positive)
), by = hospital_id]

cat(
    "Hospitals with zero cases:",
    sum(by_hosp$cases == 0),
    "\n"
)

cat(
    "Stays in hospitals with zero cases:",
    sum(by_hosp[cases == 0]$stays),
    "\n"
)

cat("Total matched case stays:", sum(joined$positive), "\n")

# Execute original observation times and exclusions,
# but stop before loading the dynamic predictors.
invisible(eval(
    parse(text = lines[cut1:(cut2 - 1L)]),
    envir = .GlobalEnv
))

cat("\n========== FINAL ATTRITION AUDIT ==========\n")
print(attrition)

cat("Final cohort stays:", nrow(patients), "\n")

cat("\n========== SAVED REFERENCE ==========\n")

print(fread(file.path(
    conf$out_dir, "sepsis", src, "attrition.csv"
)))

cat("\nAUDIT_COMPLETE\n")

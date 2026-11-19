library(data.table)
library(assertthat)
library(rlang)

source(".load_ricu.R")
source("src/steps.R")

src <- commandArgs(trailingOnly = TRUE)[1]
stopifnot(src %in% c("miiv", "eicu", "hirid", "aumc"))

cncpt_env <- new.env()

cat("\n========== DATASET:", src, "==========\n")

crea <- load_step(
    dict["kdigo_crea"],
    cache = FALSE,
    merge_data = TRUE,
    interval = hours(1L)
)

urine <- load_step(
    dict["kdigo_urine"],
    cache = FALSE,
    merge_data = TRUE,
    interval = hours(1L)
)

summarize_component <- function(x, name) {
    dt <- as.data.table(x)
    id <- id_vars(x)

    cat("\n==========", name, "==========\n")

    print(dt[, .(
        events = .N,
        stays = uniqueN(.SD[[id[1]]])
    ), by = name, .SDcols = id])

    res <- dt[, .(
        stage = if (all(is.na(get(name)))) {
            NA_real_
        } else {
            max(get(name), na.rm = TRUE)
        }
    ), by = id]

    print(res[, .(stays = .N), by = stage][order(stage)])

    res
}

cmax <- summarize_component(crea, "kdigo_crea")
umax <- summarize_component(urine, "kdigo_urine")

setnames(cmax, c(names(cmax)[1], "stage"), c("stay_id", "creatinine"))
setnames(umax, c(names(umax)[1], "stage"), c("stay_id", "urine"))

combined <- merge(cmax, umax, by = "stay_id", all = TRUE)

combined[, crea_positive := !is.na(creatinine) & creatinine >= 1]
combined[, urine_positive := !is.na(urine) & urine >= 1]

cat("\n========== CRITERION OVERLAP ==========\n")

print(combined[, .(
    stays_total = .N,
    creatinine_positive = sum(crea_positive),
    urine_positive = sum(urine_positive),
    creatinine_only = sum(crea_positive & !urine_positive),
    urine_only = sum(!crea_positive & urine_positive),
    both = sum(crea_positive & urine_positive),
    neither = sum(!crea_positive & !urine_positive)
)])

cat("\n========== WEIGHT COVERAGE ==========\n")

weight <- load_step(dict["weight"], cache = FALSE)
w <- as.data.table(weight)

print(w[, .(
    records = .N,
    missing = sum(is.na(weight)),
    minimum = min(weight, na.rm = TRUE),
    median = median(weight, na.rm = TRUE),
    maximum = max(weight, na.rm = TRUE)
)])

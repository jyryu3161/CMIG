#!/usr/bin/env Rscript
# Figure Composer — chord panel (circlize). Design Ref: §9.
# 입력 edges CSV(source_id,target_id,weight) → circlize chordDiagram → SVG/TIFF.
suppressWarnings(suppressMessages({
  args <- commandArgs(trailingOnly = TRUE)
  getarg <- function(flag, default = NA) {
    i <- which(args == flag); if (length(i) == 0) return(default); args[i + 1]
  }
  rlib <- getarg("--rlib", NA)
  if (!is.na(rlib)) .libPaths(c(rlib, .libPaths()))
  library(circlize); library(svglite)
}))

data_path <- getarg("--data"); out <- getarg("--out")
width <- as.numeric(getarg("--width", 6)); height <- as.numeric(getarg("--height", 5))
title <- getarg("--title", "Chord"); fmt <- getarg("--format", "svg")
seed <- as.integer(getarg("--seed", 42)); set.seed(seed)

PLOT_FONT <- tryCatch({
  if (requireNamespace("systemfonts", quietly = TRUE)) {
    fonts <- systemfonts::system_fonts()$family
    if ("Arial" %in% fonts) {
      "Arial"
    } else if ("Helvetica" %in% fonts) {
      "Helvetica"
    } else {
      "sans"
    }
  } else {
    "sans"
  }
}, error = function(e) "sans")

edges <- read.csv(data_path, stringsAsFactors = FALSE)
if (nrow(edges) == 0) stop("chord: empty edges")
df <- data.frame(from = edges$source_id, to = edges$target_id,
                 value = as.numeric(edges$weight))

if (fmt == "tiff") {
  tiff(out, width = width, height = height, units = "in",
       res = as.numeric(getarg("--dpi", 600)), compression = "lzw")
} else {
  svglite::svglite(out, width = width, height = height)
}
circos.clear()
nodes <- sort(unique(c(as.character(df$from), as.character(df$to))))
palette <- rep(c("#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd", "#7f7f7f"),
               length.out = length(nodes))
names(palette) <- nodes
par(family = PLOT_FONT)
chordDiagram(df, annotationTrack = c("name", "grid"), grid.col = palette,
             transparency = 0.35)
title(main = title, family = PLOT_FONT, font.main = 2, cex.main = 1.2)
circos.clear()
dev.off()

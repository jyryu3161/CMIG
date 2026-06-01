#!/usr/bin/env Rscript
# Figure Composer — heatmap panel (ComplexHeatmap). Design Ref: §9.
# 입력 matrix CSV(row_key,col_key,value) → wide matrix → ComplexHeatmap → SVG/TIFF.
suppressWarnings(suppressMessages({
  args <- commandArgs(trailingOnly = TRUE)
  getarg <- function(flag, default = NA) {
    i <- which(args == flag); if (length(i) == 0) return(default); args[i + 1]
  }
  rlib <- getarg("--rlib", NA)
  if (!is.na(rlib)) .libPaths(c(rlib, .libPaths()))
  library(ComplexHeatmap); library(circlize); library(svglite)
}))

data_path <- getarg("--data"); out <- getarg("--out")
width <- as.numeric(getarg("--width", 6)); height <- as.numeric(getarg("--height", 5))
title <- getarg("--title", "Heatmap"); fmt <- getarg("--format", "svg")

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

df <- read.csv(data_path, stringsAsFactors = FALSE)
if (nrow(df) == 0) stop("heatmap: empty matrix")
# long → wide (base R xtabs, reshape2 의존 회피)
mat <- xtabs(value ~ row_key + col_key, data = df)
mat <- as.matrix(mat)

col_fun <- colorRamp2(c(min(mat), 0, max(mat)), c("#1f77b4", "#f7f7f7", "#d62728"))
ht <- Heatmap(mat, name = "value", col = col_fun, column_title = title,
              cluster_rows = nrow(mat) > 1, cluster_columns = ncol(mat) > 1,
              border = TRUE,
              column_title_gp = grid::gpar(fontfamily = PLOT_FONT, fontsize = 12,
                                           fontface = "bold", col = "black"),
              row_names_gp = grid::gpar(fontfamily = PLOT_FONT, fontsize = 9,
                                        col = "black"),
              column_names_gp = grid::gpar(fontfamily = PLOT_FONT, fontsize = 9,
                                           col = "black"),
              heatmap_legend_param = list(
                title_gp = grid::gpar(fontfamily = PLOT_FONT, fontsize = 10,
                                      fontface = "bold", col = "black"),
                labels_gp = grid::gpar(fontfamily = PLOT_FONT, fontsize = 9,
                                       col = "black")
              ))

if (fmt == "tiff") {
  tiff(out, width = width, height = height, units = "in",
       res = as.numeric(getarg("--dpi", 600)), compression = "lzw")
} else {
  svglite::svglite(out, width = width, height = height)
}
draw(ht)
dev.off()

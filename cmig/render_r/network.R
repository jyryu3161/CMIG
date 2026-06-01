#!/usr/bin/env Rscript
# Figure Composer — network panel (ggraph). Design Ref: §9.
# 입력 edges CSV(source_id,target_id,weight,edge_type) → ggraph 네트워크 → SVG/TIFF.
suppressWarnings(suppressMessages({
  args <- commandArgs(trailingOnly = TRUE)
  getarg <- function(flag, default = NA) {
    i <- which(args == flag); if (length(i) == 0) return(default); args[i + 1]
  }
  rlib <- getarg("--rlib", NA)
  if (!is.na(rlib)) .libPaths(c(rlib, .libPaths()))
  library(ggraph); library(igraph); library(ggplot2); library(svglite)
}))

data_path <- getarg("--data"); out <- getarg("--out")
width <- as.numeric(getarg("--width", 6)); height <- as.numeric(getarg("--height", 5))
dpi <- as.numeric(getarg("--dpi", 600)); title <- getarg("--title", "Network")
seed <- as.integer(getarg("--seed", 42)); fmt <- getarg("--format", "svg")
set.seed(seed)

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
if (nrow(edges) == 0) stop("network: empty edges")
g <- graph_from_data_frame(edges[, c("source_id", "target_id")], directed = TRUE)
igraph::E(g)$weight <- as.numeric(edges$weight)
igraph::E(g)$edge_type <- edges$edge_type

p <- ggraph(g, layout = "fr") +
  geom_edge_link(aes(width = weight, colour = edge_type),
                 alpha = 0.65, arrow = arrow(length = unit(1.8, "mm")),
                 end_cap = circle(2.5, "mm")) +
  geom_node_point(size = 3.5, colour = "#2c7bb6") +
  geom_node_text(aes(label = name), repel = TRUE, size = 2.8, family = PLOT_FONT) +
  scale_edge_width(range = c(0.4, 1.6)) +
  scale_edge_colour_manual(values = c(
    "secretion" = "#d62728",
    "uptake" = "#1f77b4",
    "cross_feeding" = "#2ca02c"
  ), na.value = "grey60") +
  ggtitle(title) +
  theme_void(base_family = PLOT_FONT) +
  theme(
    plot.title = element_text(size = 12, face = "bold", hjust = 0.5, color = "black"),
    legend.position = "bottom",
    legend.title = element_text(size = 10, face = "bold", color = "black"),
    legend.text = element_text(size = 10, color = "black"),
    plot.background = element_rect(fill = "white", color = NA)
  )

if (fmt == "tiff") {
  ggsave(out, p, width = width, height = height, dpi = dpi,
         device = "tiff", compression = "lzw")
} else {
  ggsave(out, p, width = width, height = height, dpi = dpi,
         device = svglite::svglite)
}

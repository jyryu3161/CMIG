#!/usr/bin/env Rscript
# CMIG R Render — external profile diverging bar (ggplot2).
# Design Ref: §9 / FR-2.5. GPL 격리: 별도 프로세스로만 실행(§2). CMIG 는 R 을 링크하지 않는다.
# 입력: --data CSV(metabolite,net_flux,ui_flux,label) + spec flags. 출력: --out (svg|tiff|pdf|eps).

args <- commandArgs(trailingOnly = TRUE)
opt <- list(width = "6", height = "4", dpi = "600", title = "External Profile",
            format = "svg", out = "out.svg", data = "data.csv", seed = "42",
            rlib = "")
i <- 1
while (i <= length(args)) {
  key <- sub("^--", "", args[[i]])
  opt[[key]] <- args[[i + 1]]
  i <- i + 2
}

set.seed(as.integer(opt$seed))            # figure_spec 재현(§9)
if (!is.null(opt$rlib) && nzchar(opt$rlib) && dir.exists(opt$rlib)) {
  .libPaths(c(opt$rlib, .libPaths()))
}
df <- read.csv(opt$data, stringsAsFactors = FALSE)
suppressMessages(library(ggplot2))

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

nature_theme <- function(base_size = 10, base_family = PLOT_FONT) {
  theme_classic(base_size = base_size, base_family = base_family) +
    theme(
      plot.title = element_text(size = base_size + 2, face = "bold", hjust = 0.5,
                                margin = margin(b = 8), color = "black"),
      axis.title = element_text(size = base_size + 1, face = "bold", color = "black"),
      axis.text = element_text(size = base_size, color = "black"),
      axis.line = element_line(color = "black", linewidth = 0.5),
      axis.ticks = element_line(color = "black", linewidth = 0.5),
      legend.title = element_text(size = base_size, face = "bold", color = "black"),
      legend.text = element_text(size = base_size, color = "black"),
      legend.position = "right",
      legend.key = element_blank(),
      legend.background = element_blank(),
      panel.background = element_rect(fill = "white", color = NA),
      plot.background = element_rect(fill = "white", color = NA)
    )
}

# net_flux 순 정렬(결정적 레이아웃, §9)
df$metabolite <- factor(df$metabolite, levels = df$metabolite[order(df$net_flux)])
p <- ggplot(df, aes(x = metabolite, y = net_flux, fill = label)) +
  geom_col(width = 0.75, color = "black", linewidth = 0.2) +
  coord_flip() +
  geom_hline(yintercept = 0, linewidth = 0.5, color = "gray50") +
  scale_fill_manual(values = c("secretion" = "#d62728", "uptake" = "#1f77b4")) +
  labs(title = opt$title, x = "metabolite",
       y = "net exchange flux  (+ secretion / - uptake)") +
  nature_theme(base_size = 10)

w <- as.numeric(opt$width); h <- as.numeric(opt$height); dpi <- as.numeric(opt$dpi)

if (opt$format == "svg") {
  if (requireNamespace("svglite", quietly = TRUE)) {
    svglite::svglite(opt$out, width = w, height = h)        # 권장 렌더러(§9)
  } else {
    grDevices::svg(opt$out, width = w, height = h)          # base fallback(svglite 부재)
  }
  print(p); grDevices::dev.off()
} else if (opt$format == "tiff") {
  if (requireNamespace("ragg", quietly = TRUE)) {
    ragg::agg_tiff(opt$out, width = w, height = h, units = "in", res = dpi,
                   compression = "lzw")                     # 600dpi LZW(§9)
  } else {
    grDevices::tiff(opt$out, width = w, height = h, units = "in", res = dpi,
                    compression = "lzw")
  }
  print(p); grDevices::dev.off()
} else if (opt$format == "pdf") {
  grDevices::pdf(opt$out, width = w, height = h, family = PLOT_FONT, useDingbats = FALSE)
  print(p); grDevices::dev.off()
} else if (opt$format == "eps") {
  grDevices::postscript(opt$out, width = w, height = h, family = PLOT_FONT,
                        horizontal = FALSE, onefile = FALSE, paper = "special")
  print(p); grDevices::dev.off()
} else {
  stop(paste("unsupported format:", opt$format))
}
cat("OK\n")

# Reproducing the R figure environment

`renv.lock` pins R 4.3.2, Bioconductor 3.18, and the complete dependency closure observed for the
four bundled render scripts. Restore it into CMIG's ignored project-local library:

```bash
Rscript -e 'if (!requireNamespace("renv", quietly=TRUE)) install.packages("renv", repos="https://cloud.r-project.org"); renv::restore(lockfile="cmig/render_r/renv.lock", library=".Rlib", prompt=FALSE)'
```

Some packages need operating-system libraries for fonts, PNG, TIFF, or compilation. Those system
packages are intentionally not installed by CMIG. Every successful render writes
`<figure>.render_provenance.json` with the actual R/package versions and the SHA-256 checksums of the
R script, lock file, input table, figure specification, and output figure.

The lock was generated from the dependencies discovered in `figure.R`, `network.R`, `heatmap.R`,
and `chord.R`. Update it only as an intentional release change, then rerun all render tests.

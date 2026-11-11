# Changelog

## Unreleased: input checks, format conversion, and inspect

- Reject TIFF names that collide after Unicode NFC normalization and case folding, and reject Windows-reserved or otherwise non-portable TIFF names before any output directory is created.
- Treat width/height `0` as invalid instead of ignoring that side. Reject non-positive or non-finite scale, quality outside 1–100, and watermark opacity outside 0–1 before a batch writes files. When `scale` is set it still takes precedence over width and height. A single width or height still scales the other side proportionally.
- Convert modes a target format cannot encode (LA or CMYK to JPEG/PNG/BMP, and the same class of mismatch) to RGB. Modes the format can already store, including LA PNG and RGBA PNG, are unchanged.
- Add `ibp-micro inspect`. It applies the same display, crop, and scale-bar checks as export and prints pixel length, dimensions, and clipped-pixel counts without creating a directory or confirming calibration.

## Unreleased: legacy batch file-safety repair

- Reject all known batch output collisions before any processing begins, including shared stems after conversion, case/Unicode aliases, recursive file/directory conflicts, and existing targets. Preserve the established stem-plus-extension output names; do not rename implicitly.
- Reject overlapping input/output directories and unsafe linked/reparse paths. Reject nonportable output names consistently across operating systems.
- Encode before creating each output. Use exclusive file creation to prevent replacing a file that appears after the preflight check. Attempt ownership-checked cleanup of that call's incomplete output after a handled write error or keyboard interrupt; cleanup is best effort.
- Keep the direct `process_file` boolean return contract. `process_directory` now raises `BatchSafetyError` on unsafe or empty batches. Runtime failures return counts and retain successful earlier files.
- Exit the legacy CLI nonzero for preflight failures, empty input, and partial processing failures. Remove the misleading success banner after failures.
- Accept supported output-format aliases case-insensitively (`jpg`/`jpeg`, `tif`/`tiff`); retain the chosen alias in the lowercase output extension. Apply WebP quality settings consistently.

No changes to `ibp-micro` mapping, calibration, or manifest semantics are included. The batch is not a multi-file transaction. Forced termination, power loss, or concurrent directory modification can leave incomplete results; existing files are never deliberately overwritten to resume a run.

## 0.2.0

Added the separate `ibp-micro` display-export/replay workflow and synthetic-data tests. Fixed the original JPG/TIF encoder-name issue. Removed an unsupported concurrency claim.

**Breaking compatibility:** the combined distribution now requires Python >=3.10, with NumPy/tifffile and newer Pillow dependencies. The earlier project metadata advertised Python >=3.8. Existing Python 3.8/3.9 environments cannot install 0.2.0 as declared. Move to a separate supported environment rather than editing dependency metadata or reinstalling an older unsafe commit. No Python 3.8/3.9 maintenance package or migration-in-place guarantee is provided.

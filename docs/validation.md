# Validation and reproducibility notes

This is an alpha display-export utility, not a validated measurement pipeline.

## Mapping contract

1. Decode one unsigned 8/16-bit `YX`, MINISBLACK TIFF plane.
2. Select the same zero-based `(x, y, width, height)` crop for every source, or use its whole image.
3. Compute `floor(clip((value - display_min) / (display_max - display_min), 0, 1) * 255 + 0.5)` in float64 and store uint8 pixels.
4. Keep these pixels at their original size. Add a 56-pixel footer with a fixed built-in bitmap font, physical-unit label, and white bar. Rectangle coordinates are inclusive, so its endpoint is `left + length - 1`.
5. Require `scale_bar_um / pixel_size_um` to be an integer to absolute tolerance 1e-8; reject other widths. The tolerance handles floating-point representation, not deliberate physical-length rounding.

The user must independently verify that `pixel_size_um` describes square pixels and applies to all sources. Calibration metadata is not interpreted. The exporter records the confirmation, not evidence that the calibration is correct. Display settings can obscure detail and must be chosen and disclosed appropriately.

## Integrity contract

The source hash is computed from exactly the bytes passed to the decoder. It includes metadata, not just pixel values. The `image_pixel_sha256` hashes row-major uint8 crop/display pixels before the footer. `output_sha256` hashes the complete PNG. Replay checks source and output hashes. JSON contains the full recipe; CSV is a human-readable summary.

`ibp-micro inspect` runs the same input, crop, and scale-bar checks and returns clipped-pixel counts, but it does not write a directory and does not record calibration as confirmed. TIFF filenames must be portable and unique after Unicode NFC normalization and case folding, so two names that would become one file on macOS or Windows are rejected on every platform.

No absolute paths, timestamps, or source TIFF metadata are copied into the manifest. Basenames are retained. Same settings, source bytes and recorded dependency versions are intended to yield the same PNG bytes. Software versions are recorded, not locked by the tool; users must preserve their environment to reproduce older outputs. An altered manifest can redefine the expected values and is not a security signature.

## Data and testing limits

All test data and the README preview are synthetic. Tests exercise algorithmic and file-safety behavior; no real microscope acquisition, instrument calibration, journal policy, or clinical decision workflow has been validated. Limits apply to the new `ibp-micro` command; the legacy `ibp` tool is a separate general-purpose interface.

The implementation does not promise an atomic multi-file transaction across power loss. Ordinary Python exceptions trigger cleanup of the new output folder. `manifest.json` is the final completion marker. Concurrent modifications to input/output directories by another program are outside this contract.

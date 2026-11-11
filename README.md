# Image Batch Processor

## 中文摘要

本工具在本地处理图像，不上传文件。`ibp-micro` 把同一文件夹里的二维、单通道、8/16 位灰度 TIFF，按同一组线性显示范围和可选裁剪导出为 8 位 PNG，并在图像下方的页脚绘制不重采样的整数像素比例尺。导出前必须自行确认所有图像共用同一方形像素标定（微米/像素）；程序不会读取 TIFF 中的标定元数据。每次成功运行都会写入可重放的 JSON/CSV 清单和 SHA-256。`ibp-micro inspect` 只检查比例尺像素数、裁剪范围，以及有多少像素落在显示范围之外，不写出文件。这些 PNG 仅供显示，不能用于定量测量。通用命令 `ibp` 仍可批量缩放、旋转、加水印和转换普通照片。需要 Python 3.10 及以上。

**Local, traceable microscopy display exports from 2D TIFFs.** Apply one explicit intensity range and crop to a batch, draw a calibrated scale bar without resampling, and keep a replayable record of every input and output.

[MIT license](LICENSE) · Python 3.10+ · Alpha

![Two synthetic spot images exported with the same display limits, with a scale bar and synthetic labels](docs/synthetic-preview.png)

*Artificial Gaussian spots, not experimental data. The example's 0.5 µm/pixel calibration is fictional. Both panels use the same 1,000–40,000 raw intensity range, so the brighter source stays brighter.*

## Why this exists

A folder of figure exports is hard to audit if each image was adjusted separately or its settings were lost. `ibp-micro` is a small command-line workflow for a narrower job:

- One common, user-chosen linear display range and optional rectangular crop.
- Original TIFFs opened read-only; new output directory required; no overwriting.
- Unsigned 8/16-bit, single-channel, single-plane grayscale TIFF only.
- Square-pixel calibration supplied and explicitly confirmed by the user. TIFF resolution/OME calibration metadata is **not** used automatically.
- A scale bar in a separate footer, with exactly the requested integer number of pixels. No stretching, rotation, or interpolation.
- 8-bit display PNGs, JSON/CSV manifests, source/output SHA-256 hashes, software versions, and a hash-checked replay command.

**These PNGs are for display, not quantitative analysis.** Mapping to 8-bit clips and reduces intensity precision. Measure the original data. This is early-stage software, not validated scientific or clinical software. Passing tests does not establish the correctness of your acquisition calibration or the appropriateness of a figure.

## Install

```bash
git clone https://github.com/Master-626/image-batch-processor.git
cd image-batch-processor
python -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install .
```

No account, upload, or network service is needed to process images. Installation may download dependencies. Install from this repository; a PyPI release is not assumed.

## Run the synthetic example

From the repository root, in a fresh working directory for these outputs:

```bash
python examples/generate_synthetic.py synthetic-input
ibp-micro export synthetic-input -o synthetic-export \
  --display-min 1000 --display-max 40000 \
  --pixel-size-um 0.5 --scale-bar-um 20 \
  --confirm-calibration --synthetic-data
```

The demo generates two **synthetic** 16-bit TIFFs, not real experiments. `--synthetic-data` adds a visible label to each output and records the flag in both manifests. On PowerShell, enter the command on one line instead of using `\` line continuations.

Output:

```text
synthetic-export/
  SYNTHETIC_spots_1.tif.png
  SYNTHETIC_spots_2.tif.png
  manifest.json
  manifest.csv
```

Only `.tif`/`.tiff` files directly in the input folder are selected. Subfolders and other file types are ignored. The original extension is retained in each PNG name so `sample.tif` and `sample.tiff` cannot overwrite each other.

## Preview a batch without writing files

```bash
ibp-micro inspect synthetic-input \
  --display-min 1000 --display-max 40000 \
  --pixel-size-um 0.5 --scale-bar-um 20 \
  --synthetic-data
```

`inspect` selects the same files and applies the same display math, crop, and scale-bar rules as `export`. It prints the bar length in pixels, each file's dimensions and bit depth, and how many pixels fall outside the display range. It does not create a directory, write a manifest, or treat the pixel size as confirmed. On PowerShell, enter the command on one line.

## Use your own images

First verify that all images have the **same square-pixel calibration** from acquisition records or a validated calibration workflow. The flag is your confirmation; the software cannot verify it. Do not copy the demo calibration into a real experiment.

```bash
ibp-micro export raw-tiffs -o figure-export \
  --display-min 500 --display-max 30000 \
  --crop 40 20 512 384 \
  --pixel-size-um 0.1625 --scale-bar-um 13 \
  --confirm-calibration
```

Here the crop is `x=40, y=20, width=512, height=384`, in original pixels with zero-based coordinates. Every input must contain that crop. A 13 µm bar at 0.1625 µm/pixel is **80 pixels** wide. Noninteger bar widths are rejected instead of silently rounding the physical length.

The chosen intensity range is applied identically to every image. There is no per-image autoscaling or automatic percentile choice. For 8-bit TIFFs the maximum must be ≤255; for 16-bit TIFFs it must be ≤65535. Choose suitable limits for the data and report display adjustments when required by your field or journal.

The output image contains the crop at unchanged pixel dimensions, plus a 56-pixel black annotation footer. The bar occupies exactly the recorded number of horizontal pixels. Label and bar must fit within the crop width; otherwise export stops. The footer is outside the source image, so it does not hide image content. `manifest.json` records the image/footer boundaries and bar coordinates.

## Replay and audit

```bash
ibp-micro replay synthetic-input -o synthetic-replayed \
  --manifest synthetic-export/manifest.json --confirm-calibration
```

Replay checks the full TIFF filename set and SHA-256 of each source, reapplies the recorded settings, and requires an identical PNG SHA-256. Changed/missing/extra TIFFs or different rendered PNGs cause failure. It does not fetch original data. Keep the original TIFFs, manifest, and software environment together.

The JSON manifest records raw-source and exported-file hashes, image dimensions and bit depth, crop, display range, scale bar, user-confirmed calibration, synthetic-data status, and Python/NumPy/Pillow/tifffile/zlib versions. CSV is a compact audit summary; JSON is the replay recipe. Manifests contain source **basenames**, not absolute paths or copied TIFF metadata. Filenames themselves can be sensitive; review them before sharing.

Runs are deterministic in the same software environment. A library change can change PNG bytes even if pixels look identical; replay refuses the mismatch and asks you to use the recorded versions. The manifest is not a signed authenticity certificate. Do not trust a modified manifest just because its hashes match.

## Supported scope and failures

Rejected explicitly:

- RGB, palette, MINISWHITE, floating-point, signed, packed-bit, multichannel, multipage, Z/time stacks, pyramids/SubIFDs, or non-`YX` axes.
- Non-top-left TIFF orientation; this tool will not silently rotate a source.
- Source files over 256 MiB or images over 50 megapixels.
- Input/output overlap, existing output folders, TIFF symbolic links, case-insensitive or Unicode-normalized filename collisions, Windows-reserved and other non-portable filenames, and formula-like/control-character filenames unsafe for CSV.
- Unconfirmed/nonpositive calibration, invalid display ranges, crops outside any source, or bars/labels that do not fit.

Compressed TIFF support depends on the installed decoder. The minimal install does not include `imagecodecs`; unsupported compression fails with a decoding error. Export an uncompressed 2D TIFF from your acquisition tool if needed. Proprietary microscope formats are out of scope.

Processing is sequential and uses a full-file/decoded-image snapshot in memory. On a handled error, the newly created output directory is removed; existing files are never reused. A forced process termination or machine failure can leave an incomplete folder. `manifest.json` is written last as the completion marker; remove or rename an incomplete folder yourself before retrying. Do not modify inputs or the output folder while a run is active.

## Existing general image command

The original `ibp` / `image-batch-processor` CLI and Python API remain available for ordinary photos:

```bash
ibp photos -o resized --scale 0.5 --format png --quality 90
ibp photos -o wide --width 800 --height 600 --no-keep-aspect
ibp --help
```

These resize/rotate/watermark tools are **not the microscopy workflow** and do not provide its provenance/calibration safeguards. They now preflight the whole batch for filename collisions, existing destinations, overlapping input/output directories, and symbolic links before writing anything. Input files remain read-only, and output files are created exclusively, never replaced.

The naming rule stays `source_stem.selected_extension`. For example, converting both `sample.jpg` and `sample.png` to WebP would produce `sample.webp` twice, so the entire batch is rejected before output begins. Rename the source files or process them into separate output directories. Existing output folders are allowed only when every planned file is new; unrelated files are retained. There is no overwrite switch.

Name checks are deliberately conservative on all systems: case-insensitive and Unicode-normalized aliases, file-versus-directory conflicts, Windows reserved names, symbolic links, and Windows reparse points within traversed paths are rejected. Use separate, non-overlapping input/output folders. Source-root aliases are resolved for overlap checks; do not change directories or links while a run is active.

The Python batch API raises `BatchSafetyError` for preflight failures. A direct `process_file` call keeps its boolean API and returns `False` when a destination exists or processing fails; its explicitly supplied parent directory is resolved as the output root. Successful earlier files are retained if a later image cannot be decoded or encoded, with accurate success/failure counts. The CLI exits nonzero on preflight errors, empty batches, or any failed image, so scripts can detect incomplete work.

Encoding completes in memory before an output file is created. After a handled write error or keyboard interrupt, cleanup attempts to remove only the incomplete file whose ownership it can still verify; this cleanup is best effort. A forced termination or power failure can still leave a partial file; the next run refuses to overwrite it. The batch is not a filesystem transaction, and concurrent directory/link changes by another program are outside the safety contract. Keep backups. The legacy `--workers` argument is retained for compatibility, but processing is sequential. Width, height, and scale must be positive; a width or height of `0` is rejected rather than ignored. If `scale` is set, width and height are not used. One of width or height, without the other, still scales the remaining side proportionally. `--no-keep-aspect` applies only when both sides are set. Quality must be an integer from 1 to 100. Watermark text is white at the requested opacity, so it does not show on a white background. Grayscale-with-alpha PNG and CMYK JPEG files are converted to RGB when the chosen format cannot store that mode; modes the format can store are left as they are.

### Python compatibility

Version 0.2.0 raised the minimum from Python 3.8 to **Python 3.10** for the combined microscopy/general-image package and its dependencies. This is a breaking compatibility change, not just a documentation update. Use a separate Python 3.10+ virtual environment; do not replace a system Python installation. This file-safety repair does not raise the minimum again.

Python 3.8/3.9 support is not claimed or tested for this release. A future legacy-only maintenance line would need compatible dependency bounds and real tests on those interpreters before it could be offered. Installing an older commit is not a remedy for the overwrite defects. See [CHANGELOG.md](CHANGELOG.md) for migration details.

## Options

`ibp-micro export INPUT -o DIRECTORY`

| Option | Required | Meaning |
| --- | --- | --- |
| `--display-min`, `--display-max` | yes | Shared raw intensity window. `0 <= min < max <= 65535`, and `max` must fit every file's bit depth. |
| `--pixel-size-um` | yes | Micrometres per square pixel, typed by you. TIFF calibration tags are ignored. |
| `--scale-bar-um` | yes | Physical bar length. It must be an integer number of pixels (absolute tolerance 1e-8). |
| `--confirm-calibration` | yes | You checked that the same square-pixel size applies to every file. |
| `--crop X Y WIDTH HEIGHT` | no | Shared zero-based crop in original pixels. Every file must contain it. |
| `--synthetic-data` | no | Stamp `SYNTHETIC DEMO` and record that flag. |

`ibp-micro inspect INPUT` takes the same display, crop, pixel-size, scale-bar, and synthetic-data options. It does not take an output directory or `--confirm-calibration`.

`ibp-micro replay INPUT -o DIRECTORY --manifest FILE --confirm-calibration` repeats the recorded recipe and requires identical source and PNG SHA-256 hashes.

`ibp INPUT -o DIRECTORY` (alias `image-batch-processor`)

| Option | Default | Meaning |
| --- | --- | --- |
| `-o, --output` | `./output` | Directory of new files. Existing planned names are never replaced. |
| `-w, --width`, `-h, --height` | unset | Positive pixel sizes. `0` is invalid. |
| `-s, --scale` | unset | Positive factor, for example `0.5`. If set, width and height are ignored. |
| `--keep-aspect` / `--no-keep-aspect` | keep | Used when both width and height are set. One side alone always keeps aspect. |
| `-r, --rotate` | `0` | Clockwise degrees. |
| `--watermark-text` | unset | White text. Invisible on white images. |
| `--watermark-pos` | `bottom-right` | `center`, `top-left`, `top-right`, `bottom-left`, `bottom-right`. |
| `--watermark-opacity` | `0.5` | From 0 through 1. |
| `-f, --format` | source suffix | `jpeg`, `jpg`, `png`, `webp`, `bmp`, `tif`, `tiff`. |
| `-q, --quality` | `90` | Integer 1–100, applied to JPEG and WebP. |
| `-R, --recursive` | off | Include subfolders. |
| `-j, --workers` | `4` | Accepted for compatibility. Processing is sequential. |

## Development

```bash
python -m pip install -e ".[dev]"
python -m ruff check .
python -m pytest -q
python -m build
```

Tests use generated artificial arrays only. They cover exact intensity mapping, crop/bar geometry, original-file preservation, byte-identical replay, changed source/output hashes, invalid calibration, malformed TIFFs, unsupported dimensions/types, filename collisions, output protection, inspect previews, and legacy image operations. Legacy batch regressions also cover case/Unicode aliases, hard links, recursive file/directory conflicts, existing targets, exclusive-create races, interrupted writes, zero dimensions, incompatible pixel modes, and CLI exit codes. CI runs ruff and pytest on Python 3.10, 3.11, and 3.12 for Linux, Windows, and macOS; check the actual run before assuming a platform has passed.

See [CONTRIBUTING.md](CONTRIBUTING.md) for small, testable contributions and [the validation notes](docs/validation.md) for scope and reproducibility details.

## Related tools

This is not a claim of a new research method or a replacement for established microscopy tooling. [OMERO.figure](https://omero.figure.openmicroscopy.org/) offers figure preparation in the OMERO ecosystem; other batch workflows, including micrograph-batch, overlap with this area. Choose an established tool when you need richer formats, metadata handling, interactive figure layouts, or an existing laboratory workflow.

## License

[MIT](LICENSE). No real experimental images are included in this repository.

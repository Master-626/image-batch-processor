"""Conservative, local display exports. Never use these PNGs for quantification."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import platform
import shutil
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import PIL
from PIL import Image, ImageDraw, ImageFont
import tifffile

from . import __version__

SCHEMA = "ibp-microscopy-export-v1"
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_PIXELS = 50_000_000
FOOTER_HEIGHT = 56


class ExportError(ValueError):
    """Input cannot be represented safely by this deliberately narrow exporter."""


@dataclass(frozen=True)
class ExportSettings:
    display_min: float
    display_max: float
    pixel_size_um: float
    scale_bar_um: float
    crop: tuple[int, int, int, int] | None = None
    synthetic_data: bool = False

    def validate(self) -> None:
        values = (self.display_min, self.display_max, self.pixel_size_um, self.scale_bar_um)
        if any(type(v) not in (float, int) or not math.isfinite(v) for v in values):
            raise ExportError("Display range and calibration must be finite numbers.")
        if not 0 <= self.display_min < self.display_max <= 65535:
            raise ExportError("Require 0 <= display_min < display_max <= 65535.")
        if self.pixel_size_um <= 0 or self.scale_bar_um <= 0:
            raise ExportError("Pixel size and scale bar length must be positive.")
        pixels = self.scale_bar_um / self.pixel_size_um
        if not math.isfinite(pixels) or pixels < 1 or pixels > MAX_PIXELS:
            raise ExportError("Scale bar length is outside the supported pixel range.")
        if not math.isclose(pixels, round(pixels), rel_tol=0, abs_tol=1e-8):
            raise ExportError("Scale bar length must be an integer multiple of pixel size; no rounding is applied.")
        if type(self.synthetic_data) is not bool:
            raise ExportError("synthetic_data must be true or false.")
        if self.crop is not None:
            if not isinstance(self.crop, (tuple, list)) or len(self.crop) != 4:
                raise ExportError("Crop must be [x, y, width, height].")
            x, y, width, height = self.crop
            if any(type(v) is not int for v in self.crop) or min(x, y) < 0 or min(width, height) <= 0:
                raise ExportError("Crop needs nonnegative integer x/y and positive integer width/height.")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_tiff(path: Path) -> tuple[np.ndarray, str]:
    """Hash and decode the same read-only snapshot, without trusting calibration tags."""
    if path.is_symlink():
        raise ExportError(f"Symbolic links are not accepted: {path.name}")
    with path.open("rb") as handle:
        raw = handle.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise ExportError(f"{path.name}: file exceeds the 256 MiB limit.")
    try:
        with tifffile.TiffFile(io.BytesIO(raw)) as tif:
            if len(tif.pages) != 1 or len(tif.series) != 1:
                raise ExportError("Only one-page, one-series TIFFs are supported; export a 2D plane explicitly.")
            page, series = tif.pages[0], tif.series[0]
            if page.subifds:
                raise ExportError("Pyramidal TIFFs / SubIFDs are not supported.")
            if series.axes != "YX" or len(series.shape) != 2 or len(page.shape) != 2:
                raise ExportError(f"Only 2D YX images are supported, received axes={series.axes}, shape={series.shape}.")
            if page.samplesperpixel != 1 or page.photometric != tifffile.PHOTOMETRIC.MINISBLACK:
                raise ExportError("Only single-channel MINISBLACK grayscale TIFFs are supported.")
            dtype = np.dtype(page.dtype)
            if dtype.kind != "u" or dtype.itemsize not in (1, 2):
                raise ExportError("Only unsigned 8-bit or 16-bit TIFFs are supported.")
            if page.bitspersample not in (8, 16):
                raise ExportError("Packed / non-8-or-16-bit samples are not supported.")
            orientation = page.tags.get("Orientation")
            if orientation is not None and orientation.value != 1:
                raise ExportError("Only top-left TIFF orientation is supported; normalize explicitly first.")
            if math.prod(page.shape) > MAX_PIXELS or min(page.shape) < 1:
                raise ExportError("Image exceeds the 50 megapixel limit or has an empty dimension.")
            array = page.asarray()
    except ExportError as exc:
        raise ExportError(f"{path.name}: {exc}") from exc
    except Exception as exc:
        raise ExportError(f"{path.name}: cannot decode supported TIFF ({exc}).") from exc
    return array, sha256(raw)


def render(array: np.ndarray, settings: ExportSettings) -> tuple[Image.Image, dict]:
    """Linear mapping only: clip, scale to uint8, round half up. No resampling."""
    height, width = array.shape
    crop = settings.crop or (0, 0, width, height)
    x, y, crop_width, crop_height = crop
    if x + crop_width > width or y + crop_height > height:
        raise ExportError(f"Crop {crop} exceeds source dimensions {width}x{height}.")
    if settings.display_max > np.iinfo(array.dtype).max:
        raise ExportError("Display maximum exceeds this source's bit-depth range; do not mix 8/16-bit batches.")
    plane = array[y:y + crop_height, x:x + crop_width]
    pixels = round(settings.scale_bar_um / settings.pixel_size_um)
    label = f"{settings.scale_bar_um:.12g} um"
    # Fixed built-in bitmap font, never an OS-dependent Arial/font lookup.
    font = ImageFont.load_default_imagefont()
    bbox = font.getbbox(label)
    label_width = bbox[2] - bbox[0]
    synthetic_label = "SYNTHETIC DEMO" if settings.synthetic_data else None
    required_width = max(pixels, label_width, 84 if synthetic_label else 0) + 24
    if crop_width < required_width:
        raise ExportError(f"Crop width must be at least {required_width}px to fit the scale bar and label.")
    scaled = (plane.astype(np.float64) - settings.display_min) / (settings.display_max - settings.display_min)
    display = np.floor(np.clip(scaled, 0, 1) * 255 + 0.5).astype(np.uint8)
    result = Image.new("L", (crop_width, crop_height + FOOTER_HEIGHT), color=0)
    result.paste(Image.fromarray(display), (0, 0))
    draw = ImageDraw.Draw(result)
    left = (crop_width - pixels) // 2
    top = crop_height + 8
    # Rectangle coordinates are inclusive: exactly `pixels` white pixels wide.
    draw.rectangle((left, top, left + pixels - 1, top + 3), fill=255)
    draw.text(((crop_width - label_width) // 2, top + 8), label, font=font, fill=255)
    if synthetic_label:
        draw.text(((crop_width - 84) // 2, top + 26), synthetic_label, font=font, fill=255)
    metadata = {
        "source_width": width, "source_height": height,
        "source_bit_depth": array.dtype.itemsize * 8,
        "source_axes": "YX", "source_photometric": "MINISBLACK",
        "crop_xywh": list(crop), "image_width": crop_width, "image_height": crop_height,
        "footer_height": FOOTER_HEIGHT,
        "output_width": result.width, "output_height": result.height,
        "scale_bar_pixels": pixels, "scale_bar_label": label,
        "scale_bar_xywh": [left, top, pixels, 4],
        "clipped_low_pixels": int(np.count_nonzero(plane < settings.display_min)),
        "clipped_high_pixels": int(np.count_nonzero(plane > settings.display_max)),
        "image_pixel_sha256": sha256(display.tobytes()),
    }
    return result, metadata


def _inputs(input_dir: Path, output_dir: Path) -> tuple[Path, Path, list[Path]]:
    if input_dir.is_symlink():
        raise ExportError("Input directory may not be a symbolic link.")
    root, output = input_dir.resolve(), output_dir.resolve()
    if not root.is_dir():
        raise ExportError("Input must be an existing directory.")
    if output == root or root in output.parents or output in root.parents:
        raise ExportError("Input and output must be separate, non-overlapping directories.")
    if output_dir.exists() or output_dir.is_symlink():
        raise ExportError("Output already exists. Choose a new directory; overwriting is never allowed.")
    if not output.parent.is_dir():
        raise ExportError("Output parent must already exist.")
    files = sorted((p for p in root.iterdir() if p.suffix.lower() in (".tif", ".tiff")), key=lambda p: p.name)
    if not files:
        raise ExportError("No .tif / .tiff files found in the input directory (non-recursive).")
    if any(not p.is_file() or p.is_symlink() for p in files):
        raise ExportError("Every TIFF entry must be a regular file, not a directory or symbolic link.")
    if len({p.name.casefold() for p in files}) != len(files):
        raise ExportError("TIFF names collide on case-insensitive filesystems.")
    if any(any(ord(c) < 32 or ord(c) == 127 for c in p.name) or p.name.lstrip()[0] in "=+-@" for p in files):
        raise ExportError("Rename TIFFs with control characters or spreadsheet formula prefixes.")
    return root, output, files


def export_batch(input_dir: str | Path, output_dir: str | Path, settings: ExportSettings,
                 *, confirm_calibration: bool = False, expected: dict | None = None) -> dict:
    """Create a new output directory; roll back files this call creates on failure.

    Confirmation means the caller verified isotropic micrometres per pixel for
    every image. This code cannot validate a microscope or acquisition workflow.
    """
    if confirm_calibration is not True:
        raise ExportError("Confirm the same square-pixel calibration for every input with --confirm-calibration.")
    settings.validate()
    _, output, files = _inputs(Path(input_dir), Path(output_dir))
    if expected is not None and set(expected) != {p.name for p in files}:
        raise ExportError("Replay input names differ from the manifest; use the same TIFF batch.")
    manifest = {
        "schema": SCHEMA,
        "software": {"image_batch_processor": __version__, "python": platform.python_version(),
                     "numpy": np.__version__, "pillow": PIL.__version__, "tifffile": tifffile.__version__,
                     "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION},
        "settings": asdict(settings),
        "calibration": {"confirmed_by_user": True, "square_pixels": True,
                        "source": "user-supplied; TIFF calibration metadata not applied"},
        "rendering": "linear clip/scale; round half up to uint8; no resampling; annotation footer",
        "purpose": "display only; not quantitative analysis or validated scientific/clinical software",
        "files": [],
    }
    # mkdir is exclusive, so an existing output is never replaced, including races.
    output.mkdir()
    try:
        for source in files:
            array, source_hash = read_tiff(source)
            if expected is not None and source_hash != expected[source.name]["source_sha256"]:
                raise ExportError(f"{source.name}: source hash differs from the replay manifest.")
            image, record = render(array, settings)
            png_name = source.name + ".png"
            with (output / png_name).open("xb") as handle:
                image.save(handle, format="PNG", optimize=False, compress_level=9)
            png_hash = sha256((output / png_name).read_bytes())
            record.update({"source": source.name, "source_sha256": source_hash,
                           "output": png_name, "output_sha256": png_hash})
            if expected is not None and png_hash != expected[source.name]["output_sha256"]:
                raise ExportError(f"{source.name}: replay PNG hash differs; use the recorded software versions.")
            manifest["files"].append(record)
        fields = ["source", "source_sha256", "output", "output_sha256", "source_bit_depth",
                  "source_width", "source_height", "crop_xywh", "display_min", "display_max",
                  "pixel_size_um", "scale_bar_um", "scale_bar_pixels", "synthetic_data",
                  "clipped_low_pixels", "clipped_high_pixels", "image_pixel_sha256"]
        with (output / "manifest.csv").open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            for record in manifest["files"]:
                row = {**record, **asdict(settings)}
                row["crop_xywh"] = json.dumps(row["crop_xywh"], separators=(",", ":"))
                writer.writerow({k: row[k] for k in fields})
        # Completion marker is written last. No timestamp or absolute personal paths.
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except BaseException:
        shutil.rmtree(output)
        raise
    return manifest


def replay_batch(input_dir: str | Path, output_dir: str | Path, manifest_path: str | Path,
                 *, confirm_calibration: bool = False) -> dict:
    """Validate a recipe and require identical source and exported PNG hashes."""
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        if manifest["schema"] != SCHEMA:
            raise ExportError("Unsupported manifest schema.")
        settings = ExportSettings(**manifest["settings"])
        expected = {}
        for record in manifest["files"]:
            name = record["source"]
            if not isinstance(name, str) or name in expected or "/" in name or "\\" in name or name in (".", ".."):
                raise ExportError("Invalid or duplicated source filename in manifest.")
            for field in ("source_sha256", "output_sha256"):
                value = record[field]
                if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                    raise ExportError("Invalid SHA-256 in manifest.")
            expected[name] = record
    except (KeyError, TypeError, ValueError) as exc:
        raise ExportError(f"Invalid replay manifest: {exc}") from exc
    return export_batch(input_dir, output_dir, settings, confirm_calibration=confirm_calibration, expected=expected)

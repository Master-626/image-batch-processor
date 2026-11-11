from pathlib import Path

import pytest
from PIL import Image

from image_batch_processor.core import BatchProcessor, BatchSafetyError, ProcessOptions
from image_batch_processor.operations import convert_image_format, resize_image


@pytest.fixture
def sample_images_dir(tmp_path: Path):
    """Create a directory with sample test images."""
    img_dir = tmp_path / "input"
    img_dir.mkdir()

    for i in range(3):
        img = Image.new("RGB", (800, 600), color=(i * 50, 100, 200))
        img.save(img_dir / f"test_{i}.jpg")

    return img_dir


def test_resize_batch(sample_images_dir, tmp_path):
    """Test batch resizing."""
    output_dir = tmp_path / "output"
    options = ProcessOptions(scale=0.5)
    processor = BatchProcessor(options=options, workers=2)

    results = processor.process_directory(
        input_dir=str(sample_images_dir),
        output_dir=str(output_dir),
    )

    assert results["total"] == 3
    assert results["success"] == 3
    assert len(list(output_dir.glob("*.jpg"))) == 3


def test_format_conversion(sample_images_dir, tmp_path):
    """Test batch format conversion to WebP."""
    output_dir = tmp_path / "output_webp"
    options = ProcessOptions(output_format="webp", quality=85)
    processor = BatchProcessor(options=options, workers=2)

    results = processor.process_directory(
        input_dir=str(sample_images_dir),
        output_dir=str(output_dir),
    )

    assert results["success"] == 3
    assert len(list(output_dir.glob("*.webp"))) == 3


def test_watermark(sample_images_dir, tmp_path):
    """Test batch watermarking."""
    output_dir = tmp_path / "output_wm"
    options = ProcessOptions(
        watermark_text="Test Watermark",
        watermark_pos="center",
        watermark_opacity=0.5,
    )
    processor = BatchProcessor(options=options, workers=2)

    results = processor.process_directory(
        input_dir=str(sample_images_dir),
        output_dir=str(output_dir),
    )

    assert results["success"] == 3


def test_resize_geometry_and_scale_precedence():
    """Valid sizes stay exact. Scale still wins when width and height are also set."""
    image = Image.new("RGB", (40, 20), "red")
    assert resize_image(image, target_width=10, target_height=10, keep_aspect=False).size == (10, 10)
    assert resize_image(image, target_width=10, target_height=10, keep_aspect=True).size == (10, 5)
    assert resize_image(image, target_width=20).size == (20, 10)
    assert resize_image(image, target_height=10).size == (20, 10)
    assert resize_image(image, scale=0.5).size == (20, 10)
    assert resize_image(image, target_width=4, target_height=4, scale=0.5).size == (20, 10)
    assert resize_image(image).size == (40, 20)


@pytest.mark.parametrize("kwargs", [
    {"target_width": 0},
    {"target_height": 0},
    {"target_width": 0, "target_height": 10},
    {"target_width": -5, "target_height": 10},
    {"target_width": True},
    {"scale": 0},
    {"scale": -1},
    {"scale": float("nan")},
])
def test_resize_rejects_non_positive_dimensions(kwargs):
    image = Image.new("RGB", (40, 20), "red")
    with pytest.raises(ValueError):
        resize_image(image, **kwargs)


def test_tiny_scale_does_not_request_a_zero_image():
    image = Image.new("RGB", (10, 10), "red")
    with pytest.raises(ValueError, match="non-positive"):
        resize_image(image, scale=0.01)


def test_zero_width_is_not_silently_ignored(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    Image.new("RGB", (40, 20), "blue").save(source / "a.png")
    output = tmp_path / "output"
    with pytest.raises(BatchSafetyError, match="width"):
        BatchProcessor(ProcessOptions(width=0, height=10)).process_directory(source, output)
    assert not output.exists()
    assert not BatchProcessor(ProcessOptions(width=0)).process_file(source / "a.png", tmp_path / "one.png")
    assert not (tmp_path / "one.png").exists()


@pytest.mark.parametrize("options", [
    ProcessOptions(scale=0),
    ProcessOptions(scale=float("inf")),
    ProcessOptions(quality=0),
    ProcessOptions(quality=101),
    ProcessOptions(watermark_opacity=1.5),
    ProcessOptions(watermark_opacity=-0.1),
])
def test_invalid_batch_options_fail_before_writing(tmp_path, options):
    source = tmp_path / "input"
    source.mkdir()
    Image.new("RGB", (16, 16), "red").save(source / "a.png")
    output = tmp_path / "output"
    with pytest.raises(BatchSafetyError):
        BatchProcessor(options).process_directory(source, output)
    assert not output.exists()


def test_incompatible_modes_convert_without_rewriting_supported_ones(tmp_path):
    la = Image.new("LA", (8, 8), (40, 128))
    converted, fmt = convert_image_format(la, "jpeg")
    assert fmt == "JPEG" and converted.mode == "RGB"
    assert converted.getpixel((0, 0)) == (40, 40, 40)
    kept, fmt = convert_image_format(la, "png")
    assert fmt == "PNG" and kept.mode == "LA" and kept.getpixel((0, 0)) == (40, 128)
    rgba = Image.new("RGBA", (4, 4), (10, 20, 30, 40))
    jpeg, _ = convert_image_format(rgba, "jpeg")
    assert jpeg.mode == "RGB"
    assert jpeg.getpixel((0, 0)) == rgba.convert("RGB").getpixel((0, 0))
    assert convert_image_format(Image.new("1", (8, 8), 1), "jpeg")[0].mode == "1"
    cmyk = Image.new("CMYK", (4, 4), (10, 20, 30, 40))
    png, fmt = convert_image_format(cmyk, "png")
    assert fmt == "PNG" and png.mode == "RGB"
    assert png.getpixel((0, 0)) == cmyk.convert("RGB").getpixel((0, 0))

    gray = tmp_path / "gray"
    ink = tmp_path / "ink"
    gray.mkdir()
    ink.mkdir()
    la.save(gray / "gray.png")
    Image.new("CMYK", (8, 8), (0, 0, 0, 0)).save(ink / "ink.jpg", quality=95)
    jpeg_out, png_out = tmp_path / "jpeg", tmp_path / "png"
    assert BatchProcessor(ProcessOptions(output_format="jpeg")).process_directory(gray, jpeg_out)["success"] == 1
    assert BatchProcessor(ProcessOptions(output_format="png")).process_directory(ink, png_out)["success"] == 1
    with Image.open(next(jpeg_out.iterdir())) as saved:
        assert saved.format == "JPEG"
    with Image.open(next(png_out.iterdir())) as saved:
        assert saved.format == "PNG" and saved.mode == "RGB"

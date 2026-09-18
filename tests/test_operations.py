import pytest
from pathlib import Path
from PIL import Image
from image_batch_processor.core import BatchProcessor, ProcessOptions


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

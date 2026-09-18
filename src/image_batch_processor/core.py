"""
Core batch processing controller.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from PIL import Image

from .operations import resize_image, rotate_image, apply_text_watermark, convert_image_format


@dataclass
class ProcessOptions:
    """Options for batch image processing."""
    width: Optional[int] = None
    height: Optional[int] = None
    scale: Optional[float] = None
    keep_aspect: bool = True
    rotate_angle: float = 0
    watermark_text: Optional[str] = None
    watermark_pos: str = "bottom-right"
    watermark_opacity: float = 0.5
    output_format: Optional[str] = None
    quality: int = 90


class BatchProcessor:
    """Batch image processor with concurrent support."""

    SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}

    def __init__(self, options: ProcessOptions, workers: int = 4):
        self.options = options
        self.workers = workers

    def process_file(self, input_path: Path, output_path: Path) -> bool:
        """Process a single image file."""
        try:
            with Image.open(input_path) as img:
                # Resize
                if self.options.scale or self.options.width or self.options.height:
                    img = resize_image(
                        img,
                        target_width=self.options.width,
                        target_height=self.options.height,
                        scale=self.options.scale,
                        keep_aspect=self.options.keep_aspect,
                    )

                # Rotate
                if self.options.rotate_angle != 0:
                    img = rotate_image(img, self.options.rotate_angle)

                # Watermark
                if self.options.watermark_text:
                    img = apply_text_watermark(
                        img,
                        text=self.options.watermark_text,
                        position=self.options.watermark_pos,
                        opacity=self.options.watermark_opacity,
                    )

                # Format conversion
                if self.options.output_format:
                    img, save_format = convert_image_format(
                        img,
                        output_format=self.options.output_format,
                        quality=self.options.quality,
                    )
                else:
                    save_format = input_path.suffix[1:].upper()

                # Save
                output_path.parent.mkdir(parents=True, exist_ok=True)
                save_kwargs = {}
                if save_format == "JPEG":
                    save_kwargs["quality"] = self.options.quality
                elif save_format == "WEBP":
                    save_kwargs["quality"] = self.options.quality

                img.save(output_path, format=save_format, **save_kwargs)
                return True

        except Exception as e:
            print(f"Error processing {input_path}: {e}")
            return False

    def process_directory(self, input_dir: str, output_dir: str, recursive: bool = False) -> dict:
        """Process all images in a directory."""
        input_path = Path(input_dir)
        output_path = Path(output_dir)

        # Find all image files
        pattern = "**/*" if recursive else "*"
        image_files = [
            f for f in input_path.glob(pattern)
            if f.is_file() and f.suffix.lower() in self.SUPPORTED_EXTENSIONS
        ]

        results = {"total": len(image_files), "success": 0, "failed": 0}

        for img_file in image_files:
            # Calculate relative path for output
            rel_path = img_file.relative_to(input_path)

            # Change extension if format conversion
            if self.options.output_format:
                new_ext = f".{self.options.output_format}"
                output_file = output_path / rel_path.with_suffix(new_ext)
            else:
                output_file = output_path / rel_path

            if self.process_file(img_file, output_file):
                results["success"] += 1
            else:
                results["failed"] += 1

        return results

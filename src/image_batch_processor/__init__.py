"""
image-batch-processor

Local microscopy display exports and general batch image tools.
"""

from .core import BatchProcessor, ProcessOptions
from .operations import (
    resize_image,
    rotate_image,
    apply_text_watermark,
    convert_image_format,
)

__version__ = "0.2.0"
__all__ = [
    "BatchProcessor",
    "ProcessOptions",
    "resize_image",
    "rotate_image",
    "apply_text_watermark",
    "convert_image_format",
]

"""
image-batch-processor

A powerful, robust batch image processing toolkit.
"""

from .core import BatchProcessor, ProcessOptions
from .operations import (
    resize_image,
    rotate_image,
    apply_text_watermark,
    convert_image_format,
)

__version__ = "0.1.0"
__all__ = [
    "BatchProcessor",
    "ProcessOptions",
    "resize_image",
    "rotate_image",
    "apply_text_watermark",
    "convert_image_format",
]

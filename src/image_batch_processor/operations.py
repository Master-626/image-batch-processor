"""
Image manipulation operations implemented via Pillow.
"""

import math
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

# Modes Pillow can encode for each format. Anything else is converted to RGB
# before saving. Modes listed here are left unchanged so successful conversions
# keep their previous pixels (for example RGBA PNG stays RGBA; LA JPEG cannot).
_ENCODABLE_MODES = {
    "JPEG": {"1", "L", "RGB", "CMYK", "YCbCr"},
    "PNG": {"1", "L", "LA", "P", "RGB", "RGBA"},
    "WebP": None,
    "BMP": {"1", "L", "P", "RGB", "RGBA"},
    "TIFF": {"1", "L", "LA", "P", "PA", "RGB", "RGBA", "CMYK", "YCbCr", "LAB", "I", "F"},
}


def _positive_int(name: str, value: Optional[int]) -> Optional[int]:
    """Reject 0 and negatives. They used to be treated as 'not provided'."""
    if value is None:
        return None
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer, got {value!r}.")
    return value


def resize_image(
    image: Image.Image,
    target_width: Optional[int] = None,
    target_height: Optional[int] = None,
    scale: Optional[float] = None,
    keep_aspect: bool = True,
) -> Image.Image:
    """Resize an image to target dimensions or scale factor.

    When ``scale`` is set it wins over width and height. A single width or
    height always scales the other side proportionally; ``keep_aspect`` applies
    only when both sides are set. Zero is not a way to omit a side.
    """
    orig_width, orig_height = image.size

    if scale is not None:
        if isinstance(scale, bool) or not isinstance(scale, (int, float)) or not math.isfinite(scale) or scale <= 0:
            raise ValueError(f"scale must be a positive finite number, got {scale!r}.")
        new_width = int(orig_width * scale)
        new_height = int(orig_height * scale)
    else:
        target_width = _positive_int("target_width", target_width)
        target_height = _positive_int("target_height", target_height)
        if target_width is not None and target_height is not None:
            if keep_aspect:
                ratio = min(target_width / orig_width, target_height / orig_height)
                new_width = int(orig_width * ratio)
                new_height = int(orig_height * ratio)
            else:
                new_width = target_width
                new_height = target_height
        elif target_width is not None:
            ratio = target_width / orig_width
            new_width = target_width
            new_height = int(orig_height * ratio)
        elif target_height is not None:
            ratio = target_height / orig_height
            new_height = target_height
            new_width = int(orig_width * ratio)
        else:
            return image

    if new_width < 1 or new_height < 1:
        raise ValueError(f"Resize would produce a non-positive image size {new_width}x{new_height}.")
    return image.resize((new_width, new_height), Image.Resampling.LANCZOS)


def rotate_image(image: Image.Image, angle: float) -> Image.Image:
    """Rotate an image by angle degrees clockwise."""
    return image.rotate(-angle, expand=True)


def apply_text_watermark(
    image: Image.Image,
    text: str,
    position: str = "bottom-right",
    opacity: float = 0.5,
    font_size: int = 36,
) -> Image.Image:
    """Apply a text watermark to an image."""
    # Create a transparent overlay
    overlay = Image.new("RGBA", image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()

    # Get text size
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Calculate position
    margin = 20
    positions = {
        "center": ((image.width - text_width) // 2, (image.height - text_height) // 2),
        "top-left": (margin, margin),
        "top-right": (image.width - text_width - margin, margin),
        "bottom-left": (margin, image.height - text_height - margin),
        "bottom-right": (image.width - text_width - margin, image.height - text_height - margin),
    }

    x, y = positions.get(position, positions["bottom-right"])

    # Draw text with opacity
    alpha = int(255 * opacity)
    draw.text((x, y), text, font=font, fill=(255, 255, 255, alpha))

    # Composite the overlay onto the original image
    result = Image.alpha_composite(image.convert("RGBA"), overlay)
    return result.convert(image.mode)


def convert_image_format(
    image: Image.Image,
    output_format: str,
    quality: int = 90,
) -> tuple[Image.Image, str]:
    """Convert image to specified format.

    ``quality`` is not applied here. The batch saver passes it to JPEG/WebP
    when it writes the encoded bytes. Modes the target format cannot store,
    such as LA to JPEG or CMYK to PNG, are converted to RGB. Modes the format
    can already store are returned unchanged.
    """
    format_map = {
        "jpeg": "JPEG",
        "jpg": "JPEG",
        "png": "PNG",
        "webp": "WebP",
        "bmp": "BMP",
        "tiff": "TIFF",
    }

    pil_format = format_map.get(output_format.lower(), output_format.upper())
    allowed = _ENCODABLE_MODES.get(pil_format)
    if allowed is not None and image.mode not in allowed:
        image = image.convert("RGB")

    return image, pil_format

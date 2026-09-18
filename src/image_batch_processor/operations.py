"""
Image manipulation operations implemented via Pillow.
"""

from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont


def resize_image(
    image: Image.Image,
    target_width: Optional[int] = None,
    target_height: Optional[int] = None,
    scale: Optional[float] = None,
    keep_aspect: bool = True,
) -> Image.Image:
    """Resize an image to target dimensions or scale factor."""
    orig_width, orig_height = image.size

    if scale is not None:
        new_width = int(orig_width * scale)
        new_height = int(orig_height * scale)
    elif target_width and target_height:
        if keep_aspect:
            ratio = min(target_width / orig_width, target_height / orig_height)
            new_width = int(orig_width * ratio)
            new_height = int(orig_height * ratio)
        else:
            new_width = target_width
            new_height = target_height
    elif target_width:
        ratio = target_width / orig_width
        new_width = target_width
        new_height = int(orig_height * ratio)
    elif target_height:
        ratio = target_height / orig_height
        new_height = target_height
        new_width = int(orig_width * ratio)
    else:
        return image

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
    except IOError:
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
) -> Tuple[Image.Image, str]:
    """Convert image to specified format."""
    format_map = {
        "jpeg": "JPEG",
        "jpg": "JPEG",
        "png": "PNG",
        "webp": "WebP",
        "bmp": "BMP",
        "tiff": "TIFF",
    }

    pil_format = format_map.get(output_format.lower(), output_format.upper())

    # JPEG doesn't support transparency
    if pil_format == "JPEG" and image.mode in ("RGBA", "P"):
        image = image.convert("RGB")

    return image, pil_format

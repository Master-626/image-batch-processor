# Image Batch Processor

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![Pillow](https://img.shields.io/badge/Pillow-10.0+-green.svg)](https://python-pillow.org/)

A powerful, robust batch image processing toolkit. Resize, rotate, watermark, and convert image formats in bulk from the command line.

## 🌟 Features

- 📐 **Batch Resize** - Resize images by scale factor or target dimensions, with aspect ratio preservation
- 🔄 **Batch Rotate** - Rotate all images by specified angle
- 💧 **Text Watermark** - Add custom text watermarks with adjustable position and opacity
- 🔄 **Format Conversion** - Convert between JPEG, PNG, WebP, BMP, TIFF with quality control
- ⚡ **Concurrent Processing** - Multi-worker support for faster batch operations
- 🐍 **Python API** - Use as a library in your own code

## 📦 Installation

```bash
git clone https://github.com/Master-626/image-batch-processor.git
cd image-batch-processor
pip install .
```

## 🚀 Quick Start (CLI)

After installation, use `ibp` or `image-batch-processor` command:

### 1. Batch Resize
```bash
# Scale all images to 50% size
ibp input_dir -o output_dir --scale 0.5

# Fit within 1920x1080 bounds (keep aspect ratio)
ibp input_dir -o output_dir --width 1920 --height 1080 --keep-aspect
```

### 2. Batch Format Conversion
```bash
# Convert all PNG/BMP to WebP format with quality 85
ibp input_dir -o output_dir --format webp --quality 85
```

### 3. Batch Rotate
```bash
# Rotate all images 90 degrees clockwise
ibp input_dir -o output_dir --rotate 90
```

### 4. Batch Watermark
```bash
# Add copyright watermark at bottom-right
ibp input_dir -o output_dir --watermark-text "© 2026 MyStudio" --watermark-pos bottom-right --watermark-opacity 0.6
```

### 5. Chain Multiple Operations
```bash
ibp ./raw_photos -o ./ready_photos \
    --scale 0.75 \
    --watermark-text "Sample Watermark" \
    --watermark-pos center \
    --watermark-opacity 0.4 \
    --format jpeg \
    --quality 90 \
    --workers 4
```

## 🐍 Python API

```python
from image_batch_processor import BatchProcessor, ProcessOptions

# Configure options
options = ProcessOptions(
    scale=0.5,
    rotate_angle=90,
    watermark_text="Confidential",
    watermark_pos="bottom-right",
    watermark_opacity=0.5,
    output_format="webp",
    quality=85,
)

# Process directory
processor = BatchProcessor(options=options, workers=4)
results = processor.process_directory(
    input_dir="./images",
    output_dir="./processed_images",
    recursive=True
)

print(f"Done! Success: {results['success']}, Failed: {results['failed']}")
```

## 🛠️ CLI Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| input_dir | (positional) | required | Input image directory |
| --output | -o | ./output | Output directory |
| --width | -w | None | Target width (px) |
| --height | -h | None | Target height (px) |
| --scale | -s | None | Scale factor (0.5 = half) |
| --keep-aspect | | True | Preserve aspect ratio |
| --rotate | -r | 0 | Rotation angle (clockwise) |
| --watermark-text | | None | Watermark text |
| --watermark-pos | | bottom-right | Watermark position |
| --watermark-opacity | | 0.5 | Watermark opacity (0.0-1.0) |
| --format | -f | None | Output format (jpeg/png/webp) |
| --quality | -q | 90 | Output quality (1-100) |
| --recursive | -R | False | Process subdirectories |
| --workers | -j | 4 | Number of worker processes |

## 🧪 Testing

```bash
pip install -e ".[dev]"
pytest
```

## 📄 License

MIT License

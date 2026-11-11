"""
CLI interface for image-batch-processor.
"""

from pathlib import Path

import click

from .core import BatchProcessor, BatchSafetyError, ProcessOptions


@click.command()
@click.argument("input_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("-o", "--output", "output_dir", default="./output", type=click.Path(file_okay=False, path_type=Path), help="Output directory")
@click.option("-w", "--width", type=click.IntRange(min=1), default=None, help="Target width in pixels")
@click.option("-h", "--height", type=click.IntRange(min=1), default=None, help="Target height in pixels")
@click.option("-s", "--scale", type=click.FloatRange(min=0, min_open=True), default=None, help="Scale factor (for example 0.5). Wins over width and height.")
@click.option("--keep-aspect/--no-keep-aspect", default=True, help="Keep aspect ratio")
@click.option("-r", "--rotate", "rotate_angle", type=float, default=0, help="Rotation angle (clockwise)")
@click.option("--watermark-text", default=None, help="Watermark text")
@click.option("--watermark-pos", default="bottom-right", type=click.Choice(["center", "top-left", "top-right", "bottom-left", "bottom-right"]), help="Watermark position")
@click.option("--watermark-opacity", type=click.FloatRange(0, 1), default=0.5, help="Watermark opacity (0.0-1.0). Text is white.")
@click.option("-f", "--format", "output_format", default=None, help="Output format (jpeg, png, webp, bmp, tiff)")
@click.option("-q", "--quality", type=click.IntRange(1, 100), default=90, help="JPEG/WebP quality (1-100)")
@click.option("-R", "--recursive", is_flag=True, help="Recursively process subdirectories")
@click.option("-j", "--workers", type=int, default=4, help="Legacy option; processing is currently sequential")
def main(input_dir, output_dir, width, height, scale, keep_aspect, rotate_angle,
         watermark_text, watermark_pos, watermark_opacity, output_format,
         quality, recursive, workers):
    """Image Batch Processor - Batch process images: resize, rotate, watermark, convert format."""

    options = ProcessOptions(
        width=width,
        height=height,
        scale=scale,
        keep_aspect=keep_aspect,
        rotate_angle=rotate_angle,
        watermark_text=watermark_text,
        watermark_pos=watermark_pos,
        watermark_opacity=watermark_opacity,
        output_format=output_format,
        quality=quality,
    )

    click.echo("🖼️  Image Batch Processor")
    click.echo(f"📁 Input:  {input_dir.resolve()}")
    click.echo(f"📂 Output: {output_dir.resolve()}")
    click.echo("")

    processor = BatchProcessor(options=options, workers=workers)
    try:
        results = processor.process_directory(
            input_dir=str(input_dir),
            output_dir=str(output_dir),
            recursive=recursive,
        )
    except (BatchSafetyError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Total: {results['total']}, Success: {results['success']}, Failed: {results['failed']}")
    if results["failed"]:
        raise click.ClickException("One or more images failed; successful outputs were kept.")


if __name__ == "__main__":
    main()

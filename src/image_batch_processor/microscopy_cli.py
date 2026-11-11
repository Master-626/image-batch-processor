"""Separate command so the legacy general-purpose `ibp` interface remains intact."""

from pathlib import Path

import click

from . import __version__
from .microscopy import ExportError, ExportSettings, export_batch, inspect_batch, replay_batch


@click.group()
@click.version_option(version=__version__)
def main():
    """Local, traceable 2D TIFF display exports. Not for quantitative analysis."""


@main.command("export")
@click.argument("input_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("-o", "--output", required=True, type=click.Path(path_type=Path), help="New, separate output directory.")
@click.option("--display-min", required=True, type=float, help="Common lower display limit in raw pixel units.")
@click.option("--display-max", required=True, type=float, help="Common upper display limit in raw pixel units.")
@click.option("--crop", nargs=4, type=int, default=None, metavar="X Y WIDTH HEIGHT", help="Common crop, zero-based; no resizing.")
@click.option("--pixel-size-um", required=True, type=float, help="Verified micrometres per square pixel for ALL images.")
@click.option("--scale-bar-um", required=True, type=float, help="Length must be an integer number of pixels.")
@click.option("--confirm-calibration", is_flag=True, help="I verified the same square-pixel calibration for every image.")
@click.option("--synthetic-data", is_flag=True, help="Label every export and the manifest as synthetic demo data.")
def export_command(input_dir, output, **kwargs):
    """Export flat-directory unsigned 8/16-bit, single-channel TIFFs to PNG."""
    confirmed = kwargs.pop("confirm_calibration")
    try:
        result = export_batch(input_dir, output, ExportSettings(**kwargs), confirm_calibration=confirmed)
    except (ExportError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Exported {len(result['files'])} display PNG(s) to {output} with JSON/CSV manifests.")
    click.echo("Originals are unchanged. These 8-bit PNGs are for display, not measurements.")


@main.command("inspect")
@click.argument("input_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--display-min", required=True, type=float, help="Common lower display limit in raw pixel units.")
@click.option("--display-max", required=True, type=float, help="Common upper display limit in raw pixel units.")
@click.option("--crop", nargs=4, type=int, default=None, metavar="X Y WIDTH HEIGHT", help="Common crop, zero-based; no resizing.")
@click.option("--pixel-size-um", required=True, type=float, help="Micrometres per square pixel to check. This does not verify it.")
@click.option("--scale-bar-um", required=True, type=float, help="Length must be an integer number of pixels.")
@click.option("--synthetic-data", is_flag=True, help="Require room for the synthetic-data label, as export would.")
def inspect_command(input_dir, **kwargs):
    """Check scale-bar fit, crop, and clipping without writing files."""
    try:
        report = inspect_batch(input_dir, ExportSettings(**kwargs))
    except (ExportError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc
    settings = report["settings"]
    click.echo(
        f"{report['file_count']} TIFF(s); scale bar {report['scale_bar_pixels']} px "
        f"({report['scale_bar_label']}); display {settings['display_min']:g}-{settings['display_max']:g}."
    )
    click.echo("No files written. Pixel size was not read from the TIFFs and is not confirmed.")
    for record in report["files"]:
        click.echo(
            f"{record['source']}: {record['source_width']}x{record['source_height']} "
            f"{record['source_bit_depth']}-bit, image {record['image_width']}x{record['image_height']}, "
            f"clipped low/high {record['clipped_low_pixels']}/{record['clipped_high_pixels']}"
        )


@main.command("replay")
@click.argument("input_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("-o", "--output", required=True, type=click.Path(path_type=Path))
@click.option("--manifest", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--confirm-calibration", is_flag=True, help="Reconfirm the recorded square-pixel calibration.")
def replay_command(input_dir, output, manifest, confirm_calibration):
    """Replay a JSON manifest, requiring identical inputs and exported PNG hashes."""
    try:
        result = replay_batch(input_dir, output, manifest, confirm_calibration=confirm_calibration)
    except (ExportError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Verified {len(result['files'])} source and PNG hash pairs. Exported to {output}.")


if __name__ == "__main__":
    main()

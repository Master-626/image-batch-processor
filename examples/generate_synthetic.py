"""Generate artificial spots, not experiment images. Does not contact any service."""

import argparse
from pathlib import Path

import numpy as np
import tifffile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New directory for synthetic 16-bit TIFFs")
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    y, x = np.mgrid[:192, :256]
    for i, amplitude in enumerate((18000, 36000), start=1):
        plane = 1500 + amplitude * np.exp(-((x - 110) ** 2 + (y - 80) ** 2) / 600)
        plane += 8000 * np.exp(-((x - 170) ** 2 + (y - 130) ** 2) / 180)
        image = np.floor(plane + 0.5).astype(np.uint16)
        tifffile.imwrite(args.output / f"SYNTHETIC_spots_{i}.tif", image, photometric="minisblack",
                         metadata={"axes": "YX", "description": "SYNTHETIC demonstration; not experimental data"})
    (args.output / "SYNTHETIC_DATA.txt").write_text(
        "Artificial Gaussian spots, not experimental data. Calibration in the README is fictional.\n",
        encoding="utf-8")
    print(f"Created 2 SYNTHETIC 16-bit TIFFs in {args.output}")


if __name__ == "__main__":
    main()

# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "Pillow>=10.0",
# ]
# ///
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageChops, ImageStat


def open_rgb(path: Path) -> Image.Image:
    if not path.is_file():
        raise SystemExit(f"ERROR: image not found: {path}")
    return Image.open(path).convert("RGB")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare two same-size UI screenshots and emit deterministic pixel metrics."
    )
    parser.add_argument("--reference", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--diff-out")
    parser.add_argument(
        "--tolerance",
        type=int,
        default=8,
        help="Per-channel delta threshold used for changed-pixel percentage (0-255).",
    )
    args = parser.parse_args()

    if not 0 <= args.tolerance <= 255:
        parser.error("--tolerance must be between 0 and 255")

    ref_path = Path(args.reference).expanduser().resolve()
    cand_path = Path(args.candidate).expanduser().resolve()
    ref = open_rgb(ref_path)
    cand = open_rgb(cand_path)

    if ref.size != cand.size:
        raise SystemExit(
            f"ERROR: viewport mismatch: reference={ref.size[0]}x{ref.size[1]} "
            f"candidate={cand.size[0]}x{cand.size[1]}"
        )

    diff = ImageChops.difference(ref, cand)
    stats = ImageStat.Stat(diff)
    mean_channels = stats.mean
    mae = sum(mean_channels) / len(mean_channels)
    extrema = diff.getextrema()
    max_delta = max(high for _low, high in extrema)

    px = diff.load()
    width, height = diff.size
    changed = 0
    total = width * height
    tol = args.tolerance
    for y in range(height):
        for x in range(width):
            r, g, b = px[x, y]
            if max(r, g, b) > tol:
                changed += 1

    changed_pct = (changed / total * 100.0) if total else 0.0

    print(f"viewport={width}x{height}")
    print(f"mae_0_255={mae:.4f}")
    print(f"max_channel_delta={max_delta}")
    print(f"changed_pixels_gt_{tol}={changed_pct:.4f}%")

    if args.diff_out:
        out = Path(args.diff_out).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        diff.save(out)
        print(f"diff_saved={out}")


if __name__ == "__main__":
    main()

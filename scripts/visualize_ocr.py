#!/usr/bin/env python3
"""Draw bounding boxes from OCR results onto the source image using Pillow."""

import argparse
import json
from pathlib import Path
import os

from PIL import Image, ImageDraw, ImageFont


def visualize_run(run_dir, output_dir=None):
    run_dir = Path(run_dir)
    results_path = run_dir / "results.json"
    if not results_path.exists():
        raise FileNotFoundError(f"No results.json found in {run_dir}")

    with open(results_path) as f:
        results = json.load(f)

    if output_dir is None:
        output_dir = run_dir / "visualized"
    try:
        os.mkdir(output_dir)
    except:
        print(f"{output_dir} already exists")
    #.mkdir(parents=True, exist_ok=True)

    seen_images = set()
    for res in results:
        image_path = res.get("image_path")
        if not image_path:
            continue

        extracted = res.get("response", {}).get("extracted")
        if not extracted or not isinstance(extracted, list):
            continue

        # Avoid drawing the same image multiple times
        if image_path in seen_images:
            continue
        seen_images.add(image_path)

        img = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(img)

        # Try to load a font, fall back to default if not available
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        except (OSError, IOError):
            font = ImageFont.load_default()

        for item in extracted:
            pos = item.get("pos")
            if not pos or len(pos) != 4:
                continue
            x, y, w, h = pos

            # Draw rectangle
            draw.rectangle([x, y, x + w, y + h], outline="red", width=3)

            # Draw text label
            label = item.get("orig", "")
            if label:
                draw.text((x, max(0, y - 20)), label, fill="red", font=font)

        out_path = output_dir / f"{Path(image_path).stem}_boxes.png"
        img.save(out_path)
        print(f"Saved {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Visualize OCR bounding boxes")
    parser.add_argument("run_dir", help="Path to the run directory containing results.json")
    parser.add_argument("--output", "-o", help="Output directory (default: <run_dir>/visualized)")
    args = parser.parse_args()
    visualize_run(args.run_dir, args.output)


if __name__ == "__main__":
    main()

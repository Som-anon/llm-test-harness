#!/usr/bin/env python3
"""
Draw bounding boxes from OCR results onto the source image.
Optionally whiteout the boxes and render orig/trans text inside.
"""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}

def find_image_path(obj):
    """Recursively search for a string that looks like an image path."""
    if isinstance(obj, dict):
        for key in ['image_path', 'image', 'image_file', 'file_path', 'filename', 'img_path']:
            if key in obj and isinstance(obj[key], str):
                if any(obj[key].lower().endswith(ext) for ext in IMAGE_EXTENSIONS):
                    return obj[key]
        for value in obj.values():
            result = find_image_path(value)
            if result:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = find_image_path(item)
            if result:
                return result
    elif isinstance(obj, str):
        if any(obj.lower().endswith(ext) for ext in IMAGE_EXTENSIONS):
            return obj
    return None

def extract_extracted(res):
    """Try to get 'extracted' list from various common locations."""
    response = res.get('response')
    if isinstance(response, dict):
        extracted = response.get('extracted')
        if extracted is not None:
            return extracted
    extracted = res.get('extracted')
    if extracted is not None:
        return extracted
    output = res.get('output')
    if isinstance(output, dict):
        extracted = output.get('extracted')
        if extracted is not None:
            return extracted
    return None

def get_text_size(draw, text, font):
    """Return width and height of text using textbbox or textsize."""
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        # Fallback for older Pillow
        return draw.textsize(text, font=font)

def visualize_run(run_dir, output_dir=None, debug=False, whiteout=False, text_field='orig', no_outline=False):
    run_dir = Path(run_dir).resolve()
    results_path = run_dir / "results.json"

    if not results_path.exists():
        print(f"ERROR: {results_path} not found.")
        return

    with open(results_path) as f:
        data = json.load(f)

    # Normalize to a list of results
    if isinstance(data, dict):
        for key in ['results', 'data', 'items']:
            if key in data and isinstance(data[key], list):
                results = data[key]
                break
        else:
            results = [data]
    else:
        results = data if isinstance(data, list) else [data]

    if not results:
        print("WARNING: No results found.")
        return

    if output_dir is None:
        output_dir = run_dir / "visualized"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Total results: {len(results)}")
    if debug:
        print("First result keys:", list(results[0].keys()) if isinstance(results[0], dict) else "Not a dict")

    saved = 0

    for idx, res in enumerate(results):
        if not isinstance(res, dict):
            print(f"  Skipping result #{idx}: not a dict")
            continue

        # Find image path
        image_path = find_image_path(res)
        if not image_path:
            print(f"  Skipping result #{idx}: no image path found")
            if debug:
                print(f"    Available keys: {list(res.keys())}")
                print(f"    Full result (first 300 chars): {str(res)[:300]}")
            continue

        # Resolve path
        img_abs = Path(image_path)
        if not img_abs.is_absolute():
            candidate = run_dir / image_path
            if candidate.exists():
                img_abs = candidate
        if not img_abs.exists():
            print(f"  Skipping: image file not found: {img_abs}")
            continue

        if debug:
            print(f"  Image path resolved: {img_abs}")

        # Extract extracted data
        extracted = extract_extracted(res)
        if extracted is None:
            print(f"  Skipping: no 'extracted' data found")
            continue

        if not isinstance(extracted, list) or len(extracted) == 0:
            print(f"  Skipping: 'extracted' is not a non-empty list")
            continue

        # Filter valid boxes
        valid_boxes = []
        for item in extracted:
            pos = item.get('pos')
            if pos and isinstance(pos, list) and len(pos) == 4:
                try:
                    x, y, w, h = map(int, pos)
                    text = item.get(text_field, '')
                    valid_boxes.append((x, y, w, h, text))
                except (ValueError, TypeError):
                    continue

        if not valid_boxes:
            print(f"  Skipping: no valid bounding boxes after filtering")
            continue

        # Open image
        try:
            img = Image.open(img_abs).convert('RGB')
        except Exception as e:
            print(f"  Error opening image: {e}")
            continue

        draw = ImageDraw.Draw(img)

        # Load a font (try DejaVu, fallback to default)
        try:
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            font = ImageFont.truetype(font_path, 16)
        except:
            font = ImageFont.load_default()

        for (x, y, w, h, text) in valid_boxes:
            if whiteout:
                # Fill with white
                draw.rectangle([x, y, x + w, y + h], fill='white')
                # Draw the red outline unless disabled
                if not no_outline:
                    draw.rectangle([x, y, x + w, y + h], outline='red', width=2)

                # Draw text centered inside the box
                if text:
                    # Calculate a font size that fits the box with some padding
                    max_font_size = int(min(w, h) * 0.8)
                    # Start with a reasonable size and reduce if too wide
                    font_size = max(10, max_font_size)
                    # Try to load font at that size
                    try:
                        font = ImageFont.truetype(font_path, font_size)
                    except:
                        font = ImageFont.load_default()

                    # Check if text fits in width, if not, reduce font size
                    while font_size > 10:
                        tw, th = get_text_size(draw, text, font)
                        if tw <= w - 10 and th <= h - 10:
                            break
                        font_size -= 2
                        try:
                            font = ImageFont.truetype(font_path, font_size)
                        except:
                            font = ImageFont.load_default()

                    # Center the text using anchor 'mm' (requires Pillow >= 8.0)
                    center_x = x + w / 2
                    center_y = y + h / 2
                    try:
                        draw.text((center_x, center_y), text, fill='black', anchor='mm', font=font)
                    except TypeError:
                        # Fallback for older Pillow: use textbbox to center manually
                        tw, th = get_text_size(draw, text, font)
                        draw.text((x + (w - tw) // 2, y + (h - th) // 2), text, fill='black', font=font)
            else:
                # Original behavior: red rectangle and label above
                draw.rectangle([x, y, x + w, y + h], outline='red', width=3)
                if text:
                    draw.text((x, max(0, y - 20)), text, fill='red', font=font)

        out_name = f"{img_abs.stem}_boxes.png"
        out_path = output_dir / out_name
        img.save(out_path)
        print(f"  Saved: {out_path}")
        saved += 1

    print(f"\nSummary: saved {saved} images.")

def main():
    parser = argparse.ArgumentParser(description="Visualize OCR bounding boxes")
    parser.add_argument('run_dir', help='Directory containing results.json')
    parser.add_argument('--output', '-o', help='Output directory (default: <run_dir>/visualized)')
    parser.add_argument('--debug', '-d', action='store_true', help='Verbose debug output')
    parser.add_argument('--whiteout', action='store_true', help='Fill boxes with white and render text inside')
    parser.add_argument('--text-field', choices=['orig', 'trans'], default='orig',
                        help='Which field to display inside whiteout boxes (default: orig)')
    parser.add_argument('--no-outline', action='store_true', help='Remove red outline when using whiteout')
    args = parser.parse_args()
    visualize_run(args.run_dir, args.output, args.debug, args.whiteout, args.text_field, args.no_outline)

if __name__ == '__main__':
    main()

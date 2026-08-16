import json
import re
from pathlib import Path
from jsonpath_ng import parse

def evaluate(test_eval, extracted, raw_content):
    results = []
    for ev in test_eval:
        t = ev.get('type')
        res = {"type": t, "passed": False, "details": ""}
        
        try:
            if t == 'exact':
                val = str(extracted) if extracted is not None else raw_content
                if ev.get('normalize'):
                    val = val.strip().lower()
                    expected = str(ev['value']).strip().lower()
                else:
                    expected = str(ev['value'])
                res["passed"] = (val == expected)
                
            elif t == 'contains':
                val = str(extracted) if extracted is not None else raw_content
                res["passed"] = ev['value'] in val
                
            elif t == 'regex':
                val = str(extracted) if extracted is not None else raw_content
                res["passed"] = bool(re.search(ev['pattern'], val))
                
            elif t == 'json_array':
                res["passed"] = isinstance(extracted, list)
                res["details"] = f"Expected list, got {type(extracted).__name__}"

            elif t == 'contains_key':
                if isinstance(extracted, list):
                    res["passed"] = all(ev['key'] in item for item in extracted if isinstance(item, dict))
                elif isinstance(extracted, dict):
                    res["passed"] = ev['key'] in extracted
                res["details"] = f"Key '{ev['key']}' not found in all items"

            elif t == 'bbox_iou':
                ref_path = ev.get('reference')
                threshold = ev.get('threshold', 0.3)
                if not ref_path or not isinstance(extracted, list):
                    res["passed"] = False
                    res["details"] = "Missing reference path or extracted is not a list"
                else:
                    ref_boxes = _load_boxes(ref_path)
                    det_boxes = [item['pos'] for item in extracted if isinstance(item, dict) and 'pos' in item]
                    res["passed"], res["details"] = _match_boxes(ref_boxes, det_boxes, threshold)

            elif t == 'json_path':
                if extracted is not None:
                    path = parse(ev['path'])
                    match = path.find(extracted)
                    if match:
                        res["passed"] = (match[0].value == ev['value'])
                        
            elif t == 'numeric_range':
                if extracted is not None:
                    path = parse(ev['path'])
                    match = path.find(extracted)
                    if match:
                        val = float(match[0].value)
                        res["passed"] = ev['min'] <= val <= ev['max']
                        
            elif t == 'code_execution':
                # Handled dynamically in runner
                res["passed"] = True 
                
        except Exception as e:
            res["details"] = str(e)
            
        results.append(res)
    return results


def _load_boxes(ref_path):
    p = Path(ref_path)
    if not p.is_absolute():
        # Resolve relative to the project root (parent of src/)
        p = Path(__file__).resolve().parent.parent.parent / "suites" / ref_path
    with open(p) as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Reference file {ref_path} must contain a JSON array")
    boxes = []
    for item in data:
        pos = item.get('pos')
        if pos and len(pos) == 4:
            boxes.append(pos)
    return boxes


def _box_iou(a, b):
    """Compute IoU for two boxes in [x, y, w, h] format."""
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_area = max(0, inter_x2 - inter_x1) * max(0, inter_y2 - inter_y1)
    union_area = (aw * ah) + (bw * bh) - inter_area

    if union_area <= 0:
        return 0.0
    return inter_area / union_area


def _match_boxes(ref_boxes, det_boxes, threshold):
    if not ref_boxes:
        return True, "No reference boxes"
    if not det_boxes:
        return False, f"No detected boxes, expected {len(ref_boxes)}"

    matched = set()
    match_count = 0
    for ref in ref_boxes:
        best_iou = 0.0
        best_idx = -1
        for idx, det in enumerate(det_boxes):
            if idx in matched:
                continue
            iou = _box_iou(ref, det)
            if iou > best_iou:
                best_iou = iou
                best_idx = idx
        if best_idx >= 0 and best_iou >= threshold:
            matched.add(best_idx)
            match_count += 1

    if match_count == len(ref_boxes):
        return True, f"All {len(ref_boxes)} reference boxes matched (threshold={threshold})"
    return False, f"Matched {match_count}/{len(ref_boxes)} reference boxes (threshold={threshold})"

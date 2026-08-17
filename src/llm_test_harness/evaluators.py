import json
import re
import math
import difflib
from pathlib import Path
from jsonpath_ng import parse

def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _score_numeric_tolerance(name, value, target, full_tolerance, half_tolerance, max_score):
    """
    Score a numeric value using tolerance bands.

    full_tolerance:
        If abs(value - target) <= full_tolerance, give full points.

    half_tolerance:
        If abs(value - target) <= half_tolerance, give half points.

    Otherwise give zero points.
    """
    numeric_value = _to_float(value)

    if numeric_value is None:
        return 0.0, f"{name}: missing or non-numeric value"

    target = float(target)
    full_tolerance = float(full_tolerance)
    half_tolerance = float(half_tolerance)
    max_score = float(max_score)

    diff = abs(numeric_value - target)

    if diff <= full_tolerance:
        score = max_score
        tier = "full"
    elif diff <= half_tolerance:
        score = max_score / 2.0
        tier = "half"
    else:
        score = 0.0
        tier = "none"

    details = (
        f"{name}: value={numeric_value:g}, "
        f"target={target:g}, "
        f"diff={diff:g}, "
        f"score={score:g}/{max_score:g} ({tier})"
    )

    return score, details

def _load_ocr_ref(ref_path):
    p = Path(ref_path)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent.parent.parent / "suites" / ref_path
    with open(p) as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Reference file {ref_path} must contain a JSON array")
    return [item for item in data if isinstance(item, dict)]

def _get_ocr_dets(extracted):
    if not isinstance(extracted, list):
        return []
    return [item for item in extracted if isinstance(item, dict) and 'pos' in item and len(item['pos']) == 4]

def _box_distance(a, b):
    # Distance between centers of the bounding boxes
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    acx, acy = ax1 + aw / 2, ay1 + ah / 2
    bcx, bcy = bx1 + bw / 2, by1 + bh / 2
    return math.hypot(acx - bcx, acy - bcy)

def _align_boxes(refs, dets, max_dist):
    matched_dets = set()
    alignments = []
    for ref in refs:
        best_det = None
        best_dist = float('inf')
        for idx, det in enumerate(dets):
            if idx in matched_dets: continue
            dist = _box_distance(ref['pos'], det['pos'])
            if dist < best_dist:
                best_dist = dist
                best_det = idx
        if best_det is not None and best_dist <= max_dist:
            matched_dets.add(best_det)
            alignments.append((ref, dets[best_det]))
        else:
            alignments.append((ref, None))
    return alignments

def evaluate(test_eval, extracted, raw_content, client=None, default_model=None, judge_model=None, judge_endpoint=None):
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

            elif t == "numeric_tolerance_score":
                total_score = 0.0
                max_total_score = 0.0
                field_details = []

                fields = ev.get("fields", [])

                for field in fields:
                    name = field.get("name", field.get("path", "value"))
                    path = field.get("path")

                    value = None

                    if extracted is not None and path:
                        try:
                            matches = parse(path).find(extracted)
                            if matches:
                                value = matches[0].value
                        except Exception:
                            value = None

                    max_score = float(field.get("max_score", 5.0))
                    max_total_score += max_score

                    score, details = _score_numeric_tolerance(
                        name=name,
                        value=value,
                        target=field.get("target", 0),
                        full_tolerance=field.get("full_tolerance", 0),
                        half_tolerance=field.get("half_tolerance", 0),
                        max_score=max_score
                    )

                    total_score += score
                    field_details.append(details)

                passing_threshold = float(
                    ev.get("passing_threshold", max_total_score)
                )

                res["passed"] = total_score >= passing_threshold
                res["score"] = total_score
                res["max_score"] = max_total_score
                res["details"] = "; ".join(field_details)
                res["category"] = ev.get("category", "Numeric")
            elif t == 'ocr_eval':
                try:
                    ref_path = ev.get('reference')
                    if not ref_path:
                        raise ValueError("ocr_eval requires 'reference' path")
                    
                    max_dist = ev.get('pixel_accuracy', 100)
                    
                    # Use CLI provided judge_model. Fallback to default_model if not specified.
                    judge_model_to_use = judge_model or default_model
                    
                    passing_threshold = ev.get('passing_threshold', 9.99)
                    bbox_threshold = ev.get('bbox_passing_threshold', 1.0)
                    
                    refs = _load_ocr_ref(ref_path)
                    dets = _get_ocr_dets(extracted)
                    alignments = _align_boxes(refs, dets, max_dist)
                    
                    # 1. BBox Finding
                    matched = sum(1 for r, d in alignments if d is not None)
                    total = len(refs)
                    bbox_score = 10.0 * matched / total if total > 0 else 10.0
                    bbox_pass_rate = matched / total if total > 0 else 1.0
                    results.append({
                        "type": "ocr_bbox",
                        "passed": bbox_pass_rate >= bbox_threshold,
                        "details": f"Matched {matched}/{total} boxes within {max_dist}px.",
                        "score": bbox_score,
                        "max_score": 10.0,
                        "category": "BBox Finding"
                    })
                    
                    # 2. Transcription Accuracy
                    trans_score_sum = 0.0
                    for ref, det in alignments:
                        if det is not None:
                            ratio = difflib.SequenceMatcher(None, ref.get('orig', ''), det.get('orig', '')).ratio()
                            trans_score_sum += ratio
                    trans_score = 10.0 * trans_score_sum / len(alignments) if len(alignments) > 0 else 10.0
                    results.append({
                        "type": "ocr_transcription",
                        "passed": trans_score >= passing_threshold,
                        "details": f"Transcription similarity: {trans_score:.2f}/10",
                        "score": trans_score,
                        "max_score": 10.0,
                        "category": "Transcription Accuracy"
                    })
                    
                    # 3. Translation Accuracy (LLM-as-a-Judge)
                    judge_client_to_use = client
                    if judge_endpoint and getattr(client, 'base_url', '').rstrip('/') != judge_endpoint.rstrip('/'):
                        from .client import LLMClient
                        try:
                            timeout = getattr(getattr(client, 'client', None), 'timeout', 300)
                            if hasattr(timeout, 'read_timeout'): timeout = timeout.read_timeout
                        except Exception:
                            timeout = 300
                        judge_client_to_use = LLMClient(judge_endpoint, timeout=timeout)
                        
                    pairs = []
                    for idx, (ref, det) in enumerate(alignments):
                        if det is not None:
                            pairs.append({
                                "idx": idx,
                                "ref_orig": ref.get('orig', ''),
                                "ref_trans": ref.get('trans', ''),
                                "det_trans": det.get('trans', '')
                            })
                    
                    trans_scores = [0.0] * len(alignments)
                    judge_details = ""
                    if judge_client_to_use and judge_model_to_use and pairs:
                        prompt = f"""You are an expert translator evaluating translations.
For each item, rate the "Model Translation" from 0 to 10 based on whether it conveys the exact same meaning as the "Reference Translation".
- 0: Completely different meaning.
- 10: Exact same meaning, even if words are different.

Items:
"""
                        for p in pairs:
                            prompt += f"\nItem {p['idx']}:\nReference Original: {p['ref_orig']}\nReference Translation: {p['ref_trans']}\nModel Translation: {p['det_trans']}\n"

                        prompt += "\nOutput ONLY a JSON object with a 'scores' key containing an array of integers (0-10) corresponding to the items. Do not include any other text. Example: {\"scores\": [10, 8, 0]}"
                        
                        try:
                            resp = judge_client_to_use.chat(
                                model=judge_model_to_use,
                                messages=[{"role": "user", "content": prompt}],
                                temperature=0.0,
                                max_tokens=256,
                                response_format={"type": "json_object"}
                            )
                            content = resp['content'].strip()
                            match = re.search(r'\{.*?\}', content, re.DOTALL)
                            if match:
                                parsed = json.loads(match.group(0))
                                if isinstance(parsed, dict) and 'scores' in parsed:
                                    parsed_list = parsed['scores']
                                    if isinstance(parsed_list, list) and len(parsed_list) == len(pairs):
                                        for i, p in enumerate(pairs):
                                            trans_scores[p['idx']] = float(parsed_list[i])
                                        judge_details = "Successfully parsed scores from judge."
                                    else:
                                        judge_details = "Judge returned malformed scores list."
                                else:
                                    judge_details = "Judge JSON missing 'scores' key."
                            else:
                                # fallback: try to extract integers
                                ints = re.findall(r'\b(\d+)\b', content)
                                if len(ints) == len(pairs):
                                    for i, p in enumerate(pairs):
                                        trans_scores[p['idx']] = float(min(10, int(ints[i])))
                                    judge_details = "Extracted scores via regex fallback."
                                else:
                                    judge_details = "Could not parse scores from judge output."
                        except Exception as e:
                            judge_details = f"Judge LLM failed: {str(e)}"
                    elif not judge_client_to_use:
                        judge_details = "No judge client specified."
                    elif not judge_model_to_use:
                        judge_details = "No judge model specified via CLI."
                        
                    translation_score_sum = sum(trans_scores)
                    translation_score = 10.0 * translation_score_sum / len(alignments) if len(alignments) > 0 else 10.0
                    results.append({
                        "type": "ocr_translation",
                        "passed": translation_score >= passing_threshold,
                        "details": f"Translation semantic similarity: {translation_score:.2f}/10. {judge_details}",
                        "score": translation_score,
                        "max_score": 10.0,
                        "category": "Translation Accuracy"
                    })
                except Exception as e:
                    results.append({"type": "ocr_eval", "passed": False, "details": f"Error in ocr_eval: {str(e)}", "score": 0, "max_score": 10, "category": "OCR"})
                continue # Skip default result append for this evaluator type
                
        except Exception as e:
            res["details"] = str(e)
            
        results.append(res)
    return results

def _load_boxes(ref_path):
    p = Path(ref_path)
    if not p.is_absolute():
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

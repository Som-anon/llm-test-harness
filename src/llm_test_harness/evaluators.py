import re
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

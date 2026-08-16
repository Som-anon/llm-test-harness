import json
import re
from rich.console import Console
from .evaluators import evaluate
from .execution import run_code
from .ocr import build_image_messages

console = Console()

def extract_json(text):
    if not text: return None
    text = text.strip()
    try:
        return json.loads(text)
    except:
        pass
    
    # Try to find markdown fenced json
    m = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
    if m:
        try:
            return json.loads(m.group(1))
        except:
            pass
            
    # Fallback: find first { and last }
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end+1])
        except:
            pass
            
    return None

def run_test(client, model, test, run_dir):
    test_id = test['id']
    req = test['request']
    messages = req.get('messages', [])

    # Image-based tests: inject the image into the user message content parts
    if test.get('image'):
        messages = build_image_messages(test)
    
    attempts = 0
    max_rounds = test.get('retry', {}).get('max_rounds', 1)
    
    history = []
    final_result = None
    
    while attempts < max_rounds:
        attempts += 1
        current_messages = messages + history
        
        try:
            resp = client.chat(
                model=model,
                messages=current_messages,
                temperature=req.get('temperature', 0.0),
                max_tokens=req.get('max_tokens', 1024),
                response_format=req.get('response_format'),
                timeout=test.get('timeout_seconds')
            )
        except Exception as e:
            return {"status": "error", "error": str(e), "test_id": test_id, "model": model}
            
        content = resp['content']
        extracted = None
        
        if test.get('extract', {}).get('type') == 'json':
            extracted = extract_json(content)
            
        eval_defs = test.get('evaluation', [])
        code_eval = next((e for e in eval_defs if e.get('type') == 'code_execution'), None)
        
        exec_res = None
        
        # FIX: Check if extracted is actually a dict before looking for 'code'
        if code_eval and isinstance(extracted, dict) and 'code' in extracted:
            lang = code_eval.get('language', 'python')
            exec_res = run_code(lang, extracted['code'], code_eval.get('timeout_seconds', 30))
            
            if not exec_res['success'] and attempts < max_rounds:
                feedback = f"Code execution failed.\nStderr:\n{exec_res.get('stderr', '')}\nStdout:\n{exec_res.get('stdout', '')}"
                history.append({"role": "assistant", "content": content})
                history.append({"role": "user", "content": feedback})
                continue
        
        eval_results = evaluate(eval_defs, extracted, content)
        
        if code_eval:
            for er in eval_results:
                if er['type'] == 'code_execution':
                    # FIX: Handle the case where exec_res is None (JSON extraction failed)
                    if exec_res:
                        er['passed'] = exec_res['success']
                        er['details'] = exec_res
                    else:
                        er['passed'] = False
                        er['details'] = "Failed to extract 'code' key from JSON response."
                    
        passed = all(er['passed'] for er in eval_results)
        
        final_result = {
            "test_id": test_id,
            "model": model,
            "category": test.get('category', ''),
            "subcategory": test.get('subcategory', ''),
            "attempts": attempts,
            "status": "pass" if passed else "fail",
            "request": {"messages": current_messages},
            "response": {"content": content, "extracted": extracted},
            "execution": exec_res,
            "evaluations": eval_results,
            "metrics": resp.get('metrics', {}),
            "usage": resp.get('usage', {})
        }
        if test.get('image'):
            final_result['image_path'] = test['image'].get('path')
        break
        
    return final_result

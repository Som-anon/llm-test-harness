import httpx
import time

class LLMClient:
    def __init__(self, base_url="http://localhost:5000", timeout=300.0):
        self.base_url = base_url.rstrip('/')
        if not self.base_url.endswith('/v1'):
            self.base_url += '/v1'
        self.client = httpx.Client(timeout=timeout)

    def get_models(self):
        try:
            r = self.client.get(f"{self.base_url}/models")
            r.raise_for_status()
            return [m['id'] for m in r.json().get('data', [])]
        except Exception:
            return []

    def chat(self, model, messages, temperature=0.0, max_tokens=1024, response_format=None, timeout=None):
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        if response_format:
            payload["response_format"] = response_format
            
        start = time.time()
        kwargs = {}
        if timeout is not None:
            kwargs['timeout'] = timeout
        r = self.client.post(f"{self.base_url}/chat/completions", json=payload, **kwargs)
        total_latency = time.time() - start
        r.raise_for_status()
        
        data = r.json()
        content = data['choices'][0]['message']['content']
        usage = data.get('usage', {})
        
        # Attempt to extract detailed timing if the backend supports it (e.g., llama.cpp / vLLM)
        prompt_time_s = data.get('prompt_eval_duration', data.get('prompt_time', 0))
        completion_time_s = data.get('eval_duration', data.get('completion_time', 0))
        
        metrics = {
            "latency_ms": int(total_latency * 1000),
            "prompt_tokens": usage.get('prompt_tokens', 0),
            "completion_tokens": usage.get('completion_tokens', 0),
            "total_tokens": usage.get('total_tokens', 0),
        }
        
        if isinstance(prompt_time_s, (int, float)) and prompt_time_s > 0:
            metrics["prompt_time_ms"] = int(prompt_time_s * 1000)
        if isinstance(completion_time_s, (int, float)) and completion_time_s > 0:
            metrics["completion_time_ms"] = int(completion_time_s * 1000)
            
        if metrics['completion_tokens'] > 0 and metrics.get('completion_time_ms', 0) > 0:
            metrics['tokens_per_second'] = round(metrics['completion_tokens'] / (metrics['completion_time_ms'] / 1000.0), 2)

        return {
            "content": content,
            "metrics": metrics,
            "usage": usage,
            "raw": data
        }

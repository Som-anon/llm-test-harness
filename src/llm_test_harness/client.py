import httpx
import time

class LLMClient:
    def __init__(self, base_url="http://localhost:5000"):
        # Ensure we hit the /v1 endpoint if not provided, or just use what's given
        self.base_url = base_url.rstrip('/')
        if not self.base_url.endswith('/v1'):
            self.base_url += '/v1'
        self.client = httpx.Client(timeout=180.0)

    def get_models(self):
        try:
            r = self.client.get(f"{self.base_url}/models")
            r.raise_for_status()
            return [m['id'] for m in r.json().get('data', [])]
        except Exception:
            return []

    def chat(self, model, messages, temperature=0.0, max_tokens=1024, response_format=None):
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        if response_format:
            payload["response_format"] = response_format
            
        start = time.time()
        r = self.client.post(f"{self.base_url}/chat/completions", json=payload)
        latency = time.time() - start
        r.raise_for_status()
        
        data = r.json()
        content = data['choices'][0]['message']['content']
        usage = data.get('usage', {})
        
        return {
            "content": content,
            "latency_ms": int(latency * 1000),
            "usage": usage,
            "raw": data
        }

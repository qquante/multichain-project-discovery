# agent/api_client.py
import requests
import json
import time
from typing import Dict, Any, Optional

OPENROUTER_API_KEY = "[REMOVED_CREDENTIAL]"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "google/gemini-2.5-flash-lite"


class OpenRouterClient:
    
    def __init__(self, api_key: str = OPENROUTER_API_KEY, verbose: bool = True):
        self.api_key = api_key
        self.url = OPENROUTER_URL
        self.model = MODEL
        self.verbose = verbose
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/project-agent",
            "X-Title": "Project Agent"
        }
    
    def _log(self, msg: str):
        if self.verbose:
            print(msg)
    
    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 2000,
        retries: int = 3,
        timeout: int = 60
    ) -> Dict[str, Any]:
        """Send chat completion request to OpenRouter with retry."""
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"}
        }
        
        last_error = None
        
        for attempt in range(retries):
            try:
                start_time = time.time()
                
                response = requests.post(
                    self.url,
                    headers=self.headers,
                    json=payload,
                    timeout=timeout
                )
                
                elapsed = time.time() - start_time
                
                if response.status_code != 200:
                    self._log(f"[API_ERROR] status={response.status_code} | body={response.text[:200]}")
                    return {"error": response.text, "status_code": response.status_code}
                
                result = response.json()
                
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                usage = result.get("usage", {})
                
                self._log(f"[API] model={self.model} | tokens={usage.get('total_tokens', 0)} | time={elapsed:.2f}s")
                
                return {
                    "content": content,
                    "usage": usage,
                    "elapsed": elapsed,
                    "raw": result
                }
                
            except (requests.exceptions.RequestException, requests.exceptions.ChunkedEncodingError) as e:
                last_error = str(e)
                self._log(f"[RETRY] attempt={attempt+1}/{retries} | error={last_error[:50]}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
        
        return {"error": last_error, "status_code": 0}
    
    def parse_json_response(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse JSON from response content."""
        try:
            # Try direct parse
            return json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                if end > start:
                    return json.loads(content[start:end].strip())
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                if end > start:
                    return json.loads(content[start:end].strip())
            return None


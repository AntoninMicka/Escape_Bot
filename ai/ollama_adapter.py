from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass


@dataclass(slots=True)
class OllamaAdapter:
    base_url: str = "http://127.0.0.1:11434"
    model: str = "llama3.1"

    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        return str(data.get("response", "")).strip()


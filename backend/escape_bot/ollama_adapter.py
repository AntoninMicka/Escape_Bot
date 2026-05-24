import json
import urllib.request
import logging
import asyncio
import os

logger = logging.getLogger("OllamaAdapter")

class OllamaAdapter:
    def __init__(self, host=None, model="llama3"):
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.model = os.environ.get("OLLAMA_MODEL", model)

    def _post_sync(self, system_prompt: str, history: list[dict[str, str]]) -> str:
        url = f"{self.host}/api/chat"
        
        messages = [{"role": "system", "content": system_prompt}]
        
        # Vezmeme posledních 15 zpráv z historie pro kontext
        for msg in history[-15:]:
            # 'bot' z naší historie přemapujeme na Ollama formát 'assistant'
            role = "assistant" if msg["role"] == "bot" else "user"
            messages.append({"role": role, "content": msg["text"]})
            
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False
        }
        
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=15) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result.get("message", {}).get("content", "").strip()
        except Exception as e:
            logger.warning(f"Ollama nedostupná (AI generování selhalo, použije se fallback): {e}")
            return ""

    async def generate_response(self, system_prompt: str, history: list[dict[str, str]]) -> str:
        # Spuštění v threadu, aby blokující HTTP požadavek nezastavil zpracování WebSocketů serveru
        return await asyncio.to_thread(self._post_sync, system_prompt, history)

    async def is_hint_request(self, text: str) -> bool:
        """
        Klasifikuje zprávu pomocí AI: Ptá se hráč na radu/nápovědu?
        """
        system_prompt = (
            "Jsi analyzátor záměru v únikové hře. Zhodnoť zprávu od hráče. "
            "Odpověz striktně pouze slovem 'ANO', pokud zpráva splňuje alespoň jednu z podmínek:\n"
            "1. Vyjadřuje bezradnost (např. 'nevím', 'zasekl jsem se').\n"
            "2. Prosí o nápovědu či pomoc (např. 'pomoc', 'poraď').\n"
            "3. Je to otázka doptávající se na aktuální úkol (např. 'jakou frekvenci?', 'co mám hledat?', '?').\n"
            "Odpověz striktně pouze slovem 'NE', pokud hráč jen hádá řešení (čísla, kódy) nebo nevyžaduje radu.\n"
            "Napiš pouze ANO nebo NE. Žádný další text."
        )
        # Pro zjištění záměru nepotřebujeme posílat celou historii
        response = await asyncio.to_thread(self._post_sync, system_prompt, [{"role": "user", "text": text}])
        return "ANO" in response.strip().upper()

    async def ensure_model(self) -> None:
        """Na pozadí ověří existenci modelu a pokud chybí, stáhne jej přes API."""
        def _pull():
            try:
                url_tags = f"{self.host}/api/tags"
                req = urllib.request.Request(url_tags)
                with urllib.request.urlopen(req, timeout=5) as response:
                    tags_data = json.loads(response.read().decode('utf-8'))
                    models = [m.get("name") for m in tags_data.get("models", [])]
                    
                has_model = any(m == self.model or m.startswith(f"{self.model}:") for m in models)
                
                if not has_model:
                    logger.info(f"Ollama: Model '{self.model}' nenalezen. Zahajuji stahování na pozadí (může trvat několik minut)...")
                    url_pull = f"{self.host}/api/pull"
                    payload = {"name": self.model, "stream": False}
                    req_pull = urllib.request.Request(url_pull, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
                    with urllib.request.urlopen(req_pull, timeout=1200) as response_pull:
                        logger.info(f"Ollama: Model '{self.model}' úspěšně stažen a je připraven pro hru.")
            except Exception as e:
                logger.warning(f"Ollama: Nepodařilo se připojit k {self.host} nebo ověřit model. Je Ollama spuštěna? ({e})")
        
        await asyncio.to_thread(_pull)
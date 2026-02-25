import httpx
from typing import Optional
import os

class LLMClient:
    """
    Dual-backend LLM client:
    - Default: local OpenAI-compatible server (e.g., Ollama)
    - If api_key is provided and openai_base_url is set: use OpenAI API

    Supports:
    - OpenAI-style /chat/completions (local or remote)
    - OpenAI /responses (remote) with compatible parsing
    """

    def __init__(
        self,
        base_url: str,
        default_model: str,
        *,
        openai_base_url: Optional[str] = None,
        openai_default_model: Optional[str] = None,
        prefer_responses_api: bool = True,
        force_chat_completions: bool = False,   # <-- aggiungi questo
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.default_model = default_model

        self.openai_base_url = (openai_base_url or "").rstrip("/") or None
        self.openai_default_model = openai_default_model or default_model

        self.prefer_responses_api = bool(prefer_responses_api)
        self.force_chat_completions = bool(force_chat_completions)


    def _is_openai_call(self, api_key: str) -> bool:
        return bool(api_key and self.openai_base_url)

    async def ask(
        self,
        api_key: str,
        prompt: str,
        system: str = "You are a helpful study assistant.",
        model: Optional[str] = None,
        max_tokens: int = 400,
        temperature: float = 0.2,
    ) -> str:
        api_key = (api_key or "").strip()
        provider = os.getenv("LLM_PROVIDER", "").strip().lower()
        if provider == "groq":
            api_key = os.getenv("GROQ_API_KEY", "").strip() or api_key


        prompt = f"Answer in English only.\n\n{prompt or ''}"
        system = system or "You are a helpful study assistant."

        use_openai = self._is_openai_call(api_key)

        if use_openai:
            used_model = model or self.openai_default_model
            base = self.openai_base_url  # type: ignore[assignment]
        else:
            used_model = model or self.default_model
            base = self.base_url

        if not base:
            return "LLM misconfigured: missing base_url."

        headers = {"Content-Type": "application/json"}
        if use_openai:
            headers["Authorization"] = f"Bearer {api_key}"

        async with httpx.AsyncClient(timeout=60) as client:
            if use_openai and self.prefer_responses_api and (not self.force_chat_completions) and provider != "groq":


                url = f"{base}/responses"
                payload = {
                    "model": used_model,
                    "input": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": temperature,
                    # keep it simple: ask for text output
                    "max_output_tokens": max_tokens,
                }

                r = await client.post(url, headers=headers, json=payload)
                if r.status_code == 401:
                    return "Invalid API key (401). Use /setkey to update it."
                if r.status_code >= 400:
                    body = (r.text or "")[:500]
                    return f"LLM error ({r.status_code}): {body}"

                data = r.json()

                if isinstance(data, dict) and "output_text" in data:
                    out = str(data.get("output_text") or "").strip()
                    if out:
                        return out

                if isinstance(data, dict) and isinstance(data.get("output"), list):
                    texts = []
                    for item in data["output"]:
                        content = item.get("content") if isinstance(item, dict) else None
                        if isinstance(content, list):
                            for part in content:
                                if isinstance(part, dict):
                                    if "text" in part:
                                        texts.append(str(part["text"]))
                                    elif part.get("type") == "output_text" and "content" in part:
                                        texts.append(str(part["content"]))
                    out = "\n".join([t for t in texts if t]).strip()
                    if out:
                        return out

                return ""

            url = f"{base}/chat/completions"
            payload = {
                "model": used_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }

            r = await client.post(url, headers=headers, json=payload)

            if r.status_code == 401:
                return "Invalid API key (401). Use /setkey to update it."
            if r.status_code >= 400:
                body = (r.text or "")[:500]
                return f"LLM error ({r.status_code}): {body}"

            data = r.json()

            if isinstance(data, dict) and data.get("choices"):
                choice0 = data["choices"][0] or {}
                msg = choice0.get("message") or {}
                content = (msg.get("content") or "").strip()
                if content:
                    return content

                text = (choice0.get("text") or "").strip()
                if text:
                    return text

                delta = choice0.get("delta") or {}
                dcontent = (delta.get("content") or "").strip()
                if dcontent:
                    return dcontent

                return ""

            if isinstance(data, dict) and "message" in data:
                return str(data["message"]).strip()

            if isinstance(data, dict) and "response" in data:
                return str(data["response"]).strip()

            return ""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

from translation_core import validate_translation

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiTranslationError(Exception):
    def __init__(self, message: str, *, status: int | None = None, retry_after: str | None = None, quota: bool = False):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after
        self.quota = quota


def translate_text(api_key: str, model: str, text: str, target_language: str = "Turkish", glossary: dict[str, str] | None = None) -> str:
    if not api_key.strip():
        raise GeminiTranslationError("Gemini API anahtarı girilmemiş.")
    model = model.removeprefix("models/")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", model):
        raise GeminiTranslationError("Geçersiz Gemini model adı.")
    protected = {
        "placeholders": __import__("re").findall(
            r"\{[^{}]+\}|\$\{[^{}]+\}|%(?:\d+\$)?[-+#0 ]*(?:\d+|\*)?(?:\.(?:\d+|\*))?[a-zA-Z%]|\[[A-Za-z0-9_.:-]+\]|<[^>]+>|\\[nrt\\]",
            text,
        )
    }
    prompt = (
        f"Translate the game text into {target_language}. Return ONLY the translated text, no quotes or explanations. "
        "Preserve every placeholder, variable, markup tag, escape sequence, punctuation token, and line break exactly. "
        "Do not translate identifiers or text inside placeholders. Keep the same meaning, tone, and approximate length.\n"
        f"Glossary: {json.dumps(glossary or {}, ensure_ascii=False)}\n"
        f"Protected tokens (must remain exactly): {json.dumps(protected['placeholders'], ensure_ascii=False)}\n"
        f"TEXT:\n{text}"
    )
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.2}}
    request = urllib.request.Request(
        f"{API_ROOT}/{model}:generateContent",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    data = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                data = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1200]
            retry_after = exc.headers.get("Retry-After")
            quota = exc.code == 429 or "RESOURCE_EXHAUSTED" in detail
            if exc.code in (500, 502, 503, 504) and attempt < 2:
                try:
                    delay = min(20.0, max(0.0, float(retry_after))) if retry_after else 1.5 ** (attempt + 1)
                except ValueError:
                    delay = 1.5 ** (attempt + 1)
                time.sleep(delay)
                continue
            raise GeminiTranslationError(
                f"Gemini HTTP {exc.code}: {detail}", status=exc.code, retry_after=retry_after, quota=quota
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt < 2:
                time.sleep(1.5 ** (attempt + 1))
                continue
            raise GeminiTranslationError(f"Gemini bağlantı hatası: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise GeminiTranslationError("Gemini geçersiz JSON yanıtı döndürdü.") from exc
    if data is None:
        raise GeminiTranslationError("Gemini yanıtı alınamadı.")
    try:
        result = "".join(part.get("text", "") for part in data["candidates"][0]["content"]["parts"]).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise GeminiTranslationError("Gemini boş veya beklenmeyen yanıt döndürdü.") from exc
    issues = validate_translation(text, result)
    if issues:
        raise GeminiTranslationError("Çeviri kalite kontrolünden geçemedi: " + " ".join(issues))
    return result

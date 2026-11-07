from __future__ import annotations

import json
import random
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from translation_core import placeholder_signature, validate_translation

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"


def _retry_delay(retry_after: str | None, attempt: int) -> float:
    delay = None
    if retry_after:
        try:
            delay = float(retry_after)
        except ValueError:
            try:
                retry_time = parsedate_to_datetime(retry_after)
                if retry_time.tzinfo is None:
                    retry_time = retry_time.replace(tzinfo=timezone.utc)
                delay = (retry_time - datetime.now(timezone.utc)).total_seconds()
            except (TypeError, ValueError, OverflowError):
                delay = None
    if delay is None:
        delay = 1.5 ** (attempt + 1)
    return min(20.0, max(0.0, delay)) + random.uniform(0.0, 0.25)


class GeminiTranslationError(Exception):
    def __init__(self, message: str, *, status: int | None = None, retry_after: str | None = None, quota: bool = False):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after
        self.quota = quota


def _generate(api_key: str, model: str, prompt: str, json_mode: bool = False) -> str:
    if not api_key.strip():
        raise GeminiTranslationError("Gemini API anahtarı girilmemiş.")
    model = model.removeprefix("models/")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", model):
        raise GeminiTranslationError("Geçersiz Gemini model adı.")
    generation = {"temperature": 0.2}
    if json_mode:
        generation["responseMimeType"] = "application/json"
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": generation}
    request = urllib.request.Request(
        f"{API_ROOT}/{model}:generateContent",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    data = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1200]
            retry_after = exc.headers.get("Retry-After")
            quota = exc.code == 429 or "RESOURCE_EXHAUSTED" in detail
            if exc.code in (408, 500, 502, 503, 504) and attempt < 2:
                time.sleep(_retry_delay(retry_after, attempt))
                continue
            raise GeminiTranslationError(
                f"Gemini HTTP {exc.code}: {detail}", status=exc.code, retry_after=retry_after, quota=quota
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt < 2:
                time.sleep(_retry_delay(None, attempt))
                continue
            raise GeminiTranslationError(f"Gemini bağlantı hatası: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise GeminiTranslationError("Gemini geçersiz JSON yanıtı döndürdü.") from exc
    if data is None:
        raise GeminiTranslationError("Gemini yanıtı alınamadı.")
    try:
        return "".join(part.get("text", "") for part in data["candidates"][0]["content"]["parts"]).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise GeminiTranslationError("Gemini boş veya beklenmeyen yanıt döndürdü.") from exc


def translate_batch(
    api_key: str,
    model: str,
    items: list[tuple[str, str]],
    target_language: str = "Turkish",
    glossary: dict[str, str] | None = None,
) -> dict[str, str]:
    if not items:
        return {}
    ids = [item[0] for item in items]
    if len(set(ids)) != len(ids):
        raise GeminiTranslationError("Çeviri grubunda yinelenen kayıt kimliği var.")
    payload = [
        {"id": entry_id, "source": source, "protected_tokens": placeholder_signature(source)}
        for entry_id, source in items
    ]
    prompt = (
        f"Translate each source value into {target_language}. Return ONLY valid JSON in this exact shape: "
        '{"translations":[{"id":"same-id","text":"translated text"}]}. '
        "Return exactly one result for every input id, with no extra keys or commentary. "
        "Preserve placeholders, variables, markup tags, escape sequences, punctuation tokens and line breaks exactly. "
        "Never translate protected_tokens. Keep meaning, tone and approximate length. "
        f"Glossary: {json.dumps(glossary or {}, ensure_ascii=False)}\n"
        f"INPUT JSON:\n{json.dumps(payload, ensure_ascii=False)}"
    )
    raw = _generate(api_key, model, prompt, json_mode=True)
    try:
        data = json.loads(raw)
        translations = data["translations"] if isinstance(data, dict) else data
        if not isinstance(translations, list):
            raise ValueError("translations alanı liste değil")
        result = {}
        for row in translations:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not isinstance(row.get("text"), str):
                raise ValueError("Çeviri kaydı geçersiz")
            if row["id"] in result or row["id"] not in ids:
                raise ValueError("Bilinmeyen veya yinelenen çeviri kimliği")
            result[row["id"]] = row["text"]
        if set(result) != set(ids):
            raise ValueError("Gemini tüm kayıtlar için çeviri döndürmedi")
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise GeminiTranslationError(f"Gemini toplu çeviri yanıtı doğrulanamadı: {exc}") from exc
    for entry_id, source in items:
        issues = validate_translation(source, result[entry_id])
        if issues:
            raise GeminiTranslationError(f"{entry_id}: kalite kontrolü başarısız. {' '.join(issues)}")
    return result


def translate_text(api_key: str, model: str, text: str, target_language: str = "Turkish", glossary: dict[str, str] | None = None) -> str:
    return translate_batch(api_key, model, [("single", text)], target_language, glossary)["single"]

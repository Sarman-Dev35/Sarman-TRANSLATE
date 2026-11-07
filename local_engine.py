from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import urllib.request
from pathlib import Path

from translation_core import validate_translation

APP_DATA = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Sarman" / "TRANSLATE"
MODEL_DIR = APP_DATA / "models"
MODEL_NAME = "Qwen3-4B-Q4_K_M.gguf"
MODEL_PATH = MODEL_DIR / MODEL_NAME
MODEL_URL = "https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf"
MODEL_SHA256 = "7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5"
MODEL_SIZE_HINT = 2_500_000_000
_LOCK = threading.RLock()
_MODEL = None
_TOKEN_RE = re.compile(r"\{[^{}]+\}|\$\{[^{}]+\}|\$[A-Za-z_][A-Za-z0-9_]*|%(?:\d+\$)?[-+#0 ]*(?:\d+|\*)?(?:\.(?:\d+|\*))?[a-zA-Z%]|\[[A-Za-z0-9_.:-]+\]|<[^>]+>|\\[nrt]|\\u[0-9a-fA-F]{4}")


class LocalTranslationError(RuntimeError):
    pass


DEFAULT_GLOSSARY = {
    "New Game": "Yeni Oyun", "Load Game": "Oyunu Yükle", "Save Game": "Oyunu Kaydet",
    "Continue": "Devam Et", "Game Over": "Oyun Bitti", "Main Menu": "Ana Menü",
    "Options": "Ayarlar", "Settings": "Ayarlar", "Quit Game": "Oyundan Çık",
    "Press any key": "Bir tuşa bas", "Press any button": "Bir düğmeye bas",
    "Inventory": "Envanter", "Quest": "Görev", "Side Quest": "Yan Görev",
    "Skill Tree": "Yetenek Ağacı", "Level Up": "Seviye Atladın",
    "Checkpoint": "Kontrol Noktası", "Respawn": "Yeniden Doğ",
    "Boss": "Boss", "Boss Fight": "Boss Savaşı", "Health": "Can",
    "Stamina": "Dayanıklılık", "Mana": "Mana", "Achievement": "Başarım",
    "Achievements": "Başarımlar", "You Died": "Öldün", "Try Again": "Tekrar Dene",
    "Are you sure?": "Emin misin?", "Start": "Başlat", "Resume": "Devam Et",
    "Exit to Desktop": "Masaüstüne Çık"
}


def model_status() -> dict:
    installed = MODEL_PATH.is_file() and MODEL_PATH.stat().st_size > 1_000_000_000
    return {
        "installed": installed,
        "engine": "Qwen3 4B · GGUF Q4_K_M",
        "message": "Yerel yapay zekâ modeli hazır." if installed else "Qwen3 4B yerel modeli henüz indirilmedi.",
        "model_path": str(MODEL_PATH),
        "download_size": "yaklaşık 2,5 GB",
    }


def install_english_turkish_model(progress=None) -> None:
    """Download and verify the official Qwen3-4B Q4_K_M model."""
    if model_status()["installed"]:
        return
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    partial = MODEL_PATH.with_suffix(MODEL_PATH.suffix + ".part")
    request = urllib.request.Request(
        MODEL_URL,
        headers={"User-Agent": "Sarman-TRANSLATE/0.2", "Accept": "application/octet-stream"},
    )
    try:
        downloaded = 0
        with urllib.request.urlopen(request, timeout=90) as response, partial.open("wb") as output:
            total = int(response.headers.get("Content-Length") or 0)
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                downloaded += len(chunk)
                if progress:
                    progress(downloaded, total or MODEL_SIZE_HINT)
            output.flush()
            os.fsync(output.fileno())
        if downloaded < 1_000_000_000:
            raise LocalTranslationError("İndirilen model dosyası beklenenden küçük; bozuk indirme silindi.")
        digest = hashlib.sha256()
        with partial.open("rb") as source:
            for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest().lower() != MODEL_SHA256:
            raise LocalTranslationError("Model SHA-256 doğrulamasından geçmedi. Güvenlik için dosya kullanılmadı.")
        os.replace(partial, MODEL_PATH)
    except LocalTranslationError:
        partial.unlink(missing_ok=True)
        raise
    except Exception as exc:
        partial.unlink(missing_ok=True)
        raise LocalTranslationError(f"Yerel model indirilemedi: {exc}") from exc


def _cache_path() -> Path:
    return APP_DATA / "translation-memory.sqlite3"


def _glossary_terms() -> dict[str, str]:
    terms = dict(DEFAULT_GLOSSARY)
    path = APP_DATA / "glossary.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for source, target in data.items():
                if target is None:
                    terms.pop(str(source), None)
                elif str(source).strip() and str(target).strip():
                    terms[str(source)] = str(target)
    except (OSError, ValueError, TypeError):
        pass
    return terms


def _cache_key(source: str, context: str = "", game_name: str = "") -> str:
    glossary = json.dumps(_glossary_terms(), ensure_ascii=False, sort_keys=True)
    payload = "\0".join((source, context, game_name, glossary))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cache_get(source: str, context: str = "", game_name: str = "") -> str | None:
    path = _cache_path()
    if not path.exists():
        return None
    try:
        with sqlite3.connect(path, timeout=5) as db:
            row = db.execute(
                "SELECT translated FROM memory WHERE source_hash=?",
                (_cache_key(source, context, game_name),),
            ).fetchone()
            return row[0] if row else None
    except sqlite3.OperationalError:
        return None


def _cache_put(source: str, translated: str, context: str = "", game_name: str = "") -> None:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=10) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS memory (source_hash TEXT PRIMARY KEY, source TEXT NOT NULL, translated TEXT NOT NULL)"
        )
        db.execute(
            "INSERT INTO memory(source_hash,source,translated) VALUES(?,?,?) "
            "ON CONFLICT(source_hash) DO UPDATE SET source=excluded.source, translated=excluded.translated",
            (_cache_key(source, context, game_name), source, translated),
        )


def _get_model():
    global _MODEL
    with _LOCK:
        if _MODEL is not None:
            return _MODEL
        if not MODEL_PATH.is_file():
            raise LocalTranslationError("Qwen3 4B modeli kurulu değil. Önce yerel modeli indir.")
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise LocalTranslationError("llama-cpp bileşeni bulunamadı. Uygulamayı güncel paketle yeniden kur.") from exc
        try:
            _MODEL = Llama(
                model_path=str(MODEL_PATH),
                n_ctx=4096,
                n_threads=max(2, min(8, os.cpu_count() or 4)),
                n_gpu_layers=0,
                verbose=False,
            )
        except Exception as exc:
            raise LocalTranslationError(f"Yerel yapay zekâ başlatılamadı: {exc}") from exc
        return _MODEL


def translate_text(text: str, context: str = "", game_name: str = "") -> str:
    """Context-aware English→Turkish game localization with a local 4B model."""
    if not isinstance(text, str) or not text.strip():
        return text
    original_text = text
    cached = _cache_get(original_text, context, game_name)
    if cached is not None:
        return cached

    tokens: list[tuple[str, str]] = []
    glossary = sorted(_glossary_terms().items(), key=lambda item: len(item[0]), reverse=True)
    for source_term, target_term in glossary:
        pattern = r"(?<!\w)" + re.escape(source_term) + r"(?!\w)"
        if re.search(pattern, text, re.IGNORECASE):
            marker = f"SARMANTERM{len(tokens):04d}X"
            text = re.sub(pattern, lambda _m, value=marker: value, text, flags=re.IGNORECASE)
            tokens.append((marker, target_term))

    def protect(match):
        marker = f"SARMANPH{len(tokens):04d}X"
        tokens.append((marker, match.group(0)))
        return marker

    protected = _TOKEN_RE.sub(protect, text)
    game_context = game_name.strip() or "video game"
    context_block = context.strip()[:1600] if context.strip() else "(No extra context)"
    prompt = (
        "<|im_start|>system\n"
        "You are a professional video-game localization translator translating English into natural Turkish. "
        "Translate meaning, tone, humor, idioms, puns and character voice rather than translating word-for-word. "
        "Use the surrounding context to choose the correct sense of ambiguous words. "
        "Keep the translation concise and suitable for an in-game UI or dialogue. "
        "Never explain, add notes, quote the source, or output multiple alternatives. "
        "Return only the Turkish translation. Preserve every protected marker exactly.\n"
        "<|im_end|>\n"
        "<|im_start|>user\n"
        f"Game: {game_context}\n"
        f"Nearby dialogue/context:\n{context_block}\n\n"
        f"Translate this exact string into Turkish:\n{protected}\n/no_think"
        "<|im_end|>\n"
        "<|im_start|>assistant\n"
    )
    try:
        model = _get_model()
        response = model(
            prompt,
            max_tokens=min(512, max(96, len(protected) * 3)),
            temperature=0.15,
            top_p=0.85,
            repeat_penalty=1.08,
            stop=["<|im_end|>", "<|endoftext|>"],
        )
        result = response["choices"][0]["text"].strip()
        result = re.sub(r"^(Türkçe çeviri|Çeviri)\s*:\s*", "", result, flags=re.IGNORECASE)
        for marker, replacement in tokens:
            if marker not in result:
                raise LocalTranslationError("Model bir oyun terimini veya yer tutucuyu koruyamadı; bu metin güvenli biçimde çevrilmedi.")
            result = result.replace(marker, replacement)
        issues = validate_translation(original_text, result)
        if issues:
            raise LocalTranslationError("Model çevirisi oyun değişkenlerini/biçimini koruyamadı: " + " ".join(issues))
        if not result or result.casefold() == original_text.casefold():
            raise LocalTranslationError("Model geçerli bir Türkçe çeviri üretemedi. Metni elle gözden geçir.")
        _cache_put(original_text, result, context, game_name)
        return result
    except LocalTranslationError:
        raise
    except Exception as exc:
        raise LocalTranslationError(f"Yerel çeviri başarısız: {exc}") from exc


def glossary_items() -> list[tuple[str, str]]:
    return sorted(_glossary_terms().items(), key=lambda item: item[0].casefold())


def set_glossary_term(source: str, target: str) -> None:
    source, target = source.strip(), target.strip()
    if not source or not target:
        raise ValueError("Kaynak terim ve Türkçe karşılığı boş olamaz.")
    path = APP_DATA / "glossary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        custom = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(custom, dict):
            custom = {}
    except (OSError, ValueError):
        custom = {}
    custom[source] = target
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(custom, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def delete_glossary_term(source: str) -> None:
    path = APP_DATA / "glossary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        custom = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(custom, dict):
            custom = {}
        custom[source] = None
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(custom, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
    except (OSError, ValueError):
        return

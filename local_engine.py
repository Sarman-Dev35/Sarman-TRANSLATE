from __future__ import annotations

import hashlib
import gc
import sys
from contextlib import closing
import json
import os
import re
import sqlite3
import threading
import time
import urllib.request
from pathlib import Path

from translation_core import validate_translation

APP_DATA = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Sarman" / "TRANSLATE"
MODEL_NAME = "Hy-MT2-1.8B-Q4_K_M.gguf"


def _model_directory() -> Path:
    # Packaged builds keep the model beside the executable for portable management.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return APP_DATA / "models"


MODEL_DIR = _model_directory()
MODEL_PATH = MODEL_DIR / MODEL_NAME
MODEL_URL = "https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/main/Hy-MT2-1.8B-Q4_K_M.gguf"
MODEL_SHA256 = "dc5f44fcf1fa496ee7ad725982c0c8c553a4de00259b53af84c4b89fb0c06699"
MODEL_FILE_SIZE = 1_133_080_448
MODEL_SIZE_HINT = MODEL_FILE_SIZE
# Cache invalidation for translation-quality and prompt changes.
TRANSLATION_PIPELINE_VERSION = "2026-11-07.3"
DOWNLOAD_CHUNK_SIZE = 4 * 1024 * 1024
_LOCK = threading.RLock()
_INFERENCE_LOCK = threading.Lock()
_DOWNLOAD_LOCK = threading.Lock()
_CACHE_LOCK = threading.RLock()
_GLOSSARY_LOCK = threading.RLock()
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
    partial_path = MODEL_PATH.with_suffix(MODEL_PATH.suffix + ".part")
    try:
        present = MODEL_PATH.is_file() or MODEL_PATH.is_symlink()
        partial_present = partial_path.is_file() or partial_path.is_symlink()
        header_valid = False
        if present and not MODEL_PATH.is_symlink():
            with MODEL_PATH.open("rb") as model_file:
                header_valid = model_file.read(4) == b"GGUF"
        installed = present and not MODEL_PATH.is_symlink() and header_valid and MODEL_PATH.stat().st_size == MODEL_FILE_SIZE
    except (OSError, RuntimeError, ValueError):
        present = False
        partial_present = False
        header_valid = False
        installed = False
    state = "installed" if installed else "partial" if partial_present else "corrupt" if present else "missing"
    return {
        "state": state,
        "installed": installed,
        "present": present,
        "partial_present": partial_present,
        "header_valid": header_valid,
        "engine": "Tencent Hy-MT2 1.8B · GGUF Q4_K_M",
        "message": ("Hy-MT2 çeviri modeli hazır." if installed else "Eksik model indirmesi bulundu; kaldığı yerden sürdürülebilir." if partial_present else "Model dosyası eksik veya bozuk; yeniden indirilebilir." if present else "Hy-MT2 1.8B çeviri modeli henüz indirilmedi."),
        "model_path": str(MODEL_PATH),
        "download_size": "yaklaşık 1,13 GB",
    }


def install_english_turkish_model(progress=None) -> None:
    """Serialize model downloads so two windows cannot corrupt the shared partial file."""
    with _DOWNLOAD_LOCK:
        _install_english_turkish_model_locked(progress)


def _install_english_turkish_model_locked(progress=None) -> None:
    """Download and verify Tencent's official Hy-MT2 1.8B Q4_K_M translation model."""
    if model_status()["installed"]:
        return
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    partial = MODEL_PATH.with_suffix(MODEL_PATH.suffix + ".part")
    if MODEL_PATH.is_symlink() or partial.is_symlink():
        raise LocalTranslationError("Model veya yarım indirme yolu sembolik bağlantı. Güvenlik için bu dosyayı elle kontrol edip bağlantıyı kaldır.")
    existing = partial.stat().st_size if partial.exists() else 0
    if existing >= MODEL_FILE_SIZE:
        partial.unlink(missing_ok=True)
        existing = 0
    headers = {"User-Agent": "Sarman-TRANSLATE/0.4", "Accept": "application/octet-stream", "Accept-Encoding": "identity"}
    if existing:
        headers["Range"] = f"bytes={existing}-"
    request = urllib.request.Request(MODEL_URL, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            response_status = getattr(response, "status", 200)
            resumed = bool(existing and response_status == 206)
            if resumed:
                content_range = response.headers.get("Content-Range", "")
                if not content_range.startswith(f"bytes {existing}-"):
                    raise OSError("Sunucu devam indirmesi için geçersiz Content-Range döndürdü.")
            downloaded = existing if resumed else 0
            # The model size is pinned and independently verified below. Using it here
            # also keeps the progress display correct for HTTP Range responses.
            total = MODEL_FILE_SIZE
            mode = "ab" if resumed else "wb"
            last_reported_bytes = downloaded
            last_reported_at = time.monotonic()
            if progress:
                progress(downloaded, total, 0.0, 0)
            with partial.open(mode) as output:
                while True:
                    chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded += len(chunk)
                    now = time.monotonic()
                    elapsed = now - last_reported_at
                    if progress and (elapsed >= 0.5 or downloaded >= total):
                        speed = (downloaded - last_reported_bytes) / elapsed if elapsed > 0 else 0.0
                        remaining = max(0, total - downloaded)
                        eta = int(remaining / speed) if speed > 0 else 0
                        progress(downloaded, total, speed, eta)
                        last_reported_bytes = downloaded
                        last_reported_at = now
                output.flush()
                os.fsync(output.fileno())
        if downloaded != MODEL_FILE_SIZE or partial.stat().st_size != MODEL_FILE_SIZE:
            # A truncated transfer is resumable; preserve the partial file for the next attempt.
            raise OSError("Hy-MT2 indirmesi henüz tamamlanmadı; kalan bölüm sonraki denemede sürdürülebilir.")
        digest = hashlib.sha256()
        with partial.open("rb") as source:
            for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest().lower() != MODEL_SHA256:
            raise LocalTranslationError("Hy-MT2 SHA-256 doğrulamasından geçmedi. Güvenlik için dosya kullanılmadı.")
        os.replace(partial, MODEL_PATH)
        if progress:
            progress(downloaded, MODEL_FILE_SIZE, 0.0, 0)
    except LocalTranslationError:
        partial.unlink(missing_ok=True)
        raise
    except Exception as exc:
        # Keep a partial file so the next attempt can resume with HTTP Range.
        raise LocalTranslationError(f"Hy-MT2 indirilemedi; indirme kaldığı yerden sürdürülebilir: {exc}") from exc


def uninstall_english_turkish_model() -> bool:
    """Unload and remove model weights and any incomplete download only."""
    global _MODEL
    with _DOWNLOAD_LOCK, _INFERENCE_LOCK, _LOCK:
        if _MODEL is not None:
            close = getattr(_MODEL, "close", None)
            try:
                if callable(close):
                    close()
            except Exception as exc:
                raise LocalTranslationError(f"Model belleği güvenli biçimde kapatılamadı: {exc}") from exc
            _MODEL = None
            gc.collect()
        removed = False
        for path in (MODEL_PATH, MODEL_PATH.with_suffix(MODEL_PATH.suffix + ".part")):
            try:
                if path.is_file() or path.is_symlink():
                    path.unlink()
                    removed = True
            except OSError as exc:
                raise LocalTranslationError(
                    f"Model dosyası silinemedi: {path}\nUygulamayı yazma izni olan bir klasörden çalıştırıp tekrar dene.\n{exc}"
                ) from exc
        return removed


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
    payload = "\0".join((TRANSLATION_PIPELINE_VERSION, source, context, game_name, glossary))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cache_get(source: str, context: str = "", game_name: str = "") -> str | None:
    path = _cache_path()
    if not path.exists():
        return None
    try:
        with _CACHE_LOCK, closing(sqlite3.connect(path, timeout=30)) as db:
            db.execute("PRAGMA busy_timeout=30000")
            row = db.execute(
                "SELECT translated FROM memory WHERE source_hash=?",
                (_cache_key(source, context, game_name),),
            ).fetchone()
            return row[0] if row else None
    except sqlite3.Error:
        return None


def _cache_put(source: str, translated: str, context: str = "", game_name: str = "") -> None:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _CACHE_LOCK, closing(sqlite3.connect(path, timeout=30)) as db:
        db.execute("PRAGMA busy_timeout=30000")
        db.execute(
            "CREATE TABLE IF NOT EXISTS memory (source_hash TEXT PRIMARY KEY, source TEXT NOT NULL, translated TEXT NOT NULL)"
        )
        db.execute(
            "INSERT INTO memory(source_hash,source,translated) VALUES(?,?,?) "
            "ON CONFLICT(source_hash) DO UPDATE SET source=excluded.source, translated=excluded.translated",
            (_cache_key(source, context, game_name), source, translated),
        )
        db.commit()


def _get_model():
    global _MODEL
    with _LOCK:
        if _MODEL is not None:
            return _MODEL
        if not model_status()["installed"]:
            raise LocalTranslationError("Hy-MT2 1.8B modeli kurulu değil. Önce çeviri modelini indir.")
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise LocalTranslationError("llama-cpp bileşeni bulunamadı. Uygulamayı güncel paketle yeniden kur.") from exc
        try:
            _MODEL = Llama(
                model_path=str(MODEL_PATH),
                # Hy-MT2 documents an 8192-token context window.
                n_ctx=8192,
                n_threads=max(2, min(8, os.cpu_count() or 4)),
                n_threads_batch=max(2, min(8, os.cpu_count() or 4)),
                n_gpu_layers=0,
                verbose=False,
            )
        except Exception as exc:
            raise LocalTranslationError(f"Hy-MT2 çeviri motoru başlatılamadı: {exc}") from exc
        return _MODEL


def translate_text(text: str, context: str = "", game_name: str = "") -> str:
    """Translate English game text into Turkish with Tencent Hy-MT2, without chat behavior."""
    if not isinstance(text, str) or not text.strip():
        return text
    original_text = text
    cached = _cache_get(original_text, context, game_name)
    if cached is not None:
        if cached.strip() and not validate_translation(original_text, cached) and cached.casefold() != original_text.casefold():
            return cached

    # Translate each logical line independently. A single model response for a
    # multiline JSON string may collapse or add line breaks; preserving the
    # original separators here makes that impossible and keeps CRLF/LF intact.
    if re.search(r"\r\n|\r|\n", original_text):
        parts = re.split(r"(\r\n|\r|\n)", original_text)
        translated_parts = []
        for part in parts:
            if part in ("\r\n", "\r", "\n") or not part.strip():
                translated_parts.append(part)
            else:
                translated_parts.append(
                    translate_text(part, context=context, game_name=game_name)
                )
        result = "".join(translated_parts)
        issues = validate_translation(original_text, result)
        if issues:
            raise LocalTranslationError(
                "Çok satırlı metnin biçimi korunamadı: " + " ".join(issues)
            )
        _cache_put(original_text, result, context, game_name)
        return result

    tokens: list[tuple[str, str]] = []
    glossary = sorted(_glossary_terms().items(), key=lambda item: len(item[0]), reverse=True)
    for source_term, target_term in glossary:
        # Avoid forcing single words inside unrelated sentences.
        if len(source_term.split()) == 1 and text.strip().casefold() != source_term.casefold():
            continue
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
    context_block = context.strip()[:600]
    game_context = game_name.strip()[:100] or "video game"
    # Tencent's official GGUF example uses a direct translation instruction.
    prompt = (
        "Translate the following video-game text from English into Turkish, without additional explanation. "
        "Preserve meaning, character voice, tone, punctuation, line breaks and formatting. "
        "Use natural, idiomatic Turkish suitable for a game. Do not leave ordinary English words untranslated. "
        "Keep every SARMANTERM and SARMANPH placeholder exactly unchanged.\n"
        f"Game context: {game_context}.\n"
        + (f"Nearby context: {context_block}\n" if context_block else "")
        + f"Text: {protected}\n"
        + "Turkish:"
    )
    try:
        with _INFERENCE_LOCK:
            model = _get_model()
            response = model(
                prompt,
                max_tokens=min(4096, max(128, len(protected) * 3)),
                temperature=0.7,
                top_p=0.6,
                top_k=20,
                repeat_penalty=1.05,
                echo=False,
            )
        result = response["choices"][0]["text"].strip()
        result = re.sub(r"^(Turkish translation|Translation|Türkçe çeviri|Çeviri)\s*:\s*", "", result, flags=re.IGNORECASE)
        for marker, replacement in tokens:
            if result.count(marker) != 1:
                raise LocalTranslationError("Model bir oyun terimini veya yer tutucuyu kaybetti ya da çoğalttı; metin güvenli biçimde çevrilmedi.")
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
        raise LocalTranslationError(f"Hy-MT2 yerel çevirisi başarısız: {exc}") from exc


def glossary_items() -> list[tuple[str, str]]:
    return sorted(_glossary_terms().items(), key=lambda item: item[0].casefold())


def set_glossary_term(source: str, target: str) -> None:
    source, target = source.strip(), target.strip()
    if not source or not target:
        raise ValueError("Kaynak terim ve Türkçe karşılığı boş olamaz.")
    path = APP_DATA / "glossary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with _GLOSSARY_LOCK:
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
    with _GLOSSARY_LOCK:
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

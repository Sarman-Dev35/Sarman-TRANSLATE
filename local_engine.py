from __future__ import annotations

import hashlib
import re
import sqlite3
import threading
from pathlib import Path

from translation_core import validate_translation

APP_DATA = Path(__import__("os").environ.get("LOCALAPPDATA", Path.home())) / "Sarman" / "TRANSLATE"
MODEL_SOURCE = "en"
MODEL_TARGET = "tr"
_LOCK = threading.RLock()
_TOKEN_RE = re.compile(r"\{[^{}]+\}|\$\{[^{}]+\}|\$[A-Za-z_][A-Za-z0-9_]*|%(?:\d+\$)?[-+#0 ]*(?:\d+|\*)?(?:\.(?:\d+|\*))?[a-zA-Z%]|\[[A-Za-z0-9_.:-]+\]|<[^>]+>|\\[nrt]|\\u[0-9a-fA-F]{4}")


class LocalTranslationError(RuntimeError):
    pass


def model_status() -> dict:
    try:
        import argostranslate.translate
        languages = argostranslate.translate.get_installed_languages()
        source = next((x for x in languages if x.code == MODEL_SOURCE), None)
        target = next((x for x in languages if x.code == MODEL_TARGET), None)
        installed = bool(source and target and source.get_translation(target))
        return {"installed": installed, "source": "English", "target": "Türkçe",
                "engine": "Argos Translate", "message": "Yerel model hazır." if installed else "İngilizce → Türkçe modeli henüz kurulmadı."}
    except ImportError:
        return {"installed": False, "source": "English", "target": "Türkçe",
                "engine": "Argos Translate", "message": "Yerel çeviri bileşeni yüklenmemiş."}


def install_english_turkish_model(progress=None) -> None:
    """Download and install the official Argos English→Turkish package once."""
    try:
        import argostranslate.package
    except ImportError as exc:
        raise LocalTranslationError("Argos Translate bileşeni kurulu değil.") from exc
    try:
        with _LOCK:
            argostranslate.package.update_package_index()
            packages = argostranslate.package.get_available_packages()
            package = next((p for p in packages if p.from_code == MODEL_SOURCE and p.to_code == MODEL_TARGET), None)
            if package is None:
                raise LocalTranslationError("İngilizce → Türkçe yerel model paketi bulunamadı.")
            path = package.download()
            argostranslate.package.install_from_path(path)
    except LocalTranslationError:
        raise
    except Exception as exc:
        raise LocalTranslationError(f"Yerel model indirilemedi/kurulamadı: {exc}") from exc


def _cache_path() -> Path:
    return APP_DATA / "translation-memory.sqlite3"


def _cache_key(source: str) -> str:
    import json
    glossary = json.dumps(_glossary_terms(), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256((source + "\\0" + glossary).encode("utf-8")).hexdigest()


def _cache_get(source: str) -> str | None:
    path = _cache_path()
    if not path.exists():
        return None
    with sqlite3.connect(path, timeout=5) as db:
        row = db.execute("SELECT translated FROM memory WHERE source_hash=?", (_cache_key(source),)).fetchone()
        return row[0] if row else None


def _cache_put(source: str, translated: str) -> None:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=5) as db:
        db.execute("CREATE TABLE IF NOT EXISTS memory (source_hash TEXT PRIMARY KEY, source TEXT NOT NULL, translated TEXT NOT NULL)")
        db.execute("INSERT INTO memory(source_hash,source,translated) VALUES(?,?,?) ON CONFLICT(source_hash) DO UPDATE SET translated=excluded.translated",
                   (hashlib.sha256(source.encode("utf-8")).hexdigest(), source, translated))


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


def _glossary_terms():
    terms = dict(DEFAULT_GLOSSARY)
    path = APP_DATA / "glossary.json"
    try:
        import json
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            terms.update({str(k): str(v) for k, v in data.items() if str(k).strip() and str(v).strip()})
    except (OSError, ValueError, TypeError):
        pass
    return terms


def translate_text(text: str) -> str:
    """Translate one English string offline; cache hits never invoke the model."""
    if not isinstance(text, str) or not text.strip():
        return text
    original_text = text
    cached = _cache_get(original_text)
    if cached is not None:
        return cached
    try:
        import argostranslate.translate
        languages = argostranslate.translate.get_installed_languages()
        source = next((x for x in languages if x.code == MODEL_SOURCE), None)
        target = next((x for x in languages if x.code == MODEL_TARGET), None)
        translator = source.get_translation(target) if source and target else None
        if translator is None:
            raise LocalTranslationError("İngilizce → Türkçe modeli kurulu değil. Önce Yerel Model bölümünden indir.")
        tokens = []
        # Protect approved game terminology first so the model cannot mistranslate it.
        glossary = sorted(_glossary_terms().items(), key=lambda item: len(item[0]), reverse=True)
        for source_term, target_term in glossary:
            if re.search(r"(?<!\\w)" + re.escape(source_term) + r"(?!\\w)", text, re.IGNORECASE):
                marker = f" SARMANTERM{len(tokens):04d}X "
                text = re.sub(r"(?<!\\w)" + re.escape(source_term) + r"(?!\\w)", lambda _m, v=marker: v, text, flags=re.IGNORECASE)
                tokens.append((marker, target_term))
        def protect(match):
            token = f" SARMANPH{len(tokens):04d}X "
            tokens.append((token, match.group(0)))
            return token
        protected = _TOKEN_RE.sub(protect, text)
        result = translator.translate(protected)
        for token, original in tokens:
            result = result.replace(token.strip(), original).replace(token, original)
        issues = validate_translation(original_text, result)
        if issues:
            raise LocalTranslationError("Model çevirisi oyun değişkenlerini/biçimini koruyamadı: " + " ".join(issues))
        _cache_put(original_text, result)
        return result
    except LocalTranslationError:
        raise
    except Exception as exc:
        raise LocalTranslationError(f"Yerel çeviri başarısız: {exc}") from exc


def glossary_items() -> list[tuple[str, str]]:
    return sorted(_glossary_terms().items(), key=lambda item: item[0].casefold())


def set_glossary_term(source: str, target: str) -> None:
    import json
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
    import json
    path = APP_DATA / "glossary.json"
    if not path.exists():
        return
    try:
        custom = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(custom, dict) and source in custom:
            del custom[source]
            path.write_text(json.dumps(custom, ensure_ascii=False, indent=2), encoding="utf-8")
    except (OSError, ValueError):
        return

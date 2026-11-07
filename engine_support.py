from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

TEXT_SUFFIXES = {".json", ".csv", ".txt", ".ini"}


@dataclass(frozen=True)
class EngineReport:
    engine: str
    confidence: str
    supported_text_files: int
    native_localization_files: int
    status: str
    guidance: str


def inspect_game_engine(game_dir: str | Path) -> EngineReport:
    """Read-only engine fingerprinting. Never unpacks, modifies or executes game files."""
    root = Path(game_dir).resolve()
    if not root.is_dir():
        raise ValueError("Oyun klasörü bulunamadı.")

    names: set[str] = set()
    suffixes: set[str] = set()
    supported = 0
    native = 0
    visited = 0
    for current, dirs, files in __import__("os").walk(root, topdown=True, followlinks=False):
        dirs[:] = [d for d in dirs if d.casefold() not in {
            ".git", "cache", "caches", "logs", "crashdumps", "node_modules", "__pycache__"
        } and not (Path(current) / d).is_symlink()]
        for name in files:
            path = Path(current) / name
            if path.is_symlink():
                continue
            visited += 1
            if visited > 12000:
                break
            names.add(name.casefold())
            suffix = path.suffix.casefold()
            suffixes.add(suffix)
            if suffix in TEXT_SUFFIXES:
                supported += 1
            if suffix in {".locres", ".locmeta", ".assets", ".bundle", ".pak", ".utoc", ".pck", ".win", ".unx"}:
                native += 1
        if visited > 12000:
            break

    if "data.win" in names or "game.unx" in names or any(n.startswith("audiogroup") and n.endswith(".dat") for n in names):
        engine, confidence = "GameMaker", "Yüksek"
        guidance = "data.win/game.unx içindeki STRG metinleri mevcut tarayıcı tarafından açılmaz. UndertaleModTool tabanlı, kullanıcı tarafından sağlanan ayrı bir adaptör gerekir; şu an yalnızca dışarıdaki JSON/CSV/TXT/INI dosyaları çevrilebilir."
        status = "Özel motor biçimi henüz desteklenmiyor"
    elif "unityplayer.dll" in names or "globalgamemanagers" in names or "gameassembly.dll" in names:
        engine, confidence = "Unity", "Yüksek"
        guidance = "Unity AssetBundle/.assets dosyaları doğrudan değiştirilmez. Şu an yalnızca açık metin dosyaları çevrilebilir; Unity Localization StreamingAssets JSON tabloları uygunsa desteklenebilir."
        status = "Kısmi destek · açık metin dosyaları"
    elif any(n.endswith(".pak") or n.endswith(".utoc") for n in names) or "ue4game.exe" in names:
        engine, confidence = "Unreal Engine", "Orta/Yüksek"
        guidance = ".locres/.pak/.utoc dosyaları ikili/engine biçimleridir ve mevcut çeviri motoru bunları düzenlemez. Unreal için sürüme uygun çıkarma/yeniden paketleme adaptörü gerekir."
        status = "Özel motor biçimi henüz desteklenmiyor"
    elif any(n.endswith(".pck") for n in names) or "godot" in names:
        engine, confidence = "Godot", "Orta"
        guidance = "Godot PCK arşivleri bu sürümde açılmaz. Harici JSON/CSV/TXT/INI dil dosyaları çevrilebilir."
        status = "Kısmi destek · açık metin dosyaları"
    elif "renpy" in names or ".rpy" in suffixes or ".rpyc" in suffixes:
        engine, confidence = "Ren'Py", "Orta"
        guidance = "Ren'Py'nin .rpy/.rpyc kaynakları için yerleşik çeviri yapısı vardır; bu sürüm yalnızca açık JSON/CSV/TXT/INI dosyalarını işler."
        status = "Kısmi destek · açık metin dosyaları"
    elif "www" in {p.name.casefold() for p in root.iterdir() if p.is_dir()} and (root / "www" / "data").is_dir():
        engine, confidence = "RPG Maker MV/MZ", "Orta"
        guidance = "www/data içindeki JSON verileri desteklenen JSON tarayıcısıyla incelenebilir. Şifreli oyun verileri bu sürümde açılmaz."
        status = "JSON dosyaları için destek mevcut"
    else:
        engine, confidence = "Belirlenemedi", "Düşük"
        guidance = "Motor kesin belirlenemedi. Uygulama yalnızca desteklenen açık metin dosyalarını tarar; ikili arşivleri değiştirmez."
        status = "Genel metin taraması"

    return EngineReport(engine, confidence, supported, native, status, guidance)

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

@dataclass
class Game:
    name: str
    platform: str
    path: str
    app_id: str = ""
    detected_languages: tuple[str, ...] = ()

def _normal(path: Path) -> str:
    try:
        return os.path.normcase(str(path.resolve()))
    except (OSError, RuntimeError, ValueError):
        return os.path.normcase(os.path.abspath(str(path)))

def _steam_roots() -> set[Path]:
    roots: set[Path] = set()
    candidates = [
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Steam",
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Steam",
        Path.home() / "Steam",
    ]
    if sys.platform == "win32":
        try:
            import winreg
            locations = [
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
            ]
            for hive, key, value_name in locations:
                try:
                    with winreg.OpenKey(hive, key) as handle:
                        value, _ = winreg.QueryValueEx(handle, value_name)
                        if value:
                            candidates.append(Path(value))
                except OSError:
                    pass
        except ImportError:
            pass
    for steam in candidates:
        if (steam / "steamapps").is_dir():
            roots.add(steam)
            vdf = steam / "steamapps" / "libraryfolders.vdf"
            if vdf.is_file():
                try:
                    raw = vdf.read_text(encoding="utf-8", errors="ignore")
                    for value in re.findall(r'"path"\s*"((?:\\\\.|[^"])*)"', raw):
                        decoded = value.replace("\\\\", "\\").replace("\\/", "/")
                        library = Path(decoded)
                        if (library / "steamapps").is_dir():
                            roots.add(library)
                except OSError:
                    continue
    return roots

def _scan_steam() -> list[Game]:
    games: list[Game] = []
    for library in _steam_roots():
        apps = library / "steamapps"
        for manifest in apps.glob("appmanifest_*.acf"):
            try:
                raw = manifest.read_text(encoding="utf-8", errors="ignore")
                name = re.search(r'"name"\s*"([^"]+)"', raw)
                appid = re.search(r'"appid"\s*"?([0-9]+)"?', raw)
                install = re.search(r'"installdir"\s*"([^"]+)"', raw)
                if not (name and install):
                    continue
                folder = apps / "common" / install.group(1)
                if folder.is_dir():
                    games.append(Game(name.group(1), "Steam · kurulu", str(folder), appid.group(1) if appid else ""))
            except OSError:
                continue
    return games

def _scan_epic() -> list[Game]:
    games: list[Game] = []
    manifest_dir = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    if not manifest_dir.is_dir():
        return games
    for item in manifest_dir.glob("*.item"):
        try:
            data = json.loads(item.read_text(encoding="utf-8"))
            location = data.get("InstallLocation")
            if not location:
                continue
            folder = Path(location)
            if folder.is_dir():
                title = data.get("DisplayName") or data.get("AppName") or folder.name
                games.append(Game(str(title), "Epic Games · kurulu", str(folder), str(data.get("AppName", ""))))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
    return games

def _read_game_config_store() -> list[Game]:
    """Read Windows' locally registered game executable records; never reads account credentials."""
    if sys.platform != "win32":
        return []
    try:
        import winreg
    except ImportError:
        return []
    results: list[Game] = []
    locations = [
        (winreg.HKEY_CURRENT_USER, r"System\GameConfigStore\Children"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\GameConfigStore\Children"),
    ]
    for hive, subkey in locations:
        try:
            with winreg.OpenKey(hive, subkey) as parent:
                count = winreg.QueryInfoKey(parent)[0]
                children = [winreg.EnumKey(parent, i) for i in range(count)]
        except OSError:
            continue
        for child in children:
            try:
                with winreg.OpenKey(hive, subkey + "\\" + child) as entry:
                    values = {}
                    value_count = winreg.QueryInfoKey(entry)[1]
                    for index in range(value_count):
                        try:
                            key, value, _ = winreg.EnumValue(entry, index)
                            values[key.casefold()] = value
                        except OSError:
                            continue
                exe_value = values.get("matchedexefullpath") or values.get("matchedexefilename")
                if not exe_value:
                    continue
                exe = Path(str(exe_value).strip('"'))
                if not exe.is_absolute() or not exe.is_file():
                    continue
                folder = exe.parent
                package_root = next((parent for parent in (folder, *folder.parents[:5]) if (parent / "AppxManifest.xml").is_file()), None)
                if package_root:
                    folder = package_root
                    package_name = package_root.name.split("_")[0]
                    display = values.get("displayname") or values.get("name") or package_name
                    platform = "Microsoft Store / Xbox · kurulu"
                else:
                    # The GameConfigStore record is Windows' game registration signal.
                    display = values.get("name") or values.get("title") or exe.stem
                    platform = "Windows oyun kaydı"
                    # Keep the game root conservative: avoid climbing out of known game libraries.
                    if folder.name.casefold() in {"win64", "win32", "binaries", "bin"} and folder.parent != folder:
                        folder = folder.parent
                results.append(Game(str(display), platform, str(folder), child))
            except (OSError, TypeError, ValueError):
                continue
    return results

def _scan_xbox_games_folder() -> list[Game]:
    games: list[Game] = []
    roots = [Path(os.environ.get("SYSTEMDRIVE", "C:") + r"\XboxGames"), Path("D:/XboxGames")]
    excluded = ("unins", "uninstall", "setup", "redist", "crashreport", "crashhandler", "helper")
    for root in roots:
        if not root.is_dir():
            continue
        try:
            children = [p for p in root.iterdir() if p.is_dir()]
        except OSError:
            continue
        for folder in children:
            candidates: list[Path] = []
            try:
                for current, dirs, files in os.walk(folder):
                    depth = len(Path(current).relative_to(folder).parts)
                    dirs[:] = dirs[:30] if depth < 3 else []
                    for filename in files:
                        low = filename.casefold()
                        if low.endswith(".exe") and not any(token in low for token in excluded):
                            candidates.append(Path(current) / filename)
                    if len(candidates) >= 8:
                        break
            except (OSError, ValueError):
                continue
            if candidates:
                # Prefer an executable whose stem resembles the game folder.
                candidates.sort(key=lambda p: (folder.name.casefold() not in p.stem.casefold(), len(p.parts), p.name.casefold()))
                games.append(Game(folder.name, "Xbox uygulaması · kurulu", str(folder), candidates[0].stem))
    return games

def _scan_user_game_folders(extra_roots: Iterable[str] = ()) -> list[Game]:
    games: list[Game] = []
    roots = [Path("D:/Games"), Path("D:/Oyunlar"), Path.home() / "Games", Path.home() / "Oyunlar"] + [Path(p).expanduser() for p in extra_roots]
    ignored = {"common files", "windowsapps", "windows", "microsoft", "nvidia corporation", "python", "nodejs"}
    excluded = ("unins", "uninstall", "setup", "redist", "crashreport", "crashhandler", "updater")
    custom_set = {os.path.normcase(os.path.abspath(str(Path(p).expanduser()))) for p in extra_roots}
    for root in roots:
        if not root.is_dir():
            continue
        try:
            folders = [p for p in root.iterdir() if p.is_dir() and p.name.casefold() not in ignored]
            if os.path.normcase(os.path.abspath(str(root))) in custom_set:
                folders.insert(0, root)
        except OSError:
            continue
        for folder in folders:
            try:
                executables = [p for p in folder.glob("*.exe") if not any(x in p.name.casefold() for x in excluded)]
                if not executables:
                    # One level down is common for user-managed game folders.
                    for nested in folder.iterdir():
                        if nested.is_dir():
                            executables.extend(p for p in nested.glob("*.exe") if not any(x in p.name.casefold() for x in excluded))
                if executables:
                    executables.sort(key=lambda p: (folder.name.casefold() not in p.stem.casefold(), p.name.casefold()))
                    games.append(Game(folder.name, "Özel oyun klasörü · aday", str(folder), executables[0].stem))
            except OSError:
                continue
    return games


_LANGUAGE_CODES = {
    "tr": "TR", "tur": "TR", "turkish": "TR", "tr-tr": "TR",
    "en": "EN", "eng": "EN", "english": "EN", "en-us": "EN", "en-gb": "EN",
    "de": "DE", "ger": "DE", "german": "DE", "de-de": "DE",
    "fr": "FR", "fre": "FR", "french": "FR", "fr-fr": "FR",
    "es": "ES", "spa": "ES", "spanish": "ES", "es-es": "ES",
    "it": "IT", "ita": "IT", "italian": "IT",
    "pt": "PT", "por": "PT", "portuguese": "PT", "pt-br": "PT", "pt-pt": "PT",
    "ru": "RU", "rus": "RU", "russian": "RU",
    "ja": "JA", "jpn": "JA", "japanese": "JA", "jp": "JA",
    "ko": "KO", "kor": "KO", "korean": "KO",
    "zh": "ZH", "zho": "ZH", "chinese": "ZH", "zh-cn": "ZH", "zh-tw": "ZH",
    "pl": "PL", "pol": "PL", "polish": "PL",
    "nl": "NL", "dut": "NL", "dutch": "NL",
    "ar": "AR", "ara": "AR", "arabic": "AR",
    "hi": "HI", "hin": "HI", "hindi": "HI",
    "id": "ID", "ind": "ID", "indonesian": "ID",
    "uk": "UK", "ukr": "UK", "ukrainian": "UK",
    "sv": "SV", "swe": "SV", "swedish": "SV",
    "no": "NO", "nor": "NO", "norwegian": "NO",
    "da": "DA", "dan": "DA", "danish": "DA",
    "fi": "FI", "fin": "FI", "finnish": "FI",
    "cs": "CS", "ces": "CS", "czech": "CS",
    "hu": "HU", "hun": "HU", "hungarian": "HU",
    "el": "EL", "ell": "EL", "greek": "EL",
    "he": "HE", "heb": "HE", "hebrew": "HE",
    "ro": "RO", "ron": "RO", "romanian": "RO",
    "bg": "BG", "bul": "BG", "bulgarian": "BG",
    "hr": "HR", "hrv": "HR", "croatian": "HR",
    "sk": "SK", "slk": "SK", "slovak": "SK",
    "sl": "SL", "slv": "SL", "slovenian": "SL",
    "sr": "SR", "srp": "SR", "serbian": "SR",
}
_LANGUAGE_FILE = re.compile(
    r"(?:^|[._-])(" + "|".join(sorted(map(re.escape, _LANGUAGE_CODES), key=len, reverse=True)) + r")(?:[._-]|$)",
    re.I,
)
_LOCALE_DIRS = {"locale", "locales", "lang", "langs", "language", "languages", "localization", "translations", "text"}

def _detect_language_files(game_root: Path) -> tuple[str, ...]:
    """Detect locales only from supported text files and recognizable locale folders."""
    found: set[str] = set()
    scanned = 0
    visited_dirs = 0
    try:
        for current, dirs, files in os.walk(game_root):
            visited_dirs += 1
            if visited_dirs > 1500:
                break
            rel = Path(current).relative_to(game_root)
            dirs[:] = [
                d for d in dirs
                if d.casefold() not in {
                    "engine", "plugins", "thirdparty", "redist", "redistributable",
                    "crashreporter", "__pycache__",
                }
            ]
            locale_context = any(part.casefold() in _LOCALE_DIRS for part in rel.parts)
            for part in rel.parts:
                token = part.casefold()
                if locale_context or len(token) > 3 or re.fullmatch(r"[a-z]{2,3}[-_][a-z]{2,4}", token):
                    code = _LANGUAGE_CODES.get(token.replace("_", "-"))
                    if code:
                        found.add(code)
            for filename in files:
                scanned += 1
                if scanned > 5000:
                    return tuple(sorted(found))
                if Path(filename).suffix.casefold() not in {".json", ".csv", ".txt", ".ini"}:
                    continue
                match = _LANGUAGE_FILE.search(Path(filename).stem.replace('_', '-'))
                if match:
                    code = _LANGUAGE_CODES.get(match.group(1).casefold().replace("_", "-"))
                    if code:
                        found.add(code)
    except (OSError, ValueError, RuntimeError):
        pass
    return tuple(sorted(found))


def discover_games(extra_roots: Iterable[str] = ()) -> list[Game]:
    """Discover installed games while isolating inaccessible or malformed platform records."""
    discovered: list[Game] = []
    scanners = (
        _scan_steam,
        _scan_epic,
        _read_game_config_store,
        _scan_xbox_games_folder,
        lambda: _scan_user_game_folders(extra_roots),
    )
    for scanner in scanners:
        try:
            discovered.extend(scanner())
        except (OSError, RuntimeError, ValueError, TypeError):
            # A broken library/registry entry must not abort every other source.
            continue

    unique: dict[str, Game] = {}
    priority = ("Steam", "Epic Games", "Microsoft Store", "Xbox", "Windows oyun kaydı")
    for game in discovered:
        try:
            key = _normal(Path(game.path))
        except (OSError, RuntimeError, ValueError, TypeError):
            continue
        existing = unique.get(key)
        if existing is None:
            unique[key] = game
        elif any(tag in game.platform for tag in priority) and not any(tag in existing.platform for tag in priority):
            unique[key] = game

    enriched = []
    for game in unique.values():
        try:
            languages = _detect_language_files(Path(game.path))
        except (OSError, RuntimeError, ValueError, TypeError):
            languages = ()
        enriched.append(Game(
            name=game.name, platform=game.platform, path=game.path,
            app_id=game.app_id, detected_languages=languages,
        ))
    return sorted(enriched, key=lambda item: item.name.casefold())

from __future__ import annotations

import csv
import io
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

SUPPORTED = {".json", ".csv", ".txt", ".ini"}
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", "binaries", "bin", "cache", "caches", "logs", "crashdumps"}
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_FILES = 5000
MAX_DIRECTORIES = 20000
MAX_ENTRIES = 30000

_LANGUAGE_ALIASES = {
    "en": "EN", "eng": "EN", "english": "EN", "en-us": "EN", "en-gb": "EN",
    "tr": "TR", "tur": "TR", "turkish": "TR", "tr-tr": "TR",
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


def _language_code(value: str) -> str | None:
    token = str(value).strip().casefold().replace("_", "-")
    return _LANGUAGE_ALIASES.get(token)


def _language_for_path(path: Path) -> str | None:
    for part in path.parts:
        candidates = [part.casefold().replace("_", "-")]
        candidates.extend(re.split(r"[^a-z0-9-]+", Path(part).stem.casefold()))
        for candidate in candidates:
            code = _language_code(candidate)
            if code:
                return code
    return None


class StaleSourceError(ValueError):
    """Raised when a game text changed after the translation workspace was scanned."""


PLACEHOLDER_RE = re.compile(
    r"\{[^{}]+\}|\$\{[^{}]+\}|\$[A-Za-z_][A-Za-z0-9_]*|%(?:\d+\$)?[-+#0 ]*(?:\d+|\*)?(?:\.(?:\d+|\*))?[a-zA-Z%]|"
    r"\[[A-Za-z0-9_.:-]+\]|<[^>]+>|\\[nrt]|\\u[0-9a-fA-F]{4}"
)

@dataclass
class TextEntry:
    entry_id: str
    file: str
    locator: str
    source: str
    translated: str = ""
    status: str = "pending"

    def to_dict(self):
        return asdict(self)


def _is_translatable(value: str) -> bool:
    value = value.strip()
    if len(value) < 2 or len(value) > 5000 or not any(ch.isalpha() for ch in value):
        return False
    if value.startswith(("http://", "https://", "www.", "GUID:", "0x")):
        return False
    if len(value) > 2 and value[1] == ":" and value[2] in ("/", chr(92)):
        return False
    if value.startswith(("./", "../", "/")):
        return False
    if value.casefold() in {"true", "false", "yes", "no", "on", "off", "enabled", "disabled", "null", "none"}:
        return False
    try:
        float(value)
        return False
    except ValueError:
        pass
    if Path(value).suffix.casefold() in {".exe", ".dll", ".pak", ".png", ".jpg", ".jpeg", ".asset", ".dat", ".bin"}:
        return False
    return True

def _entry(file: Path, root: Path, locator: str, value: str) -> TextEntry | None:
    leaf = locator.rsplit("/", 1)[-1] if locator.startswith("/") else locator.replace("[", ".").replace("]", "").split(".")[-1]
    if locator.startswith("/"):
        leaf = leaf.replace("~1", "/").replace("~0", "~")
    leaf = leaf.casefold()
    if leaf in {"id", "uuid", "guid", "appid", "assetid", "objectid"}:
        return None
    if not _is_translatable(value):
        return None
    relative = file.relative_to(root).as_posix()
    entry_id = f"{relative}::{locator}"
    return TextEntry(entry_id, relative, locator, value)


def scan_game_texts(
    game_dir: str | Path, include_txt: bool = True, source_language: str = "EN"
) -> list[TextEntry]:
    """Scan supported text files, preferring the selected source-language locale."""
    root = Path(game_dir).resolve()
    selected_language = _language_code(source_language) or str(source_language).upper()
    if not root.is_dir():
        raise ValueError("Oyun klasörü bulunamadı.")
    entries: list[TextEntry] = []
    visited_files = 0
    visited_dirs = 0
    stop = False
    # Prune irrelevant directories during traversal instead of walking all game assets.
    for current, dirs, filenames in os.walk(root, topdown=True, followlinks=False):
        visited_dirs += 1
        if visited_dirs > MAX_DIRECTORIES:
            break
        current_path = Path(current)
        dirs[:] = sorted(
            name for name in dirs
            if name.casefold() not in SKIP_DIRS and not (current_path / name).is_symlink()
        )
        for filename in sorted(filenames):
            file = current_path / filename
            if file.is_symlink() or file.suffix.casefold() not in SUPPORTED:
                continue
            file_language = _language_for_path(file.relative_to(root))
            if file_language and file_language != selected_language:
                continue
            visited_files += 1
            if visited_files > MAX_FILES:
                stop = True
                break
            try:
                if file.stat().st_size > MAX_FILE_BYTES:
                    continue
                text = file.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError):
                continue
            suffix = file.suffix.casefold()
            found: list[TextEntry] = []
            try:
                if suffix == ".json":
                    data = json.loads(text)

                    def walk(node, path=()):
                        if isinstance(node, dict):
                            for key, val in node.items():
                                walk(val, path + (str(key),))
                        elif isinstance(node, list):
                            for index, val in enumerate(node):
                                walk(val, path + (str(index),))
                        elif isinstance(node, str):
                            # JSON Pointer escaping makes unusual keys reversible.
                            locator = "" if not path else "/" + "/".join(part.replace("~", "~0").replace("/", "~1") for part in path)
                            item = _entry(file, root, locator, node)
                            if item:
                                found.append(item)

                    walk(data)
                elif suffix == ".csv":
                    try:
                        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
                    except csv.Error:
                        dialect = csv.excel
                    rows = list(csv.reader(io.StringIO(text, newline=""), dialect=dialect))
                    if rows:
                        header = [x.casefold().strip() for x in rows[0]]
                        id_names = {"id", "key", "identifier", "translation", "target"}
                        language_cols = [
                            i for i, name in enumerate(header)
                            if _language_code(name.replace(" ", "-")) == selected_language
                        ]
                        source_cols = [
                            i for i, name in enumerate(header)
                            if name in {"source", "original", "text", "value", "string", "dialog", "dialogue", "description", "message"}
                            or any(token in name for token in ("source", "original", "dialogue", "description"))
                        ]
                        text_cols = language_cols[:1] or source_cols[:1]
                        has_header = bool(text_cols) or any(name in id_names for name in header) or any(
                            _language_code(name.replace(" ", "-")) is not None for name in header
                        )
                        if not text_cols:
                            candidates = [i for i, name in enumerate(header) if name not in id_names]
                            text_cols = candidates[:1] if has_header else list(range(min(len(rows[0]), 8)))
                        row_start = 1 if has_header else 0
                        for row_index, row in enumerate(rows[row_start:], start=row_start):
                            for column_index in text_cols:
                                if column_index < len(row):
                                    item = _entry(file, root, f"row[{row_index}].col[{column_index}]", row[column_index])
                                    if item:
                                        found.append(item)
                elif suffix == ".ini":
                    for line_index, line in enumerate(text.splitlines()):
                        stripped = line.strip()
                        if not stripped or stripped.startswith((";", "#", "[")) or "=" not in line:
                            continue
                        _, raw_value = line.split("=", 1)
                        value = raw_value.strip()
                        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                            value = value[1:-1]
                        item = _entry(file, root, f"line[{line_index}]", value)
                        if item:
                            found.append(item)
                elif suffix == ".txt" and include_txt:
                    for line_index, line in enumerate(text.splitlines()):
                        item = _entry(file, root, f"line[{line_index}]", line)
                        if item:
                            found.append(item)
            except (ValueError, csv.Error, json.JSONDecodeError):
                continue
            entries.extend(found)
            if len(entries) >= MAX_ENTRIES:
                entries = entries[:MAX_ENTRIES]
                stop = True
                break
        if stop:
            break
    unique = {}
    for item in entries:
        unique[item.entry_id] = item
    return list(unique.values())

def placeholder_signature(text: str) -> list[str]:
    return PLACEHOLDER_RE.findall(text)


def validate_translation(source: str, translated: str) -> list[str]:
    issues = []
    if not translated.strip():
        issues.append("Çeviri boş.")
    if placeholder_signature(source) != placeholder_signature(translated):
        issues.append("Değişken veya biçim kodları kaynak metinle eşleşmiyor.")
    if translated.count("\n") != source.count("\n"):
        issues.append("Satır sonu sayısı değişti.")
    return issues


def save_workspace(path: str | Path, game_dir: str | Path, entries: Iterable[TextEntry]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "game_dir": str(Path(game_dir).resolve()), "entries": [e.to_dict() for e in entries]}
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, destination)


def load_workspace(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("entries"), list):
        raise ValueError("Çeviri çalışma dosyası desteklenmiyor veya bozuk.")
    return data


def build_translated_files(game_dir: str | Path, entries: Iterable[TextEntry]) -> dict[str, bytes]:
    """Return modified copies for supported round-trip formats; never writes to the game directory."""
    import io
    from collections import defaultdict

    root = Path(game_dir).resolve()
    entries = list(entries)
    grouped = defaultdict(list)
    translated_entries = [entry for entry in entries if entry.translated.strip()]
    invalid_entries = [
        entry for entry in translated_entries
        if validate_translation(entry.source, entry.translated)
    ]
    if invalid_entries:
        sample = invalid_entries[0]
        raise ValueError(
            f"{len(invalid_entries)} çeviri dışa aktarılamıyor. "
            f"İlk sorun: {sample.file} · {sample.locator}. "
            "Değişkenleri ({player_name}, %s vb.) ve satır sonlarını koruyup düzelt."
        )
    for entry in translated_entries:
        grouped[entry.file].append(entry)
    output: dict[str, bytes] = {}
    for relative, items in grouped.items():
        source_path = (root / _safe_workspace_path(relative)).resolve()
        if root not in source_path.parents:
            raise ValueError("Çalışma dosyasında oyun klasörü dışına çıkan kaynak yolu bulundu.")
        if not source_path.is_file():
            raise StaleSourceError(f"{relative}: kaynak dosya artık bulunamıyor. Yeniden tara.")
        try:
            source_bytes = source_path.read_bytes()
            had_bom = source_bytes.startswith(b"\xef\xbb\xbf")
            raw = source_bytes.decode("utf-8-sig")
        except (OSError, UnicodeError) as exc:
            raise StaleSourceError(f"{relative}: kaynak dosya okunamıyor. Dosya değişmiş veya UTF-8 dışı olabilir.") from exc
        suffix = source_path.suffix.casefold()
        newline = "\r\n" if "\r\n" in raw else ("\r" if "\r" in raw and "\n" not in raw else "\n")
        try:
            if suffix == ".json":
                data = json.loads(raw)
                for item in items:
                    if item.locator == "":
                        if data != item.source:
                            raise StaleSourceError(f"{relative}: kaynak metin taramadan sonra değişmiş. Yeniden tara.")
                        data = item.translated
                        continue
                    if item.locator.startswith("/"):
                        keys = [
                            part.replace("~1", "/").replace("~0", "~")
                            for part in item.locator[1:].split("/")
                        ]
                    else:
                        # Backward compatibility for older workspace locator format.
                        locator = item.locator.removeprefix("root").lstrip(".")
                        if not locator:
                            raise StaleSourceError(f"{relative}: kayıtlı JSON konumu geçersiz. Metinleri yeniden tara.")
                        keys = []
                        token = ""
                        index = 0
                        while index < len(locator):
                            char = locator[index]
                            if char == ".":
                                if token:
                                    keys.append(token)
                                    token = ""
                            elif char == "[":
                                if token:
                                    keys.append(token)
                                    token = ""
                                end = locator.find("]", index + 1)
                                if end < 0:
                                    raise ValueError("Geçersiz JSON konumu")
                                number = locator[index + 1:end]
                                if not number.isdigit():
                                    raise ValueError("Geçersiz JSON dizi konumu")
                                keys.append(int(number))
                                index = end
                            else:
                                token += char
                            index += 1
                        if token:
                            keys.append(token)
                    node = data
                    for key in keys[:-1]:
                        node = node[int(key)] if isinstance(node, list) else node[key]
                    if not keys:
                        raise StaleSourceError(f"{relative}: kayıtlı JSON konumu geçersiz. Metinleri yeniden tara.")
                    last = int(keys[-1]) if isinstance(node, list) else keys[-1]
                    if node[last] != item.source:
                        raise StaleSourceError(f"{relative}: kaynak metin taramadan sonra değişmiş. Yeniden tara.")
                    node[last] = item.translated
                # Preserve source indentation, ASCII escaping and final newline.
                indent_match = re.search(r"\n([ \t]+)[^ \t\r\n]", raw)
                indent = indent_match.group(1) if indent_match else None
                ensure_ascii = bool(re.search(r"\\u[0-9a-fA-F]{4}", raw)) and not any(ord(ch) > 127 for ch in raw)
                compact = "\n" not in raw and not re.search(r":\s|,\s", raw)
                separators = (",", ":") if compact else None
                encoded = json.dumps(data, ensure_ascii=ensure_ascii, indent=indent, separators=separators)
                if newline != "\n":
                    encoded = encoded.replace("\n", newline)
                if raw.endswith(("\n", "\r")):
                    encoded += newline
            elif suffix == ".csv":
                # Retain delimiters, quoting and escaping from CSV/TSV source files.
                try:
                    dialect = csv.Sniffer().sniff(raw[:8192], delimiters=",;\t|")
                except csv.Error:
                    dialect = csv.excel
                rows = list(csv.reader(io.StringIO(raw, newline=""), dialect=dialect))
                for item in items:
                    match = re.fullmatch(r"row\[(\d+)\]\.col\[(\d+)\]", item.locator)
                    if match:
                        ri, ci = map(int, match.groups())
                        if ri >= len(rows) or ci >= len(rows[ri]):
                            raise StaleSourceError(f"{relative}: CSV konumu artık bulunamıyor. Metinleri yeniden tara.")
                        if rows[ri][ci] != item.source:
                            raise StaleSourceError(f"{relative}: kaynak metin taramadan sonra değişmiş. Yeniden tara.")
                        rows[ri][ci] = item.translated
                    else:
                        raise StaleSourceError(f"{relative}: kayıtlı CSV konumu geçersiz. Metinleri yeniden tara.")
                buffer = io.StringIO(newline="")
                dialect.lineterminator = newline
                csv.writer(buffer, dialect=dialect).writerows(rows)
                encoded = buffer.getvalue()
            elif suffix == ".ini":
                lines = raw.splitlines()
                for item in items:
                    locator = item.locator
                    if not locator.startswith("line[") or not locator.endswith("]"):
                        raise StaleSourceError(f"{relative}: INI konumu geçersiz. Metinleri yeniden tara.")
                    number = locator[5:-1]
                    if not number.isdigit():
                        raise StaleSourceError(f"{relative}: INI konumu geçersiz. Metinleri yeniden tara.")
                    line_index = int(number)
                    if line_index >= len(lines) or "=" not in lines[line_index]:
                        raise StaleSourceError(f"{relative}: INI satırı artık bulunamıyor. Metinleri yeniden tara.")
                    key, raw_value = lines[line_index].split("=", 1)
                    leading = raw_value[:len(raw_value) - len(raw_value.lstrip())]
                    trailing = raw_value[len(raw_value.rstrip()):]
                    value = raw_value.strip()
                    quote = value[0] if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"') else ""
                    current_value = value[1:-1] if quote else value
                    if current_value != item.source:
                        raise StaleSourceError(f"{relative}: kaynak metin taramadan sonra değişmiş. Yeniden tara.")
                    translated = f"{quote}{item.translated}{quote}" if quote else item.translated
                    lines[line_index] = f"{key}={leading}{translated}{trailing}"
                encoded = newline.join(lines) + (newline if raw.endswith(("\n", "\r")) else "")
            elif suffix == ".txt":
                lines = raw.splitlines()
                for item in items:
                    match = re.fullmatch(r"line\[(\d+)\]", item.locator)
                    if not match or int(match.group(1)) >= len(lines):
                        raise StaleSourceError(f"{relative}: TXT satırı artık bulunamıyor. Metinleri yeniden tara.")
                    line_index = int(match.group(1))
                    if lines[line_index] != item.source:
                        raise StaleSourceError(f"{relative}: kaynak metin taramadan sonra değişmiş. Yeniden tara.")
                    lines[line_index] = item.translated
                encoded = newline.join(lines) + (newline if raw.endswith(("\n", "\r")) else "")
            else:
                raise ValueError(f"{relative}: bu dosya biçimi yama dışa aktarımı için desteklenmiyor.")
            output[relative] = (b"\xef\xbb\xbf" if had_bom else b"") + encoded.encode("utf-8")
        except StaleSourceError:
            raise
        except (ValueError, KeyError, IndexError, TypeError, csv.Error) as exc:
            raise StaleSourceError(
                f"{relative}: çeviri dosyaya güvenli biçimde aktarılamadı ({exc}). "
                "Metinleri yeniden tara ve ilgili satırları kontrol et."
            ) from exc
    return output


def _safe_workspace_path(value: str) -> Path:
    candidate = Path(value)
    if ":" in value or chr(92) in value or candidate.is_absolute() or any(part in ("..", "") for part in candidate.parts):
        raise ValueError("Çalışma dosyasında güvenli olmayan hedef yolu.")
    return candidate


def remove_incomplete_patch(path: str | Path) -> bool:
    """Remove only Sarman-generated temporary patch archives, never arbitrary files."""
    candidate = Path(path)
    name = candidate.name.casefold()
    if not (name.endswith(".zip.tmp") or name.endswith(".sarman-tmp")):
        raise ValueError("Yalnızca .zip.tmp veya .sarman-tmp uzantılı yarım yama dosyaları silinebilir.")
    if candidate.is_symlink() or not candidate.is_file():
        return False
    candidate.unlink()
    return True


def create_translation_patch(game_dir: str | Path, entries: Iterable[TextEntry], destination: str | Path, game_name: str) -> Path:
    import zipfile
    from datetime import datetime, timezone

    files = build_translated_files(game_dir, entries)
    if not files:
        raise ValueError(
            "Yama oluşturulamadı: desteklenen JSON, CSV, INI veya TXT dosyalarında "
            "geçerli bir çeviri bulunamadı. Önce metinleri tara ve en az bir çeviriyi tamamla."
        )
    manifest_files = []
    for relative in sorted(files):
        manifest_files.append({"source": f"files/{relative}", "target": relative})
    manifest = {
        "name": f"{game_name} - Türkçe",
        "version": "1.0.0",
        "language": "tr",
        "target_game": game_name,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "files": manifest_files,
    }
    destination = Path(destination)
    if destination.suffix.casefold() != ".zip":
        destination = destination.with_suffix(".zip")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
            archive.writestr("sarman-patch.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            for relative, content in files.items():
                archive.writestr(f"files/{relative}", content)
        with zipfile.ZipFile(temporary, "r") as archive:
            bad_member = archive.testzip()
            if bad_member:
                raise ValueError(f"Oluşturulan yama doğrulanamadı: {bad_member}")
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination

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
MAX_ENTRIES = 30000
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
    leaf = locator.replace("[", ".").replace("]", "").split(".")[-1].casefold()
    if leaf in {"id", "uuid", "guid", "appid", "assetid", "objectid"}:
        return None
    if not _is_translatable(value):
        return None
    relative = file.relative_to(root).as_posix()
    entry_id = f"{relative}::{locator}"
    return TextEntry(entry_id, relative, locator, value)


def scan_game_texts(game_dir: str | Path, include_txt: bool = True) -> list[TextEntry]:
    root = Path(game_dir).resolve()
    if not root.is_dir():
        raise ValueError("Oyun klasörü bulunamadı.")
    entries: list[TextEntry] = []
    visited = 0
    for file in root.rglob("*"):
        if not file.is_file() or file.suffix.casefold() not in SUPPORTED:
            continue
        if any(part.casefold() in SKIP_DIRS for part in file.relative_to(root).parts[:-1]):
            continue
        visited += 1
        if visited > MAX_FILES:
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
                def walk(node, locator="root"):
                    if isinstance(node, dict):
                        for key, val in node.items():
                            walk(val, f"{locator}.{key}")
                    elif isinstance(node, list):
                        for index, val in enumerate(node):
                            walk(val, f"{locator}[{index}]")
                    elif isinstance(node, str):
                        item = _entry(file, root, locator, node)
                        if item: found.append(item)
                walk(data)
            elif suffix == ".csv":
                rows = list(csv.reader(io.StringIO(text, newline="")))
                if rows:
                    header = [x.casefold().strip() for x in rows[0]]
                    preferred_names = {"en", "english", "source", "original", "text", "value", "string", "dialog", "dialogue", "description", "message"}
                    text_cols = [i for i, name in enumerate(header) if name in preferred_names or any(token in name for token in ("english", "source", "original", "dialogue", "description"))]
                    has_header = bool(text_cols) or any(name in {"id", "key", "identifier", "translation", "target"} for name in header)
                    if not text_cols:
                        candidates = [i for i, name in enumerate(header) if name not in {"id", "key", "identifier", "translation", "target"}]
                        text_cols = candidates[:1] if has_header else list(range(min(len(rows[0]), 8)))
                    start = 1 if has_header else 0
                    for ri, row in enumerate(rows[start:], start=start):
                        for ci in text_cols:
                            if ci < len(row):
                                item = _entry(file, root, f"row[{ri}].col[{ci}]", row[ci])
                                if item: found.append(item)
            elif suffix == ".ini":
                for line_index, line in enumerate(text.splitlines()):
                    stripped = line.strip()
                    if not stripped or stripped.startswith((";", "#", "[")) or "=" not in line:
                        continue
                    key, raw_value = line.split("=", 1)
                    value = raw_value.strip()
                    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                        value = value[1:-1]
                    item = _entry(file, root, f"line[{line_index}]", value)
                    if item:
                        found.append(item)
            elif suffix == ".txt" and include_txt:
                for i, line in enumerate(text.splitlines()):
                    item = _entry(file, root, f"line[{i}]", line)
                    if item: found.append(item)
        except (ValueError, csv.Error, json.JSONDecodeError):
            continue
        entries.extend(found)
        if len(entries) >= MAX_ENTRIES:
            entries = entries[:MAX_ENTRIES]
            break
    # Stable de-duplication by exact source+locator.
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
    grouped = defaultdict(list)
    for entry in entries:
        if entry.translated.strip() and not validate_translation(entry.source, entry.translated):
            grouped[entry.file].append(entry)
    output: dict[str, bytes] = {}
    for relative, items in grouped.items():
        source_path = (root / _safe_workspace_path(relative)).resolve()
        if root not in source_path.parents or not source_path.is_file():
            continue
        try:
            raw = source_path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            continue
        suffix = source_path.suffix.casefold()
        try:
            if suffix == ".json":
                data = json.loads(raw)
                for item in items:
                    locator = item.locator.removeprefix("root").lstrip(".")
                    if not locator:
                        continue
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
                        node = node[key]
                    if keys:
                        node[keys[-1]] = item.translated
                encoded = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
            elif suffix == ".csv":
                rows = list(csv.reader(io.StringIO(raw, newline="")))
                for item in items:
                    match = re.fullmatch(r"row\[(\d+)\]\.col\[(\d+)\]", item.locator)
                    if match:
                        ri, ci = map(int, match.groups())
                        if ri < len(rows) and ci < len(rows[ri]):
                            rows[ri][ci] = item.translated
                buffer = io.StringIO(newline="")
                csv.writer(buffer, lineterminator="\n").writerows(rows)
                encoded = buffer.getvalue()
            elif suffix == ".ini":
                lines = raw.splitlines()
                for item in items:
                    locator = item.locator
                    if not locator.startswith("line[") or not locator.endswith("]"):
                        continue
                    number = locator[5:-1]
                    if not number.isdigit():
                        continue
                    line_index = int(number)
                    if line_index >= len(lines) or "=" not in lines[line_index]:
                        continue
                    key, raw_value = lines[line_index].split("=", 1)
                    leading = raw_value[:len(raw_value) - len(raw_value.lstrip())]
                    trailing = raw_value[len(raw_value.rstrip()):]
                    value = raw_value.strip()
                    quote = value[0] if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"') else ""
                    translated = f"{quote}{item.translated}{quote}" if quote else item.translated
                    lines[line_index] = f"{key}={leading}{translated}{trailing}"
                encoded = chr(10).join(lines) + (chr(10) if raw.endswith((chr(10), chr(13))) else "")
            elif suffix == ".txt":
                lines = raw.splitlines()
                for item in items:
                    match = re.fullmatch(r"line\[(\d+)\]", item.locator)
                    if match and int(match.group(1)) < len(lines):
                        lines[int(match.group(1))] = item.translated
                encoded = "\n".join(lines) + ("\n" if raw.endswith(("\n", "\r")) else "")
            else:
                continue
            output[relative] = encoded.encode("utf-8")
        except (ValueError, KeyError, IndexError, TypeError, csv.Error):
            continue
    return output


def _safe_workspace_path(value: str) -> Path:
    candidate = Path(value)
    if ":" in value or chr(92) in value or candidate.is_absolute() or any(part in ("..", "") for part in candidate.parts):
        raise ValueError("Çalışma dosyasında güvenli olmayan hedef yolu.")
    return candidate


def create_translation_patch(game_dir: str | Path, entries: Iterable[TextEntry], destination: str | Path, game_name: str) -> Path:
    import zipfile
    from datetime import datetime, timezone

    files = build_translated_files(game_dir, entries)
    if not files:
        raise ValueError("Desteklenen biçimlerde dışa aktarılabilir çevrilmiş dosya bulunamadı.")
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
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("sarman-patch.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for relative, content in files.items():
            archive.writestr(f"files/{relative}", content)
    return destination

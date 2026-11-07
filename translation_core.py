from __future__ import annotations

import csv
import configparser
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

SUPPORTED = {".json", ".csv", ".ini", ".po", ".txt"}
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", "binaries", "bin", "cache", "caches", "logs", "crashdumps"}
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_FILES = 5000
PLACEHOLDER_RE = re.compile(
    r"\{[^{}]+\}|\$\{[^{}]+\}|%(?:\d+\$)?[-+#0 ]*(?:\d+|\*)?(?:\.(?:\d+|\*))?[a-zA-Z%]|"
    r"\[[A-Za-z0-9_.:-]+\]|<[^>]+>|\\[nrt\\]|\u\\[0-9a-fA-F]{4}"
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
    if len(value) < 2 or not any(ch.isalpha() for ch in value):
        return False
    if value.startswith(("http://", "https://", "www.")):
        return False
    if value.startswith(("GUID:", "0x")):
        return False
    return True


def _entry(file: Path, root: Path, locator: str, value: str) -> TextEntry | None:
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
                rows = list(csv.reader(text.splitlines()))
                if rows:
                    header = [x.casefold().strip() for x in rows[0]]
                    text_cols = [i for i, h in enumerate(header) if any(k in h for k in ("text", "value", "string", "dialog", "description", "message", "translation"))]
                    if not text_cols:
                        text_cols = list(range(min(len(rows[0]), 8)))
                    start = 1 if any(header) else 0
                    for ri, row in enumerate(rows[start:], start=start):
                        for ci in text_cols:
                            if ci < len(row):
                                item = _entry(file, root, f"row[{ri}].col[{ci}]", row[ci])
                                if item: found.append(item)
            elif suffix == ".ini":
                parser = configparser.ConfigParser(interpolation=None, strict=False)
                parser.read_string(text)
                for section in parser.sections():
                    for key, value in parser.items(section):
                        item = _entry(file, root, f"{section}.{key}", value)
                        if item: found.append(item)
            elif suffix == ".po":
                # Extract msgid entries; source line index is used for safe exact replacement.
                lines = text.splitlines()
                current = None
                for i, line in enumerate(lines):
                    match = re.match(r'\s*msgid\s+"(.*)"\s*$', line)
                    if match and match.group(1):
                        current = (i, bytes(match.group(1), "utf-8").decode("unicode_escape"))
                        item = _entry(file, root, f"line[{i}]", current[1])
                        if item: found.append(item)
            elif suffix == ".txt" and include_txt:
                for i, line in enumerate(text.splitlines()):
                    item = _entry(file, root, f"line[{i}]", line)
                    if item: found.append(item)
        except (ValueError, csv.Error, configparser.Error, json.JSONDecodeError):
            continue
        entries.extend(found)
    # Stable de-duplication by exact source+locator.
    unique = {}
    for item in entries:
        unique[item.entry_id] = item
    return list(unique.values())


def placeholder_signature(text: str) -> list[str]:
    return sorted(PLACEHOLDER_RE.findall(text))


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
    payload = {"version": 1, "game_dir": str(Path(game_dir).resolve()), "entries": [e.to_dict() for e in entries]}
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_workspace(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("entries"), list):
        raise ValueError("Çeviri çalışma dosyası desteklenmiyor veya bozuk.")
    return data

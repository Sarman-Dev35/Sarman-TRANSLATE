from __future__ import annotations

import csv
import configparser
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

SUPPORTED = {".json", ".csv", ".txt"}
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
                    parts = re.findall(r"[^.\[\]]+|\[(\d+)\]", locator)
                    keys = []
                    for token in parts:
                        token = token[0] if isinstance(token, tuple) else token
                        if token:
                            keys.append(int(token) if token.isdigit() else token)
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
    if candidate.is_absolute() or any(part in ("..", "") for part in candidate.parts):
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

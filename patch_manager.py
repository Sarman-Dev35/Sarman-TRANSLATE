from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
import zlib
from datetime import datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

APP_DATA = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Sarman" / "TRANSLATE"
MAX_FILES = 2000
MAX_FILE_SIZE = 64 * 1024 * 1024
MAX_TOTAL_SIZE = 256 * 1024 * 1024
ALLOWED_TEXT_SUFFIXES = {".json", ".csv", ".txt", ".ini"}


class PatchError(Exception):
    pass


def _safe_relative(value: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise PatchError("Yama içinde boş veya geçersiz dosya yolu.")
    normalized = value.replace("\\", "/")
    posix = PurePosixPath(normalized)
    if posix.is_absolute() or not posix.parts or any(p in ("", ".", "..") for p in posix.parts):
        raise PatchError(f"Güvenli olmayan dosya yolu: {value}")
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
    invalid_chars = set('<>:"|?*')
    for part in posix.parts:
        device_stem = part.split(".", 1)[0].upper()
        if (
            any(ord(char) < 32 or char in invalid_chars for char in part)
            or device_stem in reserved
            or part.endswith((" ", "."))
        ):
            raise PatchError(f"Windows için geçersiz dosya yolu: {value}")
    if normalized.startswith("//"):
        raise PatchError(f"Güvenli olmayan dosya yolu: {value}")
    return Path(*posix.parts)


def _load_manifest(path: str | Path):
    archive_path = Path(path)
    if not zipfile.is_zipfile(archive_path):
        raise PatchError("Seçilen dosya geçerli bir ZIP yama paketi değil.")
    try:
        with zipfile.ZipFile(archive_path) as zf:
            infos = zf.infolist()
            if len({info.filename for info in infos}) != len(infos):
                raise PatchError("ZIP içinde yinelenen dosya yolları var.")
            if len(infos) > MAX_FILES + 1:
                raise PatchError("Yama paketi çok fazla dosya içeriyor.")
            manifest_infos = [info for info in infos if info.filename == "sarman-patch.json"]
            if len(manifest_infos) != 1 or manifest_infos[0].file_size > 1024 * 1024:
                raise PatchError("Manifest eksik, yinelenmiş veya 1 MB sınırını aşıyor.")
            try:
                raw = zf.read("sarman-patch.json")
                manifest = json.loads(raw.decode("utf-8-sig"))
            except KeyError as exc:
                raise PatchError("Pakette sarman-patch.json bulunamadı.") from exc
            if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list) or not manifest["files"]:
                raise PatchError("Yama manifesti geçersiz veya boş.")
            if len(manifest["files"]) > MAX_FILES:
                raise PatchError("Yama dosya sayısı sınırı aşıldı.")
            names = {info.filename for info in infos}
            checked, seen_sources, seen_targets = [], set(), set()
            total_size = 0
            for item in manifest["files"]:
                if not isinstance(item, dict) or not item.get("source") or not item.get("target"):
                    raise PatchError("Manifest içindeki dosya kaydı eksik.")
                source = _safe_relative(item["source"]).as_posix()
                target = _safe_relative(item["target"])
                if source == "sarman-patch.json" or source not in names:
                    raise PatchError(f"Pakette kaynak dosya bulunamadı: {source}")
                if Path(source).suffix.casefold() not in ALLOWED_TEXT_SUFFIXES or target.suffix.casefold() not in ALLOWED_TEXT_SUFFIXES:
                    raise PatchError("Yalnızca desteklenen metin/dil dosyaları (.json, .csv, .txt, .ini) yüklenebilir.")
                if source.casefold() in seen_sources:
                    raise PatchError(f"Kaynak dosya birden fazla kez tanımlanmış: {source}")
                if target.as_posix().casefold() in seen_targets:
                    raise PatchError(f"Hedef dosya birden fazla kez tanımlanmış: {target}")
                seen_sources.add(source.casefold())
                seen_targets.add(target.as_posix().casefold())
                info = zf.getinfo(source)
                if info.is_dir() or info.flag_bits & 0x1:
                    raise PatchError("Klasör veya şifreli ZIP girdisi yama dosyası olamaz.")
                if ((info.external_attr >> 16) & 0o170000) == 0o120000:
                    raise PatchError("Sembolik bağlantı içeren yamalar kabul edilmiyor.")
                if info.file_size > MAX_FILE_SIZE:
                    raise PatchError(f"Dosya boyutu sınırı aşıldı: {source}")
                try:
                    zf.read(info).decode("utf-8-sig")
                except UnicodeDecodeError as exc:
                    raise PatchError(f"Yama dosyası desteklenen UTF-8 metin biçiminde değil: {source}") from exc
                total_size += info.file_size
                if total_size > MAX_TOTAL_SIZE:
                    raise PatchError("Yamanın toplam açılmış boyutu sınırı aşıyor.")
                checked.append({"source": source, "target": target.as_posix(), "size": info.file_size})
            manifest["files"] = checked
            if manifest.get("target_game") is not None and not isinstance(manifest.get("target_game"), str):
                raise PatchError("Yama hedef oyun bilgisi geçersiz.")
            manifest["name"] = str(manifest.get("name") or archive_path.stem)[:120]
            manifest["version"] = str(manifest.get("version") or "Belirtilmemiş")[:40]
            return manifest
    except PatchError:
        raise
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError, KeyError, RuntimeError, zlib.error) as exc:
        raise PatchError(f"Yama paketi okunamadı: {exc}") from exc


def inspect_patch(archive: str | Path) -> dict:
    return _load_manifest(archive)


def _write_state(path: Path, state: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def install_patch(archive: str | Path, game_dir: str | Path) -> dict:
    manifest = _load_manifest(archive)
    root = Path(game_dir).resolve()
    if not root.is_dir():
        raise PatchError("Oyun klasörü bulunamadı.")
    patch_id = uuid4().hex
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_game = "".join(c if c.isalnum() or c in "-_" else "_" for c in root.name)[:60]
    backup_dir = APP_DATA / "backups" / safe_game / f"{stamp}-{patch_id[:8]}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    state_path = backup_dir / "install.json"
    state = {"schema": 1, "id": patch_id, "name": manifest["name"], "version": manifest["version"],
             "language": str(manifest.get("language") or "").casefold(),
             "game_dir": str(root), "backup_dir": str(backup_dir), "files": []}
    written = []
    try:
        with zipfile.ZipFile(archive) as zf:
            for index, item in enumerate(manifest["files"]):
                relative_target = _safe_relative(item["target"])
                candidate = root
                for part in relative_target.parts:
                    candidate = candidate / part
                    if candidate.is_symlink():
                        raise PatchError("Sembolik bağlantı hedefi engellendi.")
                target = candidate.resolve()
                if target == root or root not in target.parents:
                    raise PatchError(f"Oyun klasörü dışına çıkan hedef engellendi: {item['target']}")
                # resolve() also detects existing symlink parents that escape the game root.
                if target.exists() and (target.is_symlink() or not target.is_file()):
                    raise PatchError(f"Hedef normal bir dosya değil: {item['target']}")
                existed = target.is_file()
                backup_name = f"{index:05d}.bak" if existed else None
                if existed:
                    shutil.copy2(target, backup_dir / backup_name)
                state["files"].append({"target": str(target), "backup": backup_name})
                _write_state(state_path, state)  # journal before modifying the game
                target.parent.mkdir(parents=True, exist_ok=True)
                temp_path = None
                try:
                    with zf.open(item["source"]) as src, tempfile.NamedTemporaryFile(
                        mode="wb", dir=target.parent, prefix=".sarman-", delete=False
                    ) as tmp:
                        temp_path = Path(tmp.name)
                        shutil.copyfileobj(src, tmp, length=1024 * 1024)
                    os.replace(temp_path, target)
                    written.append(target)
                finally:
                    if temp_path and temp_path.exists():
                        temp_path.unlink(missing_ok=True)
        return {"name": manifest["name"], "version": manifest["version"], "backup": str(backup_dir)}
    except Exception:
        _restore_state(root, backup_dir, state, strict=False)
        shutil.rmtree(backup_dir, ignore_errors=True)
        raise


def _restore_state(root: Path, state_dir: Path, state: dict, strict: bool = True) -> None:
    entries = state.get("files")
    if not isinstance(entries, list):
        raise PatchError("Yedek kaydı bozuk.")
    validated = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("target"), str):
            raise PatchError("Yedek kaydında geçersiz dosya hedefi bulundu.")
        raw_target = Path(entry["target"])
        if not raw_target.is_absolute():
            raise PatchError("Yedek kaydında mutlak hedef yolu bekleniyordu.")
        probe = raw_target
        try:
            relative = raw_target.relative_to(root)
        except ValueError as exc:
            raise PatchError("Yedek kaydında oyun klasörü dışına çıkan hedef bulundu.") from exc
        probe = root
        for part in relative.parts:
            probe = probe / part
            if probe.is_symlink():
                raise PatchError("Geri alma sırasında sembolik bağlantı hedefi engellendi.")
        target = probe.resolve()
        if target == root or root not in target.parents:
            raise PatchError("Yedek kaydında oyun klasörü dışına çıkan hedef bulundu.")
        backup_name = entry.get("backup")
        backup_path = None
        if backup_name is not None and not isinstance(backup_name, str):
            raise PatchError("Yedek kaydında geçersiz yedek dosya adı.")
        if backup_name:
            if Path(backup_name).name != backup_name:
                raise PatchError("Yedek kaydında geçersiz yedek dosya adı.")
            backup_path = state_dir / backup_name
            if not backup_path.is_file():
                raise PatchError(f"Yedek dosyası eksik: {backup_name}")
        validated.append((target, backup_path))
    for target, backup_path in reversed(validated):
        if backup_path:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_path, target)
        elif target.exists():
            if target.is_file() and not target.is_symlink():
                target.unlink()
            elif strict:
                raise PatchError(f"Geri alınacak hedef normal dosya değil: {target}")


def uninstall_latest(game_dir: str | Path) -> str:
    root = Path(game_dir).resolve()
    base = APP_DATA / "backups"
    states = []
    if base.exists():
        for state_path in base.glob("*/**/install.json"):
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
                if not isinstance(state, dict):
                    continue
                if state.get("schema") == 1 and Path(state.get("game_dir", "")).resolve() == root:
                    states.append((state_path.stat().st_mtime, state_path, state))
            except (OSError, ValueError, TypeError):
                continue
    if not states:
        raise PatchError("Bu oyun için geri alınabilir bir Sarman yama kaydı bulunamadı.")
    _, state_path, state = max(states, key=lambda item: item[0])
    _restore_state(root, state_path.parent, state, strict=True)
    name = state.get("name", "Yama")
    shutil.rmtree(state_path.parent, ignore_errors=True)
    return name


def installed_patch_languages(game_dir: str | Path) -> set[str]:
    """Return language codes from active Sarman patch journals for one game."""
    root = Path(game_dir).resolve()
    base = APP_DATA / "backups"
    found: set[str] = set()
    if not base.is_dir():
        return found
    try:
        for state_path in base.glob("*/**/install.json"):
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
                if not isinstance(state, dict):
                    continue
                if state.get("schema") != 1 or Path(state.get("game_dir", "")).resolve() != root:
                    continue
                language = state.get("language")
                if isinstance(language, str) and language.strip():
                    found.add(language.strip().casefold())
                elif "türkçe" in str(state.get("name", "")).casefold() or "turkish" in str(state.get("name", "")).casefold():
                    found.add("tr")
            except (OSError, ValueError, TypeError):
                continue
    except OSError:
        return found
    return found


def uninstall_all(game_dir: str | Path) -> list[str]:
    """Restore every active Sarman patch for a game, newest first, then remove its journals."""
    root = Path(game_dir).resolve()
    base = APP_DATA / "backups"
    states = []
    if not base.exists():
        return []
    for state_path in base.glob("*/**/install.json"):
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(state, dict) and state.get("schema") == 1 and Path(state.get("game_dir", "")).resolve() == root:
                states.append((state_path.stat().st_mtime_ns, state_path, state))
        except (OSError, ValueError, TypeError):
            continue
    names = []
    for _, state_path, state in sorted(states, key=lambda item: item[0], reverse=True):
        _restore_state(root, state_path.parent, state, strict=True)
        names.append(str(state.get("name", "Yama")))
        shutil.rmtree(state_path.parent)
    return names

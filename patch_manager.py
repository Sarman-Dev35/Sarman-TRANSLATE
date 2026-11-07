from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

APP_DATA = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Sarman" / "TRANSLATE"


class PatchError(Exception):
    pass


def _safe_relative(value: str) -> Path:
    posix = PurePosixPath(value.replace("\\", "/"))
    if posix.is_absolute() or not posix.parts or any(p in ("", ".", "..") for p in posix.parts):
        raise PatchError(f"Güvenli olmayan dosya yolu: {value}")
    if ":" in posix.parts[0]:
        raise PatchError(f"Güvenli olmayan dosya yolu: {value}")
    return Path(*posix.parts)


def inspect_patch(archive: str | Path) -> dict:
    path = Path(archive)
    if not zipfile.is_zipfile(path):
        raise PatchError("Seçilen dosya geçerli bir ZIP yama paketi değil.")
    try:
        with zipfile.ZipFile(path) as zf:
            try:
                manifest = json.loads(zf.read("sarman-patch.json").decode("utf-8-sig"))
            except KeyError as exc:
                raise PatchError("Pakette sarman-patch.json bulunamadı.") from exc
            if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
                raise PatchError("Yama manifesti geçersiz.")
            if not manifest["files"]:
                raise PatchError("Yama paketi boş.")
            names = set(zf.namelist())
            checked = []
            for item in manifest["files"]:
                if not isinstance(item, dict) or not item.get("source") or not item.get("target"):
                    raise PatchError("Manifest içindeki dosya kaydı eksik.")
                source = _safe_relative(str(item["source"])).as_posix()
                target = _safe_relative(str(item["target"]))
                if source not in names:
                    raise PatchError(f"Pakette dosya bulunamadı: {source}")
                info = zf.getinfo(source)
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise PatchError("Sembolik bağlantı içeren yamalar kabul edilmiyor.")
                checked.append({"source": source, "target": target.as_posix()})
            manifest["files"] = checked
            manifest.setdefault("name", path.stem)
            manifest.setdefault("version", "Belirtilmemiş")
            return manifest
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PatchError(f"Yama paketi okunamadı: {exc}") from exc


def install_patch(archive: str | Path, game_dir: str | Path) -> dict:
    manifest = inspect_patch(archive)
    root = Path(game_dir).resolve()
    if not root.is_dir():
        raise PatchError("Oyun klasörü bulunamadı.")
    patch_id = uuid4().hex
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_game = "".join(c if c.isalnum() or c in "-_" else "_" for c in root.name)[:60]
    backup_dir = APP_DATA / "backups" / safe_game / f"{stamp}-{patch_id[:8]}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    state = {"id": patch_id, "name": manifest["name"], "version": manifest["version"],
             "game_dir": str(root), "backup_dir": str(backup_dir), "files": []}
    written = []
    try:
        with zipfile.ZipFile(archive) as zf:
            for item in manifest["files"]:
                target = (root / _safe_relative(item["target"])).resolve()
                if target != root and root not in target.parents:
                    raise PatchError(f"Oyun klasörü dışına çıkan hedef engellendi: {item['target']}")
                if target.exists() and not target.is_file():
                    raise PatchError(f"Hedef normal bir dosya değil: {item['target']}")
                backup_name = f"{len(state['files']):05d}.bak"
                existed = target.is_file()
                if existed:
                    backup_dir.joinpath(backup_name).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, backup_dir / backup_name)
                state["files"].append({"target": str(target), "backup": backup_name if existed else None})
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(item["source"]) as src, tempfile.NamedTemporaryFile(
                    mode="wb", dir=target.parent, prefix=".sarman-", delete=False
                ) as tmp:
                    temp_path = Path(tmp.name)
                    shutil.copyfileobj(src, tmp)
                os.replace(temp_path, target)
                written.append(target)
        state_path = backup_dir / "install.json"
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"name": manifest["name"], "version": manifest["version"], "backup": str(backup_dir)}
    except Exception:
        for entry in reversed(state["files"]):
            target = Path(entry["target"])
            backup = entry["backup"]
            try:
                if backup:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup_dir / backup, target)
                elif target.exists():
                    target.unlink()
            except OSError:
                pass
        shutil.rmtree(backup_dir, ignore_errors=True)
        raise


def uninstall_latest(game_dir: str | Path) -> str:
    root = Path(game_dir).resolve()
    base = APP_DATA / "backups"
    states = []
    if base.exists():
        for state_path in base.glob("*/**/install.json"):
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
                if Path(state.get("game_dir", "")).resolve() == root:
                    states.append((state_path.stat().st_mtime, state_path, state))
            except (OSError, ValueError, TypeError):
                continue
    if not states:
        raise PatchError("Bu oyun için geri alınabilir bir Sarman yama kaydı bulunamadı.")
    _, state_path, state = max(states, key=lambda item: item[0])
    for entry in reversed(state["files"]):
        target = Path(entry["target"]).resolve()
        if root not in target.parents and target != root:
            raise PatchError("Yedek kaydında güvenli olmayan hedef bulundu; işlem durduruldu.")
        backup = entry["backup"]
        if backup:
            source = state_path.parent / backup
            if not source.is_file():
                raise PatchError(f"Yedek dosyası eksik: {backup}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        elif target.exists():
            target.unlink()
    name = state.get("name", "Yama")
    shutil.rmtree(state_path.parent, ignore_errors=True)
    return name

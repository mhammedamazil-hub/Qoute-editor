"""Brain snapshot export/import — one zip, everything needed to clone a brain."""
from __future__ import annotations
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from .config import get_settings
from .db import backup_db, export_json_snapshot, import_json_snapshot
from .util import utcnow_compact


def export_snapshot(dest: Path | None = None) -> Path:
    settings = get_settings()
    settings.ensure_dirs()
    backup_db("pre-export")
    ts = utcnow_compact()
    dest = Path(dest) if dest else settings.home / f"snapshot_{ts}.zip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("brain_export.json", json.dumps(export_json_snapshot(), default=str))
        for sub in ("procedural", "sleep_logs", "knowledge_graph"):
            base = getattr(settings, {"procedural": "procedural_dir", "sleep_logs": "sleep_logs",
                                      "knowledge_graph": "graph_dir"}[sub])
            if base.exists():
                for f in base.rglob("*"):
                    if f.is_file():
                        zf.write(f, arcname=f"{sub}/{f.relative_to(base)}")
        zf.writestr("MANIFEST.json", json.dumps({
            "created_at": ts, "format": "minicoder-snapshot/1",
            "note": "Contains personal memory. Treat like a private key."}, indent=2))
    return dest


def import_snapshot(archive: Path, *, merge: bool = True) -> dict:
    archive = Path(archive)
    if not archive.exists():
        raise FileNotFoundError(archive)
    settings = get_settings()
    settings.ensure_dirs()
    backup_db("pre-import")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(archive) as zf:
            _safe_extract(zf, tmp_path)
        brain_json = tmp_path / "brain_export.json"
        if not brain_json.exists():
            raise ValueError("not a minicoder snapshot: brain_export.json missing")
        snap = json.loads(brain_json.read_text(encoding="utf-8"))
        imported = import_json_snapshot(snap)
        files_restored = 0
        for sub, attr in (("procedural", "procedural_dir"), ("sleep_logs", "sleep_logs"),
                          ("knowledge_graph", "graph_dir")):
            src_dir = tmp_path / sub
            if not src_dir.exists():
                continue
            dest_dir = getattr(settings, attr)
            dest_dir.mkdir(parents=True, exist_ok=True)
            for f in src_dir.rglob("*"):
                if f.is_file():
                    target = dest_dir / f.relative_to(src_dir)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, target)
                    files_restored += 1
    return {"imported_rows": imported, "files_restored": files_restored}


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    dest = dest.resolve()
    for member in zf.infolist():
        target = (dest / member.filename).resolve()
        if not str(target).startswith(str(dest)):
            raise ValueError(f"unsafe path in archive: {member.filename}")
    zf.extractall(dest)

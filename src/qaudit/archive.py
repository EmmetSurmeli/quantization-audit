"""Portable, weight-free archives for reproducing analysis on a CPU machine."""
from __future__ import annotations

import gzip
import shutil
import sqlite3
import tempfile
from pathlib import Path

from .common import file_hash,read_json,write_json


def export_archive(workspace,out):
    ws,out=Path(workspace),Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError("Archive destination must be empty")
    frozen=read_json(ws/"frozen.json")
    out.mkdir(parents=True,exist_ok=True)
    names=["study.json","pins.json","splits.json","split-manifest.json","frozen.json"]
    for role in frozen["roles"]:
        names += [f"pilot-{role}.json",f"calibration-{role}.json"]
        names += [f"models/{role}/{b}/artifact.json" for b in (16,8,4)]
    names += [n for n in ("hardware.json","execution.json") if (ws/n).exists()]
    names += [p.name for p in sorted(ws.glob('amendment-*-migration.json'))]
    for name in names:
        dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ws/name,dest)
    # SQLite's backup API also safely incorporates any committed WAL contents.
    with tempfile.TemporaryDirectory(dir=out) as temp:
        backup=Path(temp)/"scores.sqlite"
        with sqlite3.connect(ws/"scores.sqlite") as source,sqlite3.connect(backup) as target:
            source.backup(target)
        with backup.open("rb") as source,gzip.open(out/"scores.sqlite.gz","wb") as target:
            shutil.copyfileobj(source,target)
    names.append("scores.sqlite.gz")
    manifest={name:file_hash(out/name) for name in names}
    write_json(out/"archive.json",{"schema":1,"files":manifest,"contains_weights":False})
    return {"archive":str(out),"files":len(manifest),"contains_weights":False}


def restore_archive(archive,workspace):
    archive,ws=Path(archive),Path(workspace)
    if ws.exists() and any(p.name!=".lock" for p in ws.iterdir()):
        raise ValueError("Restore destination must be empty")
    manifest=read_json(archive/"archive.json")
    for name,expected in manifest["files"].items():
        path=Path(name)
        if path.is_absolute() or ".." in path.parts or file_hash(archive/path)!=expected:
            raise ValueError("Unsafe or corrupt archive")
    ws.mkdir(parents=True,exist_ok=True)
    for name in manifest["files"]:
        if name=="scores.sqlite.gz":
            with gzip.open(archive/name,"rb") as source,(ws/"scores.sqlite").open("wb") as target:
                shutil.copyfileobj(source,target)
        else:
            dest=ws/name;dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(archive/name,dest)
    return {"workspace":str(ws),"restored":True,"contains_weights":False}

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .common import configure_cache,config_at,read_json,workspace_lock


def parser():
    p=argparse.ArgumentParser(description="Quantization and confidence audit; no paid services")
    p.add_argument("--workspace",type=Path,default=Path("workspaces/main"))
    sub=p.add_subparsers(dest="command",required=True)
    s=sub.add_parser("prepare",help="Pin revisions, download ARC, and create disjoint splits")
    s.add_argument("--config",type=Path,default=Path("configs/study.json"))
    s=sub.add_parser("convert",help="Create local BF16/8/4-bit artifacts from one checkpoint")
    s.add_argument("--role",choices=["primary","replication"],default="primary")
    s.add_argument("--bits",type=int,choices=[16,8,4],nargs="+",default=[16,8,4])
    s=sub.add_parser("score",help="Resume scoring; test/robustness require protocol freeze")
    s.add_argument("--role",choices=["primary","replication"],default="primary")
    s.add_argument("--bits",type=int,choices=[16,8,4],nargs="+",default=[16,8,4])
    s.add_argument("--stage",choices=["pilot","calibration","validation","test","robustness"],required=True)
    s.add_argument("--limit",type=int,help="Process at most this many NEW questions per dataset; never marks incomplete cells complete")
    s=sub.add_parser("gate",help="Check pilot integrity, accuracy, runtime and memory")
    s.add_argument("--role",choices=["primary","replication"],default="primary")
    s=sub.add_parser("calibrate",help="Fit scalar temperatures using calibration split only")
    s.add_argument("--role",choices=["primary","replication"],default="primary")
    s=sub.add_parser("freeze",help="Lock protocol and fitted calibration before test scoring")
    s.add_argument("--replication",action="store_true")
    s=sub.add_parser("analyze",help="Generate statistics, figures and report from complete saved scores")
    s.add_argument("--out",type=Path,required=True)
    s=sub.add_parser("export",help="Export scores and provenance without large model weights")
    s.add_argument("--out",type=Path,required=True)
    s=sub.add_parser("restore",help="Restore a portable archive into an empty workspace")
    s.add_argument("--archive",type=Path,required=True)
    sub.add_parser("status",help="Show progress without loading a model")
    return p


def main(argv=None):
    args=parser().parse_args(argv)
    ws=args.workspace.resolve()
    configure_cache(ws)
    try:
        with workspace_lock(ws):
            if args.command=="prepare":
                from .data import prepare
                result=prepare(ws,args.config)
                result={"counts":result["counts"],"exclusions":result["exclusions"]}
            elif args.command=="convert":
                from .backend import convert_model
                result=[{"bits":b,"artifact_hash":convert_model(ws,args.role,b)["artifact_hash"]} for b in args.bits]
            elif args.command=="score":
                from .scoring import score
                if args.limit is not None and args.limit<1:
                    raise ValueError("Limit must be positive")
                result=[score(ws,args.role,b,args.stage,limit=args.limit) for b in args.bits]
            elif args.command=="gate":
                from .scoring import pilot_gate
                result=pilot_gate(ws,args.role)
            elif args.command=="calibrate":
                from .analysis import calibrate
                result=calibrate(ws,args.role)
            elif args.command=="freeze":
                from .scoring import freeze
                result=freeze(ws,args.replication)
            elif args.command=="analyze":
                from .analysis import analyze
                result=analyze(ws,args.out.resolve())
            elif args.command=="export":
                from .archive import export_archive
                result=export_archive(ws,args.out)
            elif args.command=="restore":
                from .archive import restore_archive
                result=restore_archive(args.archive,ws)
            else:
                from .store import ScoreStore
                with ScoreStore(ws/"scores.sqlite") as store:
                    result={"workspace":str(ws),"frozen":(ws/"frozen.json").exists(),
                            "cells":{c:len(store.records(c)) for c in store.cells()}}
            print(json.dumps(result,indent=2,allow_nan=False))
        return 0
    except (ValueError,RuntimeError,FileNotFoundError) as exc:
        print(f"Audit stopped: {exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())

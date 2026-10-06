"""Sequential, resumable local study runner. No paid services or parallel models."""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from qaudit.analysis import analyze,calibrate
from qaudit.backend import convert_model
from qaudit.common import configure_cache,read_json,utc_now,workspace_lock,write_json
from qaudit.data import prepare
from qaudit.scoring import check_frozen,freeze,pilot_gate,score


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace",type=Path,required=True)
    p.add_argument("--config",type=Path,default=Path("configs/study.json"))
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--replication",action="store_true")
    p.add_argument("--stop-before-test",action="store_true")
    args=p.parse_args()
    ws=args.workspace.resolve();configure_cache(ws)
    start=time.perf_counter()
    ledger=read_json(ws/"execution.json") if (ws/"execution.json").exists() else {"phases":[],"additional_spend_usd":0}

    def phase(name,fn):
        if time.perf_counter()-start>24*3600:
            raise RuntimeError("24-hour execution ceiling reached; stop for scope review")
        print(f"START {name}",flush=True)
        t=time.perf_counter();began=utc_now()
        try:
            result=fn()
        except BaseException as error:
            ledger["phases"].append({"phase":name,"started":began,"finished":utc_now(),"seconds":time.perf_counter()-t,"status":"failed","error":str(error)})
            write_json(ws/"execution.json",ledger)
            raise
        ledger["phases"].append({"phase":name,"started":began,"finished":utc_now(),"seconds":time.perf_counter()-t,"status":"complete"})
        write_json(ws/"execution.json",ledger)
        print(f"DONE {name} ({time.perf_counter()-t:.1f}s)",flush=True)
        return result

    with workspace_lock(ws):
        if not (ws/"split-manifest.json").exists():
            phase("prepare",lambda:prepare(ws,args.config))
        roles=["primary","replication"] if args.replication else ["primary"]
        if not (ws/"frozen.json").exists():
            for role in roles:
                for bits in (16,8,4):
                    phase(f"convert/{role}/{bits}",lambda:convert_model(ws,role,bits))
                    phase(f"pilot/{role}/{bits}",lambda:score(ws,role,bits,"pilot"))
                gate=phase(f"gate/{role}",lambda:pilot_gate(ws,role))
                if not gate["passed"]:
                    raise RuntimeError(f"Pilot failed: {gate['reasons']}")
                if role=="primary" and args.replication and gate["conservative_two_model_hours"]>24:
                    raise RuntimeError("Replication exceeds the runtime allowance")
                for stage in ("calibration","validation"):
                    for bits in (16,8,4):
                        phase(f"{stage}/{role}/{bits}",lambda:score(ws,role,bits,stage))
                phase(f"fit/{role}",lambda:calibrate(ws,role))
            if args.stop_before_test:
                print("Pre-test scoring complete. Inspect validation and freeze before held-out evaluation.",flush=True)
                return
            phase("freeze",lambda:freeze(ws,args.replication))
        frozen=check_frozen(ws)
        if roles!=frozen["roles"]:
            raise ValueError("Requested roles differ from frozen study scope")
        for role in roles:
            for stage in ("test","robustness"):
                for bits in (16,8,4):
                    phase(f"{stage}/{role}/{bits}",lambda:score(ws,role,bits,stage))
        phase("analyze",lambda:analyze(ws,args.out))


if __name__=="__main__":
    main()

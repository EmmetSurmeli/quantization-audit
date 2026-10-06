from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .backend import MLXScorer, model_path, model_inventory
from .common import config_at,digest,environment,read_json,source_hash,utc_now,write_json
from .data import permute,selection
from .stats import matrix,probabilities
from .store import ScoreStore,aligned_records,cell_name


def protocol_identity(workspace):
    ws=Path(workspace)
    return {"config":digest(config_at(ws)),"pins":digest(read_json(ws/"pins.json")),
            "splits":digest(read_json(ws/"splits.json")),
            "scoring_source":source_hash(["backend","data","scoring","store","common","stats"]),
            "environment":environment()}


def check_frozen(workspace):
    path=Path(workspace)/"frozen.json"
    if not path.exists():
        raise ValueError("Test scoring requires a passed pilot and frozen protocol")
    frozen=read_json(path)
    if frozen["identity"]!=protocol_identity(workspace):
        raise ValueError("Frozen protocol or environment changed; start a new workspace")
    for role in frozen["roles"]:
        if digest(read_json(Path(workspace)/f"calibration-{role}.json"))!=frozen["calibration_hashes"][role]:
            raise ValueError("Calibration artifact changed after protocol freeze")
    return frozen


def score(workspace,role,bits,stage,*,limit=None):
    ws=Path(workspace)
    cfg=config_at(ws)
    if stage in ("test","robustness"):
        frozen=check_frozen(ws)
        if role not in frozen["roles"]:
            raise ValueError("This model role is outside the frozen study scope")
    path=model_path(ws,role,bits)
    meta=read_json(path/"artifact.json")
    if model_inventory(path)!=meta["files"]:
        raise ValueError("Model files differ from the immutable artifact manifest")
    identity={"protocol":protocol_identity(ws),"artifact_hash":meta["artifact_hash"],"role":role,"bits":bits,"stage":stage}
    scorer=MLXScorer(path,cfg)
    try:
        with ScoreStore(ws/"scores.sqlite") as store:
            for dataset in cfg["datasets"]:
                cell=cell_name(role,bits,dataset,stage)
                store.register(cell,dict(identity,dataset=dataset))
                rows=selection(ws,dataset,stage)
                if stage=="robustness":
                    rows=[permute(r,cfg["seed"]) for r in rows]
                done={r["key"] for r in store.records(cell)}
                remaining=[r for r in rows if r["key"] not in done]
                if limit is not None:
                    remaining=remaining[:limit]
                # Warm-up excluded from latency summaries, included in execution time.
                if remaining:
                    scorer.score(remaining[0])
                for i,row in enumerate(remaining):
                    record=scorer.score(row)
                    if stage=="pilot" and rows.index(row)<3:
                        repeat=scorer.score(row)
                        p1=probabilities(matrix([record["option_scores"]]))
                        p2=probabilities(matrix([repeat["option_scores"]]))
                        record["repeat_max_probability_delta"]=float(np.max(np.abs(p1-p2)))
                    store.insert(cell,record)
                    if (i+1)%25==0 or i+1==len(remaining):
                        print(f"{cell}: {len(done)+i+1}/{len(rows)}",flush=True)
    finally:
        scorer.close()
    return {"role":role,"precision":bits,"stage":stage,"status":"scored"}


def pilot_gate(workspace,role="primary"):
    ws=Path(workspace);cfg=config_at(ws)
    summaries=[];reasons=[]
    with ScoreStore(ws/"scores.sqlite") as store:
        for bits in cfg["precisions"]:
            for dataset in cfg["datasets"]:
                rows=selection(ws,dataset,"pilot")
                cell=cell_name(role,bits,dataset,"pilot")
                if store.identity(cell)["protocol"]!=protocol_identity(ws):
                    raise ValueError("Pilot scores came from a different protocol")
                records=aligned_records(store,cell,rows)
                p=probabilities(matrix([r["option_scores"] for r in records]))
                y=np.array([r["gold"] for r in rows])
                acc=float(np.mean(p.argmax(axis=1)==y))
                repeat=[r["repeat_max_probability_delta"] for r in records if "repeat_max_probability_delta" in r]
                if len(repeat)!=3 or max(repeat)>cfg["pilot_gate"]["repeat_probability_atol"]:
                    reasons.append(f"{bits}/{dataset}: repeatability check failed")
                peak=max(r["peak_memory_bytes"] for r in records)/1e9
                if peak>cfg["budget"]["max_peak_memory_gb"]:
                    reasons.append(f"{bits}/{dataset}: memory ceiling exceeded")
                if bits==16 and dataset=="ARC-Challenge":
                    chance=float(np.mean([1/len(r["choices"]) for r in rows]))
                    if not chance+cfg["pilot_gate"]["minimum_above_chance"]<acc<cfg["pilot_gate"]["maximum_challenge_accuracy"]:
                        reasons.append("BF16 challenge accuracy outside prespecified informative range")
                summaries.append({"precision":bits,"dataset":dataset,"n":len(rows),"accuracy":acc,
                                  "mean_seconds":float(np.mean([r["latency_seconds"] for r in records])),
                                  "p95_seconds":float(np.quantile([r["latency_seconds"] for r in records],.95)),
                                  "mean_input_tokens":float(np.mean([r["input_tokens"] for r in records])),"peak_memory_gb":peak})
        # Verify EXACT prompt token identity across precisions, including resumed records.
        for dataset in cfg["datasets"]:
            ref={r["key"]:r for r in store.records(cell_name(role,16,dataset,"pilot"))}
            for bits in (8,4):
                for r in store.records(cell_name(role,bits,dataset,"pilot")):
                    if any(r[k]!=ref[r["key"]][k] for k in ("prompt_hash","option_token_ids","option_order")):
                        reasons.append("Prompt/token mapping differs across precisions")
    projected=0.0
    for s in summaries:
        count=sum(len(selection(ws,s["dataset"],stage)) for stage in ("pilot","calibration","validation","test","robustness"))
        projected+=count*s["mean_seconds"]
    hours=projected/3600*cfg["budget"]["overhead_factor"]
    if hours>cfg["budget"]["max_runtime_hours"]:
        reasons.append("Primary study exceeds runtime limit")
    result={"role":role,"passed":not reasons,"reasons":reasons,"cells":summaries,
            "projected_primary_hours":hours,"conservative_two_model_hours":2*hours,
            "identity":protocol_identity(ws)}
    write_json(ws/f"pilot-{role}.json",result)
    return result


def freeze(workspace,replication=False):
    ws=Path(workspace);cfg=config_at(ws)
    gate=pilot_gate(ws)
    if not gate["passed"]:
        raise ValueError("Pilot gate failed: "+"; ".join(gate["reasons"]))
    if replication and gate["conservative_two_model_hours"]>cfg["budget"]["max_runtime_hours"]:
        raise ValueError("Two-model projection exceeds runtime cap")
    roles=["primary","replication"] if replication else ["primary"]
    with ScoreStore(ws/"scores.sqlite") as store:
        # Validate all pre-test records and exact prompt pairing for every included model.
        for role in roles:
            if role!="primary" and not pilot_gate(ws,role)["passed"]:
                raise ValueError("Replication pilot gate failed")
            for stage in ("calibration","validation"):
                for dataset in cfg["datasets"]:
                    rows=selection(ws,dataset,stage)
                    ref=None
                    for bits in cfg["precisions"]:
                        cell=cell_name(role,bits,dataset,stage)
                        if store.identity(cell)["protocol"]!=protocol_identity(ws):
                            raise ValueError("Pre-test scores came from a different protocol")
                        records=aligned_records(store,cell,rows)
                        logits=matrix([r["option_scores"] for r in records])
                        probabilities(logits)
                        ids=[(r["prompt_hash"],r["option_token_ids"],r["option_order"]) for r in records]
                        if ref is not None and ids!=ref:
                            raise ValueError("Pre-test prompt mismatch")
                        ref=ids
    path=ws/"frozen.json"
    calibration_hashes={}
    for role in roles:
        artifact=read_json(ws/f"calibration-{role}.json")
        if artifact["config_hash"]!=digest(cfg):
            raise ValueError("Calibration config mismatch")
        if artifact["fit_source"]!=source_hash(["stats"]):
            raise ValueError("Calibration implementation changed")
        calibration_hashes[role]=digest(artifact)
    result={"identity":protocol_identity(ws),"roles":roles,"pilot_gate_hash":digest(gate),"calibration_hashes":calibration_hashes}
    write_json(path,result,immutable=True)
    return result

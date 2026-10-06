"""Small artificial fixtures test plumbing only; they are never study results."""
from pathlib import Path

import numpy as np
import pytest

from qaudit.analysis import analyze,calibrate
from qaudit.archive import export_archive,restore_archive
from qaudit.audit import audit
from qaudit.common import digest,read_json,write_json
from qaudit.data import canonical_row,permute
from qaudit.scoring import freeze,check_frozen,protocol_identity
from qaudit.store import ScoreStore,cell_name


def test_complete_cached_pipeline_without_gpu(tmp_path,monkeypatch):
    monkeypatch.setenv("MPLCONFIGDIR",str(tmp_path/"mpl"))
    cfg=read_json(Path(__file__).parents[1]/"configs/study.json")
    cfg.update(calibration_sizes=[2,4],calibration_seeds=2,bootstrap_replicates=12)
    cfg["counts"]={"pilot":8,"calibration":4,"validation":4,"robustness":4}
    write_json(tmp_path/"study.json",cfg)
    pin={"repo":"test-fixture/never-download","revision":"fixture-only"}
    write_json(tmp_path/"pins.json",{"fixture_only":True,"models":{"primary":pin}})
    splits={}
    for d in cfg["datasets"]:
        splits[d]={}
        for stage,n in (("pilot",8),("calibration",4),("validation",4),("test",8)):
            rows=[]
            for i in range(n):
                rows.append(canonical_row({"id":f"{stage}-{i}","question":f"{d} {stage} {i}",
                    "choices":{"label":["A","B","C"],"text":["red","blue","green"]},"answerKey":"A"},d))
            splits[d][stage]=rows
        splits[d]["robustness"]=splits[d]["test"][:4]
    write_json(tmp_path/"splits.json",splits)
    write_json(tmp_path/"split-manifest.json",{"fixture_only":True})
    with ScoreStore(tmp_path/"scores.sqlite") as store:
        for bits in cfg["precisions"]:
            files={"fixture":{"sha256":digest("fixture"),"bytes":1000}}
            write_json(tmp_path/"models"/"primary"/str(bits)/"artifact.json",{
                "serialized_bytes":1000,"fixture_only":True,"files":files,"artifact_hash":digest(files),"spec":{"pin":pin},
                "quantized_modules":[] if bits==16 else [{"name":"fixture","bits":bits,"group_size":64}]})
            for d in cfg["datasets"]:
                for stage,rows in splits[d].items():
                    cell=cell_name("primary",bits,d,stage)
                    store.register(cell,{"fixture_only":True,"protocol":protocol_identity(tmp_path),"artifact_hash":digest(files),
                                         "role":"primary","bits":bits,"dataset":d,"stage":stage})
                    for i,row in enumerate(rows):
                        r=permute(row,cfg["seed"]) if stage=="robustness" else row
                        original_scores=np.array([3.,1.,0.]) if i%4 else np.array([1.,3.,0.])
                        order=r.get("option_order",[0,1,2])
                        record={"key":r["key"],"prompt_hash":digest([r["key"],order]),"input_tokens":40,
                                "option_scores":original_scores[order].tolist(),
                                "option_token_ids":[1,2,3],"option_order":order,"outside_option_mass":.1,
                                "latency_seconds":.01,"peak_memory_bytes":1000}
                        if stage=="pilot" and i<3:
                            record["repeat_max_probability_delta"]=0.0
                        store.insert(cell,record)
    calibrate(tmp_path,"primary")
    freeze(tmp_path)
    out=tmp_path/"results"
    result=analyze(tmp_path,out)
    assert result["primary"]["replicates"]==12
    assert len(list(out.glob("figure-*.png")))==4
    assert (out/"REPORT.md").exists()
    assert read_json(out/"results.json")["primary"]["estimate"]==pytest.approx(0,abs=1e-7)
    archive=tmp_path/"archive"
    export_archive(tmp_path,archive)
    restored=tmp_path/"restored"
    restore_archive(archive,restored)
    # The archive round trip retains question identities and complete statistics.
    assert analyze(restored,tmp_path/"reanalysis")["primary"]==result["primary"]
    checked=audit(restored,tmp_path/"acceptance.json")
    assert checked["passed"] and checked["scoring_records"]==168
    # Corrupt a restored model manifest: the score-to-artifact link must fail.
    artifact_path=restored/"models/primary/4/artifact.json"
    artifact=read_json(artifact_path);artifact["artifact_hash"]="tampered"
    write_json(artifact_path,artifact)
    with pytest.raises(ValueError,match="failed acceptance"):
        audit(restored,tmp_path/"corrupt-acceptance.json")
    with pytest.raises(ValueError,match="empty"):
        restore_archive(archive,restored)
    modified=read_json(tmp_path/"calibration-primary.json")
    modified["role"]="tampered"
    write_json(tmp_path/"calibration-primary.json",modified)
    with pytest.raises(ValueError,match="Calibration artifact changed"):
        check_frozen(tmp_path)

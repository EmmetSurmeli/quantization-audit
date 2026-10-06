import numpy as np
import pytest

from qaudit.data import canonical_row,build_splits,permute
from qaudit.common import write_json,read_json,workspace_lock
from qaudit.store import ScoreStore,aligned_records
from qaudit.analysis import assert_paired
from qaudit.scoring import check_frozen


def raw(i,question=None):
    return {"id":str(i),"question":question or f"Question {i}","choices":{"label":["1","2","3"],"text":["red","blue","green"]},"answerKey":"2"}


def test_permutation_keeps_semantic_gold_and_is_reproducible():
    row=canonical_row(raw(1),"ARC-Challenge")
    p=permute(row,7)
    assert p["choices"][p["gold"]]=="blue"
    assert p["option_order"]!=[0,1,2]
    assert p==permute(row,7)
    assert row["gold"]==1


def test_duplicate_content_never_leaks_even_with_different_id_and_order():
    test=raw(90," same   QUESTION ")
    duplicate=raw(91,"SAME question")
    duplicate["choices"]={"label":["A","B","C"],"text":["green","red","blue"]}
    duplicate["answerKey"]="C"
    cfg={"datasets":["D"],"seed":3,"counts":{"pilot":1,"calibration":2,"validation":1,"robustness":1}}
    source={"D":{"test":[test],"validation":[raw(80)],"train":[duplicate]+[raw(i) for i in range(5)]}}
    splits,excluded=build_splits(source,cfg)
    assert any(r["key"]=="D:91" for r in excluded)
    allrows=[r for s in ["pilot","calibration","validation","test"] for r in splits["D"][s]]
    assert len({r["content_hash"] for r in allrows})==len(allrows)
    assert build_splits(source,cfg)==(splits,excluded)


def test_bad_label_rejected():
    r=raw(2);r["answerKey"]="Z"
    with pytest.raises(ValueError):
        canonical_row(r,"D")


def test_repeated_stem_with_changed_distractors_cannot_cross_splits():
    a=raw(90,"The same question?")
    variant=raw(91,"the same question?")
    variant["choices"]["text"][0]="different distractor"
    cfg={"datasets":["D"],"seed":3,"counts":{"pilot":1,"calibration":2,"validation":1,"robustness":1}}
    source={"D":{"test":[a],"validation":[raw(80)],"train":[variant]+[raw(i) for i in range(5)]}}
    splits,excluded=build_splits(source,cfg)
    assert {"key":"D:91","split":"train","reason":"cross_split_question_stem"} in excluded
    assert len(splits["D"]["test"])==1


def test_resume_is_exactly_once_and_immutable(tmp_path):
    path=tmp_path/"s.sqlite"
    with ScoreStore(path) as store:
        store.register("cell",{"model":"a"})
        store.insert("cell",{"key":"one","value":2})
    with ScoreStore(path) as store:
        store.register("cell",{"model":"a"})
        store.insert("cell",{"key":"one","value":2})
        store.insert("cell",{"key":"two","value":3})
        assert len(store.records("cell"))==2
        with pytest.raises(ValueError):
            store.register("cell",{"model":"different"})
        with pytest.raises(ValueError):
            store.insert("cell",{"key":"one","value":9})
        with pytest.raises(ValueError):
            aligned_records(store,"cell",[{"key":"one"}])
        assert [r["key"] for r in aligned_records(store,"cell",[{"key":"two"},{"key":"one"}])]==["two","one"]


def test_atomic_immutable_manifest(tmp_path):
    path=tmp_path/"manifest.json"
    write_json(path,{"seed":1},immutable=True)
    write_json(path,{"seed":1},immutable=True)
    with pytest.raises(ValueError):
        write_json(path,{"seed":2},immutable=True)
    assert read_json(path)=={"seed":1}


def test_pairing_rejects_shuffled_or_changed_prompts():
    a={"key":"one","prompt_hash":"x","option_token_ids":[1,2],"option_order":[0,1]}
    with pytest.raises(ValueError):
        assert_paired([a],[dict(a,prompt_hash="y")])


def test_test_access_requires_freeze(tmp_path):
    with pytest.raises(ValueError,match="frozen"):
        check_frozen(tmp_path)

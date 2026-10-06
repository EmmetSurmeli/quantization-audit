from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from .common import config_at,digest,environment,read_json,source_hash,write_json,stable_order
from .data import permute,selection
from .stats import (bootstrap_transfer,conclusion,fit_temperature,matrix,metrics,probabilities)
from .store import ScoreStore,aligned_records,cell_name


def load_cell(workspace,store,role,bits,dataset,stage):
    rows=selection(workspace,dataset,stage)
    if stage=="robustness":
        rows=[permute(r,config_at(workspace)["seed"]) for r in rows]
    records=aligned_records(store,cell_name(role,bits,dataset,stage),rows)
    for row,record in zip(rows,records):
        if len(record["option_scores"])!=len(row["choices"]) or record["option_order"]!=row.get("option_order",list(range(len(row["choices"])))):
            raise ValueError("Option alignment mismatch")
    return rows,records,matrix([r["option_scores"] for r in records]),np.array([r["gold"] for r in rows])


def assert_paired(left,right):
    for a,b in zip(left,right):
        if any(a[k]!=b[k] for k in ("key","prompt_hash","option_token_ids","option_order")):
            raise ValueError("Question/prompt pairing broken")
    if len(left)!=len(right):
        raise ValueError("Question count pairing broken")


def calibrate(workspace,role):
    ws=Path(workspace);cfg=config_at(ws)
    result={"role":role,"config_hash":digest(cfg),"fit_source":source_hash(["stats"]),"datasets":{}}
    with ScoreStore(ws/"scores.sqlite") as store:
        for dataset in cfg["datasets"]:
            fits={};source={};ref=None
            for bits in cfg["precisions"]:
                rows,records,logits,y=load_cell(ws,store,role,bits,dataset,"calibration")
                if ref is not None:
                    assert_paired(ref,records)
                ref=records
                fits[str(bits)]=fit_temperature(logits,y,cfg["temperature_bounds"])
                source[str(bits)]=digest(records)
            result["datasets"][dataset]={"fits":fits,"score_hashes":source,"ids":[r["key"] for r in rows]}
    write_json(ws/f"calibration-{role}.json",result,immutable=True)
    return result


def csv_write(path,rows):
    if not rows:
        return
    with Path(path).open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)


def analyze(workspace,out):
    ws=Path(workspace);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    frozen=read_json(ws/"frozen.json");cfg=config_at(ws)
    # Reanalysis needs no GPU or original OS. Verify immutable inputs and fit code,
    # while recording the analysis environment separately from the scoring one.
    for key,value in (("config",cfg),("pins",read_json(ws/"pins.json")),("splits",read_json(ws/"splits.json"))):
        if frozen["identity"][key]!=digest(value):
            raise ValueError("Frozen analysis input changed")
    for role in frozen["roles"]:
        calibration=read_json(ws/f"calibration-{role}.json")
        if digest(calibration)!=frozen["calibration_hashes"][role] or calibration["fit_source"]!=source_hash(["stats"]):
            raise ValueError("Frozen calibration or metric implementation changed")
    metric_rows=[];curves=[];flips=[];resources=[];robust=[];examples=[];details={};primary=None
    with ScoreStore(ws/"scores.sqlite") as store:
        for role in frozen["roles"]:
            cal=read_json(ws/f"calibration-{role}.json")
            for dataset in cfg["datasets"]:
                cal_rows,cal_ref_records,cal_ref,cal_y=load_cell(ws,store,role,16,dataset,"calibration")
                test_rows,ref_records,ref_logits,test_y=load_cell(ws,store,role,16,dataset,"test")
                ref_pred=ref_logits.argmax(axis=1)
                suborders=[]
                for seed in range(cfg["calibration_seeds"]):
                    rng=np.random.default_rng(cfg["seed"]+seed)
                    suborders.append(rng.permutation(len(cal_y)))
                for bits in cfg["precisions"]:
                    _,crecords,clogits,cy=load_cell(ws,store,role,bits,dataset,"calibration")
                    rows,records,tlogits,ty=load_cell(ws,store,role,bits,dataset,"test")
                    assert_paired(ref_records,records);assert_paired(cal_ref_records,crecords)
                    if digest(crecords)!=cal["datasets"][dataset]["score_hashes"][str(bits)]:
                        raise ValueError("Calibration scores changed after fitting")
                    fits=cal["datasets"][dataset]["fits"]
                    treatments={"raw":1.0,"transferred":fits["16"]["temperature"],"refitted":fits[str(bits)]["temperature"]}
                    cell=cell_name(role,bits,dataset,"test")
                    for treatment,temp in treatments.items():
                        m=metrics(tlogits,ty,temp,cfg["ece_bins"],cfg["confidence_thresholds"])
                        metric_rows.append({"model":role,"dataset":dataset,"bits":bits,"treatment":treatment,"temperature":temp,
                                            **{k:m[k] for k in ("n","accuracy","brier","nll","ece")}})
                        details[f"{cell}/{treatment}"]=m
                    uniform=np.where(np.isfinite(tlogits),0.0,-np.inf)
                    um=metrics(uniform,ty)
                    if bits==16:
                        metric_rows.append({"model":role,"dataset":dataset,"bits":0,"treatment":"uniform","temperature":1.0,
                                           **{k:um[k] for k in ("n","accuracy","brier","nll","ece")}})
                    qp=tlogits.argmax(axis=1)
                    changed=qp!=ref_pred
                    harmful=(ref_pred==ty)&(qp!=ty)
                    beneficial=(ref_pred!=ty)&(qp==ty)
                    flips.append({"model":role,"dataset":dataset,"bits":bits,"n":len(ty),"changed":int(changed.sum()),
                                  "harmful":int(harmful.sum()),"beneficial":int(beneficial.sum()),
                                  "wrong_to_different_wrong":int((changed&~harmful&~beneficial).sum())})
                    meta=read_json(ws/"models"/role/str(bits)/"artifact.json")
                    resources.append({"model":role,"dataset":dataset,"bits":bits,"model_bytes":meta["serialized_bytes"],
                                      "peak_memory_gb":max(r["peak_memory_bytes"] for r in records)/1e9,
                                      "mean_latency_seconds":float(np.mean([r["latency_seconds"] for r in records])),
                                      "p95_latency_seconds":float(np.quantile([r["latency_seconds"] for r in records],.95)),
                                      "input_tokens":sum(r["input_tokens"] for r in records),
                                      "mean_outside_option_mass":float(np.mean([r["outside_option_mass"] for r in records]))})
                    for n in cfg["calibration_sizes"]:
                        # At n=400 all ten subsets coincide: do not pretend ten repeats add information.
                        for seed,order in enumerate(suborders[:1] if n==len(cy) else suborders):
                            idx=order[:n]
                            f0=fit_temperature(cal_ref[idx],cal_y[idx],cfg["temperature_bounds"])
                            f1=fit_temperature(clogits[idx],cy[idx],cfg["temperature_bounds"])
                            for treatment,fit in (("transferred",f0),("refitted",f1)):
                                temp=fit["temperature"]
                                m=metrics(tlogits,ty,temp)
                                curves.append({"model":role,"dataset":dataset,"bits":bits,"n_calibration":n,"subset_seed":seed,
                                               "treatment":treatment,"temperature":temp,"at_boundary":fit["at_boundary"],"test_brier":m["brier"]})
                    if role=="primary" and dataset=="ARC-Challenge" and bits==4:
                        primary=bootstrap_transfer(cal_ref,clogits,cy,tlogits,ty,reps=cfg["bootstrap_replicates"],
                                                   seed=cfg["seed"],bounds=cfg["temperature_bounds"])
                        primary["conclusion"]=conclusion(primary,cfg["practical_brier_difference"])
                        primary["baseline_brier"]=metrics(tlogits,ty,treatments["transferred"])["brier"]
                        primary["refitted_brier"]=metrics(tlogits,ty,treatments["refitted"])["brier"]
                        primary["comparison"]="Qwen3-4B / ARC-Challenge / 4-bit / transferred minus refitted / n_cal=400"
                        categories={"unchanged_correct":(~changed)&(qp==ty),"unchanged_wrong":(~changed)&(qp!=ty),
                                    "beneficial_flip":beneficial,"harmful_flip":harmful}
                        for name,mask in categories.items():
                            candidates=[dict(rows[i],_index=i) for i in np.flatnonzero(mask)]
                            for r in stable_order(candidates,cfg["seed"],"error-analysis")[:5]:
                                i=r.pop("_index")
                                examples.append(dict(r,category=name,reference_prediction=int(ref_pred[i]),quantized_prediction=int(qp[i]),
                                                     reference_probabilities=probabilities(ref_logits[[i]],treatments["transferred"])[0,:len(r['choices'])].tolist(),
                                                     quantized_probabilities=probabilities(tlogits[[i]],treatments["refitted"])[0,:len(r['choices'])].tolist()))
                    rr,rrecords,rlogits,ry=load_cell(ws,store,role,bits,dataset,"robustness")
                    originals={r["key"]:i for i,r in enumerate(rows)}
                    indices=[originals[r["key"]] for r in rr]
                    for treatment,temp in treatments.items():
                        a=metrics(tlogits[indices],ty[indices],temp)
                        b=metrics(rlogits,ry,temp)
                        robust.append({"model":role,"dataset":dataset,"bits":bits,"treatment":treatment,"n_pairs":len(rr),
                                       "original_brier":a["brier"],"permuted_brier":b["brier"],
                                       "paired_brier_change":b["brier"]-a["brier"],"original_accuracy":a["accuracy"],"permuted_accuracy":b["accuracy"]})
    result={"status":"measured","primary":primary,"metrics":metric_rows,"sample_size_curves":curves,
            "flips":flips,"resources":resources,"robustness":robust,"details":details,"error_cases":examples,
            "protocol":frozen,"split_amendment":(ws/'amendment-pretest-migration.json').exists(),
            "analysis_source":source_hash(),"analysis_environment":environment(),"limitations":[
                "Two related ARC subsets; at most two sizes of one model family.",
                "Closed-choice scores, not free-form reliability or reasoning quality.",
                "MLX affine weight quantization only; pretraining contamination unresolved.",
                "Secondary comparisons and option permutations are exploratory."]}
    for name,rows in (("metrics",metric_rows),("sample-size",curves),("prediction-changes",flips),("resources",resources),("robustness",robust)):
        csv_write(out/f"{name}.csv",rows)
    reliability_rows=[];selective_rows=[]
    for key,m in details.items():
        role,bits,dataset,stage,treatment=key.split('/')
        identity={'model':role,'bits':int(bits),'dataset':dataset,'treatment':treatment,'test_n':m['n']}
        reliability_rows.extend(dict(identity,**row) for row in m['reliability'])
        for row in m['selective']:
            row=dict(row);low,high=row.pop('error_rate_ci95')
            selective_rows.append(dict(identity,**row,error_ci_low=low,error_ci_high=high))
    csv_write(out/'reliability-bins.csv',reliability_rows)
    csv_write(out/'selective-answering.csv',selective_rows)
    write_json(out/"results.json",result)
    write_json(out/"error-cases.json",examples)
    make_figures(result,out)
    write_report(result,out)
    return {"primary":primary,"output":str(out)}


def make_figures(result,out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family":"sans-serif","font.size":10,"axes.spines.top":False,"axes.spines.right":False})
    colors={"raw":"#64748b","transferred":"#d97706","refitted":"#087f8c"}
    datasets=["ARC-Challenge","ARC-Easy"]
    fig,axes=plt.subplots(2,2,figsize=(10,7),layout="constrained")
    for j,d in enumerate(datasets):
        ms=[r for r in result["metrics"] if r["model"]=="primary" and r["dataset"]==d and r["treatment"]=="raw"]
        ms=sorted(ms,key=lambda r:r["bits"])
        axes[0,j].bar([str(r["bits"]) for r in ms],[r["accuracy"] for r in ms],color="#087f8c")
        axes[0,j].set(title=d,ylabel="Accuracy",ylim=(0,1),xlabel="Weight precision (bits)")
        fs=sorted([r for r in result["flips"] if r["model"]=="primary" and r["dataset"]==d],key=lambda r:r["bits"])
        x=np.arange(len(fs))
        axes[1,j].bar(x-.16,[r["harmful"]/r["n"] for r in fs],.32,label="Correct → wrong",color="#b44c42")
        axes[1,j].bar(x+.16,[r["beneficial"]/r["n"] for r in fs],.32,label="Wrong → correct",color="#087f8c")
        axes[1,j].set(xticks=x,xticklabels=[r["bits"] for r in fs],ylabel="Fraction of questions",xlabel="Weight precision (bits)")
        axes[1,j].legend(fontsize=8)
    fig.savefig(out/"figure-1-accuracy-flips.png",dpi=180);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(10,4),layout="constrained")
    for ax,d in zip(axes,datasets):
        ax.plot([0,1],[0,1],"--",color="#aaaaaa",label="Perfect calibration")
        for t in colors:
            bins=result["details"][f"primary/4/{d}/test/{t}"]["reliability"]
            bins=[b for b in bins if b["n"]]
            ax.plot([b["confidence"] for b in bins],[b["accuracy"] for b in bins],"o-",label=t,color=colors[t])
        ax.set(title=f"4-bit · {d}",xlabel="Mean predicted confidence",ylabel="Observed accuracy",xlim=(0,1),ylim=(0,1))
        ax.legend(fontsize=8)
    fig.savefig(out/"figure-2-reliability.png",dpi=180);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(10,4),layout="constrained")
    for ax,d in zip(axes,datasets):
        for t in ("transferred","refitted"):
            selected=[r for r in result["sample_size_curves"] if r["model"]=="primary" and r["dataset"]==d and r["bits"]==4 and r["treatment"]==t]
            ns=sorted({r["n_calibration"] for r in selected})
            values=[np.array([r["test_brier"] for r in selected if r["n_calibration"]==n]) for n in ns]
            means=[v.mean() for v in values]
            ax.plot(ns,means,"o-",color=colors[t],label=t)
            ax.fill_between(ns,[v.min() for v in values],[v.max() for v in values],alpha=.15,color=colors[t])
        ax.set(title=f"4-bit · {d}",xlabel="Calibration examples",ylabel="Held-out Brier score (lower is better)")
        ax.legend(fontsize=8)
    fig.suptitle("Shading: range across calibration subsets, not a confidence interval",fontsize=10)
    fig.savefig(out/"figure-3-label-budget.png",dpi=180);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(10,4),layout="constrained")
    for ax,d in zip(axes,datasets):
        for t in colors:
            points=result["details"][f"primary/4/{d}/test/{t}"]["selective"]
            points=[p for p in points if p["answered"]]
            ax.plot([p["coverage"] for p in points],[p["error_rate"] for p in points],"-",label=t,color=colors[t])
            for p in points:
                marker={0.5:"o",0.7:"s",0.9:"^"}[p["threshold"]]
                ax.plot(p["coverage"],p["error_rate"],marker=marker,color=colors[t],linestyle="none",markersize=5)
        ax.set(title=f"4-bit · {d}",xlabel="Coverage",ylabel="Error among answered questions",xlim=(0,1))
        ax.legend(fontsize=8)
    from matplotlib.lines import Line2D
    treatment_legend=axes[1].get_legend()
    axes[1].add_artist(treatment_legend)
    axes[1].legend(handles=[Line2D([],[],color="0.4",marker=m,linestyle="none",label=str(t))
                           for t,m in [(0.5,"o"),(0.7,"s"),(0.9,"^")]],
                   title="Confidence threshold",loc="lower left",fontsize=8,title_fontsize=8)
    fig.suptitle("Prespecified confidence thresholds; not optimized on test data",fontsize=10)
    fig.savefig(out/"figure-4-coverage-error.png",dpi=180);plt.close(fig)


def write_report(result,out):
    p=result["primary"]
    rows=["# Quantization and confidence: measured calibration-transfer audit","",
          "Status: measured results. This report is generated from saved model scores; no synthetic results are included.","",
          "## Primary result","",p["conclusion"],"",
          f"{p['comparison']}. Paired Brier difference: **{p['estimate']:.6f}**, 95% bootstrap interval **[{p['ci95'][0]:.6f}, {p['ci95'][1]:.6f}]**. Positive values favor refitting.","",
          "The bootstrap resamples calibration and test questions independently, retains pairing across treatments, and refits temperatures. Brier score measures probability quality, not calibration alone. Positive temperature scaling cannot change the selected option.","",
          "## Methods","",
          "Official Qwen3 checkpoints were converted to BF16 and MLX affine 8/4-bit weight quantization with group size 64. One model is loaded at a time. Scores are obtained with thinking disabled, identical prompt tokens across precisions, and verified single-token option labels. Probabilities are conditional on the available choices.","",
          "For each ARC subset, 100 training questions are reserved for the pilot, 400 disjoint training questions for calibration, and 100 validation questions for pipeline checks. Content, normalized question-stem, and ID overlap are checked across official splits. The primary test is the complete ARC-Challenge test split.","",
          ("Protocol timing: an initial freeze preceded test scoring. A data-only stem-overlap correction was made before any held-out performance summary was inspected; calibration was refitted and frozen anew. Unchanged raw scores acquired under the initial protocol were reused with per-record provenance. See docs/PROTOCOL-AMENDMENT.md." if result['split_amendment'] else "The protocol and calibration were frozen before held-out scoring."),"",
          "## Results","","| Model | Dataset | Bits | Treatment | Accuracy | Brier | NLL | ECE |","|---|---|---:|---|---:|---:|---:|---:|"]
    for r in result["metrics"]:
        rows.append(f"| {r['model']} | {r['dataset']} | {r['bits']} | {r['treatment']} | {r['accuracy']:.4f} | {r['brier']:.4f} | {r['nll']:.4f} | {r['ece']:.4f} |")
    for number,name in [(1,"accuracy-flips"),(2,"reliability"),(3,"label-budget"),(4,"coverage-error")]:
        rows.extend(["",f"![Figure {number}](figure-{number}-{name}.png)"])
    rows.extend(["","## Resource measurements","","| Model | Dataset | Bits | File GB | Peak MLX GB | Mean seconds/question |","|---|---|---:|---:|---:|---:|"])
    for r in result["resources"]:
        rows.append(f"| {r['model']} | {r['dataset']} | {r['bits']} | {r['model_bytes']/1e9:.3f} | {r['peak_memory_gb']:.3f} | {r['mean_latency_seconds']:.4f} |")
    rows.extend(["","## Robustness and limitations","",
                 "Option-order checks use paired originals and one prespecified permutation per question. They are exploratory; permutations are not new independent observations. See robustness.csv for every cell.",""])
    rows.extend(f"- {s}" for s in result["limitations"])
    rows.extend(["","## Interpretation and next steps","",
                 "A null or inconclusive result does not establish universal equivalence. A positive result is specific to the reported baseline and scoring protocol. Claims about label efficiency should consider the full sample-size curve, including subset variability, rather than its best seed.","",
                 "Twenty error-analysis slots are prespecified across four prediction-transition categories. If a category has fewer than five examples, the report includes fewer cases rather than substituting favorable examples. Saved cases are in error-cases.json.","",
                 "## Prior work","",
                 "- Guo et al. (2017), [On Calibration of Modern Neural Networks](https://proceedings.mlr.press/v70/guo17a.html).",
                 "- Proskurina et al. (2024), [When Quantization Affects Confidence](https://aclanthology.org/2024.findings-naacl.124/).",
                 "- [Accuracy Is Not All You Need](https://arxiv.org/abs/2407.09141) (2024).",
                 "- Zhong et al. (2025), [Quantized Can Still Be Calibrated](https://aclanthology.org/2025.acl-long.1473/).",
                 "- [Target-Aware Calibration Data Selection](https://arxiv.org/abs/2608.21019) (2026 preprint).",""])
    (out/"REPORT.md").write_text("\n".join(rows))

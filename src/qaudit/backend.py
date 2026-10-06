from __future__ import annotations

import gc
import json
import time
from pathlib import Path

import numpy as np
from scipy.special import logsumexp

from .common import config_at, digest, environment, file_hash, read_json, write_json


def model_path(workspace, role, bits):
    return Path(workspace) / "models" / role / str(bits)


def model_inventory(path):
    files = {p.name: {"sha256": file_hash(p), "bytes": p.stat().st_size}
             for p in sorted(Path(path).glob("*")) if p.is_file() and p.name != "artifact.json"}
    return files


def convert_model(workspace, role, bits):
    from huggingface_hub import snapshot_download
    from mlx_lm.convert import convert
    from mlx_lm import load
    import mlx.core as mx

    cfg = config_at(workspace)
    pin = read_json(Path(workspace)/"pins.json")["models"][role]
    path = model_path(workspace,role,bits)
    metadata = path/"artifact.json"
    spec = {"pin":pin, "bits":bits, "quantization":cfg["quantization"]}
    if metadata.exists():
        saved = read_json(metadata)
        if saved["spec"] != spec or model_inventory(path) != saved["files"]:
            raise ValueError("Model artifact changed; do not reuse it")
        return saved
    if path.exists():
        raise ValueError(f"Incomplete conversion at {path}; move it aside before retrying")
    # Quantized variants are derived from the exact locally converted BF16 reference.
    if bits == 16:
        source = snapshot_download(pin["repo"], revision=pin["revision"],
                                   allow_patterns=["*.json","*.safetensors","tokenizer.model","*.jinja","*.txt"])
    else:
        reference = model_path(workspace,role,16)
        if not (reference/"artifact.json").exists():
            raise ValueError("Convert BF16 first")
        source = str(reference)
    path.parent.mkdir(parents=True,exist_ok=True)
    convert(hf_path=str(source), mlx_path=str(path), quantize=bits != 16,
            q_bits=bits if bits != 16 else None, q_group_size=cfg["quantization"]["group_size"],
            q_mode="affine", dtype="bfloat16", upload_repo=None, trust_remote_code=False)
    model, tokenizer = load(str(path))
    model.eval()
    mx.eval(model.parameters())
    quantized = []
    for name,module in model.named_modules():
        if hasattr(module,"bits") and hasattr(module,"group_size"):
            quantized.append({"name":name,"class":type(module).__name__,"bits":int(module.bits),
                              "group_size":int(module.group_size)})
    if bits != 16 and (not quantized or any(q["bits"] != bits or q["group_size"] != 64 for q in quantized)):
        raise ValueError("Unexpected quantization layout")
    if bits == 16 and quantized:
        raise ValueError("Reference must not contain quantized modules")
    del model,tokenizer
    gc.collect()
    mx.clear_cache()
    files = model_inventory(path)
    result = {"spec":spec,"files":files,"artifact_hash":digest(files),"quantized_modules":quantized,
              "serialized_bytes":sum(f["bytes"] for f in files.values()),"environment":environment()}
    write_json(metadata,result,immutable=True)
    return result


class MLXScorer:
    def __init__(self,path,cfg):
        import mlx.core as mx
        from mlx_lm import load
        if not mx.metal.is_available():
            raise RuntimeError("Metal GPU unavailable; no silent CPU/backend fallback")
        self.mx,self.cfg = mx,cfg
        self.model,self.tokenizer = load(str(path))
        self.model.eval()
        mx.eval(self.model.parameters())
        self.label_tokens = {}
        for label in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            encoded = self.tokenizer.encode(label,add_special_tokens=False)
            if len(encoded)==1 and self.tokenizer.decode(encoded)==label:
                self.label_tokens[label]=encoded[0]

    def prompt(self,row):
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[:len(row["choices"])]
        if any(x not in self.label_tokens for x in letters):
            raise ValueError("Option letters are not verified single tokens")
        content = self.cfg["instruction"]+"\n\nQuestion: "+row["question"]+"\n"+"\n".join(f"{c}. {text}" for c,text in zip(letters,row["choices"]))
        ids = self.tokenizer.apply_chat_template([{"role":"user","content":content}],
                  tokenize=True,add_generation_prompt=True,enable_thinking=False)
        if len(ids)>self.cfg["max_input_tokens"]:
            raise ValueError(f"Question exceeds token cap; never truncate silently: {row['key']}")
        return list(ids),[self.label_tokens[c] for c in letters]

    def score(self,row):
        mx = self.mx
        ids,labels = self.prompt(row)
        mx.synchronize()
        mx.reset_peak_memory()
        start = time.perf_counter()
        # No persistent KV cache: one independent, deterministic forward pass.
        last = self.model(mx.array([ids]))[0,-1,:].astype(mx.float32)
        mx.eval(last)
        scores = np.asarray(last,dtype=np.float64)
        elapsed = time.perf_counter()-start
        selected = scores[labels]
        if not np.isfinite(selected).all():
            raise ValueError("Non-finite option scores")
        log_mass = float(logsumexp(selected)-logsumexp(scores))
        return {"key":row["key"],"prompt_hash":digest(ids),"input_tokens":len(ids),
                "option_scores":selected.tolist(),"option_token_ids":labels,
                "option_order":row.get("option_order",list(range(len(labels)))),
                "outside_option_mass":float(np.clip(-np.expm1(log_mass),0,1)),
                "latency_seconds":elapsed,"peak_memory_bytes":int(mx.get_peak_memory())}

    def close(self):
        del self.model,self.tokenizer
        gc.collect()
        self.mx.clear_cache()

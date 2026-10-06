from __future__ import annotations

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import logsumexp


def matrix(scores):
    """Pad variable-choice questions with -inf, never with an extra option."""
    if not scores:
        raise ValueError("No scores")
    x = np.full((len(scores), max(map(len, scores))), -np.inf, dtype=np.float64)
    for i, row in enumerate(scores):
        if len(row) < 2 or not np.isfinite(row).all():
            raise ValueError("Each question needs at least two finite option scores")
        x[i, :len(row)] = row
    return x


def probabilities(logits, temperature=1.0):
    if not np.isfinite(temperature) or temperature <= 0:
        raise ValueError("Temperature must be finite and positive")
    z = np.asarray(logits, dtype=np.float64) / temperature
    if z.ndim != 2 or np.isnan(z).any() or np.isposinf(z).any() or not np.isfinite(z).any(axis=1).all():
        raise ValueError("Invalid logit matrix")
    p = np.exp(z - logsumexp(z, axis=1, keepdims=True))
    return p


def validate_labels(logits, labels):
    y = np.asarray(labels, dtype=int)
    if len(y) != len(logits) or (y < 0).any() or (y >= logits.shape[1]).any() or not np.isfinite(logits[np.arange(len(y)), y]).all():
        raise ValueError("Invalid or misaligned labels")
    return y


def fit_temperature(logits, labels, bounds=(0.05, 20.0)):
    y = validate_labels(logits, labels)
    if len(y) == 0:
        raise ValueError("Empty calibration set")
    def loss(log_t):
        z = logits / np.exp(log_t)
        return float(np.mean(logsumexp(z, axis=1) - z[np.arange(len(y)), y]))
    lo, hi = np.log(bounds)
    opt = minimize_scalar(loss, bounds=(lo, hi), method="bounded", options={"xatol": 1e-7})
    if not opt.success:
        raise RuntimeError("Temperature fit failed")
    t = float(np.exp(opt.x))
    return {"temperature": t, "fit_nll": float(opt.fun), "n": len(y),
            "at_boundary": bool(min(abs(opt.x-lo), abs(opt.x-hi)) < 1e-3)}


def brier_rows(p, y):
    return np.sum(p*p, axis=1) - 2*p[np.arange(len(y)), y] + 1


def reliability(p, y, bins=10):
    conf, correct = p.max(axis=1), p.argmax(axis=1) == y
    assignments = np.minimum((conf * bins).astype(int), bins-1)
    result = []
    for b in range(bins):
        mask = assignments == b
        result.append({"left": b/bins, "right": (b+1)/bins, "n": int(mask.sum()),
                       "confidence": float(conf[mask].mean()) if mask.any() else None,
                       "accuracy": float(correct[mask].mean()) if mask.any() else None})
    return result


def wilson(success, n):
    if n == 0:
        return [None, None]
    z, p = 1.95996398454, success/n
    d = 1 + z*z/n
    center = (p + z*z/(2*n))/d
    half = z*np.sqrt(p*(1-p)/n + z*z/(4*n*n))/d
    return [float(center-half), float(center+half)]


def metrics(logits, y, temperature=1.0, bins=10, thresholds=(.5,.7,.9)):
    y = validate_labels(logits, y)
    p = probabilities(logits, temperature)
    z = logits / temperature
    rel = reliability(p, y, bins)
    pred, conf = p.argmax(axis=1), p.max(axis=1)
    selective = []
    for threshold in thresholds:
        mask = conf >= threshold
        n, errors = int(mask.sum()), int((pred[mask] != y[mask]).sum())
        selective.append({"threshold": threshold, "answered": n, "errors": errors,
                          "coverage": n/len(y), "error_rate": errors/n if n else None,
                          "error_rate_ci95": wilson(errors,n), "small_sample": n < 50})
    return {"n": len(y), "accuracy": float(np.mean(pred == y)),
            "brier": float(brier_rows(p,y).mean()),
            "nll": float(np.mean(logsumexp(z,axis=1)-z[np.arange(len(y)),y])),
            "ece": float(sum(b["n"]*abs(b["accuracy"]-b["confidence"]) for b in rel if b["n"])/len(y)),
            "reliability": rel, "selective": selective}


def bootstrap_transfer(cal_ref, cal_q, cal_y, test_q, test_y, *, reps=2000, seed=0, bounds=(.05,20)):
    """Two independent resampling units: calibration questions and test questions.

    Both precisions use the SAME sampled calibration indices. Both treatments
    use the SAME sampled test indices. Temperatures are refitted per replicate.
    """
    if len(cal_ref) != len(cal_q):
        raise ValueError("Calibration pairing broken")
    rng = np.random.default_rng(seed)
    tr = fit_temperature(cal_ref, cal_y, bounds)["temperature"]
    tq = fit_temperature(cal_q, cal_y, bounds)["temperature"]
    delta = brier_rows(probabilities(test_q,tr),test_y)-brier_rows(probabilities(test_q,tq),test_y)
    samples = np.empty(reps)
    for b in range(reps):
        c = rng.integers(len(cal_y),size=len(cal_y))
        t = rng.integers(len(test_y),size=len(test_y))
        t0 = fit_temperature(cal_ref[c],cal_y[c],bounds)["temperature"]
        t1 = fit_temperature(cal_q[c],cal_y[c],bounds)["temperature"]
        d = brier_rows(probabilities(test_q[t],t0),test_y[t])-brier_rows(probabilities(test_q[t],t1),test_y[t])
        samples[b] = d.mean()
    return {"estimate": float(delta.mean()), "ci95": np.quantile(samples,[.025,.975]).tolist(),
            "replicates": reps, "seed": seed, "method": "paired two-sample bootstrap with calibration refit"}


def conclusion(result, margin=.01):
    low, high = result["ci95"]
    if low > 0 and result["estimate"] >= margin:
        return "Refitting improves Brier score with a practically meaningful point estimate."
    if low >= -margin and high <= margin:
        return "The interval supports little practical difference within the prespecified margin in this setup."
    if high < 0:
        return "Refitting worsens Brier score in this setup."
    return "The evidence is inconclusive at the prespecified practical-effect threshold."

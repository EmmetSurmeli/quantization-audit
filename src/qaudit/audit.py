"""Acceptance checks against the actual completed score archive, without inference."""
from __future__ import annotations

from pathlib import Path
import numpy as np

from .analysis import load_cell,assert_paired
from .common import config_at,digest,read_json,write_json
from .stats import probabilities
from .store import ScoreStore,cell_name
from .data import normalize


def audit(workspace,out):
    ws=Path(workspace);cfg=config_at(ws)
    frozen=read_json(ws/'frozen.json');splits=read_json(ws/'splits.json');pins=read_json(ws/'pins.json')
    checks=[];observations=0;input_tokens=0;modules=[];score_seconds=0.0
    def check(name,passed):
        checks.append({'check':name,'passed':bool(passed)})
    seen_keys=set();seen_content=set()
    stems={stage:{normalize(r['question']) for d in splits.values() for r in d[stage]}
           for stage in ('pilot','calibration','validation','test')}
    for a,b in (('pilot','test'),('calibration','test'),('validation','test'),('calibration','validation')):
        check(f'No normalized question-stem overlap: {a}/{b}',not(stems[a]&stems[b]))
    for d,stages in splits.items():
        for stage in ('pilot','calibration','validation','test'):
            rows=stages[stage]
            keys={r['key'] for r in rows};content={r['content_hash'] for r in rows}
            check(f'Unique IDs and normalized content: {d}/{stage}',
                  len(rows)==len(keys)==len(content) and not(keys&seen_keys) and not(content&seen_content))
            seen_keys.update(keys);seen_content.update(content)
        check(f'Permutation subset: {d}',{r['key'] for r in stages['robustness']} <= {r['key'] for r in stages['test']})
    with ScoreStore(ws/'scores.sqlite') as store:
        for role in frozen['roles']:
            cal=read_json(ws/f'calibration-{role}.json')
            check(f'Frozen calibration: {role}',digest(cal)==frozen['calibration_hashes'][role])
            for b in cfg['precisions']:
                meta=read_json(ws/'models'/role/str(b)/'artifact.json')
                check(f'Artifact identity: {role}/{b}',meta['artifact_hash']==digest(meta['files']) and meta['spec']['pin']==pins['models'][role])
                qm=meta['quantized_modules']
                check(f'Quantizer layout: {role}/{b}',not qm if b==16 else bool(qm) and all(x['bits']==b and x['group_size']==64 for x in qm))
                modules.append({'model':role,'bits':b,'quantized_modules':len(qm)})
            for d in cfg['datasets']:
                for stage in ('pilot','calibration','validation','test','robustness'):
                    reference=None
                    for b in cfg['precisions']:
                        name=cell_name(role,b,d,stage)
                        rows,records,x,y=load_cell(ws,store,role,b,d,stage)
                        check(f'Frozen scoring provenance: {name}',store.identity(name)['protocol']==frozen['identity'])
                        meta=read_json(ws/'models'/role/str(b)/'artifact.json')
                        identity=store.identity(name)
                        check(f'Cell and model identity: {name}',identity['artifact_hash']==meta['artifact_hash'] and
                              (identity['role'],identity['bits'],identity['stage'],identity['dataset'])==(role,b,stage,d))
                        if reference is not None: assert_paired(reference,records)
                        reference=records
                        p=probabilities(x)
                        check(f'Valid probabilities: {name}',np.isfinite(p).all() and np.allclose(p.sum(axis=1),1,atol=1e-12))
                        check(f'No truncation / valid diagnostics: {name}',all(0<r['input_tokens']<=cfg['max_input_tokens'] and 0<=r['outside_option_mass']<=1 and r['latency_seconds']>0 for r in records))
                        for temp in (cal['datasets'][d]['fits']['16']['temperature'],cal['datasets'][d]['fits'][str(b)]['temperature']):
                            check(f'Temperature preserves choices: {name} T={temp:.8f}',np.array_equal(x.argmax(axis=1),probabilities(x,temp).argmax(axis=1)))
                        if stage=='calibration':
                            check(f'Calibration scores match fit: {name}',digest(records)==cal['datasets'][d]['score_hashes'][str(b)])
                        if stage=='robustness':
                            originals={r['key']:r for r in splits[d]['test']}
                            check(f'Permutation preserves answer meaning: {name}',all(r['choices'][r['gold']]==originals[r['key']]['choices'][originals[r['key']]['gold']] for r in rows))
                        observations+=len(records)
                        input_tokens+=sum(r['input_tokens'] for r in records)
                        score_seconds+=sum(r['latency_seconds'] for r in records)
    result={'passed':all(x['passed'] for x in checks),'checks':checks,'checks_count':len(checks),
            'scoring_records':observations,'input_token_evaluations':input_tokens,'measured_scoring_seconds':score_seconds,
            'quantization_coverage':modules,'warmups_and_repeatability_passes_excluded':True,
            'scope':'Actual completed archive; immutable artifact manifests are verified, but weights are not reloaded.'}
    write_json(out,result)
    if not result['passed']:
        raise ValueError('Completed archive failed acceptance checks')
    return {k:v for k,v in result.items() if k!='checks'}

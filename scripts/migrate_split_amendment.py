"""Audited reuse of unchanged raw scores after the documented stem-overlap fix.

This is a one-purpose migration, not a bypass for arbitrary protocol changes.
Held-out reuse requires the corrected protocol to be frozen first.
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

from qaudit.common import config_at,configure_cache,digest,file_hash,read_json,write_json,workspace_lock
from qaudit.data import selection,permute
from qaudit.scoring import protocol_identity,check_frozen
from qaudit.store import ScoreStore,cell_name


def migrate(source,destination,old_commit,phase):
    source,destination=Path(source).resolve(),Path(destination).resolve()
    configure_cache(destination)
    old=read_json(source/'frozen.json')['identity'];new=protocol_identity(destination)
    repo=Path(__file__).resolve().parents[1]
    # Prove that the old Git checkpoint is the code actually used for scoring.
    old_hashes={}
    for name in ('backend','data','scoring','store','common','stats'):
        blob=subprocess.check_output(['git','show',f'{old_commit}:src/qaudit/{name}.py'],cwd=repo)
        old_hashes[name+'.py']=hashlib.sha256(blob).hexdigest()
        if name!='data' and old_hashes[name+'.py']!=file_hash(repo/'src'/'qaudit'/f'{name}.py'):
            raise ValueError('Only data selection may change in this migration')
    if digest(old_hashes)!=old['scoring_source']:
        raise ValueError('The supplied commit does not match the original scoring code')
    old_cfg=config_at(source);new_cfg=config_at(destination)
    exempt={'schema_version','name','deduplication'}
    if {k:v for k,v in old_cfg.items() if k not in exempt}!={k:v for k,v in new_cfg.items() if k not in exempt}:
        raise ValueError('Scoring configuration changed; reuse is forbidden')
    if old['pins']!=new['pins'] or old['environment']!=new['environment']:
        raise ValueError('Pinned inputs or scoring environment changed')
    if new_cfg.get('deduplication',{}).get('cross_split')!='normalized_question_stem':
        raise ValueError('Destination lacks the corrected split rule')
    if phase=='heldout': check_frozen(destination)
    stages=('pilot','calibration','validation') if phase=='pretest' else ('test','robustness')
    log={'source_commit':old_commit,'source_protocol':old,'destination_protocol':new,
         'phase':phase,'justification':'Exclude repeated question stems across official splits; unchanged raw scores only.',
         'heldout_performance_used_for_selection':False,'cells':[]}
    with workspace_lock(destination),ScoreStore(source/'scores.sqlite') as src,ScoreStore(destination/'scores.sqlite') as dst:
        available=set(src.cells())
        for role in new_cfg['models']:
            for b in new_cfg['precisions']:
                meta=read_json(destination/'models'/role/str(b)/'artifact.json')
                for d in new_cfg['datasets']:
                    for stage in stages:
                        cell=cell_name(role,b,d,stage)
                        if cell not in available: continue
                        original_identity=src.identity(cell)
                        if original_identity['protocol']!=old or original_identity['artifact_hash']!=meta['artifact_hash']:
                            raise ValueError('Source scores or model artifact identity mismatch')
                        old_rows={r['key']:r for r in selection(source,d,stage)}
                        new_rows=selection(destination,d,stage)
                        original_records={r['key']:r for r in src.records(cell)}
                        dst.register(cell,{'protocol':new,'artifact_hash':meta['artifact_hash'],'role':role,'bits':b,'dataset':d,'stage':stage})
                        kept=[]
                        for index,row in enumerate(new_rows):
                            key=row['key']
                            # Repeat the new pilot's first three cases afresh.
                            if stage=='pilot' and index<3: continue
                            if key not in original_records or key not in old_rows: continue
                            if row!=old_rows[key]:
                                raise ValueError('A reused question changed in content, labels, or options')
                            record=dict(original_records[key])
                            origin_hash=digest(record)
                            if stage=='pilot': record.pop('repeat_max_probability_delta',None)
                            record['reused_from']={'protocol_hash':digest(old),'cell':cell,'record_hash':origin_hash}
                            dst.insert(cell,record);kept.append(key)
                        log['cells'].append({'cell':cell,'reused_count':len(kept),'reused_ids':kept,
                                             'new_expected_count':len(new_rows),'source_count':len(original_records)})
        write_json(destination/f'amendment-{phase}-migration.json',log,immutable=True)
    print({'phase':phase,'reused_records':sum(c['reused_count'] for c in log['cells'])})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--destination',type=Path,required=True)
    p.add_argument('--old-commit',required=True);p.add_argument('--phase',choices=['pretest','heldout'],required=True)
    a=p.parse_args();migrate(a.source,a.destination,a.old_commit,a.phase)

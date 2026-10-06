"""Render the fixed qualitative review; refuse to reuse notes for changed cases."""
import argparse
import json
from pathlib import Path


def build(cases_path,notes_path,out):
    cases=json.loads(Path(cases_path).read_text())
    notes=json.loads(Path(notes_path).read_text())
    lines=['# Prespecified case review','',
        'These 20 primary ARC-Challenge cases were selected by the frozen hash rule: five from each prediction-transition category. They are a stratified inspection sample, not a representative estimate of error frequencies. No case was substituted because it produced a more interesting story.','',
        'All selected cases retain matching prompt-token hashes and option mappings across precision. Gold answers below are the original ARC labels. Potential ambiguity is documented without relabeling the test set. Probabilities use each precision\'s own 400-example fitted temperature; temperature scaling preserves the selected answer. No generated reasoning traces were collected.','']
    for i,r in enumerate(cases,1):
        note=notes[r['key']]
        for field in ('category','content_hash','gold','reference_prediction','quantized_prediction'):
            if r[field]!=note[field]: raise ValueError('Case changed; perform a new qualitative review')
        lines += [f"## {i}. {r['category'].replace('_',' ')} - {r['id']}",'',r['question'],'']
        lines += [f'{chr(65+j)}. {choice}' for j,choice in enumerate(r['choices'])]
        lines += ['',f"Gold: **{chr(65+r['gold'])}**. BF16: **{chr(65+r['reference_prediction'])}**. 4-bit: **{chr(65+r['quantized_prediction'])}**.",
                  f"Probability assigned to the gold option: BF16 **{r['reference_probabilities'][r['gold']]:.4f}**; 4-bit **{r['quantized_probabilities'][r['gold']]:.4f}**.",'',note['note'],'']
    lines += ['## Attribution and limits','',
        'Question and option excerpts are from [AllenAI AI2 ARC](https://huggingface.co/datasets/allenai/ai2_arc), under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Canonical letter mapping and quantitative annotations are added for this study. See THIRD_PARTY.md and the pinned dataset revision.','',
        'This AI-assisted review distinguishes visible content errors and possible benchmark ambiguity from mapping errors. It is not an independent expert adjudication of all labels, and it does not establish the model\'s internal cause for a prediction change.']
    Path(out).parent.mkdir(parents=True,exist_ok=True)
    Path(out).write_text('\n'.join(lines)+'\n')
    print(out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cases',type=Path,required=True)
    p.add_argument('--notes',type=Path,default=Path('docs/case-notes.json'))
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();build(a.cases,a.notes,a.out)

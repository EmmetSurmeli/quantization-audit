"""Build the six-page technical report from measured, cached analysis only.

Usage: python scripts/build_report.py --results results/measured --provenance results/pretest
Requires reportlab and pypdf, independently of the scoring environment.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,PageBreak,Image,Table,TableStyle,KeepTogether
from pypdf import PdfReader


INK=colors.HexColor('#152c3a')
TEAL=colors.HexColor('#087f8c')
MUTED=colors.HexColor('#566674')
PALE=colors.HexColor('#edf5f6')
WIDTH=522
STYLES={
    'title':ParagraphStyle('title',fontName='Helvetica-Bold',fontSize=22,leading=25,textColor=INK,spaceAfter=9),
    'h1':ParagraphStyle('h1',fontName='Helvetica-Bold',fontSize=17,leading=21,textColor=INK,spaceAfter=12),
    'h2':ParagraphStyle('h2',fontName='Helvetica-Bold',fontSize=10.5,leading=14,textColor=TEAL,spaceBefore=10,spaceAfter=5),
    'body':ParagraphStyle('body',fontName='Helvetica',fontSize=9.3,leading=13.2,textColor=INK,spaceAfter=8),
    'small':ParagraphStyle('small',fontName='Helvetica',fontSize=8.0,leading=10.5,textColor=MUTED,spaceAfter=6),
    'table':ParagraphStyle('table',fontName='Helvetica',fontSize=8.1,leading=10.4,textColor=INK),
    'thead':ParagraphStyle('thead',fontName='Helvetica-Bold',fontSize=8.1,leading=10.4,textColor=colors.white),
    'ref':ParagraphStyle('ref',fontName='Helvetica',fontSize=7.7,leading=10.1,textColor=MUTED,spaceAfter=4),
}


def p(text,style='body'):
    return Paragraph(text,STYLES[style])


def table(headers,rows,widths=None):
    data=[[p(escape(str(x)),'thead') for x in headers]]
    data += [[p(escape(str(x)),'table') for x in row] for row in rows]
    t=Table(data,colWidths=widths or [WIDTH/len(headers)]*len(headers),repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),INK),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,PALE]),
        ('LINEBELOW',(0,0),(-1,0),.5,INK),('BOTTOMPADDING',(0,0),(-1,-1),6),
        ('TOPPADDING',(0,0),(-1,-1),6),('LEFTPADDING',(0,0),(-1,-1),7),
        ('RIGHTPADDING',(0,0),(-1,-1),7),
    ]))
    return t


def figure(path,width=WIDTH):
    iw,ih=ImageReader(str(path)).getSize()
    return Image(str(path),width=width,height=width*ih/iw,hAlign='CENTER')


def footer(canvas,doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor('#cedadd'));canvas.line(45,39,567,39)
    canvas.setFont('Helvetica',7.5);canvas.setFillColor(MUTED)
    canvas.drawString(45,27,'QUANTIZATION AND CONFIDENCE  /  REPRODUCIBLE EMPIRICAL AUDIT')
    canvas.drawRightString(567,27,f'{doc.page} / 6')
    canvas.restoreState()


def build(results,provenance):
    results,provenance=Path(results),Path(provenance)
    r=json.loads((results/'results.json').read_text())
    if r.get('status')!='measured':
        raise ValueError('A report requires measured results; synthetic stand-ins are forbidden')
    pins=json.loads((provenance/'pins.json').read_text())
    splits=json.loads((provenance/'split-manifest.json').read_text())
    primary=r['primary']
    def metric(role,d,b,t):
        return next(x for x in r['metrics'] if (x['model'],x['dataset'],x['bits'],x['treatment'])==(role,d,b,t))
    def change(role,d,b):
        return next(x for x in r['flips'] if (x['model'],x['dataset'],x['bits'])==(role,d,b))
    def resource(role,d,b):
        return next(x for x in r['resources'] if (x['model'],x['dataset'],x['bits'])==(role,d,b))
    roles=r['protocol']['roles']
    model_names={'primary':'Qwen3-4B','replication':'Qwen3-1.7B'}
    ds=['ARC-Challenge','ARC-Easy']
    f=lambda x:f'{x:.4f}'
    pages=[]
    def add(*items): pages.extend(items)
    def new(title): add(PageBreak(),p(title,'h1'))

    add(p('Quantization and confidence','title'),p('A calibration-transfer audit of small Qwen3 models','h1'),
        p('Emmet Surmeli  |  Independent research project  |  Measured local deployment study','small'),
        p('Abstract','h2'),
        p('Can a language model retain its existing confidence calibration after weight quantization? '
          'We compare transferred BF16 temperature scaling with a scalar temperature refitted at each precision. '
          'The controlled intervention is MLX affine weight quantization at 8 and 4 bits, with one pinned checkpoint '
          'per model, identical prompts across precisions, and no model training. The primary comparison uses '
          'Qwen3-4B on 1,172 held-out ARC-Challenge questions and 400 disjoint calibration examples.'),
        table(['Primary Brier difference','95% paired bootstrap interval','Practical threshold'],
              [[f(primary['estimate']),f"[{f(primary['ci95'][0])}, {f(primary['ci95'][1])}]",'0.0100 absolute']], [160,220,142]),
        Spacer(1,8),p('<b>'+escape(primary['conclusion'])+'</b>'),
        p('Positive differences favor refitting. The interval includes uncertainty from both calibration sampling '
          'and test sampling. It is conditional on the selected checkpoints, tasks, and scoring procedure.'),
        p('Question, baseline, and contribution','h2'),
        p('The operational baseline is to reuse the temperature already fitted to the BF16 model. Comparing '
          'refitting only with raw probabilities would answer an easier question. Secondary analyses examine '
          '8-bit transfer, 50/100/200-example nested calibration subsets, ARC-Easy, and the 1.7B scale replication.'),
        p('Temperature scaling [1], quantization-induced confidence changes [2], and calibration repair [3] are '
          'established. Our contribution is an applied replication and extension: paired transfer evaluation, '
          'label-budget sensitivity, and deployment measurements in a reproducible local MLX pipeline. '
          'We do not establish that this combination is unprecedented.'),
        p('What the endpoint measures','h2'),
        p('For question i and available option k, p<sub>ik</sub>(T) = softmax(z<sub>i</sub>/T)<sub>k</sub>. '
          'Brier = mean<sub>i</sub> sum<sub>k</sub> (p<sub>ik</sub> - 1[y<sub>i</sub>=k])<super>2</super>. '
          'We report the sum-of-squares convention, with range 0 to 2. The endpoint is '
          'Brier(4-bit, transferred) minus Brier(4-bit, refitted).'),
        p('Brier score measures overall probability quality, not calibration alone. A positive scalar temperature '
          'preserves the highest-scoring option, so calibration cannot improve answer accuracy. '
          'All probabilities are conditional on the listed choices; this is not a study of free-form hallucinations.'))

    new('1. Controlled design and prediction changes')
    add(p('The official Qwen3-4B and Qwen3-1.7B checkpoints [6] were converted to BF16, then to affine '
          '8-bit and 4-bit weights with group size 64 in MLX-LM [7]. Activations remain BF16. All runs use '
          'batch size one and independent forward passes without a persistent KV cache. The official chat '
          'template disables thinking and requests a single option letter. Verified single-token letter logits '
          'are normalized over the available options; no question is silently truncated.'),
        figure(results/'figure-1-accuracy-flips.png',width=490),
        p('Figure 1. Qwen3-4B accuracy and paired prediction transitions relative to BF16. Counts below retain '
          'the question as the unit of observation. Changed predictions can cancel in aggregate accuracy.','small'))
    rows=[]
    for role in roles:
        for d in ds:
            a=metric(role,d,16,'raw');b=metric(role,d,4,'raw');c=change(role,d,4)
            rows.append([model_names[role],d.replace('ARC-',''),a['n'],f(a['accuracy']),f(b['accuracy']),f"{c['beneficial']} / {c['harmful']}"])
    add(table(['Model','Subset','Test n','BF16 acc.','4-bit acc.','Beneficial / harmful'],rows,[98,83,50,77,77,137]),
        Spacer(1,7),p('Data separation. Each ARC subset [5] contributes 100 training questions to the pilot, '
          '400 different training questions to calibration, and 100 validation questions to pre-test checks. '
          f'Global ID/content screening excluded {len(splits["exclusions"])} duplicate records; all 1,172 Challenge '
          'and 2,376 Easy test questions remain. The 200-question permutation subset per task is chosen deterministically. '
          'Both models passed the pilot. An initial freeze preceded test scoring; a data-only stem-overlap '
          'amendment preceded all held-out performance review. Calibration was refitted and frozen anew; '
          'unchanged raw scores retain their original provenance. See PROTOCOL-AMENDMENT.md.','small'))

    new('2. Calibration transfer on the held-out test')
    add(figure(results/'figure-2-reliability.png'),
        p('Figure 2. Qwen3-4B, 4-bit reliability diagrams using 10 fixed equal-width confidence bins. '
          'Empty bins are omitted. These descriptive curves can be noisy in sparsely populated bins; '
          'the primary inference uses paired Brier differences rather than ECE.','small'))
    rows=[]
    for d in ds:
        for t in ['raw','transferred','refitted']:
            m=metric('primary',d,4,t)
            rows.append([d.replace('ARC-',''),t,f(m['temperature']),f(m['brier']),f(m['nll']),f(m['ece'])])
        u=metric('primary',d,0,'uniform')
        rows.append([d.replace('ARC-',''),'uniform','-',f(u['brier']),f(u['nll']),'-'])
    add(table(['Subset','Treatment','Temperature','Brier','NLL','ECE'],rows,[83,102,95,81,81,80]),
        Spacer(1,9),p(f'The primary Brier score changes from <b>{f(primary["baseline_brier"])}</b> after transfer '
          f'to <b>{f(primary["refitted_brier"])}</b> after refitting. The absolute improvement is '
          f'<b>{f(primary["estimate"])}</b>, with a 95% interval of '
          f'<b>[{f(primary["ci95"][0])}, {f(primary["ci95"][1])}]</b>. The prespecified operational '
          'margin is 0.01, rather than a threshold selected after seeing the data.'),
        p('Uncertainty and decision rule','h2'),
        p('We use 2,000 paired bootstrap replicates. Within each replicate, calibration questions are sampled '
          'with replacement using the same indices for BF16 and quantized scores; both temperatures are refitted '
          'by minimizing NLL over log-temperature, bounded to T in [0.05,20]. Test questions are resampled '
          'independently, retaining pairing between treatments. A useful positive headline requires a positive '
          'interval and an estimated improvement of at least 0.01. An interval within [-0.01,0.01] supports '
          'little practical difference only in this setup. Crossing zero alone does not establish equivalence.'))

    new('3. Label budgets and scale replication')
    add(figure(results/'figure-3-label-budget.png'),
        p('Figure 3. Held-out Brier score versus calibration sample count for Qwen3-4B at 4 bits. '
          'Both transferred and refitted temperatures use the same subset IDs and size. Shading is the range '
          'across ten seeded nested calibration subsets, not a confidence interval. At 400 all subsets coincide.','small'))
    rows=[]
    for d in ds:
        for n in (50,100,200,400):
            v=[x['test_brier'] for x in r['sample_size_curves'] if x['model']=='primary' and x['dataset']==d and x['bits']==4 and x['treatment']=='refitted' and x['n_calibration']==n]
            rows.append([d.replace('ARC-',''),n,f(sum(v)/len(v)),f"{f(min(v))} - {f(max(v))}"])
    add(table(['Subset','Calibration n','Mean refitted Brier','Range over subsets'],rows,[105,90,155,172]),
        Spacer(1,7),p('The subsets overlap and share one test set. They measure sensitivity to label selection; '
          'they are not ten independent replications. The 400-example fit is a reference, not a proven optimum. '
          'A favorable small subset cannot establish a label-efficiency claim by itself. '
          f"{sum(x.get('at_boundary',False) for x in r['sample_size_curves'])} of {len(r['sample_size_curves'])} "
          'sample-curve rows reach a temperature boundary (rows share fits and are not independent). '
          'Boundary flags and exact temperatures are saved in sample-size.csv.','small'))
    rows=[]
    for role in roles:
        for d in ds:
            vals=[]
            for b in (8,4):
                vals.append(f(metric(role,d,b,'transferred')['brier']-metric(role,d,b,'refitted')['brier']))
            rows.append([model_names[role],d.replace('ARC-',''),*vals])
    add(p('Secondary 400-example transfer differences','h2'),
        table(['Model','Subset','8-bit difference','4-bit difference'],rows,[135,115,136,136]),
        Spacer(1,7),p('Positive differences favor refitting. Only the prespecified primary comparison carries '
          'the primary bootstrap decision. These secondary comparisons are exploratory; no family of '
          'significance claims is made. ARC-Easy and ARC-Challenge are related tasks, and the models share a family.','small'))

    new('4. Selective answering and deployment cost')
    add(figure(results/'figure-4-coverage-error.png'),
        p('Figure 4. Qwen3-4B, 4-bit error among answered questions versus coverage at fixed confidence '
          'thresholds 0.5, 0.7, and 0.9. Connected points are descriptive, not a threshold optimized on the test set. '
          'Counts and Wilson error intervals are retained in results.json; small groups are flagged.','small'))
    rows=[]
    for role in roles:
        for b in (16,8,4):
            cells=[resource(role,d,b) for d in ds]
            total=sum(metric(role,d,b,'raw')['n'] for d in ds)
            latency=sum(resource(role,d,b)['mean_latency_seconds']*metric(role,d,b,'raw')['n'] for d in ds)/total
            rows.append([model_names[role],'BF16' if b==16 else str(b),f"{cells[0]['model_bytes']/1e9:.3f}",f"{max(x['peak_memory_gb'] for x in cells):.3f}",f"{latency:.4f}"])
    add(table(['Model','Bits','Serialized GB','Peak MLX GB','Mean sec/question'],rows,[120,52,110,110,130]),
        Spacer(1,8),p('Hardware: Apple M5 with 24 GB unified memory. Values are measured on this host, not '
          'hardware-independent compute estimates. Serialized size includes model files and quantization metadata. '
          'Peak memory is MLX allocation, not total resident system memory. Synchronized per-question latency '
          'excludes cold loading, tokenization, and warm-up. Models run sequentially; run order, temperature, '
          'and other host activity may affect latency. Quantized kernels need not be faster than BF16.'),
        p('Interpreting confidence thresholds','h2'),
        p('Temperature scaling changes which questions pass a fixed confidence threshold while preserving each '
          'question\'s answer. A low observed error on a tiny answered subset is not evidence of reliable deployment. '
          'The error-rate intervals are descriptive binomial intervals conditional on the fitted treatment and '
          'threshold, not simultaneous risk-control guarantees. No threshold was tuned using test labels.'),
        p('Additional spending: $0. Both pilot runtime projections passed the 24-hour cap. Model weights are '
          'kept outside Git; the repository includes a portable archive of scores and provenance.','small'))

    new('5. Robustness, limitations, and reproducibility')
    rows=[]
    for role in roles:
        for d in ds:
            x=next(x for x in r['robustness'] if x['model']==role and x['dataset']==d and x['bits']==4 and x['treatment']=='refitted')
            rows.append([model_names[role],d.replace('ARC-',''),x['n_pairs'],f(x['paired_brier_change']),f(x['permuted_accuracy']-x['original_accuracy'])])
    add(table(['Model','Subset','Pairs','Brier change','Accuracy change'],rows,[120,100,52,125,125]),
        Spacer(1,6),p('One prespecified nonidentity option permutation per question. Changes are permuted minus '
          'original on the same 200-question subset; the frozen temperature is reused. These descriptive '
          'paired checks are not 400 independent examples. Full precision/treatment results are in robustness.csv.','small'),
        p('Error inspection and scope','h2'),
        p(f'{len(r["error_cases"])} cases were selected by a fixed rule: up to five each of unchanged-correct, '
          'unchanged-wrong, beneficial flips, and harmful flips in the primary comparison. The supporting '
          'case review records questions, original labels, canonical mappings, selected answers, and probabilities. '
          'No generated reasoning was collected; explanations of why a model changed its answer are hypotheses.'),
        p('Benchmark contamination remains unresolved. Paired comparisons control many implementation differences '
          'but cannot remove pretraining exposure. Exact normalized-content deduplication does not detect all '
          'semantic duplicates. Two related ARC subsets and two sizes of one family do not establish generality. '
          'Results concern this MLX affine quantizer, not GPTQ, AWQ, all 4-bit models, or open-ended confidence. '
          'A uniform baseline and agreement with BF16 do not make BF16 an oracle.'),
        p('Reproducibility and next question','h2'),
        p('The repository records split IDs, immutable source revisions, prompt-token hashes, option scores, '
          'quantized-module inventories, calibration fits, environment versions, and question-level cached output. '
          'The analysis archive restores without model weights; all four figures and tables regenerate from saved '
          'scores. Automated checks cover hand-calculated metrics, label permutations, data separation, paired '
          'IDs, immutable resume behavior, and archive round trips. Implementation was AI-assisted; interpretation '
          'and ownership require understanding the controls, held-out design, and claim limits.'),
        p('A focused follow-up is to preregister the same transfer test on a different model family and a task '
          'outside ARC, while keeping the score definition and practical margin fixed. This would test whether '
          'the observed transfer behavior survives a meaningful change of setting.','small'),
        p('References and source artifacts','h2'))
    refs=[
        ('[1] Guo et al. (2017). On Calibration of Modern Neural Networks. ICML.','https://proceedings.mlr.press/v70/guo17a.html'),
        ('[2] Proskurina et al. (2024). When Quantization Affects Confidence of Large Language Models? NAACL Findings.','https://aclanthology.org/2024.findings-naacl.124/'),
        ('[3] Zhong et al. (2025). Quantized Can Still Be Calibrated. ACL.','https://aclanthology.org/2025.acl-long.1473/'),
        ('[4] Yang et al. (2026). Target-Aware Calibration Data Selection for Preserving Uncertainty in Quantized Language Models. arXiv:2608.21019.','https://arxiv.org/abs/2608.21019'),
        ('[5] Allen Institute for AI. AI2 ARC dataset, pinned revision '+pins['dataset']['revision'][:12]+'.','https://huggingface.co/datasets/allenai/ai2_arc'),
        ('[6] Qwen. Qwen3-4B / 1.7B; revisions '+pins['models']['primary']['revision'][:12]+' / '+pins['models']['replication']['revision'][:12]+'.','https://huggingface.co/Qwen'),
        ('[7] ML Explore. MLX-LM 0.31.3; MLX 0.32.3.','https://github.com/ml-explore/mlx-lm'),
    ]
    for label,url in refs:
        add(p(f'<link href="{url}" color="#087f8c">{escape(label)}</link>','ref'))
    add(p('<link href="https://github.com/EmmetSurmeli/quantization-audit" color="#087f8c">Repository: github.com/EmmetSurmeli/quantization-audit</link>','ref'))
    target=results/'technical-report.pdf'
    doc=SimpleDocTemplate(str(target),pagesize=(612,792),leftMargin=45,rightMargin=45,topMargin=42,bottomMargin=50,
        title='Quantization and confidence: a calibration-transfer audit',author='Emmet Surmeli',subject='Measured calibration transfer across MLX weight precision')
    doc.build(pages,onFirstPage=footer,onLaterPages=footer)
    count=len(PdfReader(target).pages)
    if count!=6:
        raise ValueError(f'Report layout is {count} pages, expected six; inspect and repair before delivery')
    print(target)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,required=True)
    parser.add_argument('--provenance',type=Path,required=True)
    args=parser.parse_args();build(args.results,args.provenance)

"""Render the pilot stop snapshot without turning unconfirmed quality into zero."""
import argparse
import csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager


def render(source, output):
    with source.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    if len(rows) != 2 or {r['condition'] for r in rows} != {'normal', 'anti'}:
        raise ValueError('Expected the two pilot conditions')
    if any(r['quality_percent'] != '' or r['usage_complete'].lower() != 'true' for r in rows):
        raise ValueError('This stop snapshot requires complete usage and unconfirmed quality')
    installed = {f.name for f in font_manager.fontManager.ttflist}
    plt.rcParams['font.family'] = next(n for n in ['Yu Gothic', 'Meiryo', 'DejaVu Sans'] if n in installed)
    plt.rcParams['axes.unicode_minus'] = False
    colors = ['#3572B0' if r['condition'] == 'normal' else '#D17A29' for r in rows]
    values = [int(r['total_tokens']) for r in rows]
    fig, (usage, quality) = plt.subplots(1, 2, figsize=(12, 5.7), gridspec_kw={'width_ratios': [1.2, 1]}, layout='constrained')
    bars = usage.barh([r['condition'] for r in rows], values, color=colors, height=.46)
    usage.invert_yaxis()
    usage.bar_label(bars, labels=[f'{v:,}' for v in values], padding=7, fontsize=12)
    usage.set_xlim(0, max(values) * 1.3)
    usage.set_xticks([0, 2_000_000, 4_000_000, 6_000_000], ['0', '2', '4', '6'])
    usage.set_xlabel('実装Runの総トークン量（百万）')
    usage.set_title('使用量：過去の照合記録を保持', loc='left', fontsize=13, pad=20)
    usage.spines[['top', 'right', 'left']].set_visible(False)
    usage.grid(axis='x', color='#E5E7EB')
    usage.set_axisbelow(True)
    quality.axis('off')
    quality.set_title('品質：両条件とも未確定', loc='left', fontsize=13, pad=20)
    quality.text(.03, .76, 'normal   未確定\nanti         未確定', fontsize=18, linespacing=1.8, transform=quality.transAxes)
    quality.text(.03, .30, '旧採点は無効。評価器の修正作業を実施。\n固定提出物・Run原本が現在欠落しており、\n同じ提出物の再採点は未実施。\n品質の値・散布図の点は確定できない。', fontsize=11, linespacing=1.6, color='#4B5563', transform=quality.transAxes)
    fig.suptitle('パイロット各1回：原本欠落で再採点できず、品質は未確定', x=.03, ha='left', fontsize=17)
    fig.supxlabel('過去記録: 両Run agent_completed・usage照合済み / 今回は原本未確認 / 追加比較0 Run\n出典: pilot-runs.csv・pilot-provenance.json  |  品質未確定は0点を意味しない', fontsize=10)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=160, metadata={'Software': 'sample1 analysis/pilot_snapshot.py'})
    plt.close(fig)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('source', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    render(a.source, a.output)

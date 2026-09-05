"""Reproducible static research plot; missing values never become zero."""
import argparse
import csv
import math
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager


def plot(source, destination):
    with source.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError('Empty input')
    groups = {(r['phase'], r['experiment_version']) for r in rows}
    scores = {r['score_version'] for r in rows if r['score_version']}
    if len(groups) != 1 or len(scores) > 1:
        raise ValueError('Plot one phase and one experiment/evaluation version at a time')
    if len({r['run_id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate Run ID in plot input')
    for row in rows:
        for field in ('total_tokens', 'quality_percent'):
            if row[field] != '':
                value = float(row[field])
                if not math.isfinite(value) or value < 0 or (field == 'quality_percent' and value > 100):
                    raise ValueError('Invalid coordinate: ' + field)
        if row['quality_percent'] != '' and not row['score_version']:
            raise ValueError('Scored coordinate requires an evaluation version')
    candidates = ['Yu Gothic', 'Meiryo', 'Noto Sans CJK JP', 'DejaVu Sans']
    installed = {f.name for f in font_manager.fontManager.ttflist}
    plt.rcParams['font.family'] = next(f for f in candidates if f in installed)
    plt.rcParams['axes.unicode_minus'] = False
    colors = {'normal': '#3572B0', 'anti': '#D17A29'}
    markers = {'agent_completed': 'o', 'budget_exhausted': '^', 'environment_failure': 's', 'agent_error': 'X', 'operator_aborted': 'D'}
    valid = [r for r in rows if r['total_tokens'] != '' and r['quality_percent'] != '']
    missing = [r for r in rows if r not in valid]
    fig, ax = plt.subplots(figsize=(12, 7), layout='constrained')
    for r in valid:
        x, y = float(r['total_tokens']), float(r['quality_percent'])
        color = colors[r['condition']]
        ax.scatter(x, y, marker=markers[r['end_reason']], s=75, edgecolors=color,
                   facecolors=color if r['condition'] == 'normal' else 'none', linewidths=1.5)
        ax.annotate(r['run_id'], (x, y), xytext=(5, 6), textcoords='offset points', fontsize=7)
    for condition, color in colors.items():
        ax.scatter([], [], s=60, edgecolors=color, facecolors=color if condition == 'normal' else 'none', label=condition)
    for reason in sorted({r['end_reason'] for r in valid}):
        ax.scatter([], [], marker=markers[reason], c='#555555', s=45, label=reason)
    ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1), frameon=False)
    ax.set(xlabel='実装Runの総トークン量', ylabel='非公開E2E項目充足率（%）', ylim=(-5, 108))
    xmax = max([float(r['total_tokens']) for r in valid] + [1])
    ax.set_xlim(-0.03 * xmax, 1.25 * xmax)
    ax.spines[['top', 'right']].set_visible(False)
    ax.grid(axis='y', color='#E8E8E8')
    ax.set_axisbelow(True)
    phase, exp = next(iter(groups))
    score = next(iter(scores), '未採点')
    ax.set_title(f'総トークン量と非公開E2E項目充足率\n{phase} | {exp} | 固定分母57 | 全{len(rows)} Run', loc='left', pad=18)
    caps = sum(r['end_reason'] == 'budget_exhausted' for r in rows)
    incomplete = sum(r['end_reason'] != 'agent_completed' for r in rows)
    missing_path = destination.with_suffix('.missing-runs.csv')
    fig.supxlabel(f'上限到達 {caps} / 未完了 {incomplete} / 座標欠測 {len(missing)}（{missing_path.name}参照）\n出典: {source.name} | 評価版 {score[:16]} | calibrationは効果比較に使用しない', fontsize=9)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination, dpi=150, metadata={'Software': 'sample1 analysis/plot.py'})
    plt.close(fig)
    with missing_path.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(missing)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('input', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    plot(args.input, args.output)

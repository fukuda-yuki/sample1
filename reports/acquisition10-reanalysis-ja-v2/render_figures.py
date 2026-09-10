"""Draw the six report figures from derived data; does not call any experiment code."""
from pathlib import Path
import argparse
import hashlib
import json
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch
import numpy as np

BASE = Path(__file__).resolve().parent
BLUE, ORANGE, INK, GREY = "#26648E", "#A45C15", "#243746", "#596773"
COLORS = {"normal": BLUE, "anti": ORANGE}
MARKERS = {"normal": "o", "anti": "^"}
NAMES = {"normal": "通常条件（normal）", "anti": "不整合条件（anti）"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def configure():
    choices = [Path("/mnt/c/Windows/Fonts/YuGothR.ttc"), Path("C:/Windows/Fonts/YuGothR.ttc")]
    font = next((p for p in choices if p.is_file()), None)
    if font is None:
        raise FileNotFoundError("Yu Gothic is required to render Japanese labels")
    font_manager.fontManager.addfont(str(font))
    plt.rcParams.update({"font.family": font_manager.FontProperties(fname=str(font)).get_name(),
        "font.size": 13, "axes.titlesize": 16, "axes.labelsize": 14,
        "text.color": INK, "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
        "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#A6B2BA",
        "figure.facecolor": "white", "savefig.facecolor": "white", "axes.unicode_minus": False,
        "grid.color": "#DFE6EB", "svg.fonttype": "path", "svg.hashsalt": "sample1-ja-v2"})
    return font


def header(fig, number, title, subtitle):
    fig.text(.035, .95, f"図{number}  {title}", fontsize=18, weight="bold", va="top")
    fig.text(.035, .892, subtitle, fontsize=12, color=GREY, va="top")


def box(ax, x, y, w, h, text, color=BLUE, fill="#EDF4F8", fontsize=13):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.01,rounding_size=0.014",
                              linewidth=1.4, edgecolor=color, facecolor=fill))
    ax.text(x+w/2, y+h/2, text, ha="center", va="center", fontsize=fontsize, linespacing=1.55)


def arrow(ax, start, end, color=GREY):
    ax.annotate("", xy=end, xytext=start, arrowprops={"arrowstyle": "->", "lw": 1.6, "color": color})


def build(data_path, output):
    output = output.resolve()
    if output == BASE/"source" or BASE/"source" in output.parents:
        raise ValueError("Cannot write over source inputs")
    output.mkdir(parents=True, exist_ok=True)
    font = configure()
    data = json.loads(data_path.read_text(encoding="utf-8"))
    runs, pairs = data["tables"]["runs"], data["tables"]["pairs"]
    assert len(runs) == 20 and len(pairs) == 10
    trace = []
    def emit(fig, name, inputs, fact, limits):
        fig.savefig(output/(name+".png"), dpi=170, metadata={"Software": "Matplotlib"})
        fig.savefig(output/(name+".svg"), metadata={"Date": None, "Creator": "Matplotlib"})
        trace.append(dict(figure=name, files=[name+".png", name+".svg"], source_data=inputs,
            source_results_sha256=sha(data_path), generator_sha256=sha(Path(__file__)),
            caption_claim=fact, limitations=limits))
        plt.close(fig)

    # Figure 1: the initial acquisition is separate from this offline reanalysis.
    fig, ax = plt.subplots(figsize=(12, 7.3))
    header(fig, 1, "仕様の配布から保存記録の再分析まで", "実装エージェントが読む業務資料は、自分の条件の仕様書だけ")
    ax.set_position([.035, .06, .93, .76]); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    box(ax, .015, .75, .43, .18, "通常条件の仕様書\n共通ルール100万円／詳細100万円")
    box(ax, .555, .75, .43, .18, "不整合条件の仕様書\n共通ルール100万円／詳細50万円", ORANGE, "#FAF1E6")
    box(ax, .22, .39, .56, .22, "共通指示の下で各条件10 Runを独立実装\n新規セッション・隔離環境・1件ずつ実行\n矛盾に気づいた場合は解釈と理由を記録")
    arrow(ax, (.23, .74), (.37, .62)); arrow(ax, (.77, .74), (.63, .62))
    box(ax, .015, .035, .275, .19, "停止・提出物を固定\n入力・コード・ログを保存")
    box(ax, .365, .035, .275, .19, "共通のv6で評価\n両条件とも100万円基準\n57 ID・58ケース")
    box(ax, .715, .035, .27, .19, "今回の再分析\n保存済み20件を集計\n生成・採点の再実行なし", GREY, "#F1F3F5")
    arrow(ax, (.38, .38), (.16, .235)); arrow(ax, (.30, .13), (.355, .13)); arrow(ax, (.65, .13), (.705, .13))
    emit(fig, "01-study-flow", ["source/run-contract.md", "source/normal-spec.md", "source/anti-spec.md", "source/planned-runs.json"],
         "各条件10 Runを実装・固定し、共通v6の保存結果を再分析した。", ["この図の再分析は新しい実装や再採点ではない。"])

    fig, axes = plt.subplots(1, 2, figsize=(12, 6.8))
    header(fig, 2, "各条件10 Runの分布", "点は1 Run、太い横線は中央値。重なる値は横へずらして表示")
    fig.subplots_adjust(left=.095, right=.97, bottom=.18, top=.77, wspace=.36)
    for ax, key, scale, title, ylabel, ylim in [
        (axes[0], "recorded_total_tokens", 1e6, "記録済み総トークン", "記録済み総トークン（百万）", (0, 10)),
        (axes[1], "recorded_pass_rate", 1, "保存済みv6の合格率", "合格ID数 ÷ 57（%）", (0, 100))]:
        for x, c in enumerate(("normal", "anti")):
            values = sorted(r[key]/scale for r in runs if r["condition"] == c)
            jitter = np.array([-.14, .04, -.05, .14, -.10, .09, -.02, .17, -.17, .02])
            ax.scatter(x+jitter, values, s=80, color=COLORS[c], marker=MARKERS[c], zorder=3)
            med = statistics.median(values)
            ax.plot([x-.27, x+.27], [med, med], color=INK, lw=2.7, zorder=2)
            ax.text(x+.29, med, f"{med:.2f}" if scale>1 else f"{med:.1f}", fontsize=11, va="center")
        ax.set_title(title, pad=12); ax.set_ylabel(ylabel); ax.set_ylim(*ylim)
        ax.set_xlim(-.5, 1.55); ax.set_xticks([0, 1], ["通常条件\n10 Run", "不整合条件\n10 Run"])
        ax.grid(axis="y"); ax.set_axisbelow(True)
    emit(fig, "02-distributions", ["data/runs.csv"], "全20点と各条件の中央値を表示。", ["記録されていないusageは補完していない。", "合格率は保存済みv6の出力。"])

    fig, axes = plt.subplots(1, 2, figsize=(12, 7.5))
    header(fig, 3, "固定10ペアで見た条件間の差", "差は不整合条件 − 通常条件。左側ほど不整合条件の値が小さい")
    fig.subplots_adjust(left=.11, right=.965, bottom=.16, top=.79, wspace=.36)
    for ax, key, scale, xlabel, limits in [
        (axes[0], "token_difference", 1e6, "記録済み総トークンの差（百万）", (-4.2, 4.2)),
        (axes[1], "pass_rate_difference_pp", 1, "保存済み合格率の差（ポイント）", (-86, 16))]:
        values = [p[key]/scale for p in pairs]
        ys = list(range(1, 11))
        ax.axvline(0, color=GREY, lw=1)
        ax.hlines(ys, 0, values, color=ORANGE, alpha=.6, lw=2)
        ax.scatter(values, ys, color=ORANGE, marker="^", s=70, zorder=3)
        for value, y in zip(values, ys):
            ax.annotate(f"{value:+.2f}" if scale>1 else f"{value:+.1f}", (value, y),
                        xytext=(-7 if value<0 else 7, 0), textcoords="offset points",
                        ha="right" if value<0 else "left", va="center", fontsize=10)
        ax.set_yticks(ys, [f"{i:02}" for i in ys]); ax.set_ylim(10.6, .4); ax.set_xlim(*limits)
        ax.set_xlabel(xlabel); ax.grid(axis="x"); ax.set_axisbelow(True)
    axes[0].set_ylabel("予定ペア番号")
    emit(fig, "03-pair-differences", ["data/pairs.csv"], "トークンと合格ID数はそれぞれ8ペアで不整合条件が少ない。", ["ペアは事前の実行順ブロックであり、共有モデル乱数ではない。"])

    fig, ax = plt.subplots(figsize=(11, 7))
    header(fig, 4, "消費量と保存済み評価結果の関係", "全20 Runを表示。注記は本文で取り上げる6件（N：通常条件、A：不整合条件）")
    fig.subplots_adjust(left=.115, right=.96, bottom=.15, top=.78)
    for c in ("normal", "anti"):
        rr = [r for r in runs if r["condition"] == c]
        ax.scatter([r["recorded_total_tokens"]/1e6 for r in rr], [r["recorded_pass_rate"] for r in rr],
                   s=95, marker=MARKERS[c], color=COLORS[c], label=NAMES[c], zorder=3)
    offsets = {"normal-002": (9, 4), "normal-008": (15, 15), "anti-006": (9, -1),
               "anti-009": (-52, -19), "anti-004": (9, 6), "anti-008": (8, -18)}
    for r in runs:
        if r["planned_run"] in offsets:
            tag = ("N" if r["condition"] == "normal" else "A") + r["planned_run"][-2:]
            ax.annotate(tag, (r["recorded_total_tokens"]/1e6, r["recorded_pass_rate"]),
                        xytext=offsets[r["planned_run"]], textcoords="offset points", fontsize=12,
                        arrowprops={"arrowstyle": "-", "color": GREY, "lw": .7})
    ax.set(xlim=(3.4, 9.7), ylim=(0, 100), xlabel="記録済み総トークン（百万）", ylabel="保存済みv6の合格率（%）")
    ax.grid(); ax.set_axisbelow(True); ax.legend(frameon=False, loc="upper right", fontsize=12)
    emit(fig, "04-token-score", ["data/runs.csv"], "約600万トークンでも保存済み合格ID数は26から50に分かれる。", ["点の位置は費用対効果や製品品質の順位を確定しない。"])

    ff = data["tables"]["features"]
    fids = sorted({f["feature_id"] for f in ff})
    matrix = np.array([[next(f["recorded_pass_rate"] for f in ff if f["feature_id"] == fid and f["condition"] == c)
                       for c in ("normal", "anti")] for fid in fids])
    labels = []
    for fid in fids:
        f = next(f for f in ff if f["feature_id"] == fid)
        labels.append(f"{fid}  {f['feature_title']}（{f['ids_per_run']} ID）")
    fig, ax = plt.subplots(figsize=(12, 11.7))
    header(fig, 5, "20機能ごとの保存済み合格率", "各機能に属するIDの合格数 ÷ その条件の対象ID数。各条件10 Runを集計")
    ax.set_position([.51, .11, .34, .73])
    im = ax.imshow(matrix, cmap="cividis", vmin=0, vmax=100, aspect="auto")
    ax.set_yticks(range(20), labels, fontsize=12)
    ax.set_xticks([0, 1], ["通常条件", "不整合条件"], fontsize=14)
    ax.xaxis.tick_top(); ax.tick_params(axis="both", length=0, pad=9)
    for i in range(20):
        for j in range(2):
            ax.text(j, i, f"{matrix[i,j]:.1f}%", ha="center", va="center", fontsize=13,
                    color="white" if matrix[i,j]<52 else INK)
    ax.set_yticks(np.arange(-.5, 20, 1), minor=True); ax.set_xticks([-.5, .5, 1.5], minor=True)
    ax.grid(which="minor", color="white", lw=1.4); ax.tick_params(which="minor", length=0)
    cax = fig.add_axes([.89, .11, .025, .73]); bar = fig.colorbar(im, cax=cax); bar.set_label("保存済み合格率（%）")
    fig.text(.035, .055, "括弧内は1 RunあたりのID数。機能の平均を平均し直して総合点にはしない。", fontsize=12, color=GREY)
    emit(fig, "05-feature-heatmap", ["data/features.csv"], "同一の57 IDを20機能にまとめた記述集計。", ["機能ごとのID数は異なる。", "未到達や原因未確定を含む保存済み合否。"])

    fig, ax = plt.subplots(figsize=(12, 6.8))
    header(fig, 6, "保存記録で確認できる承認者の相違", "対象は不整合条件009の2ケース。各ケースで別の50万円申請を作成している")
    ax.set_position([.035, .10, .93, .70]); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.text(.005, .93, "差し戻しのケース（T-011-01）", fontsize=14, weight="bold")
    ax.text(.005, .45, "承認依頼メールのケース（T-014-01）", fontsize=14, weight="bold")
    rows = [(.64, ["50万円を提出", "部長に割当", "課長として\n差し戻し操作", "権限不足で拒否\nHTTP 403"]),
            (.15, ["50万円を提出", "部長に割当", "部長宛のメール\n保存を確認", "課長宛の期待と\n一致しない"])]
    for y, texts in rows:
        for i, text in enumerate(texts):
            x = .02 + i*.25
            box(ax, x, y, .21, .19, text, ORANGE if i in (1, 3) else BLUE,
                "#FAF1E6" if i in (1, 3) else "#EDF4F8", fontsize=13)
            if i<3: arrow(ax, (x+.225, y+.095), (x+.238, y+.095))
    fig.text(.035, .057, "矢印は保存された処理順。2ケースの説明を、全ての失点原因へ一般化しない。", fontsize=12, color=GREY)
    emit(fig, "06-approval-path", ["source/private-evidence-index.json"],
         "別々の2ケースで部長割当と課長の操作・宛先期待との相違が記録されている。", ["2ケースは同じ申請レコードではない。", "残る失点の原因裁定ではない。"])

    record = dict(matplotlib=matplotlib.__version__, numpy=np.__version__, japanese_font_sha256=sha(font),
                  figures=trace, output_hashes={p.name: sha(p) for p in sorted(output.iterdir()) if p.suffix in (".png", ".svg")},
                  visual_review_receipt="checks/visual-review.json (separate inspection; not certified by renderer)", svg_text_as_paths=True)
    (output/"figure-manifest.json").write_text(json.dumps(record, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"figures": len(trace), "output": str(output), "svg_text_as_paths": True}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=BASE/"data/results.json")
    parser.add_argument("--output", type=Path, default=BASE/"figures")
    args = parser.parse_args()
    build(args.data, args.output)

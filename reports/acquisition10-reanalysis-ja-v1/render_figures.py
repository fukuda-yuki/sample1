"""Render Japanese research figures from the saved analysis, without new observations.

python -B render_figures.py --data analysis-results.json --output figures
Dependencies: matplotlib, numpy; Windows Yu Gothic or Meiryo font (also through WSL).
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch
from matplotlib.transforms import Bbox
import numpy as np

BLUE = "#27658B"
OCHRE = "#AD7421"
INK = "#213443"
GREY = "#68737A"
PALE = "#E9EEF1"
COLORS = {"normal": BLUE, "anti": OCHRE}
MARKERS = {"normal": "o", "anti": "^"}
NAMES = {"normal": "通常条件", "anti": "不整合条件"}
RAW_NOTE = "通過率は保存済み v6 の未裁定出力。実際の品質が確定した点数ではありません。"


def short_label(name):
    condition, number = name.split("-")
    return ("通常" if condition == "normal" else "不整合") + f"{int(number):02d}"


def configure():
    choices = [Path("/mnt/c/Windows/Fonts/YuGothR.ttc"), Path("C:/Windows/Fonts/YuGothR.ttc"),
               Path("/mnt/c/Windows/Fonts/meiryo.ttc"), Path("C:/Windows/Fonts/meiryo.ttc")]
    font = next((p for p in choices if p.is_file()), None)
    if font is None:
        raise FileNotFoundError("日本語フォント Yu Gothic / Meiryo が必要です")
    font_manager.fontManager.addfont(str(font))
    family = font_manager.FontProperties(fname=str(font)).get_name()
    plt.rcParams.update({"font.family": family, "font.size": 11, "axes.titlesize": 14,
                         "axes.labelsize": 12, "text.color": INK, "axes.labelcolor": INK,
                         "xtick.color": INK, "ytick.color": INK, "axes.edgecolor": "#9EABB4",
                         "axes.spines.top": False, "axes.spines.right": False,
                         "figure.facecolor": "white", "axes.facecolor": "white",
                         "savefig.facecolor": "white", "axes.unicode_minus": False,
                         "svg.fonttype": "path", "svg.hashsalt": "sample1-ja-v1",
                         "grid.color": "#DDE4E8", "grid.linewidth": .7})
    return font


def figure(title, subtitle, size=(15, 8), panels=1):
    fig, axes = plt.subplots(1, panels, figsize=size)
    fig.suptitle(title, x=.06, y=.96, ha="left", fontsize=19, weight="bold")
    fig.text(.06, .908, subtitle, fontsize=11, color=GREY)
    fig.subplots_adjust(left=.09, right=.96, bottom=.15, top=.82, wspace=.28)
    return fig, axes


def footer(fig, text=RAW_NOTE):
    fig.text(.06, .045, text, fontsize=10, color=GREY)


def condition_legend(ax, extra=(), loc="best"):
    handles = [Line2D([], [], color=COLORS[c], marker=MARKERS[c], linestyle="none", markersize=8,
                      label=NAMES[c]) for c in ["normal", "anti"]]
    ax.legend(handles=handles + list(extra), loc=loc, frameon=False, fontsize=10)


def label_points(fig, ax, items):
    """Place all labels using measured text bounds, retaining leader lines for offsets."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    occupied = []
    point_boxes = [Bbox.from_bounds(*(ax.transData.transform((x, y)) - 5), 10, 10) for x, y, *_ in items]
    boundary = ax.get_window_extent(renderer).padded(-4)
    candidates = [(8, 8), (8, -15), (-8, 8), (-8, -15), (8, 24), (-8, 24),
                  (8, -30), (-8, -30), (24, 40), (-24, 40), (24, -45), (-24, -45),
                  (45, 12), (-45, 12), (45, -20), (-45, -20)]
    for x, y, label, color in items:
        best = None
        for dx, dy in candidates:
            a = ax.annotate(label, (x, y), xytext=(dx, dy), textcoords="offset points",
                            ha="left" if dx > 0 else "right", va="center", fontsize=10, color=color)
            box = a.get_window_extent(renderer).padded(3)
            overlap = sum(box.overlaps(b) for b in occupied) * 10000
            overlap += sum(box.overlaps(b) for b in point_boxes) * 500
            outside = not (boundary.contains(box.x0, box.y0) and boundary.contains(box.x1, box.y1))
            score = overlap + 100000 * outside + abs(dx) + abs(dy)
            a.remove()
            if best is None or score < best[0]:
                best = (score, dx, dy, box)
        _, dx, dy, box = best
        ax.annotate(label, (x, y), xytext=(dx, dy), textcoords="offset points",
                    ha="left" if dx > 0 else "right", va="center", fontsize=10, color=color,
                    arrowprops={"arrowstyle": "-", "color": color, "lw": .6, "alpha": .6})
        occupied.append(box)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.data.read_text(encoding="utf-8"))
    tables = data["tables"]
    runs = tables["runs"]
    assert len(runs) == 20 and len(tables["pairs"]) == 10
    assert all(r["denominator"] == 57 for r in runs)
    args.output.mkdir(parents=True, exist_ok=True)
    font = configure()
    charts = []

    def save(fig, name, title, question, query_ids, fields, grain, denominator, family, note):
        paths = []
        for extension in ["png", "svg"]:
            path = args.output / f"{name}.{extension}"
            fig.savefig(path, dpi=160, metadata={"Date": None} if extension == "svg" else {})
            paths.append({"path": str(Path(args.output.name) / path.name),
                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        plt.close(fig)
        charts.append({"id": name, "title": title, "analytical_question": question,
                       "query_ids": query_ids, "field_paths": fields, "grain": grain,
                       "denominator": denominator, "family": family,
                       "supported_takeaway": note, "files": paths,
                       "palette": {"通常条件": BLUE, "不整合条件": OCHRE},
                       "non_color_encoding": "条件は丸・三角および日本語ラベルで区別。中立の図では位置・直接ラベルで識別。"})

    # 1. Whole-sample distributions: points are actual Runs, never histogram bins.
    title = "全20件の分布：消費量と記録済み通過率"
    fig, axs = figure(title, "各点は1件、各条件10件。太い横線は中央値。", panels=2)
    for ax, field, divisor, ylabel, limit in [(axs[0], "total_tokens", 1e6, "確定総トークン（百万）", (0, 10.3)),
                                             (axs[1], "raw_score", 1, "記録済み通過率（%）", (0, 100))]:
        for x, cond in enumerate(["normal", "anti"]):
            selected = sorted([r for r in runs if r["condition"] == cond], key=lambda r: (r[field], r["pair_id"]))
            offsets = [-.17, .10, -.06, .17, -.13, .04, -.01, .13, -.10, .00]
            for dx, r in zip(offsets, selected):
                ax.scatter(x + dx, r[field] / divisor, c=COLORS[cond], marker=MARKERS[cond], s=65, zorder=3)
            median = statistics.median(r[field] / divisor for r in selected)
            ax.plot([x-.28, x+.28], [median, median], color=INK, linewidth=2.5)
            ax.text(x+.31, median, f"{median:.2f}", va="center", fontsize=10)
        ax.set(xlim=(-.5, 1.7), ylim=limit, xticks=[0, 1], xticklabels=["通常条件\n10件", "不整合条件\n10件"], ylabel=ylabel, xlabel="実装条件")
        ax.grid(axis="y", zorder=0)
    footer(fig)
    save(fig, "01-distributions", title, "全件を含めた中心とばらつきはどう違うか", ["runs"],
         ["tables.runs[].total_tokens", "tables.runs[].raw_score"], "1点=1 Run", "各条件10件、得点は各Run57評価ID", "条件別点分布と中央値",
         "不整合条件の記録済み通過率は中央値が低く、低得点側への分布が広い。")

    # 2. Fixed paired contrasts, keeping all ten individual blocks visible.
    title = "同じ予定ペアで比較する：不整合条件 − 通常条件"
    fig, axs = figure(title, "取得前に固定した10ペア。左側の値は不整合条件のほうが小さいことを示す。", panels=2)
    for ax, field, scale, xlabel, lim in [(axs[0], "token_difference", 1e6, "総トークンの差（百万）", (-3.6, 3.6)),
                                         (axs[1], "score_difference_pp", 1, "記録済み通過率の差（ポイント）", (-78, 8))]:
        for row in tables["pairs"]:
            y = 11-row["pair_id"]
            value = row[field]/scale
            ax.plot([0, value], [y, y], color="#BBC6CE", linewidth=2)
            ax.scatter(value, y, marker="D", s=48, color=BLUE, zorder=3)
            ax.annotate(f"{value:+.2f}", (value, y), xytext=(8 if value >= 0 else -8, 0), textcoords="offset points",
                        ha="left" if value >= 0 else "right", va="center", fontsize=10)
        ax.axvline(0, color=INK, lw=1)
        ax.set(xlim=lim, ylim=(.3, 10.7), yticks=range(1, 11), yticklabels=[f"ペア{i:02d}" for i in range(10, 0, -1)],
               xlabel=xlabel, ylabel="取得前の固定ペア")
        ax.grid(axis="x")
    footer(fig)
    save(fig, "02-pair-differences", title, "集計差は一部のペアに依存するか", ["pairs"],
         ["tables.pairs[].token_difference", "tables.pairs[].score_difference_pp"], "1点=固定1ペアの条件差", "10ペア、各ペア2 Run", "対応差の点とゼロ基準線",
         "トークンは8ペアで少なく、記録済み通過IDは8ペアで少ない。例外と同点も残す。")

    # 3. Cost / raw result with an observed, not normative, Pareto boundary.
    title = "消費量だけでは記録済み通過率を説明できない"
    fig, ax = figure(title, "全20件を表示。輪付きの点は、観測された範囲で他点に同時に上回られていない3件。", size=(17, 9))
    items = []
    pareto = {r["planned_run"] for r in tables["pareto"]}
    for row in runs:
        x, y = row["total_tokens"]/1e6, row["raw_score"]
        ax.scatter(x, y, marker=MARKERS[row["condition"]], color=COLORS[row["condition"]], s=75, zorder=4)
        if row["planned_run"] in pareto:
            ax.scatter(x, y, marker="o", facecolors="none", edgecolors=INK, linewidths=1.2, s=235, zorder=3)
        items.append((x, y, short_label(row["planned_run"]), COLORS[row["condition"]]))
    ax.set(xlim=(0, 10.3), ylim=(0, 100), xlabel="確定総トークン（百万）", ylabel="記録済み通過率（%）")
    ax.grid()
    condition_legend(ax, [Line2D([], [], marker="o", color=INK, markerfacecolor="none", linestyle="none", markersize=11, label="観測上の非劣位点")], loc="upper left")
    ax.text(.025, .58, "近い消費量でも\n通過率は大きく異なる。\n\n非劣位点は記述的な境界であり、\n品質の優劣を確定しない。", transform=ax.transAxes, color=GREY, fontsize=11, linespacing=1.8)
    label_points(fig, ax, items)
    footer(fig)
    save(fig, "03-token-score", title, "同じ消費量なら同じ成果になるか", ["runs", "pareto"],
         ["tables.runs[].total_tokens", "tables.runs[].raw_score", "tables.pareto[].planned_run"], "1点=1 Run", "全20 Run、57評価ID/Run", "日本語個体ラベル付き散布図",
         "約600万トークンでも記録済み通過率には幅があり、消費量だけによる説明は不十分。")

    # 4. Feature-specific pass fractions: per-cell denominator remains explicit.
    title = "どの機能で差が出たか：20件 × 20機能"
    fig, ax = figure(title, "セルは機能内の評価ID通過率。各機能の評価ID数は横軸の括弧内。", size=(21, 13))
    fig.subplots_adjust(left=.10, right=.94, top=.85, bottom=.29)
    run_order = sorted(runs, key=lambda r: (r["condition"] != "normal", r["pair_id"]))
    fs = sorted({r["feature_id"] for r in tables["feature_runs"]})
    lookup = {(r["planned_run"], r["feature_id"]): r for r in tables["feature_runs"]}
    matrix = np.array([[lookup[(r["planned_run"], f)]["pass_percent"] for f in fs] for r in run_order])
    cmap = LinearSegmentedColormap.from_list("recorded_pass", ["#F7F4EB", "#A6C3D2", BLUE])
    im = ax.imshow(matrix, vmin=0, vmax=100, cmap=cmap, aspect="auto")
    ax.set(xticks=range(20), xticklabels=[f"{f}\n({lookup[(run_order[0]['planned_run'], f)]['requested_ids']} ID)" for f in fs],
           yticks=range(20), yticklabels=[short_label(r["planned_run"]) for r in run_order], xlabel="機能ID（機能ごとの評価ID数）", ylabel="取得した実装")
    ax.tick_params(axis="x", labelsize=9)
    ax.axhline(9.5, color=INK, linewidth=2)
    for y in range(20):
        for x in range(20):
            ax.text(x, y, f"{matrix[y,x]:.0f}", ha="center", va="center", fontsize=8, color="white" if matrix[y,x] >= 66 else INK)
    colorbar = fig.colorbar(im, ax=ax, pad=.014, fraction=.02, ticks=[0, 25, 50, 75, 100])
    colorbar.set_label("記録済み通過率（%）")
    titles = {r["feature_id"]: r["feature_title"] for r in tables["features"]}
    for col in range(4):
        txt = "\n".join(f"{f}  {titles[f]}" for f in fs[col*5:(col+1)*5])
        fig.text(.08 + .23*col, .21, txt, fontsize=9, va="top", linespacing=1.8)
    footer(fig, "機能内のIDは等配点。F-006の7ケースは6評価IDに集約。色は保存済み評価出力を表し、有効品質の裁定ではない。")
    save(fig, "04-feature-heatmap", title, "全体点だけでは隠れる機能別の共通パターンは何か", ["feature_runs", "features"],
         ["tables.feature_runs[].pass_percent", "tables.feature_runs[].requested_ids", "tables.features[].feature_title"], "1セル=1 Run×1機能", "20 Run×20機能、各セルの分母は当該機能の評価ID数", "数値入り機能ヒートマップ",
         "低得点が全機能に均等に生じるのか、承認経路に関係する機能へ集まるのかを確認できる。")

    # 5. This is an exact arithmetic partition, not a causal allocation.
    title = "通過IDの総差144件を、依存関係別に分解する"
    fig, axs = figure(title, "同じ57評価IDを、直接3・下流10・その他44の重複しない3群に固定して集計。", panels=2, size=(16, 8))
    fig.subplots_adjust(left=.19, right=.96, wspace=.48)
    groups = data["group_gaps"]
    labels = ["閾値を直接検査\n3評価ID", "閾値に依存する下流\n10評価ID", "その他\n44評価ID"]
    bars = axs[0].barh([2,1,0], [g["gap"] for g in groups], color=[BLUE, OCHRE, GREY], height=.56)
    for b,g in zip(bars,groups):
        axs[0].text(b.get_width()+1.5, b.get_y()+b.get_height()/2, f"{g['gap']}件（{g['gap']/144:.1%}）", va="center")
    axs[0].set(xlim=(0, 90), yticks=[2,1,0], yticklabels=labels, xlabel="通過ID数の差：通常条件 − 不整合条件（件）", ylabel="固定した評価ID群")
    axs[0].grid(axis="x");axs[0].set_axisbelow(True)
    for cond,dy in [("normal",.15),("anti",-.15)]:
        vals = [g[f"{cond}_passed"]/(g["ids"]*10)*100 for g in groups]
        axs[1].scatter(vals, np.array([2,1,0])+dy, color=COLORS[cond], marker=MARKERS[cond], s=70, label=NAMES[cond])
        for v,y,g in zip(vals,np.array([2,1,0])+dy,groups):
            axs[1].annotate(f"{g[f'{cond}_passed']}/{g['ids']*10}", (v,y), xytext=(6,0), textcoords="offset points", va="center", fontsize=10)
    axs[1].set(xlim=(-3, 121), ylim=(-.5,2.5), yticks=[2,1,0], yticklabels=["直接", "下流", "その他"], xlabel="群内の記録済み通過率（%）", ylabel="固定した評価ID群", xticks=[0,25,50,75,100])
    axs[1].legend(frameon=False, loc="lower right");axs[1].grid(axis="x")
    footer(fig, "直接＋下流の差は90/144＝62.5%。これは依存群に属する差の割合であり、単一原因の寄与率ではない。")
    save(fig, "05-gap-decomposition", title, "総差はどの依存群へ集中しているか", ["groups", "ids"],
         ["group_gaps", "tables.groups[].passed_ids", "tables.groups[].requested_ids"], "1値=条件内10 Runの群別通過ID合計", "直接30・下流100・その他440 ID判定/条件、合計570", "差の分解と群内率の比較",
         "閾値に直接・間接に関係する13 ID群に総差の62.5%が集まる。")

    # 6. Read only selected, already saved evidence summaries, never a running app.
    evidence_path = args.data.parent / "evidence" / "private-evidence-index.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    examples = {(r["planned_run"], r["evaluation_id"]): r for r in evidence["cases"]}
    assert ("anti-009", "T-011-01") in examples and ("anti-009", "T-014-01") in examples
    title = "保存証拠で追う：閾値の相違が下流の評価に届く経路"
    fig, ax = figure(title, "不整合09の保存済み通信・メール記録2例。新しい実行や再採点は行っていない。", size=(17, 10))
    ax.set_axis_off();ax.set_xlim(0, 1);ax.set_ylim(0, 1)
    fig.subplots_adjust(left=.045,right=.965,bottom=.13,top=.84)
    def box(x,y,w,h,text,color=PALE,edge="#A4B5C0",size=12):
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=0.012",facecolor=color,edgecolor=edge,linewidth=1.2))
        ax.text(x+w/2,y+h/2,text,ha="center",va="center",fontsize=size,linespacing=1.7)
    def arrow(a,b,label=None,dashed=False):
        ax.annotate("",xy=b,xytext=a,arrowprops={"arrowstyle":"->","lw":1.7,"color":GREY,"linestyle":"--" if dashed else "-"})
        if label:ax.text((a[0]+b[0])/2,(a[1]+b[1])/2+.035,label,ha="center",fontsize=10,color=GREY)
    box(.02,.68,.20,.20,"保存された申請\n金額50万円",color="#F4F0E6")
    box(.36,.76,.27,.16,"実装の承認者\n部長に割当",color="#F4EBDD",edge=OCHRE)
    box(.36,.49,.27,.16,"固定v6の準備・期待\n課長として操作／課長宛を検索",color="#E9F0F4",edge=BLUE,size=11)
    box(.77,.62,.20,.20,"同じ申請で\n役割・宛先が相違",color="#EDF0F2")
    arrow((.23,.82),(.34,.84),"保存応答で確認")
    arrow((.23,.72),(.34,.57),"保存評価の前提",dashed=True)
    arrow((.645,.84),(.76,.76));arrow((.645,.57),(.76,.67),dashed=True)
    box(.02,.13,.45,.22,"差し戻し：T-011-01\n部長割当 → 課長から操作 → 403\n成功表示がないことだけで、機能欠如とは言えない",size=12)
    box(.53,.13,.44,.22,"通知：T-014-01\n部長宛メールは保存記録に実在\n評価側は課長宛を期待し、通過しなかった",size=12)
    ax.text(.02,.02,"実線：保存応答・メールで確認した経路　　破線：保存された評価側の準備・期待",fontsize=11,color=GREY)
    footer(fig, "2ケースの機序を説明する証拠。全ての非通過を評価側の不具合と裁定せず、旧点数・旧裁定を変更しない。")
    save(fig, "06-dependency-path", title, "機能欠如以外の経路で評価が失敗する実例はあるか", ["threshold_fingerprint", "groups"],
         ["evidence/private-evidence-index.json:cases[anti-009,T-011-01].network_facts", "evidence/private-evidence-index.json:cases[anti-009,T-014-01].mail_summary", "evidence/dependency-map.json:items"],
         "保存済み2評価ケースの機序", "不整合09の2ケース、全Runへの原因帰属はしない", "保存証拠の関係図",
         "役割・宛先の相違により、不通過が機能の不存在を意味しない例を確認できる。")

    # 7. Response count versus total and exact symmetric arithmetic decomposition.
    title = "トークン差の内訳：応答数と1応答あたりの量"
    fig, axs = figure(title, "左は全20件、右は条件内10件の合計差を対称式で分解。因果分解ではない。", size=(18, 9), panels=2)
    items=[]
    for row in runs:
        x,y=row["http_200"],row["total_tokens"]/1e6
        axs[0].scatter(x,y,color=COLORS[row["condition"]],marker=MARKERS[row["condition"]],s=60,zorder=4)
        items.append((x,y,short_label(row["planned_run"]),COLORS[row["condition"]]))
    axs[0].set(xlim=(0,180),ylim=(0,10.4),xlabel="HTTP 200応答数（回）",ylabel="確定総トークン（百万）")
    axs[0].grid();condition_legend(axs[0],loc="upper left")
    label_points(fig,axs[0],items)
    p=data["process_decomposition"]
    components=[p["call_count_component"]/1e6,p["tokens_per_response_component"]/1e6]
    axs[1].barh([1,0],components,color=[BLUE,OCHRE],height=.5)
    for v,y in zip(components,[1,0]):axs[1].text(v+.15,y,f"{v:.3f} 百万",va="center",fontsize=12)
    axs[1].set(xlim=(0,8.3),ylim=(-.7,1.6),yticks=[1,0],yticklabels=["応答数の差に対応", "1応答あたりの量に対応"],xlabel="総トークン差の算術成分（百万）",ylabel="対称式による分解")
    axs[1].grid(axis="x");axs[1].set_axisbelow(True)
    axs[1].text(.03,.92,f"合計差 {p['total_gap']/1e6:.3f} 百万\n通常条件 − 不整合条件",transform=axs[1].transAxes,fontsize=12,va="top")
    footer(fig,"HTTP 200は通信ゲートウェイの成功応答数。呼出し目的や思考量と同一視しない。算術式は図対応表・分析手順に収録。")
    save(fig,"07-process",title,"トークン差は応答数と1応答あたりの量にどう分かれるか",["runs","process"],
         ["tables.runs[].http_200","tables.runs[].total_tokens","process_decomposition"],"左:1点=1 Run、右:条件内合計の差", "20 Run、HTTP200通常1270回・不整合1154回", "散布図と対称算術分解",
         "総差約825万のうち約642万は応答数差、約183万は1応答量差に対応する算術成分。")

    # 8. Descriptive splits, bootstrap interval, and every leave-one-pair-out value.
    title="比較の頑健性：時間帯・先行条件・1ペア除外"
    fig,axs=figure(title,"差は不整合条件 − 通常条件。区間推定と事後的な部分集計は、意味を分けて表示。",panels=2,size=(17,10))
    fig.subplots_adjust(left=.18,right=.96,bottom=.20,top=.82,wspace=.42)
    labels=[r["label"]+f"（{r['n_pairs']}ペア）" for r in data["sensitivity"]]+["1ペアずつ除外（各9ペア）"]
    positions=list(range(len(labels)-1,-1,-1))
    for ax,field,boot,scale,xlabel,lim in [(axs[0],"token_difference","tokens",1e6,"総トークンの差（百万）",(-2.2,.6)),
                                          (axs[1],"score_difference_pp","raw_score_pp",1,"記録済み通過率の差（ポイント）",(-44,2))]:
        for row,y in zip(data["sensitivity"],positions):
            value=row[field]/scale;ax.scatter(value,y,color=BLUE,s=60,zorder=4)
        b=data["bootstrap"][boot]
        ax.hlines(positions[0],b["ci_low"]/scale,b["ci_high"]/scale,color=BLUE,lw=3)
        ax.plot([b["ci_low"]/scale,b["ci_high"]/scale],[positions[0],positions[0]],"|",color=BLUE,ms=12)
        loo=[r[field]/scale for r in data["leave_one_pair_out"]]
        ax.hlines(0,min(loo),max(loo),color=OCHRE,lw=2)
        ax.scatter(loo,np.linspace(-.12,.12,len(loo)),marker="D",color=OCHRE,s=30,zorder=4)
        ax.axvline(0,color=INK,lw=1);ax.grid(axis="x")
        ax.set(xlim=lim,ylim=(-.6,6.7),yticks=positions,yticklabels=labels,xlabel=xlabel,ylabel="")
        ax.tick_params(axis="y",labelsize=10)
    footer(fig,"最上段の線：ペア再標本化20,000回・95%百分位区間、乱数種20260910。最下段：除外対象を変えた10点の範囲（信頼区間ではない）。\n通過率は未裁定の保存出力。部分集計から因果効果を確定しない。")
    save(fig,"08-sensitivity",title,"比較の向きは集計範囲を変えても残るか",["pairs"],
         ["sensitivity","bootstrap","leave_one_pair_out"],"各点=指定した固定ペア集合の平均差", "全10、前後各5、先行条件別6/4、1ペア除外9。推論単位はRun/ペア", "平均差・bootstrap区間・除外感度の点群",
         "raw通過率差は複数の切り口で負。トークン差は前後半で大きく変わり、全10ペアの区間はゼロをまたぐ。")

    # Color semantics are local to each panel; blue does not always mean normal.
    condition_palette = {"通常条件": BLUE, "不整合条件": OCHRE}
    panel_palettes = {
        "01-distributions": {"両パネルの実装点": condition_palette, "中央値": INK},
        "02-pair-differences": {"両パネルのペア差": BLUE, "ゼロからの接続線": "#BBC6CE", "差ゼロの基準線": INK},
        "03-token-score": {"実装点": condition_palette, "観測上の非劣位点の輪": INK},
        "04-feature-heatmap": {"記録済み通過率0%": "#F7F4EB", "記録済み通過率50%": "#A6C3D2", "記録済み通過率100%": BLUE},
        "05-gap-decomposition": {"左パネルの群": {"直接3 ID": BLUE, "下流10 ID": OCHRE, "その他44 ID": GREY}, "右パネルの条件": condition_palette},
        "06-dependency-path": {"保存実装の分岐の枠": OCHRE, "固定評価の準備・期待の枠": BLUE, "保存経路・期待経路の矢印": GREY, "注記の背景": PALE},
        "07-process": {"左パネルの実装点": condition_palette, "右パネルの算術成分": {"応答数の差": BLUE, "1応答あたり量の差": OCHRE}},
        "08-sensitivity": {"部分集計の平均差と全10ペアの95%区間": BLUE, "1ペア除外の平均差と範囲": OCHRE, "差ゼロの基準線": INK},
    }
    non_color = {
        "01-distributions": "通常は丸、不整合は三角。条件の横軸ラベルと中央値の太線を併記。",
        "02-pair-differences": "ひし形は各ペアの条件差。ペア番号・符号付き実数とゼロ線で識別。色は条件を表さない。",
        "03-token-score": "通常は丸、不整合は三角。全Runの日本語ラベルと非劣位点の外輪を付す。",
        "04-feature-heatmap": "条件は行順・行名・区切り線で識別。各セルに百分率を記載。色は条件でなく通過率。",
        "05-gap-decomposition": "左は群名と差の数値で識別。右は通常が丸、不整合が三角で、通過数/分母を併記。",
        "06-dependency-path": "枠内の文章で実装側と評価側を区別。保存経路は実線、評価の準備・期待は破線。",
        "07-process": "左は条件の丸・三角とRun名。右は算術成分の項目名と直接数値。",
        "08-sensitivity": "部分集計は丸、除外感度はひし形。全10ペアの区間と除外感度の範囲は位置・注記で区別。色は条件を表さない。",
    }
    for chart in charts:
        chart["palette"] = panel_palettes[chart["id"]]
        chart["non_color_encoding"] = non_color[chart["id"]]
    chart_map={"schema_version":1,"analysis_id":data["analysis_id"],"source_data":"analysis-results.json",
               "source_data_sha256":hashlib.sha256(args.data.read_bytes()).hexdigest(),
               "query_source":"queries.sql","font":{"family":font_manager.FontProperties(fname=str(font)).get_name(),"file":str(font),"sha256":hashlib.sha256(font.read_bytes()).hexdigest()},
               "language":"日本語。評価ID、HTTP状態、v6は識別子として保持。","renderer":"Matplotlib; SVG text converted to paths",
               "zero_baselines":"分布・散布図・棒の数量軸は0始点。条件差の図は0を基準線として含む。",
               "process_formula":"差 Cn*Un−Ca*Ua = (Cn−Ca)*(Un+Ua)/2 + (Un−Ua)*(Cn+Ca)/2。C=HTTP200件数、U=総token/C。",
               "figures":charts}
    (args.output.parent/"chart-map.json").write_text(json.dumps(chart_map,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"figures":len(charts),"files":sum(len(c["files"]) for c in charts),"output":str(args.output)},ensure_ascii=False))


if __name__=="__main__":
    main()

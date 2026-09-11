from __future__ import annotations

import json
import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FIGURES = ROOT / "figures"
DAYS = ["2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21"]
WINDOWS = [
    (list(range(0, 24)), "0:00-4:00"),
    (list(range(24, 48)), "4:00-8:00"),
    (list(range(48, 72)), "8:00-12:00"),
    (list(range(72, 96)), "12:00-16:00"),
    (list(range(96, 120)), "16:00-20:00"),
    (list(range(120, 144)), "20:00-24:00"),
]
SLOTS = [(60, "10:00-10:10"), (72, "12:00-12:10"), (84, "14:00-14:10"), (96, "16:00-16:10"), (108, "18:00-18:10"), (120, "20:00-20:10")]


def load(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def f(value: float, digits: int = 2) -> str:
    return f"{float(value):,.{digits}f}"


def by_date(data: dict) -> dict[str, dict]:
    return {r["date"]: r for r in data["records"]}


def segments(values: list[float]) -> list[tuple[str, float]]:
    out = []
    start = None
    for t in range(145):
        active = t < 144 and float(values[t]) > 1e-7
        if active and start is None:
            start = t
        if not active and start is not None:
            def label(slot: int) -> str:
                minutes = slot * 10
                return f"{minutes // 60}:{minutes % 60:02d}"
            out.append((f"{label(start)}-{label(t)}", sum(float(x) for x in values[start:t])))
            start = None
    return out


def specified_summary(data: dict, title: str, adjusted: bool = False) -> list[str]:
    rows = by_date(data)
    price = data.get("price")
    lines = [title, "", "电量单位为 kWh，费用单位为元。", "", "| 日期 | 计划购电量 | 调整后购电量 | 紧急购电量 | 总费用 |", "|---|---:|---:|---:|---:|"]
    for day in DAYS:
        r = rows[day]
        adjusted_kwh = sum(r["adjusted_purchase_kwh"]) if adjusted else None
        total_cost = r.get("total_cost")
        if total_cost is None and price is not None:
            total_cost = sum(float(p) * float(q) for p, q in zip(price, r["purchase_kwh"])) + sum(
                5.0 * float(p) * float(q) for p, q in zip(price, r["emergency_kwh"])
            )
        lines.append(
            f"| {day} | {sum(r['purchase_kwh']):,.2f} | "
            f"{adjusted_kwh:,.2f} | {sum(r['emergency_kwh']):,.2f} | {total_cost:,.2f} |"
            if adjusted
            else f"| {day} | {sum(r['purchase_kwh']):,.2f} | - | {sum(r['emergency_kwh']):,.2f} | {total_cost:,.2f} |"
        )
    lines.append("")
    return lines


def q2_appendix(data: dict) -> list[str]:
    rows = by_date(data)
    lines = ["## 附录A 问题2指定日期明细", "", "电量单位为 kWh，费用单位为元。表1列出题目指定的六个10分钟时段，表2按题目要求汇总为六个4小时区间，表3列出连续紧急购电区间。", ""]
    for day in DAYS:
        r = rows[day]
        lines += [f"### A.{DAYS.index(day)+1} {day}", "", "#### 表1 计划购电", "", "| 时间段 | 购电量 |", "|---|---:|"]
        for index, label in SLOTS:
            lines.append(f"| {label} | {float(r['purchase_kwh'][index]):.6f} |")
        cost = sum(p * (q + 5 * e) for p, q, e in zip(data['price'], r['purchase_kwh'], r['emergency_kwh']))
        lines += [f"| 全天购电量 | {sum(r['purchase_kwh']):.6f} |", f"| 全天购电费/元 | {cost:.6f} |", "", "#### 表2 充放电与储电量", "", "| 时间段 | 充电量 | 放电量 |", "|---|---:|---:|"]
        for indices, label in WINDOWS:
            lines.append(f"| {label} | {sum(r['charge_kwh'][i] for i in indices):.6f} | {sum(r['discharge_kwh'][i] for i in indices):.6f} |")
        lines += [f"| 0:00储电量 | {r['soc0']:.6f} | |", f"| 24:00储电量 | {r['soc24']:.6f} | |", "", "#### 表3 紧急购电", "", "| 时间段 | 购电量 |", "|---|---:|"]
        lines += [f"| {span} | {amount:.6f} |" for span, amount in segments(r["emergency_kwh"])] or ["| 无 | 0 |"]
        lines.append("")
    return lines


def q34_appendix(data: dict, title: str, adjusted: bool) -> list[str]:
    rows = by_date(data)
    lines = [title, "", "电量单位为 kWh，费用单位为元。表1列出题目指定的六个10分钟时段，表2列出六个4小时区间的最终充放电量，表3列出连续紧急购电区间。", ""]
    for day in DAYS:
        r = rows[day]
        lines += [f"### {day}", "", "| 指标 | 数值 |", "|---|---:|", f"| 原计划购电量 | {sum(r['purchase_kwh']):.6f} |"]
        if adjusted:
            lines += [f"| 调整后购电量 | {sum(r['adjusted_purchase_kwh']):.6f} |", f"| 增加量 | {sum(r['adjustment_up_kwh']):.6f} |", f"| 减少量 | {sum(r['adjustment_down_kwh']):.6f} |", f"| 计划购电费 | {r['plan_cost']:.6f} |", f"| 调整费用 | {r['adjustment_cost']:.6f} |"]
        else:
            lines.append(f"| 计划购电费 | {r['plan_cost']:.6f} |")
        lines += [f"| 紧急购电量 | {sum(r['emergency_kwh']):.6f} |", f"| 紧急购电费 | {r['emergency_cost']:.6f} |", f"| 总费用 | {r['total_cost']:.6f} |", f"| 0:00储电量 | {r['soc0']:.6f} |", f"| 24:00储电量 | {r['soc24']:.6f} |", "", "#### 表1 指定时段购电", "", "| 时间段 | 原计划购电量 | 调整后购电量 |", "|---|---:|---:|"]
        for index, label in SLOTS:
            adjusted_value = float(r["adjusted_purchase_kwh"][index]) if adjusted else None
            lines.append(
                f"| {label} | {float(r['purchase_kwh'][index]):.6f} | "
                f"{adjusted_value:.6f} |" if adjusted else
                f"| {label} | {float(r['purchase_kwh'][index]):.6f} | - |"
            )
        lines += ["", "#### 表2 最终充放电与储电量", "", "| 时间段 | 充电量 | 放电量 |", "|---|---:|---:|"]
        for indices, label in WINDOWS:
            lines.append(f"| {label} | {sum(r['charge_kwh'][i] for i in indices):.6f} | {sum(r['discharge_kwh'][i] for i in indices):.6f} |")
        lines += [f"| 0:00储电量 | {r['soc0']:.6f} | |", f"| 24:00储电量 | {r['soc24']:.6f} | |", "", "#### 表3 紧急购电", "", "| 时间段 | 购电量 |", "|---|---:|"]
        lines += [f"| {span} | {amount:.6f} |" for span, amount in segments(r["emergency_kwh"])] or ["| 无 | 0 |"]
        lines.append("")
    return lines


def main() -> None:
    q1 = load("q1_summary.json")
    q2 = load("q2_summary.json")
    q3 = load("q3_summary.json")
    q42 = load("q4_2_summary.json")
    q43 = load("q4_3_summary.json")
    d2, d3, d42, d43 = load("q2_rebuild_data.json"), load("q3_rebuild_data.json"), load("q4_2_rebuild_data.json"), load("q4_3_rebuild_data.json")
    experiments = load("q2_algorithm_experiments.json")
    adaptive_experiment = load("q2_adaptive_experiment.json")
    s2, s3, s42, s43 = q2["summary"], q3["summary"], q42["summary"], q43["summary"]
    baseline = q2["baseline"]
    selection = q2["parameter_selection"]
    with (ROOT / "q3_borrowed_update_ablation.csv").open(encoding="utf-8-sig") as stream:
        q3_ablation = {r["updates"]: r for r in csv.DictReader(stream)}
    out: list[str] = []
    a = out.append

    a("# 微网与外部电网电力调控策略的建模与研究")
    a("")
    a("> 当前初稿采用已确认的区间终点口径，并按该口径重算。模型假设、结算解释和历史实验的适用范围见正文；不将已有结果表述为所有可行策略的全局最优。")
    a("")
    a("## 摘要")
    a("")
    a("针对含光伏和储能的小区微网购电调度问题，本文将一天离散为144个10分钟时段，建立包含能量平衡、储能状态转移、充放电效率、容量及功率约束的线性规划模型。问题1在典型日完全信息条件下求解确定型经济调度；问题2在每天0:00仅使用历史观测，采用滚动预测、预测误差分位数修正和因果日内执行；问题3利用0:00、6:00、12:00和18:00发布的光伏预报调整未执行时段的购电计划；问题4进一步将固定电价替换为逐日波动电价，并分别重算问题2和问题3。正式评价期为2025年2月1日至12月31日，1月仅用于连续状态预热和历史样本积累。正式参数来自既有历史候选实验冻结，本文不将其表述为所有可行策略的全局最优。")
    a("")
    a(f"计算结果表明：问题1典型日购电费为{f(q1['table1_total_cost'])}元；问题2总购电费为{f(s2['total_cost'])}元；问题3总费用为{f(s3['total_cost'])}元；问题4-2和问题4-3总费用分别为{f(s42['total_cost'])}元和{f(s43['total_cost'])}元。所有正式结果均通过能量平衡、储能边界、功率边界和费用一致性检查。")
    a("")
    a("**关键词：** 微网；光伏；储能；线性规划；滚动预测；因果决策；波动电价")
    a("")

    a("## 1 问题重述与符号说明")
    a("")
    a("微网由小区负荷、光伏发电、储能设备和外部电网构成。调度目标是在供电不低于负荷的前提下，利用光伏和储能减少正常购电及高价紧急购电。题目要求问题1给出典型日计划，问题2在全年负荷和光伏实际值变化下每天0:00制定计划，问题3加入日内多时刻光伏预报，问题4再考虑外部电价的逐日波动。")
    a("")
    a(r"本文符号约定如下：\(t=1,\ldots,144\)为10分钟时段，\(\Delta t=1/6\) h；\(L_t\)为负荷功率，\(P_t\)为光伏功率；\(q_t\)为计划购电量，\(u_t\)为紧急购电量，\(c_t,d_t\)分别为储能充电量和放电量，\(w_t\)为弃用余电，\(s_t\)为时段末储电量；\(p_t\)为交易时刻电价。")
    a("")
    a("SOC（荷电状态）通常表示储电量占额定容量的比例。为便于能量平衡计算，本文表格沿用程序命名，以kWh报告储电量；对应SOC百分比为储电量除以12000再乘100%。线性规划是目标函数和约束均为线性表达式的优化模型；因果决策是指决策只能依赖当时已经获得的信息。")
    a("")

    a("## 2 数据处理与信息边界")
    a("")
    a(r"附件1提供典型日的分时电价、负荷和光伏预测；附件2提供2025年1月1日至12月31日每个10分钟时段的负荷和光伏实际功率；附件3提供每日四个发布时间的未来24小时整点光伏预报；附件4提供逐日变化的10分钟电价。所有功率均先乘以\(\Delta t\)转换为电量后进入能量平衡。")
    a("")
    a("时间标签按区间终点解释：0:10代表0:00--0:10，0:00+1代表23:50--24:00。每行144点恰好覆盖一个自然日，按原顺序读取，不跨行搬移、不补造首段数据。输出Excel保留模板结构，但将计划时段表头修正为0:00--0:10至23:50--24:00；原始附件不改。10:00--10:10取源标签10:10，即数组索引60；每个4小时区间连续取24点。")
    a("")
    a("储能最大容量为12000 kWh，运行范围为1200--10800 kWh，最大充放电功率为5000 kW，充放电单程效率为0.9，2025年1月1日0:00初始储电量为6000 kWh。题目未给出上网电价，因此不向外售电，光伏余电只能充入储能或弃用。")
    a("")
    a("为避免未来信息泄漏，本文执行以下时间规则：")
    a("")
    a("1. 第d天0:00的日前计划只使用第d天以前已完成的负荷、光伏和价格历史，以及当前储电量。")
    a("2. 日内实际值仅用于该时段的供需兑现和时段末储电量递推，不进入该时段开始前的计划。时段内恒功率且忽略响应延迟的假设，使这一能量结算可解释为实时反馈的离散近似。")
    a("3. 问题3的6:00、12:00、18:00调整只使用对应发布时间已经获得的预报，并只修改尚未执行的时段。")
    a("4. 问题4的日前价格由截至决策时刻的历史同星期价格预测；日内调整保留这一价格预测，目标日实际价格仅用于费用结算。")
    a("5. 整个1月采用原固定预热策略：误差分位数0.80、窗口7天、保留比例0、期末价值0.60，使用加权同星期负荷和4日加权光伏预测。四种年度策略均从6000 kWh实际连续推进，2月1日均得到10800 kWh。正式模型的选型发生在已有全年历史比较之后，因此单次决策虽不读取未来实际值，整个研发选型不能称为只用一月或独立测试。")
    a("")
    a("基本假设：每个时段功率恒定；充电与放电效率各为90%；储能功率上限按交流侧计量；外网正常与紧急供电不设额外容量上限；无售电收入，无法消纳的剩余电量允许弃用；不计电池衰减和通信延迟。实时执行允许观测当前时段状态，这不等于在当天0:00知道未来实际数据。")
    a("")

    a("## 3 统一储能调度模型")
    a("")
    a("### 3.1 能量平衡")
    a("")
    a("在一个10分钟时段内，系统能量平衡为")
    a("")
    a("\\[")
    a("q_t+P_t\\Delta t+d_t+u_t=L_t\\Delta t+c_t+w_t.")
    a("\\]")
    a("")
    a(r"其中，\(w_t\ge0\)表示不能继续消纳的光伏或购电余量。问题2--4的执行阶段在实际净负荷超过计划购电和可用储能时产生\(u_t\)，其价格为\(5p_t\)。")
    a("")
    a("### 3.2 储能状态与约束")
    a("")
    a("储能状态递推为")
    a("")
    a("\\[")
    a("s_t=s_{t-1}+0.9c_t-d_t/0.9,")
    a("\\]")
    a("")
    a("并满足")
    a("")
    a("\\[")
    a("1200\\le s_t\\le10800,\\qquad 0\\le c_t,d_t\\le5000\\Delta t.")
    a("\\]")
    a("")
    a("模型允许弃电，因此同时充放电产生的额外能量损耗没有消纳优势。问题2--4在目标中加入微小的充放电惩罚以减少多解中的循环，实际执行规则按供需余量的正负只选择一个方向；不能仅凭效率小于1就替代充放电互斥检查。")
    a("")
    a("### 3.3 费用定义")
    a("")
    a("问题2的费用为")
    a("")
    a("\\[")
    a("C_2=\\sum_{d,t}p_tq_{d,t}+\\sum_{d,t}5p_tu_{d,t}.")
    a("\\]")
    a("")
    a(r"问题3和问题4-3中，令\(q^0_t\)为0:00计划，\(q^a_t\)为调整计划，增加和减少量分别为")
    a("")
    a("\\[")
    a("v_t^+=\\max(q_t^a-q_t^0,0),\\qquad v_t^-=\\max(q_t^0-q_t^a,0).")
    a("\\]")
    a("")
    a(r"按题面给出的结算规则，调整费用为\(1.5p_tv_t^++0.5p_tv_t^-\)，总费用为原计划正常费用、调整费用和紧急购电费用之和。")
    a("")

    a("## 4 问题1：典型日完全信息调度")
    a("")
    a(r"问题1中当天电价、负荷和光伏预测均已知，要求\(s_0=s_{144}=6000\) kWh。以正常购电费用最小为目标，建立线性规划并结合第3节约束求解。")
    a("")
    a("| 指标 | 结果 |")
    a("|---|---:|")
    a(f"| 全天负荷电量 | {f(q1['diagnostics']['load_kwh'])} kWh |")
    a(f"| 全天光伏电量 | {f(q1['diagnostics']['pv_kwh'])} kWh |")
    a(f"| 全天计划购电量 | {f(q1['table1_total_buy_kwh'])} kWh |")
    a(f"| 全天购电费 | {f(q1['table1_total_cost'])} 元 |")
    a(f"| 充电量 / 放电量 | {f(q1['diagnostics']['ch_kwh'])} / {f(q1['diagnostics']['dis_kwh'])} kWh |")
    a(f"| 储电量范围 | {q1['diagnostics']['soc_min']:.0f}--{q1['diagnostics']['soc_max']:.0f} kWh |")
    a("")
    a("按题目表1给出的六个指定10分钟时段，计划购电量如下：")
    a("")
    a("| 时间段 | 购电量/kWh | 时间段 | 购电量/kWh | 时间段 | 购电量/kWh |")
    a("|---|---:|---|---:|---|---:|")
    q1_slots = list(q1["table1"].items())
    a("| " + " | ".join(f"{label} | {float(value):.6f}" for label, value in q1_slots[:3]) + " |")
    a("| " + " | ".join(f"{label} | {float(value):.6f}" for label, value in q1_slots[3:]) + " |")
    a("")
    a("按题目表2汇总的储能充放电量如下：")
    a("")
    a("| 时间段 | 充电量/kWh | 放电量/kWh |")
    a("|---|---:|---:|")
    for label, values in q1["table2"].items():
        a(f"| {label} | {float(values['charge']):.6f} | {float(values['discharge']):.6f} |")
    a(f"| 0:00储电量 | {float(q1['soc0']):.6f} | |")
    a(f"| 24:00储电量 | {float(q1['soc24']):.6f} | |")
    a("")
    a("储能主要在低价时段充电、在高价时段放电，首末SOC相同。与不使用储能的基准相比，典型日节省费用约为" + f(q1['diagnostics']['savings_vs_baseline']) + "元。")
    a("")

    a("## 5 问题2：历史信息下的日前计划")
    a("")
    a("### 5.1 历史滚动预测")
    a("")
    a("负荷预测取最近4个相同星期的已完成日，采用普通均值并进行三点平滑；若同星期历史不足，则退化为已有历史的同一时段均值。光伏预测取最近21个已完成日，在每个10分钟位置拟合线性趋势并将预测负值截为0。记预测净需求为")
    a(r"具体地，对最近\(m\le21\)日、某时段的光伏样本\(y_j\)，令\(x_j=j\)，则\(\beta=\sum_j(x_j-\bar x)y_j/\sum_j(x_j-\bar x)^2\)，下一日预测为\(\widehat P=\max\{0,\bar y+\beta(m-\bar x)\}\)。三点平滑指相邻三个时段取均值，边界重复端点。")
    a("")
    a("\\[")
    a("\\widehat n_t=(\\widehat L_t-\\widehat P_t)\\Delta t.")
    a("\\]")
    a("")
    a("用最近7个已完成日的逐时段误差计算经验82.5%分位数，得到")
    a("")
    a("\\[")
    a("b_t=\\widehat n_t+Q_{0.825}(n_t-\\widehat n_t).")
    a("\\]")
    a("")
    a(r"负的\(b_t\)表示预测的光伏余电，不强行截断为0。")
    a("")
    a("分位数表示历史误差分布中不超过某个数值的样本比例，较高分位数用于兼顾多买电的成本和缺电时的高价补购。设单时段不考虑储能、净需求为随机变量N、正常购电量为q，则期望成本为")
    a("")
    a(r"\[ J(q)=pq+5p\,\mathbb{E}[(N-q)_+],\qquad (x)_+=\max(x,0). \]")
    a("")
    a(r"若N的分布函数F连续且最优解在q>0内部，\(J'(q)=p-5p[1-F(q)]=0\)，从而\(F(q)=0.8\)。实际采用0.825是结合储能耦合、预测偏差和离散滚动执行的历史折中，不能将单时段0.8推导当作完整模型的全局最优性证明。")
    a("")
    a("### 5.2 日前计划与日内执行")
    a("")
    a("每天0:00求解")
    a("")
    a("\\[")
    a("\\min\\sum_{t=1}^{144}p_tq_t-\\mu s_{144}+\\varepsilon\\sum_{t=1}^{144}(c_t+d_t),")
    a("\\]")
    a("")
    a(r"日前约束为\(q_t+d_t-c_t-w_t=b_t\)，加上储能递推、容量与功率边界，以及计划期末等式\(s_{144}=2400\) kWh。代码保留的\(-\mu s_{144}\)在此等式下是常数，不影响最优解，也不计入实际购电账单。\(\varepsilon=10^{-5}\)元/kWh为充放电正则项，即以微小成本抑制无意义的循环。2400仅约束计划轨迹，实际日末储电量不重置。")
    a("")
    a(r"正式参数为\(\alpha=0.825\)、误差窗口\(W=7\)天、SOC保留比例\(\rho=0.625\)、期末SOC价值\(\mu=0.30\)元/kWh。若计划购电超过实际净需求，先用余量充电；若不足，先放电再紧急购电。放电下限为")
    a("")
    a("\\[")
    a("R_t=1200+\\rho(s_t^{\\rm ref}-1200).")
    a("\\]")
    a("")
    a("每天末实际SOC传递到下一天，1月31日末状态传递到2月1日；本次重算得到2月1日0:00储电量为" + f(s2['state_at_report_start']) + " kWh。")
    a("")
    a(r"令\(z_t=q_t-(L_t-P_t)\Delta t\)为当前时段余量。若\(z_t\ge0\)，则\(c_t=\min\{z_t,5000\Delta t,(10800-s_{t-1})/0.9\}\)，\(w_t=z_t-c_t\)，\(d_t=u_t=0\)；若\(z_t<0\)，则\(d_t=\min\{-z_t,5000\Delta t,0.9(s_{t-1}-R_t)_+\}\)，\(u_t=-z_t-d_t\)，\(c_t=w_t=0\)。该反馈规则只需要当前观测及此前确定的储能参考轨迹。")
    a("")
    a("### 5.3 计算结果")
    a("")
    a("| 指标 | 2025-02-01 至 2025-12-31 |")
    a("|---|---:|")
    a(f"| 计划购电量 | {f(s2['plan_kwh'])} kWh |")
    a(f"| 紧急购电量 | {f(s2['emergency_kwh'])} kWh |")
    a(f"| 计划购电费 | {f(s2['plan_cost'])} 元 |")
    a(f"| 紧急购电费 | {f(s2['emergency_cost'])} 元 |")
    a(f"| 总购电费 | **{f(s2['total_cost'])} 元** |")
    a(f"| 2月1日0:00 SOC | {f(s2['state_at_report_start'])} kWh |")
    a(f"| 年末SOC | {f(s2['period_end_soc'])} kWh |")
    a("")
    a("### 5.4 基线对比与参数选择")
    a("")
    a("基线与正式策略使用相同的1月预热、2月1日初始SOC、历史预测和因果执行；仅取消2月1日以后日前计划中的预测误差分位数修正，并保留预测净需求的正负值。该对比用于检验误差修正模块的增量作用。")
    a("")
    a("| 方法 | 总费用/元 | 紧急购电量/kWh | 2月1日0:00 SOC/kWh |")
    a("|---|---:|---:|---:|")
    a(f"| 正式策略 | {f(s2['total_cost'])} | {f(s2['emergency_kwh'])} | {f(s2['state_at_report_start'])} |")
    a(f"| 无误差修正基线 | {f(baseline.get('total_cost', 0))} | {f(baseline.get('emergency_kwh', 0))} | {f(baseline.get('state_at_report_start', 0))} |")
    if baseline:
        saving = baseline['total_cost'] - s2['total_cost']
        a("")
        a(f"正式策略相对基线减少购电费用 {f(saving)} 元，且紧急购电量减少 {f(baseline['emergency_kwh'] - s2['emergency_kwh'])} kWh，说明历史误差分位数修正对当前数据具有实际增益。")
    a("")
    a("当前正式参数沿用既有历史候选实验中冻结的最低已评估配置；候选实验和全年结果均不能证明全局最优。表中若有历史候选记录，仅作为参数敏感性参考，不把同一评价期结果当作独立测试。")
    a("")
    a("| 策略 | 误差分位数 | 窗口/天 | 保留比例 | 计划日末储电量/kWh |")
    a("|---|---:|---:|---:|---:|")
    a(f"| 问题2 | {q2['parameters']['alpha']} | 7 | {q2['parameters']['reserve_ratio']} | 2400 |")
    a(f"| 问题3 | {q3['parameters']['alpha']} | 7 | {q3['parameters']['reserve_ratio']} | 2400 |")
    a("以下分块实验保留自旧模型，表中普通分位数为旧版参照而非本次新正式策略；只说明旧候选集的表现，不参与本次重新选参。")
    a("")
    rolling = experiments.get("rolling_validation", {})
    folds = rolling.get("folds", [])
    if folds:
        a("为检验近期加权分位数的跨时间表现，补充历史分块回放。每一折先在前一时间块选择方法，再在后一时间块评价；各候选共享固定基准策略产生的期初状态。方法设计发生在全年探索之后，因此这不是从未见过的独立测试；各块重新预热，也不是一条跨月连续部署的自适应轨迹。下表仅检验给定选参规则的历史迁移表现。")
        a("")
        a("| 选择期 | 测试期 | 选择方法 | 测试期正式普通分位数费用/元 | 选择方法费用/元 | 差额/元 |")
        a("|---|---|---|---:|---:|---:|")
        for fold in folds:
            selected = fold["selected_test"]["summary"]["total_cost"]
            official = fold["official_test"]["summary"]["total_cost"]
            method = "普通分位数" if fold["selected_method"] == "ordinary_quantile" else "加权分位数，衰减" + fold["selected_method"].rsplit("_", 1)[-1]
            a(
                f"| {fold['selection_period'].replace(' to ', '至')} | {fold['test_period'].replace(' to ', '至')} | {method} | "
                f"{f(official)} | {f(selected)} | {f(selected - official)} |"
            )
        selected_delta = sum(float(fold["selected_minus_official_cost"]) for fold in folds)
        a("")
        a(f"四个历史评价块中，按前块选择的方法相对同起始状态的普通分位数累计增加费用 {f(selected_delta)} 元。这是分块差额之和，不是全年连续策略费用。当前证据不支持替换正式方法，也不构成对所有近期加权方法的否定。")
        a("")
    adaptive_delta = float(adaptive_experiment.get("aggregate_selected_minus_official_cost", 0.0))
    adaptive_folds = adaptive_experiment.get("folds", [])
    if adaptive_folds:
        a(f"进一步比较分位数水平、历史窗口和近期权重，共{adaptive_experiment.get('candidate_count', 0)}种配置、{len(adaptive_folds)}个历史回放折。在2、4、6、8、10、12月六个评价块上，按前块选参累计增加费用 {f(adaptive_delta)} 元。该候选集的过去月份最优参数未能稳定迁移；正式参数不据此反向改动。这两项探索实验引用已有历史运行结果，本次没有重跑；此次问题2时间修正不改变原始数组顺序和费用计算，但历史输出标签不能沿用。")
        a("")

    a("## 6 问题3：多时刻光伏预报调整")
    a("")
    a("### 6.1 调整模型")
    a("")
    a(r"每天0:00利用附件3的0:00预报形成原计划\(q^0\)。6:00、12:00和18:00获得新预报后，只对尚未执行的区间重新求解线性规划，得到\(q^a\)。预报1小时表示发布时间之后第1个小时，采用相对发布时间的小时网格插值到10分钟时段。已执行时段的购电量和SOC不回溯修改。")
    a("插值在区间终点计算，由发布时刻已观测光伏连接到预报+1小时、+2小时等节点，不跨日旋转；0:00锚点取前一日最后观测，6:00锚点取5:50--6:00观测。负荷沿用问题2的同星期均值预测，光伏由附件3已发布预报与21日历史趋势各占0.5融合。每个发布时刻分别使用过去7日同发布时刻的净需求误差作0.70分位数修正，执行保留比例为0.625。")
    a(r"\[\widehat P_{d,t}^{(h)}=0.5\,\widehat P_{d,t}^{\rm issued(h)}+0.5\,\widehat P_{d,t}^{\rm trend},\quad b_{d,t}^{(h)}=(\widehat L_{d,t}-\widehat P_{d,t}^{(h)})\Delta t+Q_{0.70}\{n_{j,t}-\widehat n_{j,t}^{(h)}:d-7\le j<d\}.\]")
    a("6:00、12:00、18:00调整分别从索引36、72、108开始。日前LP不允许计划性紧急购电；修订LP中的紧急变量仅为预测缺口的代理量，真实紧急费用由实际执行重新核算。")
    a("")
    a("### 6.2 计算结果")
    a("")
    a("| 指标 | 2025-02-01 至 2025-12-31 |")
    a("|---|---:|")
    a(f"| 原计划购电量 | {f(s3['plan_kwh'])} kWh |")
    a(f"| 调整后购电量 | {f(s3['adjusted_plan_kwh'])} kWh |")
    a(f"| 增加计划量 | {f(s3['adjustment_up_kwh'])} kWh |")
    a(f"| 减少计划量 | {f(s3['adjustment_down_kwh'])} kWh |")
    a(f"| 原计划费用 | {f(s3['plan_cost'])} 元 |")
    a(f"| 调整费用 | {f(s3['adjustment_cost'])} 元 |")
    a(f"| 紧急购电费用 | {f(s3['emergency_cost'])} 元 |")
    a(f"| 总费用 | **{f(s3['total_cost'])} 元** |")
    a("")
    a("在当前结算规则下，调整计划增加了正常购电量和调整费用，因此总费用不必低于问题2。题目只给出四个预报发布时间，本文采用全部可用预报，不虚构额外时刻。")
    a("题目中其他时刻的预报指6:00、12:00和18:00相对于0:00的新增预报。每个调整时刻均与同一状态下的无调整LP比较，仅当代理目标改善且当前6小时提交块存在正的上调量时才接受调整；代理规划可覆盖当日剩余时段，但只提交下一段6小时，未来块的补购在后续发布时间重新确认。问题2与问题3的日前预测本身不同，不能把两问总费用差全部归因于日内预报。")
    a("代理目标指使用当前预测计算的规划成本，并非实际发生费用；其改善不能保证每次实际调整都省钱。在原计划全额支付、下调另付0.5倍费用且弃电免费的解释下，下调被保留原购电并弃用余电所支配，因此只优化上调。")
    no_update_cost = float(q3_ablation["none"]["total_cost"])
    a("")
    a("| 同条件问题3对照 | 总费用/元 | 紧急购电量/kWh |")
    a("|---|---:|---:|")
    a(f"| 无日内调整 | {f(no_update_cost)} | {f(float(q3_ablation['none']['emergency_kwh']))} |")
    a(f"| 三个时刻允许调整 | {f(s3['total_cost'])} | {f(s3['emergency_kwh'])} |")
    a(f"共享10800 kWh初态、融合预测和参数的历史对照减少费用{f(no_update_cost-s3['total_cost'])}元。这是允许调整和使用相应新预报的联合收益，不是预报信息本身的独立贡献，也不是逐次收益保证。")
    a("")
    a("对每个调整时刻，只保留尚未执行的时段。令当前储能状态为\\(s_{t-1}\\)，当前时刻之后的预测负荷和光伏电量为\\(\\widehat L_i,\\widehat P_i\\)，则调整问题的供需约束为")
    a("")
    a("\\[")
    a("q_i+u_i+d_i+\\widehat P_i=\\widehat L_i+c_i+w_i,\\qquad i=t,\\ldots,144.")
    a("\\]")
    a("")
    a("调整量通过")
    a("")
    a("\\[")
    a("q_i-q_i^0=v_i^+-v_i^-,\\qquad v_i^+,v_i^-\\ge0")
    a("\\]")
    a("表示。由于已执行区间不再重算，调整不会改变历史购电量、历史储能状态或已经发生的紧急购电。")
    a(r"此处预测功率先转换为kWh，风险修正并入净需求\(b_i^{(h)}\)。日前LP最小化\(\sum_i\widehat p_iq_i+\varepsilon\sum_i(c_i+d_i)\)；修订LP最小化\(\sum_{i=t}^{144}\widehat p_i(1.5v_i^++5u_i)+\varepsilon\sum_{i=t}^{144}(c_i+d_i)\)，约束\(q_i^0+v_i^++u_i+d_i-c_i-w_i=b_i^{(h)}\)。两阶段均加计划日末\(s_{144}=2400\)，\(\varepsilon=10^{-7}\)。未来允许更新的块可以规划代理补购，但仅将本次6小时的增量计入最终调整量，避免重复结算。")
    a("")

    a("## 7 问题4：波动电价下的重算")
    a("")
    a("每天0:00的计划价格由截至当天以前、同星期的最多4个历史价格日加权预测；当天真实价格只在对应交易时刻用于结算和当前时段执行。问题4-2沿用问题2的历史负荷和光伏预测及因果执行，问题4-3沿用问题3的光伏预报调整机制。")
    a("")
    a("| 情形 | 计划购电量/kWh | 调整后购电量/kWh | 紧急购电量/kWh | 总费用/元 |")
    a("|---|---:|---:|---:|---:|")
    a(f"| 问题4-2 | {f(s42['plan_kwh'])} | - | {f(s42['emergency_kwh'])} | **{f(s42['total_cost'])}** |")
    a(f"| 问题4-3 | {f(s43['plan_kwh'])} | {f(s43['adjusted_plan_kwh'])} | {f(s43['emergency_kwh'])} | **{f(s43['total_cost'])}** |")
    a("")
    a("问题4-2直接将问题2的固定价格替换为附件4的逐日价格，并在日前仅依据历史价格预测；问题4-3同时使用逐日价格预测和问题3的光伏滚动预报。实际费用均用当日真实价格结算，因而不把事后价格当作日前信息。")
    a("")
    a("对问题4-2，日前价格预测为")
    a("")
    a("\\[")
    a("\\widehat p_{d,t}=\\frac{\\sum_{j=1}^{m}j p_{d_j,t}}{\\sum_{j=1}^{m}j},\\qquad d_j<d,\\quad m\\le4.")
    a("\\]")
    a("")

    a("## 8 综合比较、误差分析与局限性")
    a("")
    a("### 8.1 全年结果对比")
    a("")
    a(f"![各策略日末储电量轨迹]({(FIGURES / 'soc_curves.svg').as_posix()})")
    a("")
    a(f"![年度购电费用构成对比]({(FIGURES / 'cost_comparison.svg').as_posix()})")
    a("")
    a("| 情形 | 总费用/元 | 紧急购电量/kWh | 年末SOC/kWh |")
    a("|---|---:|---:|---:|")
    a(f"| 问题2 | {f(s2['total_cost'])} | {f(s2['emergency_kwh'])} | {f(s2['period_end_soc'])} |")
    a(f"| 问题3 | {f(s3['total_cost'])} | {f(s3['emergency_kwh'])} | {f(s3['year_end_soc'])} |")
    a(f"| 问题4-2 | {f(s42['total_cost'])} | {f(s42['emergency_kwh'])} | {f(s42['year_end_soc'])} |")
    a(f"| 问题4-3 | {f(s43['total_cost'])} | {f(s43['emergency_kwh'])} | {f(s43['year_end_soc'])} |")
    a("")
    a("问题1为单日完全信息基准，不与全年费用直接相加比较。当前重算中问题3的总费用低于问题2，但两问同时改变了预测方式和结算机制，不能把差额全部归因于日内预报；问题4说明波动价格会改变储能在各时段的套利价值。")
    a("")
    out.extend(specified_summary(d2, "### 8.1.1 四个指定日期汇总：问题2"))
    out.extend(specified_summary(d3, "### 8.1.2 四个指定日期汇总：问题3", True))
    out.extend(specified_summary(d42, "### 8.1.3 四个指定日期汇总：问题4-2"))
    out.extend(specified_summary(d43, "### 8.1.4 四个指定日期汇总：问题4-3", True))
    a("### 8.2 数值与因果性校验")
    a("")
    a("问题2、问题3、问题4-2和问题4-3均覆盖334天、48096个10分钟时段。复核从当前完整轨迹重新计算能量平衡、储能递推、容量与功率边界、充放电互斥、费用和跨日连续性，不将程序退出成功等同于模型正确。时间边界与产物核对结果分别记录在causal_time_audit.json和artifact_audit.json。")
    a("")
    a("问题2的时间审计实际采用扰动测试：更改目标日及以后的实测值，检查日前输入不变；更改某日未来时段的实测值，检查此前已执行的动作和SOC轨迹不变。问题3和问题4则通过代码中的发布时间索引、只重算未执行区间以及独立物理校验进行复核；尚未对这两问分别运行同等的随机扰动测试，因此不将其表述为已完成的形式化因果证明。")
    a("")
    a("### 8.3 误差分析")
    a("")
    a("本文将误差分为预测误差、执行误差和结算误差。预测误差来自历史样本对负荷、光伏和价格的估计；执行误差来自日前计划与实际负荷、光伏之间的偏差；结算误差来自问题3的调整价格和问题2的5倍紧急购电价格。严格单因素基线显示，取消误差分位数修正后，紧急购电量从" + f(s2['emergency_kwh']) + " kWh增加到" + f(baseline.get('emergency_kwh', 0.0)) + " kWh，总费用增加" + f(baseline.get('total_cost', 0.0) - s2['total_cost']) + " 元。")
    a("")
    a("源时间轴、指定时段及六个4小时分组统一按终点口径核对。数值计算误差与预测偏差必须分开：能量平衡成立只能说明执行物理可行，不表示负荷、光伏和价格预测准确。预测样本有限、小时预报插值、忽略响应延迟以及调整结算规则解释仍是主要不确定性。")
    a("")
    a("### 8.4 算法流程与可复现性")
    a("")
    a("问题2--4均按以下顺序运行：")
    a("")
    a("1. 读取决策时刻以前已经完成的历史数据，生成负荷、光伏和必要时的价格预测。")
    a("2. 将功率预测转换为10分钟电量，建立含能量平衡、储能状态和功率边界的线性规划。")
    a("3. 固定当前决策时刻前的结果，只执行当前及之后的计划；当前时段到来后才读取实际负荷和光伏。")
    a("4. 实际缺口由储能按保留SOC规则补足，仍不足的部分记为紧急购电；供需余量优先充电，剩余记为弃电。")
    a("5. 将日末实际储电量传递给下一天，并在问题3的6:00、12:00、18:00重新优化尚未执行的区间。")
    a("")
    a("全部报告期为2025年2月1日至12月31日，共334天、48096个10分钟时段。1月用于固定策略连续预热和历史样本积累。冻结配置后各决策只读取当时可用信息，但研发选型已接触全年数据，所报下降是历史回放增益，不是独立测试的泛化保证。结果保留计算精度，论文表格按可读性四舍五入。")
    a("")
    a("### 8.5 模型局限性")
    a("")
    a("正式参数沿用既有历史候选实验，历史样本有限且候选实验存在评价口径限制；问题3的调整结算按题面字面解释，若官方对结算基数有更细定义，应替换相应费用公式；模型未考虑设备老化、通信延迟、预报失效和启停成本。后续算法比较必须使用独立时间切分，不能用2至12月测试结果反向调参。")
    a("")

    a("## 9 结论")
    a("")
    a("本文建立了从典型日确定性调度到全年因果滚动调度的统一模型。问题1验证了储能峰谷搬移的经济作用；问题2通过历史预测和误差分位数修正完成了无未来信息的全年计划；问题3利用四个可用发布时间进行滚动调整；问题4说明波动电价下需要重新预测价格并重新优化储能。")
    a("")
    a("本文已给出四问模型、当前结果、问题1指定时段表及问题2--4指定日期明细，时间口径统一为区间终点。问题2保留共享1月预热状态和仅取消误差修正的公平基线；问题3采用同状态无调整LP门控和下一段6小时提交规则。参数来自既有历史候选实验，结果可作为当前计算初稿，但不构成全局最优性证明。")
    a("")
    a("## 参考资料")
    a("")
    a("[1] 2026年高教社杯全国大学生数学建模竞赛C题《微网与外部电网电力调控策略》。")
    a("[2] 题目附件1--附件5：典型日数据、全年实际数据、光伏预报、波动电价及结果模板。")
    a("")
    a("## 附件与复核文件")
    a("")
    a("`result1.xlsx`、`result2.xlsx`、`result3.xlsx`、`result4-2.xlsx`和`result4-3.xlsx`分别保存五类完整策略；对应JSON文件保存汇总和校验结果；图表文件位于`figures/`。")
    a("")
    out.extend(q2_appendix(d2))
    out.extend(q34_appendix(d3, "## 附录B 问题3指定日期明细", True))
    out.extend(q34_appendix(d42, "## 附录C 问题4-2指定日期明细", False))
    out.extend(q34_appendix(d43, "## 附录D 问题4-3指定日期明细", True))
    rendered = "\n".join(out)
    for command in ("(", ")", "widehat", "times"):
        rendered = rendered.replace("\\\\" + command, "\\" + command)
    (ROOT / "论文初稿.md").write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

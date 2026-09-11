from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FIGURES = ROOT / "figures"
FIGURES.mkdir(exist_ok=True)


def load(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def esc(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def line_chart(series: list[tuple[str, list[float], str]], output: Path) -> None:
    width, height = 1200, 560
    left, right, top, bottom = 90, 35, 55, 70
    plot_w, plot_h = width - left - right, height - top - bottom
    all_values = [v for _, values, _ in series for v in values]
    low = 0.0
    high = max(12000.0, max(all_values) * 1.05)
    def x(i: int, n: int) -> float:
        return left + plot_w * i / max(n - 1, 1)
    def y(value: float) -> float:
        return top + plot_h * (high - value) / (high - low)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<style>text{font-family:"Noto Sans CJK SC","Microsoft YaHei",sans-serif;fill:#253238} .axis{stroke:#607d8b;stroke-width:1} .grid{stroke:#d7dee2;stroke-width:1} .legend{font-size:16px} .label{font-size:14px}</style>',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="90" y="30" font-size="22" font-weight="bold">各策略日末储电量轨迹</text>',
    ]
    for tick in range(0, 12001, 2000):
        yy = y(tick)
        parts.append(f'<line class="grid" x1="{left}" y1="{yy:.1f}" x2="{width-right}" y2="{yy:.1f}"/>')
        parts.append(f'<text class="label" x="{left-12}" y="{yy+5:.1f}" text-anchor="end">{tick:,}</text>')
    parts.append(f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}"/>')
    parts.append(f'<line class="axis" x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}"/>')
    for index, (label, values, color) in enumerate(series):
        points = " ".join(f"{x(i, len(values)):.1f},{y(v):.1f}" for i, v in enumerate(values))
        parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2" opacity="0.9"/>')
        lx = left + index * 245
        parts.append(f'<line x1="{lx}" y1="{height-48}" x2="{lx+28}" y2="{height-48}" stroke="{color}" stroke-width="3"/>')
        parts.append(f'<text class="legend" x="{lx+36}" y="{height-42}">{esc(label)}</text>')
    parts.append('<text class="label" x="600" y="550" text-anchor="middle">2025年2月1日至12月31日（按日连接）</text>')
    parts.append('</svg>')
    output.write_text("\n".join(parts), encoding="utf-8")


def cost_chart(summaries: list[tuple[str, dict, str]], output: Path) -> None:
    width, height = 1200, 560
    left, right, top, bottom = 90, 40, 55, 95
    plot_w, plot_h = width - left - right, height - top - bottom
    max_cost = max(s[1]["total_cost"] for s in summaries) * 1.12
    bar_w = 140
    gap = (plot_w - len(summaries) * bar_w) / (len(summaries) + 1)
    colors = {"plan": "#1976d2", "adjust": "#f9a825", "emergency": "#d32f2f"}
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<style>text{font-family:"Noto Sans CJK SC","Microsoft YaHei",sans-serif;fill:#253238} .axis{stroke:#607d8b;stroke-width:1} .grid{stroke:#d7dee2;stroke-width:1} .label{font-size:14px}</style>',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="90" y="30" font-size="22" font-weight="bold">年度购电费用构成对比</text>',
    ]
    for tick in range(0, 16000001, 2000000):
        yy = top + plot_h * (max_cost - tick) / max_cost
        parts.append(f'<line class="grid" x1="{left}" y1="{yy:.1f}" x2="{width-right}" y2="{yy:.1f}"/>')
        parts.append(f'<text class="label" x="{left-12}" y="{yy+5:.1f}" text-anchor="end">{tick/1e6:.0f}M</text>')
    parts.append(f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}"/>')
    parts.append(f'<line class="axis" x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}"/>')
    for i, (label, summary, _) in enumerate(summaries):
        x0 = left + gap * (i + 1) + bar_w * i
        segments = [("plan", summary["plan_cost"]), ("adjust", summary.get("adjustment_cost", 0.0)), ("emergency", summary["emergency_cost"])]
        current = height - bottom
        for key, value in segments:
            h = plot_h * value / max_cost
            current -= h
            if h > 0:
                parts.append(f'<rect x="{x0:.1f}" y="{current:.1f}" width="{bar_w}" height="{h:.1f}" fill="{colors[key]}"/>')
        parts.append(f'<text class="label" x="{x0+bar_w/2:.1f}" y="{height-bottom+22}" text-anchor="middle">{esc(label)}</text>')
        parts.append(f'<text class="label" x="{x0+bar_w/2:.1f}" y="{current-8:.1f}" text-anchor="middle">{summary["total_cost"]/1e6:.2f}M</text>')
    legend = [("计划购电", colors["plan"]), ("调整费用", colors["adjust"]), ("紧急购电", colors["emergency"])]
    for i, (label, color) in enumerate(legend):
        lx = 120 + i * 220
        parts.append(f'<rect x="{lx}" y="{height-55}" width="18" height="18" fill="{color}"/>')
        parts.append(f'<text class="label" x="{lx+27}" y="{height-40}">{label}</text>')
    parts.append('</svg>')
    output.write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    q2 = load("q2_rebuild_data.json")
    q3 = load("q3_rebuild_data.json")
    q42 = load("q4_2_rebuild_data.json")
    q43 = load("q4_3_rebuild_data.json")
    line_chart(
        [
            ("问题2", [r["soc24"] for r in q2["records"]], "#1565c0"),
            ("问题3", [r["soc24"] for r in q3["records"]], "#2e7d32"),
            ("问题4-2", [r["soc24"] for r in q42["records"]], "#ef6c00"),
            ("问题4-3", [r["soc24"] for r in q43["records"]], "#8e24aa"),
        ],
        FIGURES / "soc_curves.svg",
    )
    cost_chart(
        [("问题2", q2["summary"], "#1565c0"), ("问题3", q3["summary"], "#2e7d32"), ("问题4-2", q42["summary"], "#ef6c00"), ("问题4-3", q43["summary"], "#8e24aa")],
        FIGURES / "cost_comparison.svg",
    )


if __name__ == "__main__":
    main()

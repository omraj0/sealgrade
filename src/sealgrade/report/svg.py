"""An SVG heat map of the proof matrix (attacks x tiers), generated from the matrix JSON."""

from __future__ import annotations

from typing import Any
from xml.sax.saxutils import escape

TIER_LABELS = {"t0": "T0 naive", "t1": "T1 typical", "t2": "T2 compat", "t3": "T3 strict"}
COLOURS = {
    "exploit": ("#3a1618", "#ff7b72", "EXPLOIT"),
    "blocked": ("#10281d", "#3ddc97", "blocked"),
    "partial": ("#33260f", "#ffb454", "PARTIAL"),
    None: ("#161d26", "#7d8fa0", "-"),
}

NAME_WIDTH = 292
CELL_WIDTH = 104
ROW_HEIGHT = 22
HEADER_HEIGHT = 64
FOOTER_HEIGHT = 58
PAD = 18


def matrix_svg(data: dict[str, Any]) -> str:
    """Render the dict produced by ``MatrixResult.to_json`` as a standalone SVG document."""
    tiers: list[str] = data["tiers"]
    attacks: list[dict[str, Any]] = data["attacks"]
    width = PAD * 2 + NAME_WIDTH + CELL_WIDTH * len(tiers)
    height = HEADER_HEIGHT + ROW_HEIGHT * len(attacks) + FOOTER_HEIGHT + PAD
    out: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        'aria-label="SealGrade proof matrix: which attacks work on which harness tier">',
        "<style>"
        "text{font-family:ui-monospace,SFMono-Regular,Consolas,Menlo,monospace;fill:#d6e2ee}"
        ".t{font-size:15px;font-weight:700}.s{font-size:11px;fill:#7d8fa0}"
        ".h{font-size:12px;font-weight:700;text-anchor:middle}.n{font-size:12px}"
        ".c{font-size:11px;font-weight:700;text-anchor:middle}"
        ".f{font-size:12px;font-weight:700;text-anchor:middle}"
        "</style>",
        f'<rect width="{width}" height="{height}" rx="14" fill="#0b0f14"/>',
        f'<text class="t" x="{PAD}" y="26">SealGrade proof matrix</text>',
        f'<text class="s" x="{PAD}" y="45">each attack is a submission that does NOT solve the task; '
        "if the verdict says pass, the exploit worked</text>",
    ]
    for column, tier in enumerate(tiers):
        x = PAD + NAME_WIDTH + column * CELL_WIDTH + CELL_WIDTH / 2
        out.append(
            f'<text class="h" x="{x}" y="{HEADER_HEIGHT - 8}">{escape(TIER_LABELS.get(tier, tier))}</text>'
        )
    for row, attack in enumerate(attacks):
        y = HEADER_HEIGHT + row * ROW_HEIGHT
        if row % 2:
            out.append(
                f'<rect x="{PAD}" y="{y}" width="{width - 2 * PAD}" height="{ROW_HEIGHT}" fill="#0e141b"/>'
            )
        out.append(f'<text class="n" x="{PAD + 6}" y="{y + 15}">{escape(attack["id"])}</text>')
        for column, tier in enumerate(tiers):
            observed = attack["observed"].get(tier)
            fill, ink, label = COLOURS.get(observed, COLOURS[None])
            x = PAD + NAME_WIDTH + column * CELL_WIDTH
            out.append(
                f'<rect x="{x + 4}" y="{y + 3}" width="{CELL_WIDTH - 8}" height="{ROW_HEIGHT - 6}" '
                f'rx="4" fill="{fill}"/>'
                f'<text class="c" x="{x + CELL_WIDTH / 2}" y="{y + 15}" style="fill:{ink}">{label}</text>'
            )
    footer_y = HEADER_HEIGHT + ROW_HEIGHT * len(attacks) + 22
    out.append(f'<text class="n" x="{PAD + 6}" y="{footer_y}">exploits that worked</text>')
    counts = data.get("exploit_counts", {})
    for column, tier in enumerate(tiers):
        info = counts.get(tier, {})
        x = PAD + NAME_WIDTH + column * CELL_WIDTH + CELL_WIDTH / 2
        colour = "#3ddc97" if info.get("exploited", 0) == 0 else "#ff7b72"
        out.append(
            f'<text class="f" x="{x}" y="{footer_y}" style="fill:{colour}">'
            f"{info.get('exploited', 0)} / {info.get('measured', 0)}</text>"
        )
    latency = data.get("mean_latency_sec", {})
    if latency:
        out.append(
            f'<text class="s" x="{PAD + 6}" y="{footer_y + 20}">mean seconds per run (parallel)</text>'
        )
        for column, tier in enumerate(tiers):
            x = PAD + NAME_WIDTH + column * CELL_WIDTH + CELL_WIDTH / 2
            out.append(
                f'<text class="s" x="{x}" y="{footer_y + 20}" text-anchor="middle">{latency.get(tier, 0)}</text>'
            )
    out.append("</svg>")
    return "\n".join(out) + "\n"

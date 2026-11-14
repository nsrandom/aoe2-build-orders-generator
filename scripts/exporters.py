#!/usr/bin/env python3
"""
HTML & RTS Overlay JSON Exporters for AoE2:DE Build Orders.

Generates:
1. A rich standalone HTML document with top-level Tab Views for each build order
   variant, containing the Villager-by-Villager timeline table, Age-Up Transition
   Reallocations, Steady-State Production target, and Rot/Wood-Efficiency telemetry.
2. An RTS Overlay compatible JSON file matching the `AoE Overlay` / `RTS_Overlay`
   schema (`name`, `civilization`, `author`, `source`, `description`, `build_order`).
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

# Standard RTS Overlay / AoE Overlay inline icon tags
RTS_ICONS: Dict[str, str] = {
    "villager": "@resource/MaleVillDE.jpg@",
    "sheep": "@animal/Sheep_aoe2DE.png@",
    "boar": "@animal/Boar_aoe2DE.png@",
    "deer": "@animal/Deer_aoe2DE.png@",
    "berries": "@resource/BerryBushDE.png@",
    "wood": "@resource/Aoe2de_wood.png@",
    "food": "@resource/Aoe2de_food.png@",
    "gold": "@resource/Aoe2de_gold.png@",
    "stone": "@resource/Aoe2de_stone.png@",
    "build": "@resource/Aoe2de_hammer.png@",
    "farm": "@mill/FarmDE.png@",
    "loom": "@town_center/LoomDE.png@",
    "wheelbarrow": "@town_center/WheelbarrowDE.png@",
    "feudal_age": "@age/FeudalAgeIconDE_alpha.png@",
    "castle_age": "@age/CastleAgeIconDE_alpha.png@",
    "imperial_age": "@age/ImperialAgeIconDE_alpha.png@",
    "barracks": "@barracks/Barracks_aoe2DE.png@",
    "archery_range": "@archery_range/Archery_range_aoe2DE.png@",
    "stable": "@stable/Stable_aoe2DE.png@",
    "blacksmith": "@blacksmith/Blacksmith_aoe2de.png@",
    "siege_workshop": "@siege_workshop/Siege_workshop_aoe2DE.png@",
    "lumber_camp": "@lumber_camp/Lumber_camp_aoe2de.png@",
    "mining_camp": "@mining_camp/Mining_camp_aoe2de.png@",
    "mill": "@mill/Mill_aoe2de.png@",
    "market": "@market/Market_aoe2DE.png@",
    "castle": "@castle/Castle_aoe2DE.png@",
    "double_bit_axe": "@lumber_camp/DoubleBitAxe_aoe2DE.png@",
    "bow_saw": "@lumber_camp/BowSaw_aoe2DE.png@",
    "horse_collar": "@mill/HorseCollar_aoe2DE.png@",
}


@dataclass
class DetailedBuildRow:
    pop: str  # e.g. "4 (3v)" or "20v" or "Transition"
    timestamp: str  # e.g. "00:25"
    age: str  # "Dark Age", "Feudal Transit", "Feudal Age", "Castle Transit", "Castle Age"
    action: str
    food_vils: int
    wood_vils: int
    gold_vils: int
    stone_vils: int
    bank_food: float
    bank_wood: float
    bank_gold: float
    bank_stone: float
    notes: str = ""
    sheep_vils: int = 0
    boar_vils: int = 0
    deer_vils: int = 0
    chicken_vils: int = 0
    berry_vils: int = 0
    farm_vils: int = 0


@dataclass
class RTSOverlayStep:
    villager_count: int
    age: int
    wood: int
    food: int
    gold: int
    stone: int
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "villager_count": self.villager_count,
            "age": self.age,
            "resources": {
                "wood": self.wood,
                "food": self.food,
                "gold": self.gold,
                "stone": self.stone,
            },
            "notes": self.notes,
        }


@dataclass
class BuildOrderDocument:
    name: str
    civilization: str
    variant_label: str  # e.g. "3 Deer Pushed (20 Pop)"
    description: str
    rows: List[DetailedBuildRow]
    rts_steps: List[RTSOverlayStep]
    steady_state_summary: Dict[str, object] = field(default_factory=dict)
    telemetry_summary: Dict[str, object] = field(default_factory=dict)
    author: str = "AoE2 Build Order Generator"
    source: str = "rules.md"


def export_rts_overlay_json(doc: BuildOrderDocument, output_path: Path) -> Path:
    """Writes an RTS Overlay compatible JSON file and validates its structure."""
    payload = {
        "name": f"{doc.name} ({doc.variant_label})",
        "civilization": doc.civilization,
        "author": doc.author,
        "source": doc.source,
        "description": doc.description,
        "build_order": [step.to_dict() for step in doc.rts_steps],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4)
    return output_path


def export_build_order_html(
    docs: List[BuildOrderDocument], title: str, output_path: Path
) -> Path:
    """Writes a standalone HTML report with top-level Tab Views for each build order variant."""
    tab_buttons_html = []
    tab_panels_html = []

    for idx, doc in enumerate(docs):
        active_cls = " active" if idx == 0 else ""
        tab_id = f"tab-{idx}"
        tab_buttons_html.append(
            f'<button class="tab-btn{active_cls}" onclick="switchTab(\'{tab_id}\', this)">'
            f'{html.escape(doc.variant_label)}'
            f"</button>"
        )

        def fmt_sub(val: int) -> str:
            return f'<strong>{val}</strong>' if val > 0 else '<span class="zero">-</span>'

        # Group contiguous rows by phase (`r.age`) into separate sections
        phase_groups: List[Tuple[str, List[DetailedBuildRow]]] = []
        for r in doc.rows:
            if not phase_groups or phase_groups[-1][0] != r.age:
                phase_groups.append((r.age, [r]))
            else:
                phase_groups[-1][1].append(r)

        phase_sections_html = []
        for phase_name, phase_rows in phase_groups:
            rows_html = []
            for r in phase_rows:
                deer_or_chk = r.deer_vils if r.deer_vils > 0 else r.chicken_vils
                rows_html.append(
                    f"""
                    <tr>
                        <td class="mono center">{html.escape(r.pop)}</td>
                        <td class="mono center">{html.escape(r.timestamp)}</td>
                        <td>{html.escape(r.action)}</td>
                        <td class="mono center res-f-sub">{fmt_sub(r.sheep_vils)}</td>
                        <td class="mono center res-f-sub">{fmt_sub(r.boar_vils)}</td>
                        <td class="mono center res-f-sub">{fmt_sub(deer_or_chk)}</td>
                        <td class="mono center res-f-sub">{fmt_sub(r.berry_vils)}</td>
                        <td class="mono center res-f-sub">{fmt_sub(r.farm_vils)}</td>
                        <td class="mono center res-f">{r.food_vils}</td>
                        <td class="mono center res-w">{r.wood_vils}</td>
                        <td class="mono center res-g">{r.gold_vils}</td>
                        <td class="mono center res-s">{r.stone_vils}</td>
                        <td class="mono center">{r.bank_food:.0f}F / {r.bank_wood:.0f}W / {r.bank_gold:.0f}G / {r.bank_stone:.0f}S</td>
                        <td class="notes">{html.escape(r.notes)}</td>
                    </tr>
                    """
                )
            start_ts = phase_rows[0].timestamp
            end_ts = phase_rows[-1].timestamp
            phase_sections_html.append(
                f"""
                <div class="phase-block">
                    <h3 class="phase-title">
                        <span class="badge phase-badge">{html.escape(phase_name)}</span>
                        <span class="phase-range mono">{html.escape(start_ts)} &rarr; {html.escape(end_ts)}</span>
                    </h3>
                    <div class="table-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th rowspan="2" class="center">Pop / Vils</th>
                                    <th rowspan="2" class="center">Time</th>
                                    <th rowspan="2">Villager Assignment / Action</th>
                                    <th colspan="6" class="center food-group-hdr">Food Villagers Breakdown</th>
                                    <th rowspan="2" class="center">Wood</th>
                                    <th rowspan="2" class="center">Gold</th>
                                    <th rowspan="2" class="center">Stone</th>
                                    <th rowspan="2" class="center">Resource Bank</th>
                                    <th rowspan="2">Notes &amp; Buildings</th>
                                </tr>
                                <tr>
                                    <th class="center sub-hdr">Sheep</th>
                                    <th class="center sub-hdr">Boar</th>
                                    <th class="center sub-hdr">Deer/Chk</th>
                                    <th class="center sub-hdr">Berries</th>
                                    <th class="center sub-hdr">Farms</th>
                                    <th class="center sub-hdr">Total F</th>
                                </tr>
                            </thead>
                            <tbody>
                                {''.join(rows_html)}
                            </tbody>
                        </table>
                    </div>
                </div>
                """
            )

        ss_html = ""
        if doc.steady_state_summary:
            rec = doc.steady_state_summary.get("recommended_vils", {})
            ex = doc.steady_state_summary.get("exact_vils", {})
            rot_info = doc.telemetry_summary.get("rotted_food", {})
            tot_rot = doc.telemetry_summary.get("total_rotted_food", 0)
            rot_str = (
                f"Sheep: {rot_info.get('sheep', 0)}F &middot; "
                f"Boar: {rot_info.get('boar', 0)}F &middot; "
                f"Deer: {rot_info.get('deer', 0)}F &middot; "
                f"Chicken: {rot_info.get('chicken', 0)}F "
                f"(Total Rot: <strong>{tot_rot}F</strong>)"
                if rot_info
                else ""
            )
            ss_html = f"""
            <div class="summary-card">
                <h4>Steady-State Continuous Production Target (1 TC Vils + 1 Range Archers + Farm Reseed)</h4>
                <p>
                    <strong>Recommended Minimum Villagers:</strong>
                    <span class="res-f">{rec.get('food', 0)} Food</span> &middot;
                    <span class="res-w">{rec.get('wood', 0)} Wood</span> &middot;
                    <span class="res-g">{rec.get('gold', 0)} Gold</span> &middot;
                    <span class="res-s">{rec.get('stone', 0)} Stone</span>
                    (Total: <strong>{rec.get('total', 0)}</strong> vils; exact: {ex.get('food', 0)}F / {ex.get('wood', 0)}W / {ex.get('gold', 0)}G / {ex.get('stone', 0)}S)
                </p>
                {f'<p style="margin-top:6px;"><strong>Simulated Animal Rot Telemetry:</strong> {rot_str}</p>' if rot_str else ''}
            </div>
            """

        tab_panels_html.append(
            f"""
            <section id="{tab_id}" class="variant-section tab-panel{active_cls}">
                <h2>{html.escape(doc.name)} &mdash; <span class="variant-tag">{html.escape(doc.variant_label)}</span></h2>
                <p class="desc">{html.escape(doc.description)}</p>
                {ss_html}
                {''.join(phase_sections_html)}
            </section>
            """
        )

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)}</title>
    <style>
        :root {{
            --bg: #0f141c;
            --card: #18202c;
            --border: #2a3546;
            --text: #e6edf3;
            --muted: #9aa7b8;
            --accent: #eab308;
            --food: #f87171;
            --wood: #a3e635;
            --gold: #facc15;
            --stone: #94a3b8;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 24px 32px;
            line-height: 1.45;
        }}
        h1 {{
            margin-top: 0;
            margin-bottom: 16px;
        }}
        .tab-bar {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            border-bottom: 2px solid var(--border);
            padding-bottom: 12px;
            margin-bottom: 20px;
        }}
        .tab-btn {{
            background: #1b2534;
            color: var(--muted);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 10px 18px;
            font-size: 0.96rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s ease;
        }}
        .tab-btn:hover {{
            color: var(--text);
            border-color: #475872;
        }}
        .tab-btn.active {{
            background: var(--accent);
            color: #0f141c;
            border-color: var(--accent);
        }}
        .tab-panel {{
            display: none;
        }}
        .tab-panel.active {{
            display: block;
        }}
        .variant-section {{
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 20px 24px;
            margin-bottom: 28px;
        }}
        .variant-tag {{
            color: var(--accent);
            font-weight: 600;
        }}
        .desc {{
            color: var(--muted);
            margin-top: 4px;
        }}
        .summary-card {{
            background: rgba(255, 255, 255, 0.03);
            border-left: 4px solid var(--accent);
            padding: 10px 16px;
            margin: 14px 0;
            border-radius: 4px;
        }}
        .summary-card h4 {{
            margin: 0 0 6px 0;
        }}
        .summary-card p {{
            margin: 0;
        }}
        .table-wrap {{
            overflow-x: auto;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.92rem;
            margin-top: 12px;
        }}
        th, td {{
            border: 1px solid var(--border);
            padding: 8px 10px;
            text-align: left;
        }}
        th {{
            background: #202b3b;
            font-weight: 600;
        }}
        tr:nth-child(even) {{
            background: rgba(255, 255, 255, 0.02);
        }}
        .mono {{
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        }}
        .center {{
            text-align: center;
        }}
        .badge {{
            background: #2b394e;
            padding: 2px 8px;
            border-radius: 999px;
            font-size: 0.8rem;
            white-space: nowrap;
        }}
        .phase-block {{
            margin-top: 22px;
            margin-bottom: 26px;
        }}
        .phase-title {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin: 0 0 8px 0;
            font-size: 1.05rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 6px;
        }}
        .phase-badge {{
            background: #334155;
            color: var(--accent);
            font-size: 0.9rem;
            padding: 4px 12px;
            font-weight: 700;
            border: 1px solid #475569;
        }}
        .phase-range {{
            color: var(--muted);
            font-size: 0.88rem;
            font-weight: 400;
        }}
        .res-f {{ color: var(--food); font-weight: 700; background: rgba(248, 113, 113, 0.08); }}
        .res-f-sub {{ color: #fca5a5; }}
        .zero {{ color: #475569; }}
        .food-group-hdr {{ background: #2d222a !important; color: #fca5a5; text-align: center; }}
        .sub-hdr {{ background: #252029 !important; font-size: 0.82rem; color: #f87171; }}
        .res-w {{ color: var(--wood); font-weight: 600; }}
        .res-g {{ color: var(--gold); font-weight: 600; }}
        .res-s {{ color: var(--stone); font-weight: 600; }}
        .notes {{ color: var(--muted); }}
    </style>
</head>
<body>
    <h1>{html.escape(title)}</h1>
    <div class="tab-bar" role="tablist">
        {''.join(tab_buttons_html)}
    </div>
    {''.join(tab_panels_html)}
    <script>
        function switchTab(tabId, btnEl) {{
            document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            const target = document.getElementById(tabId);
            if (target) target.classList.add('active');
            if (btnEl) btnEl.classList.add('active');
        }}
    </script>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(page)
    return output_path

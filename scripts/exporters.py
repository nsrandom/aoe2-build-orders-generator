#!/usr/bin/env python3
"""
HTML & RTS Overlay JSON Exporters for AoE2:DE Build Orders.

Generates:
1. A rich standalone HTML document linking to the shared stylesheet (`styles/build_order.css`),
   with Light/Dark mode support (defaulting to Light mode), top-level Tab Views for each build
   order variant, collapsible sections (`<details>`), an interactive SVG Resources Bank by Time
   chart, Villager-by-Villager compressed timeline tables with Army Counts by Type in the notes
   column, and Steady-State/Rot telemetry.
2. An RTS Overlay compatible JSON file matching the `AoE Overlay` / `RTS_Overlay`
   schema (`name`, `civilization`, `author`, `source`, `description`, `build_order`).
"""

from __future__ import annotations

import html
import json
import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
    "town_center": "@town_center/Towncenter_aoe2DE.png@",
    "university": "@university/University_aoe2DE.png@",
    "monastery": "@monastery/Monastery_aoe2DE.png@",
    "double_bit_axe": "@lumber_camp/DoubleBitAxe_aoe2DE.png@",
    "bow_saw": "@lumber_camp/BowSaw_aoe2DE.png@",
    "horse_collar": "@mill/HorseCollar_aoe2DE.png@",
    "heavy_plow": "@mill/HeavyPlow_aoe2DE.png@",
    "hand_cart": "@town_center/HandCartDE.png@",
    "ballistics": "@university/Ballistics_aoe2DE.png@",
    "chemistry": "@university/Chemistry_aoe2DE.png@",
    "light_cavalry": "@stable/Lightcavalry_aoe2DE.png@",
    "trebuchet": "@castle/Trebuchet_aoe2DE.png@",
    "bombard_cannon": "@siege_workshop/Bombard_cannon_aoe2DE.png@",
}


@dataclass
class DetailedBuildRow:
    pop: str  # e.g. "4 (3v)" or "20v" or "Transition"
    timestamp: str  # e.g. "00:25"
    age: str  # "Dark Age", "Feudal Transition", "Feudal Age", "Castle Transition", "Castle Age"
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
    army_counts: Dict[str, int] = field(default_factory=dict)


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
    resource_timeline: List[Dict[str, object]] = field(default_factory=list)
    author: str = "AoE2 Build Order Generator"
    source: str = "rules.md"


def export_rts_overlay_json(doc: BuildOrderDocument, output_path: Path) -> Path:
    """Writes an RTS Overlay compatible JSON file and validates its structure."""
    for idx, step in enumerate(doc.rts_steps):
        res_sum = step.wood + step.food + step.gold + step.stone
        if res_sum != step.villager_count:
            raise ValueError(
                f"RTS Overlay step {idx} violates villager sum invariant: "
                f"sum(resources)={res_sum} != villager_count={step.villager_count}"
            )
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


_UNIT_DISPLAY_NAMES: Dict[str, Tuple[str, str]] = {
    "scout": ("Scout", "Scouts"),
    "militia": ("Militia", "Militia"),
    "maa": ("MAA", "MAA"),
    "man_at_arms": ("MAA", "MAA"),
    "archer": ("Archer", "Archers"),
    "crossbow": ("Crossbow", "Crossbows"),
    "crossbowman": ("Crossbow", "Crossbows"),
    "skirmisher": ("Skirm", "Skirms"),
    "genoese": ("Genoese", "Genoese"),
    "light_cav": ("Light Cav", "Light Cav"),
    "monk": ("Monk", "Monks"),
    "trebuchet": ("Treb", "Trebs"),
    "bombard_cannon": ("BBC", "BBCs"),
}


def format_army_counts(army_counts: Dict[str, int]) -> str:
    """Formats a unit-type dictionary into a compact string, e.g. 'Army: 38 Genoese · 4 Light Cav'."""
    if not army_counts:
        return ""
    parts: List[str] = []
    for key, cnt in army_counts.items():
        if cnt and cnt > 0:
            singular, plural = _UNIT_DISPLAY_NAMES.get(key.lower(), (key, key))
            label = singular if cnt == 1 else plural
            parts.append(f"{cnt} {label}")
    if not parts:
        return ""
    return "Army: " + " · ".join(parts)


def _merge_pop_str(p1: str, p2: str) -> str:
    pop_re = re.compile(r"^(?:(\d+)[–-](\d+)|(\d+))v(?:\s*\((?:(\d+)[–-](\d+)|(\d+))\s*pop\))?$")
    m1 = pop_re.match(p1.strip())
    m2 = pop_re.match(p2.strip())
    if not m1 or not m2:
        return p2 if p1 == p2 else f"{p1} -> {p2}"
    v_start = m1.group(1) or m1.group(3)
    v_end = m2.group(2) or m2.group(3)
    pop_start = m1.group(4) or m1.group(6)
    pop_end = m2.group(5) or m2.group(6)
    v_str = f"{v_start}–{v_end}v" if v_start != v_end else f"{v_start}v"
    if pop_start and pop_end:
        pop_str = f" ({pop_start}–{pop_end} pop)" if pop_start != pop_end else f" ({pop_start} pop)"
        return v_str + pop_str
    return v_str


def _merge_time_str(t1: str, t2: str) -> str:
    s1 = re.split(r"\s*[–-]\s*", t1.strip())[0]
    s2 = re.split(r"\s*[–-]\s*", t2.strip())[-1]
    return f"{s1} – {s2}" if s1 != s2 else s1


def _merge_notes(n1: str, n2: str) -> str:
    parts: List[str] = []
    for n in (n1.strip(), n2.strip()):
        if n and n not in parts:
            parts.append(n)
    return " ".join(parts)


def _parse_vil_action(action: str) -> Optional[Tuple[int, int, str, str]]:
    """
    Matches single or already-compressed villager assignment strings:
    - 'Vil #4 -> Sheep under TC (0s walk)'
    - 'Vil #27 (TC #1) -> Gold (7/7 on Gold)'
    - 'Vils #4–#6 (3 vils) -> Sheep under TC (0s walk)'
    Returns (v_start, v_end, tc_tag, dest).
    """
    m_single = re.match(r"^Vil #(\d+)(?: \((TC #\d+)\))? -> (.+)$", action.strip())
    if m_single:
        v = int(m_single.group(1))
        return (v, v, m_single.group(2) or "", m_single.group(3))
    m_multi = re.match(r"^Vils #(\d+)[–-]#?(\d+) \(\d+ vils(?:, (TC #\d+))?\) -> (.+)$", action.strip())
    if m_multi:
        return (int(m_multi.group(1)), int(m_multi.group(2)), m_multi.group(3) or "", m_multi.group(4))
    return None


def _norm_vil_dest(dest: str) -> Optional[str]:
    low = dest.lower().strip()
    # Do not merge unique building constructions (Houses, Camps, Mills), only gathering or Farm seeding
    if "build " in low and "farm #" not in low and "farms #" not in low:
        return None
    low = re.sub(r"(?:seed|build) farms? #\d+(?:[–-]#?\d+)?", "seed farm #n", low)
    low = re.sub(r"-60w(?: each)?", "-60w", low)
    low = re.sub(r";\s*\d+(?:/\d+)?\s+on\s+[a-z ]+", "; n on res", low)
    low = re.sub(r"\(\d+(?:/\d+)?\s+on\s+[^)]+\)", "(n on res)", low)
    low = re.sub(r";\s*\d+(?:/\d+)?\s+(?:active\s+)?farms?", "; n farms", low)
    low = re.sub(r"\s+across\s+\d+\s+lcs?", "", low)
    return low


def compress_build_rows(rows: List[DetailedBuildRow]) -> List[DetailedBuildRow]:
    """
    Compresses consecutive DetailedBuildRow entries within the same phase when:
    1. Multiple continuous villagers perform the same assignment (e.g. Vils #4-#6 -> Sheep under TC).
    2. Multiple Horse Collar Farms are seeded consecutively during a transition.
    3. Multiple identical military units are queued consecutively at the same production building.
    """
    if not rows:
        return []

    out: List[DetailedBuildRow] = [rows[0]]
    for curr in rows[1:]:
        prev = out[-1]
        if prev.age != curr.age:
            out.append(curr)
            continue

        # 1. Check consecutive villager assignments
        v1 = _parse_vil_action(prev.action)
        v2 = _parse_vil_action(curr.action)
        if v1 and v2 and v2[0] == v1[1] + 1:
            k1 = _norm_vil_dest(v1[3])
            k2 = _norm_vil_dest(v2[3])
            if k1 is not None and k1 == k2:
                v_start, v_end = v1[0], v2[1]
                cnt = v_end - v_start + 1
                tc_tag = v1[2] if v1[2] == v2[2] else ""
                tc_str = f", {tc_tag}" if tc_tag else ""
                dest_final = v2[3]
                # If farm seeding, rewrite 'Seed Farm #X' -> 'Seed Farms #A–#B'
                fm1 = re.search(r"(Seed|Build) Farms? #(\d+)", v1[3])
                fm2 = re.search(r"(Seed|Build) Farms? #(?:\d+[–-]#?)?(\d+)", v2[3])
                if fm1 and fm2:
                    verb = fm1.group(1)
                    f_start, f_end = fm1.group(2), fm2.group(2)
                    dest_final = re.sub(
                        r"(?:Seed|Build) Farms? #\d+(?:[–-]#?\d+)?",
                        f"{verb} Farms #{f_start}–#{f_end}",
                        dest_final,
                    )
                    dest_final = re.sub(r"-60W(?!\s*each)", "-60W each", dest_final)
                merged_action = f"Vils #{v_start}–#{v_end} ({cnt} vils{tc_str}) -> {dest_final}"
                out[-1] = replace(
                    curr,
                    pop=_merge_pop_str(prev.pop, curr.pop),
                    timestamp=_merge_time_str(prev.timestamp, curr.timestamp),
                    action=merged_action,
                    notes=_merge_notes(prev.notes, curr.notes),
                )
                continue

        # 2. Check consecutive Horse Collar Farm seeding rows
        f_re = re.compile(r"^Seed Horse Collar Farms? #(\d+)(?:[–-]#?(\d+))? \((?:\d+ Farms,\s*)?(.+)\)\.$")
        fm1 = f_re.match(prev.action.strip())
        fm2 = f_re.match(curr.action.strip())
        if fm1 and fm2:
            f_start = int(fm1.group(1))
            f_end = int(fm2.group(2) or fm2.group(1))
            cnt = f_end - f_start + 1
            merged_action = f"Seed Horse Collar Farms #{f_start}–#{f_end} ({cnt} Farms, -60W each, 5s walk + 15s build)."
            out[-1] = replace(
                curr,
                pop=_merge_pop_str(prev.pop, curr.pop),
                timestamp=_merge_time_str(prev.timestamp, curr.timestamp),
                action=merged_action,
                notes=_merge_notes(prev.notes, curr.notes),
            )
            continue

        # 3. Check consecutive military unit queue rows
        u_re = re.compile(
            r"^Queue (Light Cavalry|Genoese Crossbowman|Monk|Archer|Militia) #(\d+)(?:[–-]#?(\d+))?(?: \(\d+ units\))? at ([^()]+) \((.+)\)\.$"
        )
        um1 = u_re.match(prev.action.strip())
        um2 = u_re.match(curr.action.strip())
        if um1 and um2 and um1.group(1) == um2.group(1) and um1.group(4).strip() == um2.group(4).strip():
            unit_name = um1.group(1)
            u_start = int(um1.group(2))
            u_end = int(um2.group(3) or um2.group(2))
            cnt = u_end - u_start + 1
            bldg = um1.group(4).strip()
            details = um2.group(5)
            merged_action = f"Queue {unit_name} #{u_start}–#{u_end} ({cnt} units) at {bldg} ({details})."
            out[-1] = replace(
                curr,
                pop=_merge_pop_str(prev.pop, curr.pop),
                timestamp=_merge_time_str(prev.timestamp, curr.timestamp),
                action=merged_action,
                notes=_merge_notes(prev.notes, curr.notes),
            )
            continue

        out.append(curr)

    return out


def _parse_mmss_to_sec(ts: str) -> int:
    """Parses 'MM:SS' (or the end of 'MM:SS – MM:SS') into seconds."""
    part = re.split(r"\s*[–-]\s*", ts.strip())[-1]
    m = re.match(r"^(\d+):(\d{2})$", part)
    if not m:
        return 0
    return int(m.group(1)) * 60 + int(m.group(2))


def _fmt_sec_mmss(sec: int) -> str:
    return f"{sec // 60:02d}:{sec % 60:02d}"


def _build_resource_chart_html(doc: BuildOrderDocument, tab_idx: int) -> str:
    """
    Renders an interactive SVG chart of the Resource Bank (Food, Wood, Gold, Stone) over time,
    complete with age milestone lines, series toggle checkboxes, and hover crosshair readout.
    """
    # Collect data points from doc.resource_timeline if populated, else from doc.rows
    points: List[Dict[str, object]] = []
    if doc.resource_timeline:
        points = list(doc.resource_timeline)
    else:
        for r in doc.rows:
            t_sec = _parse_mmss_to_sec(r.timestamp)
            points.append(
                {
                    "t": t_sec,
                    "ts": re.split(r"\s*[–-]\s*", r.timestamp.strip())[-1],
                    "food": round(r.bank_food),
                    "wood": round(r.bank_wood),
                    "gold": round(r.bank_gold),
                    "stone": round(r.bank_stone),
                    "army": format_army_counts(r.army_counts),
                }
            )

    if not points:
        return ""

    # Deduplicate same-timestamp points by keeping the latest state at each timestamp,
    # except preserve sharp pre-click -> post-click drops by keeping points where resources changed significantly
    cleaned_pts: List[Dict[str, object]] = []
    for pt in points:
        if cleaned_pts and int(cleaned_pts[-1]["t"]) == int(pt["t"]):
            cleaned_pts[-1] = pt
        else:
            cleaned_pts.append(pt)

    max_t = max(int(p["t"]) for p in cleaned_pts) or 1
    max_val_raw = max(
        max(float(p["food"]), float(p["wood"]), float(p["gold"]), float(p["stone"]))
        for p in cleaned_pts
    )
    # Round Y-axis max up to a clean step (e.g. nearest 200 or 500)
    step_y = 200 if max_val_raw <= 1200 else 400
    max_y = max(step_y * 2, int(((max_val_raw + step_y - 1) // step_y) * step_y))

    # SVG coordinate geometry
    width, height = 860, 270
    pad_l, pad_r, pad_t, pad_b = 52, 24, 24, 34
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    def x_of(t_val: float) -> float:
        return pad_l + (t_val / max_t) * plot_w

    def y_of(v_val: float) -> float:
        clamped = max(0.0, min(float(max_y), v_val))
        return pad_t + plot_h - (clamped / max_y) * plot_h

    # Y-axis gridlines & labels
    y_grid_html = []
    num_y_ticks = max(2, max_y // step_y)
    for i in range(num_y_ticks + 1):
        val = i * step_y
        yp = y_of(val)
        y_grid_html.append(
            f'<line x1="{pad_l}" y1="{yp:.1f}" x2="{width - pad_r}" y2="{yp:.1f}" class="chart-grid-line" />'
            f'<text x="{pad_l - 8}" y="{yp + 4:.1f}" text-anchor="end" class="chart-axis-label">{val}</text>'
        )

    # X-axis time ticks (every 2 or 3 minutes depending on duration)
    x_step_sec = 120 if max_t <= 1200 else 180
    x_grid_html = []
    t_tick = 0
    while t_tick <= max_t:
        xp = x_of(t_tick)
        x_grid_html.append(
            f'<line x1="{xp:.1f}" y1="{pad_t}" x2="{xp:.1f}" y2="{height - pad_b}" class="chart-grid-line" />'
            f'<text x="{xp:.1f}" y="{height - pad_b + 18}" text-anchor="middle" class="chart-axis-label">{_fmt_sec_mmss(t_tick)}</text>'
        )
        t_tick += x_step_sec

    # Extract key milestone markers from doc.rows
    milestones: List[Tuple[int, str]] = []
    seen_ms = set()
    for r in doc.rows:
        act_up = r.action.upper()
        t_s = _parse_mmss_to_sec(r.timestamp)
        label = ""
        if "CLICK FEUDAL" in act_up:
            label = "Feudal Click"
        elif "REACHED FEUDAL" in act_up:
            label = "Feudal Age"
        elif "CLICK CASTLE" in act_up:
            label = "Castle Click"
        elif "REACHED CASTLE" in act_up:
            label = "Castle Age"
        elif "CLICK IMPERIAL" in act_up:
            label = "Imp Click"
        elif "REACHED IMPERIAL" in act_up:
            label = "Imp Age"
        if label and label not in seen_ms:
            seen_ms.add(label)
            milestones.append((t_s, label))

    milestone_svg = []
    for idx_m, (m_sec, m_lbl) in enumerate(milestones):
        mx = x_of(m_sec)
        # Alternate label vertical offset slightly to prevent overlap
        lbl_y = pad_t - 6 if idx_m % 2 == 0 else pad_t + 11
        milestone_svg.append(
            f'<line x1="{mx:.1f}" y1="{pad_t}" x2="{mx:.1f}" y2="{height - pad_b}" class="chart-milestone-line" />'
            f'<text x="{mx + 3:.1f}" y="{lbl_y}" text-anchor="start" class="chart-milestone-label">{html.escape(m_lbl)} ({_fmt_sec_mmss(m_sec)})</text>'
        )

    # Build polyline strings for food, wood, gold, stone
    def build_polyline(res_key: str) -> str:
        coords = [f"{x_of(float(p['t'])):.1f},{y_of(float(p[res_key])):.1f}" for p in cleaned_pts]
        return " ".join(coords)

    food_pts = build_polyline("food")
    wood_pts = build_polyline("wood")
    gold_pts = build_polyline("gold")
    stone_pts = build_polyline("stone")

    chart_id = f"res-chart-{tab_idx}"
    pts_json = html.escape(json.dumps(cleaned_pts))

    return f"""
    <details open class="phase-block chart-block">
        <summary class="phase-title">
            <span class="badge">Resources Bank Over Time</span>
            <span class="phase-range mono">00:00 &rarr; {_fmt_sec_mmss(max_t)}</span>
            <span class="phase-row-count">Interactive Chart</span>
        </summary>
        <div class="phase-body">
            <div class="chart-controls">
                <div class="chart-legend" role="group" aria-label="Toggle resource series">
                    <label class="chart-series-toggle">
                        <input type="checkbox" checked data-chart-id="{chart_id}" data-series="food">
                        <span class="swatch swatch-food"></span>
                        <span class="res-f">Food</span>
                    </label>
                    <label class="chart-series-toggle">
                        <input type="checkbox" checked data-chart-id="{chart_id}" data-series="wood">
                        <span class="swatch swatch-wood"></span>
                        <span class="res-w">Wood</span>
                    </label>
                    <label class="chart-series-toggle">
                        <input type="checkbox" checked data-chart-id="{chart_id}" data-series="gold">
                        <span class="swatch swatch-gold"></span>
                        <span class="res-g">Gold</span>
                    </label>
                    <label class="chart-series-toggle">
                        <input type="checkbox" checked data-chart-id="{chart_id}" data-series="stone">
                        <span class="swatch swatch-stone"></span>
                        <span class="res-s">Stone</span>
                    </label>
                </div>
                <div class="chart-readout mono" id="{chart_id}-readout">
                    Hover chart to inspect exact resource bank &amp; army by timestamp
                </div>
            </div>
            <div class="chart-svg-wrap">
                <svg id="{chart_id}" class="resource-chart-svg" viewBox="0 0 {width} {height}"
                     role="img" aria-label="Resource bank over time chart for {html.escape(doc.variant_label)}"
                     data-points="{pts_json}" data-max-t="{max_t}" data-max-y="{max_y}"
                     data-pad-l="{pad_l}" data-pad-r="{pad_r}" data-pad-t="{pad_t}" data-pad-b="{pad_b}"
                     data-width="{width}" data-height="{height}">
                    {''.join(y_grid_html)}
                    {''.join(x_grid_html)}
                    <line x1="{pad_l}" y1="{height - pad_b}" x2="{width - pad_r}" y2="{height - pad_b}" class="chart-axis-line" />
                    <line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{height - pad_b}" class="chart-axis-line" />
                    {''.join(milestone_svg)}
                    <polyline class="chart-line chart-line-food" data-series-line="food" points="{food_pts}" />
                    <polyline class="chart-line chart-line-wood" data-series-line="wood" points="{wood_pts}" />
                    <polyline class="chart-line chart-line-gold" data-series-line="gold" points="{gold_pts}" />
                    <polyline class="chart-line chart-line-stone" data-series-line="stone" points="{stone_pts}" />
                    <line class="chart-hover-line" id="{chart_id}-hline" x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{height - pad_b}" />
                    <circle class="chart-hover-dot" id="{chart_id}-dot-food" r="4.5" fill="var(--food)" />
                    <circle class="chart-hover-dot" id="{chart_id}-dot-wood" r="4.5" fill="var(--wood)" />
                    <circle class="chart-hover-dot" id="{chart_id}-dot-gold" r="4.5" fill="var(--gold)" />
                    <circle class="chart-hover-dot" id="{chart_id}-dot-stone" r="4.5" fill="var(--stone)" />
                </svg>
            </div>
        </div>
    </details>
    """


def export_build_order_html(
    docs: List[BuildOrderDocument], title: str, output_path: Path
) -> Path:
    """Writes a standalone HTML report linking to the shared stylesheet (`styles/build_order.css`)."""
    tab_buttons_html = []
    tab_panels_html = []

    for idx, doc in enumerate(docs):
        active_cls = " active" if idx == 0 else ""
        tab_id = f"tab-{idx}"
        tab_buttons_html.append(
            f'<button type="button" class="tab-btn{active_cls}" role="tab" '
            f'aria-selected="{"true" if idx == 0 else "false"}" data-tab-target="{tab_id}">'
            f"{html.escape(doc.variant_label)}"
            f"</button>"
        )

        def fmt_sub(val: int) -> str:
            return f"<strong>{val}</strong>" if val > 0 else '<span class="zero">-</span>'

        # Compress consecutive identical villager assignments / actions before rendering
        compressed_rows = compress_build_rows(doc.rows)

        # Group contiguous rows by phase (`r.age`) into separate collapsible sections
        phase_groups: List[Tuple[str, List[DetailedBuildRow]]] = []
        for r in compressed_rows:
            if not phase_groups or phase_groups[-1][0] != r.age:
                phase_groups.append((r.age, [r]))
            else:
                phase_groups[-1][1].append(r)

        phase_sections_html = []
        for phase_name, phase_rows in phase_groups:
            rows_html = []
            for r in phase_rows:
                deer_or_chk = r.deer_vils if r.deer_vils > 0 else r.chicken_vils
                army_str = format_army_counts(r.army_counts)
                army_badge_html = (
                    f'<span class="army-badge">{html.escape(army_str)}</span>'
                    if army_str
                    else ""
                )
                notes_html = f"{army_badge_html}{html.escape(r.notes)}"
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
                        <td class="notes">{notes_html}</td>
                    </tr>
                    """
                )
            start_ts = re.split(r"\s*[–-]\s*", phase_rows[0].timestamp.strip())[0]
            end_ts = re.split(r"\s*[–-]\s*", phase_rows[-1].timestamp.strip())[-1]
            row_cnt = len(phase_rows)
            phase_sections_html.append(
                f"""
                <details open class="phase-block">
                    <summary class="phase-title">
                        <span class="badge">{html.escape(phase_name)}</span>
                        <span class="phase-range mono">{html.escape(start_ts)} &rarr; {html.escape(end_ts)}</span>
                        <span class="phase-row-count">{row_cnt} {"row" if row_cnt == 1 else "rows"}</span>
                    </summary>
                    <div class="phase-body">
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
                                        <th rowspan="2">Notes, Buildings &amp; Army</th>
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
                </details>
                """
            )

        ss_html = ""
        if doc.steady_state_summary:
            rec = doc.steady_state_summary.get("recommended_vils", {})
            ex = doc.steady_state_summary.get("exact_vils", {})
            ss_title = doc.steady_state_summary.get(
                "title",
                "Steady-State Continuous Production Target",
            )
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
            final_army_str = format_army_counts(doc.rows[-1].army_counts) if doc.rows else ""
            final_army_html = (
                f'<p><strong>Final Army by Type:</strong> <span class="army-badge">{html.escape(final_army_str)}</span></p>'
                if final_army_str
                else ""
            )
            ss_html = f"""
            <details open class="phase-block">
                <summary class="phase-title">
                    <span class="badge">Steady-State &amp; Telemetry</span>
                    <span class="phase-range">{html.escape(str(ss_title))}</span>
                </summary>
                <div class="phase-body">
                    <div class="summary-card">
                        <p>
                            <strong>Recommended Minimum Villagers:</strong>
                            <span class="res-f">{rec.get('food', 0)} Food</span> &middot;
                            <span class="res-w">{rec.get('wood', 0)} Wood</span> &middot;
                            <span class="res-g">{rec.get('gold', 0)} Gold</span> &middot;
                            <span class="res-s">{rec.get('stone', 0)} Stone</span>
                            (Total: <strong>{rec.get('total', 0)}</strong> vils; exact: {ex.get('food', 0)}F / {ex.get('wood', 0)}W / {ex.get('gold', 0)}G / {ex.get('stone', 0)}S)
                        </p>
                        {f'<p><strong>Simulated Animal Rot Telemetry:</strong> {rot_str}</p>' if rot_str else ''}
                        {final_army_html}
                    </div>
                </div>
            </details>
            """

        chart_html = _build_resource_chart_html(doc, idx)

        tab_panels_html.append(
            f"""
            <section id="{tab_id}" class="variant-section tab-panel{active_cls}" role="tabpanel">
                <div class="variant-header">
                    <h2>{html.escape(doc.name)} &mdash; <span class="variant-tag">{html.escape(doc.variant_label)}</span></h2>
                    <button type="button" class="toggle-all-btn" data-toggle-all="{tab_id}" aria-expanded="true">
                        <span class="expand-label">Expand all sections</span>
                        <span class="collapse-label">Collapse all sections</span>
                    </button>
                </div>
                <p class="desc">{html.escape(doc.description)}</p>
                {ss_html}
                {chart_html}
                {''.join(phase_sections_html)}
            </section>
            """
        )

    # Compute relative path from output_path.parent to shared styles/build_order.css
    repo_root = Path(__file__).resolve().parent.parent
    shared_css_path = repo_root / "styles" / "build_order.css"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    css_rel_path = os.path.relpath(shared_css_path, output_path.parent).replace("\\", "/")

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="color-scheme" content="light">
    <script>
        try {{
            document.querySelector('meta[name="color-scheme"]').content = localStorage.getItem("color-scheme") ?? "light";
        }} catch (e) {{}}
    </script>
    <title>{html.escape(title)}</title>
    <link rel="stylesheet" href="{html.escape(css_rel_path)}">
</head>
<body>
    <header class="page-header">
        <h1>{html.escape(title)}</h1>
        <div class="header-actions">
            <button type="button" class="theme-toggle" id="theme-toggle-btn">
                <span class="theme-toggle-option theme-option-dark">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
                    </svg>
                    <span>Dark mode</span>
                </span>
                <span class="theme-toggle-option theme-option-light">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                        <circle cx="12" cy="12" r="5"></circle>
                        <line x1="12" y1="1" x2="12" y2="3"></line>
                        <line x1="12" y1="21" x2="12" y2="23"></line>
                        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
                        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
                        <line x1="1" y1="12" x2="3" y2="12"></line>
                        <line x1="21" y1="12" x2="23" y2="12"></line>
                        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
                        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
                    </svg>
                    <span>Light mode</span>
                </span>
            </button>
        </div>
    </header>
    <main>
        <div class="tab-bar" role="tablist">
            {''.join(tab_buttons_html)}
        </div>
        {''.join(tab_panels_html)}
    </main>
    <script>
        // 1. Light / Dark Mode Toggle (defaults to Light Mode)
        const metaScheme = document.querySelector('meta[name="color-scheme"]');
        const themeBtn = document.getElementById('theme-toggle-btn');
        if (themeBtn && metaScheme) {{
            themeBtn.addEventListener('click', () => {{
                const current = metaScheme.content === 'dark' ? 'dark' : 'light';
                const next = current === 'dark' ? 'light' : 'dark';
                metaScheme.content = next;
                try {{
                    localStorage.setItem('color-scheme', next);
                }} catch (e) {{}}
            }});
            window.addEventListener('storage', (ev) => {{
                if (ev.key === 'color-scheme') {{
                    metaScheme.content = ev.newValue || 'light';
                }}
            }});
        }}

        // 2. Top-Level Variant Tab Switching
        document.querySelectorAll('.tab-btn[data-tab-target]').forEach((btn) => {{
            btn.addEventListener('click', () => {{
                const tabId = btn.getAttribute('data-tab-target');
                document.querySelectorAll('.tab-panel').forEach((p) => p.classList.remove('active'));
                document.querySelectorAll('.tab-btn').forEach((b) => {{
                    b.classList.remove('active');
                    b.setAttribute('aria-selected', 'false');
                }});
                const target = document.getElementById(tabId);
                if (target) target.classList.add('active');
                btn.classList.add('active');
                btn.setAttribute('aria-selected', 'true');
            }});
        }});

        // 3. Collapsible Sections: Expand / Collapse All + Sync
        document.querySelectorAll('.toggle-all-btn[data-toggle-all]').forEach((btn) => {{
            btn.addEventListener('click', () => {{
                const panelId = btn.getAttribute('data-toggle-all');
                const panel = document.getElementById(panelId);
                if (!panel) return;
                const expand = btn.getAttribute('aria-expanded') !== 'true';
                panel.querySelectorAll('details.phase-block').forEach((d) => {{
                    d.open = expand;
                }});
                btn.setAttribute('aria-expanded', String(expand));
            }});
        }});

        document.addEventListener('toggle', (ev) => {{
            const details = ev.target;
            if (!(details instanceof HTMLDetailsElement) || !details.classList.contains('phase-block')) return;
            const panel = details.closest('.tab-panel');
            if (!panel) return;
            const btn = panel.querySelector('.toggle-all-btn[data-toggle-all]');
            if (!btn) return;
            const allDetails = panel.querySelectorAll('details.phase-block');
            const allOpen = Array.prototype.every.call(allDetails, (d) => d.open);
            btn.setAttribute('aria-expanded', String(allOpen));
        }}, {{ capture: true }});

        // 4. Interactive Resource Bank Chart: Series Toggles & Hover Crosshair
        document.querySelectorAll('input[data-chart-id][data-series]').forEach((chk) => {{
            chk.addEventListener('change', () => {{
                const chartId = chk.getAttribute('data-chart-id');
                const series = chk.getAttribute('data-series');
                const svg = document.getElementById(chartId);
                if (!svg) return;
                const line = svg.querySelector(`[data-series-line="${{series}}"]`);
                if (line) line.classList.toggle('chart-series-hidden', !chk.checked);
            }});
        }});

        document.querySelectorAll('.resource-chart-svg').forEach((svg) => {{
            const ptsRaw = svg.getAttribute('data-points');
            if (!ptsRaw) return;
            let pts = [];
            try {{ pts = JSON.parse(ptsRaw); }} catch (e) {{ return; }}
            if (!pts.length) return;

            const maxT = parseFloat(svg.getAttribute('data-max-t') || '1');
            const maxY = parseFloat(svg.getAttribute('data-max-y') || '1000');
            const padL = parseFloat(svg.getAttribute('data-pad-l') || '52');
            const padR = parseFloat(svg.getAttribute('data-pad-r') || '24');
            const padT = parseFloat(svg.getAttribute('data-pad-t') || '24');
            const padB = parseFloat(svg.getAttribute('data-pad-b') || '34');
            const width = parseFloat(svg.getAttribute('data-width') || '860');
            const height = parseFloat(svg.getAttribute('data-height') || '270');
            const plotW = width - padL - padR;
            const plotH = height - padT - padB;

            const hline = document.getElementById(`${{svg.id}}-hline`);
            const dotF = document.getElementById(`${{svg.id}}-dot-food`);
            const dotW = document.getElementById(`${{svg.id}}-dot-wood`);
            const dotG = document.getElementById(`${{svg.id}}-dot-gold`);
            const dotS = document.getElementById(`${{svg.id}}-dot-stone`);
            const readout = document.getElementById(`${{svg.id}}-readout`);

            const xOf = (t) => padL + (t / maxT) * plotW;
            const yOf = (v) => padT + plotH - (Math.max(0, Math.min(maxY, v)) / maxY) * plotH;

            svg.addEventListener('mousemove', (ev) => {{
                const rect = svg.getBoundingClientRect();
                const relX = ((ev.clientX - rect.left) / rect.width) * width;
                const clampedX = Math.max(padL, Math.min(width - padR, relX));
                const targetT = ((clampedX - padL) / plotW) * maxT;

                let best = pts[0];
                let bestDist = Math.abs(best.t - targetT);
                for (let i = 1; i < pts.length; i++) {{
                    const d = Math.abs(pts[i].t - targetT);
                    if (d < bestDist) {{
                        best = pts[i];
                        bestDist = d;
                    }}
                }}

                const cx = xOf(best.t);
                if (hline) {{
                    hline.setAttribute('x1', String(cx));
                    hline.setAttribute('x2', String(cx));
                    hline.style.opacity = '0.85';
                }}
                const setDot = (dot, val) => {{
                    if (!dot) return;
                    dot.setAttribute('cx', String(cx));
                    dot.setAttribute('cy', String(yOf(val)));
                    dot.style.opacity = '1';
                }};
                setDot(dotF, best.food);
                setDot(dotW, best.wood);
                setDot(dotG, best.gold);
                setDot(dotS, best.stone);

                if (readout) {{
                    const armyPart = best.army ? ` | ${{best.army}}` : '';
                    readout.textContent = `Time: ${{best.ts}} | Food: ${{best.food}}F · Wood: ${{best.wood}}W · Gold: ${{best.gold}}G · Stone: ${{best.stone}}S${{armyPart}}`;
                }}
            }});

            svg.addEventListener('mouseleave', () => {{
                if (hline) hline.style.opacity = '0';
                [dotF, dotW, dotG, dotS].forEach((d) => {{ if (d) d.style.opacity = '0'; }});
            }});
        }});
    </script>
</body>
</html>
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(page)
    return output_path

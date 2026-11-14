#!/usr/bin/env python3
"""
HTML & RTS Overlay JSON Exporters for AoE2:DE Build Orders.

Generates:
1. A rich standalone HTML document linking to the shared stylesheet (`styles/build_order.css`),
   with Light/Dark mode support (defaulting to Light mode), top-level Tab Views for each build
   order variant, collapsible sections (`<details>`), an interactive SVG Resources Bank by Time
   chart (with dedicated stacked readout lines for resources and total vils/military distribution),
   standard AoE2 resource icons (`styles/icons/{food,wood,gold,stone}.png`), Villager-by-Villager
   compressed timeline tables with Army Counts by Type in the notes column, and Steady-State/Rot telemetry.
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
    "battering_ram": "@siege_workshop/Battering_ram_aoe2DE.png@",
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
    "battering_ram": ("Ram", "Rams"),
    "ram": ("Ram", "Rams"),
    "trebuchet": ("Treb", "Trebs"),
    "bombard_cannon": ("BBC", "BBCs"),
}


def format_army_distribution(army_counts: Dict[str, int]) -> str:
    """
    Formats unit counts into a compact distribution string, e.g. '38 Genoese · 4 Light Cav'.
    Omits the single starting Scout ('scout' == 1) so only produced/upgraded military units are listed.
    """
    if not army_counts:
        return ""
    parts: List[str] = []
    for key, cnt in army_counts.items():
        if not cnt or cnt <= 0:
            continue
        if key.lower() == "scout" and cnt == 1:
            continue
        singular, plural = _UNIT_DISPLAY_NAMES.get(key.lower(), (key, key))
        label = singular if cnt == 1 else plural
        parts.append(f"{cnt} {label}")
    return " · ".join(parts)


def format_army_counts(army_counts: Dict[str, int]) -> str:
    """
    Formats a unit-type dictionary with 'Army: ' prefix, e.g. 'Army: 38 Genoese · 4 Light Cav'.
    Skips 'Army: 1 Scout' when only the starting Scout exists and no other military units have been made.
    """
    if not army_counts:
        return ""
    non_scout_total = sum(
        cnt for k, cnt in army_counts.items() if k.lower() != "scout" and cnt and cnt > 0
    )
    if non_scout_total == 0 and army_counts.get("scout", 0) <= 1:
        return ""
    dist = format_army_distribution(army_counts)
    return f"Army: {dist}" if dist else ""


def _res_icon_img(icon_dir_rel: str, res_key: str) -> str:
    """Returns an inline <img> tag for one of the 4 standard AoE2 resources ('food', 'wood', 'gold', 'stone')."""
    names = {
        "food": ("food.png", "Food"),
        "wood": ("wood.png", "Wood"),
        "gold": ("gold.png", "Gold"),
        "stone": ("stone.png", "Stone"),
    }
    fname, alt = names[res_key]
    return f'<img src="{html.escape(icon_dir_rel)}/{fname}" alt="{alt}" title="{alt}" class="res-icon" width="15" height="15">'


def _replace_res_abbr_with_icons(escaped_text: str, icon_dir_rel: str) -> str:
    """
    Replaces numeric resource abbreviations (e.g. '-100W', '680F', '170G', '650+S', '84.4F')
    in already HTML-escaped text with the number followed by the standard AoE2 resource icon.
    """
    abbr_map = {
        "F": _res_icon_img(icon_dir_rel, "food"),
        "W": _res_icon_img(icon_dir_rel, "wood"),
        "G": _res_icon_img(icon_dir_rel, "gold"),
        "S": _res_icon_img(icon_dir_rel, "stone"),
    }

    def repl(match: re.Match) -> str:
        num_part = match.group(1)
        letter = match.group(2)
        return f"{num_part}{abbr_map[letter]}"

    return re.sub(r"([+-]?\d+(?:\.\d+)?\+?)([FWGS])\b", repl, escaped_text)


def _format_vils_pop_str(pop_str: str, fallback_vils: int = 0, fallback_mil: int = 1) -> str:
    """
    Normalizes population strings into 'Vils (Pop)' format without 'v' or 'pop' suffixes:
    - '23v (24 pop)' -> '23 (24)'
    - '4–6v (5–7 pop)' -> '4–6 (5–7)'
    - '18v' -> '18 (19)'
    """
    s = pop_str.strip()
    pop_re = re.compile(
        r"^(?:(\d+)[–-](\d+)|(\d+))v?(?:\s*\((?:(\d+)[–-](\d+)|(\d+))(?:\s*pop)?\))?$"
    )
    m = pop_re.match(s)
    if not m:
        return s
    v_start = m.group(1) or m.group(3)
    v_end = m.group(2) or m.group(3)
    pop_start = m.group(4) or m.group(6)
    pop_end = m.group(5) or m.group(6)
    v_part = f"{v_start}–{v_end}" if v_start != v_end else f"{v_start}"
    if pop_start and pop_end:
        p_part = f"{pop_start}–{pop_end}" if pop_start != pop_end else f"{pop_start}"
        return f"{v_part} ({p_part})"
    mil = max(1, fallback_mil)
    p1 = int(v_start) + mil
    p2 = int(v_end) + mil
    p_part = f"{p1}–{p2}" if p1 != p2 else f"{p1}"
    return f"{v_part} ({p_part})"


def _merge_pop_str(p1: str, p2: str) -> str:
    pop_re = re.compile(
        r"^(?:(\d+)[–-](\d+)|(\d+))v?(?:\s*\((?:(\d+)[–-](\d+)|(\d+))(?:\s*pop)?\))?$"
    )
    m1 = pop_re.match(p1.strip())
    m2 = pop_re.match(p2.strip())
    if not m1 or not m2:
        return p2 if p1 == p2 else f"{p1} -> {p2}"
    v_start = m1.group(1) or m1.group(3)
    v_end = m2.group(2) or m2.group(3)
    pop_start = m1.group(4) or m1.group(6)
    pop_end = m2.group(5) or m2.group(6)
    v_str = f"{v_start}–{v_end}" if v_start != v_end else f"{v_start}"
    if pop_start and pop_end:
        pop_str = f" ({pop_start}–{pop_end})" if pop_start != pop_end else f" ({pop_start})"
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

    norm_rows = [
        replace(
            r,
            pop=_format_vils_pop_str(
                r.pop,
                r.food_vils + r.wood_vils + r.gold_vils + r.stone_vils,
                sum(r.army_counts.values()),
            ),
        )
        for r in rows
    ]

    out: List[DetailedBuildRow] = [norm_rows[0]]
    for curr in norm_rows[1:]:
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
            r"^Queue (Light Cavalry|Genoese Crossbowman|Monk|Battering Ram|Archer|Militia) #(\d+)(?:[–-]#?(\d+))?(?: \(\d+ units\))? at ([^()]+) \((.+)\)\.$"
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


def _build_resource_chart_html(doc: BuildOrderDocument, tab_idx: int, icon_dir_rel: str) -> str:
    """
    Renders an interactive SVG chart of the Resource Bank (Food, Wood, Gold, Stone) over time,
    complete with age milestone lines, series toggle checkboxes, and two fixed-line hover readouts:
      1. Resource bank readout with standard AoE2 icons (always on its own line)
      2. Total Vils & Military counts, followed by Military Distribution (on the line below)
    """
    points: List[Dict[str, object]] = []
    if doc.resource_timeline:
        for p in doc.resource_timeline:
            raw_army = str(p.get("army", ""))
            clean_dist = re.sub(r"^Army:\s*", "", raw_army).strip()
            points.append(
                {
                    "t": int(p.get("t", 0)),
                    "ts": str(p.get("ts", "00:00")),
                    "food": round(float(p.get("food", 0))),
                    "wood": round(float(p.get("wood", 0))),
                    "gold": round(float(p.get("gold", 0))),
                    "stone": round(float(p.get("stone", 0))),
                    "vils": int(p.get("vils", 0)),
                    "mil": int(p.get("mil", 0)),
                    "army_dist": clean_dist or "None",
                }
            )
    else:
        for r in doc.rows:
            t_sec = _parse_mmss_to_sec(r.timestamp)
            vils_cnt = r.food_vils + r.wood_vils + r.gold_vils + r.stone_vils
            mil_cnt = sum(r.army_counts.values())
            points.append(
                {
                    "t": t_sec,
                    "ts": re.split(r"\s*[–-]\s*", r.timestamp.strip())[-1],
                    "food": round(r.bank_food),
                    "wood": round(r.bank_wood),
                    "gold": round(r.bank_gold),
                    "stone": round(r.bank_stone),
                    "vils": vils_cnt,
                    "mil": mil_cnt,
                    "army_dist": format_army_distribution(r.army_counts) or "None",
                }
            )

    if not points:
        return ""

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
    step_y = 200 if max_val_raw <= 1200 else 400
    max_y = max(step_y * 2, int(((max_val_raw + step_y - 1) // step_y) * step_y))

    width, height = 860, 290
    pad_l, pad_r, pad_t, pad_b = 52, 24, 28, 34
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    def x_of(t_val: float) -> float:
        return pad_l + (t_val / max_t) * plot_w

    def y_of(v_val: float) -> float:
        clamped = max(0.0, min(float(max_y), v_val))
        return pad_t + plot_h - (clamped / max_y) * plot_h

    y_grid_html = []
    num_y_ticks = max(2, max_y // step_y)
    for i in range(num_y_ticks + 1):
        val = i * step_y
        yp = y_of(val)
        y_grid_html.append(
            f'<line x1="{pad_l}" y1="{yp:.1f}" x2="{width - pad_r}" y2="{yp:.1f}" class="chart-grid-line" />'
            f'<text x="{pad_l - 8}" y="{yp + 4:.1f}" text-anchor="end" class="chart-axis-label">{val}</text>'
        )

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
    lanes_y = [20, 38, 56, 74]
    lane_right_x = [-999.0] * len(lanes_y)
    for m_sec, m_lbl in milestones:
        mx = x_of(m_sec)
        lbl_txt = f"{m_lbl} ({_fmt_sec_mmss(m_sec)})"
        est_w = len(lbl_txt) * 6.2 + 10.0
        if mx + est_w + 6 > width - pad_r:
            anchor = "end"
            tx = mx - 5.0
            box_x = mx - est_w - 2.0
            span_start = box_x
            span_end = mx
        else:
            anchor = "start"
            tx = mx + 5.0
            box_x = mx + 2.0
            span_start = mx
            span_end = mx + est_w + 2.0

        chosen_lane = 0
        for l_idx, right_x in enumerate(lane_right_x):
            if span_start >= right_x + 12.0:
                chosen_lane = l_idx
                break
        else:
            chosen_lane = min(range(len(lanes_y)), key=lambda i: lane_right_x[i])

        lane_right_x[chosen_lane] = span_end
        lbl_y = lanes_y[chosen_lane]
        milestone_svg.append(
            f'<line x1="{mx:.1f}" y1="{pad_t}" x2="{mx:.1f}" y2="{height - pad_b}" class="chart-milestone-line" />'
            f'<rect x="{box_x:.1f}" y="{lbl_y - 11:.1f}" width="{est_w:.1f}" height="15" rx="3" class="chart-milestone-bg" />'
            f'<text x="{tx:.1f}" y="{lbl_y:.1f}" text-anchor="{anchor}" class="chart-milestone-label">{html.escape(lbl_txt)}</text>'
        )

    def build_polyline(res_key: str) -> str:
        coords = [f"{x_of(float(p['t'])):.1f},{y_of(float(p[res_key])):.1f}" for p in cleaned_pts]
        return " ".join(coords)

    food_pts = build_polyline("food")
    wood_pts = build_polyline("wood")
    gold_pts = build_polyline("gold")
    stone_pts = build_polyline("stone")

    chart_id = f"res-chart-{tab_idx}"
    pts_json = html.escape(json.dumps(cleaned_pts))

    icon_f = _res_icon_img(icon_dir_rel, "food")
    icon_w = _res_icon_img(icon_dir_rel, "wood")
    icon_g = _res_icon_img(icon_dir_rel, "gold")
    icon_s = _res_icon_img(icon_dir_rel, "stone")

    last_pt = cleaned_pts[-1]
    last_vils = int(last_pt["vils"])
    last_mil = int(last_pt["mil"])
    last_pop = last_vils + last_mil
    last_dist = html.escape(str(last_pt["army_dist"]))

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
                        <span class="res-f">Food</span>{icon_f}
                    </label>
                    <label class="chart-series-toggle">
                        <input type="checkbox" checked data-chart-id="{chart_id}" data-series="wood">
                        <span class="swatch swatch-wood"></span>
                        <span class="res-w">Wood</span>{icon_w}
                    </label>
                    <label class="chart-series-toggle">
                        <input type="checkbox" checked data-chart-id="{chart_id}" data-series="gold">
                        <span class="swatch swatch-gold"></span>
                        <span class="res-g">Gold</span>{icon_g}
                    </label>
                    <label class="chart-series-toggle">
                        <input type="checkbox" checked data-chart-id="{chart_id}" data-series="stone">
                        <span class="swatch swatch-stone"></span>
                        <span class="res-s">Stone</span>{icon_s}
                    </label>
                </div>
                <div class="chart-readout mono" id="{chart_id}-readout">
                    <span>Time: <strong>{html.escape(str(last_pt['ts']))}</strong></span>
                    <span>|</span>
                    <span class="bank-item"><strong class="res-f">{last_pt['food']}</strong>{icon_f}</span>
                    <span>&middot;</span>
                    <span class="bank-item"><strong class="res-w">{last_pt['wood']}</strong>{icon_w}</span>
                    <span>&middot;</span>
                    <span class="bank-item"><strong class="res-g">{last_pt['gold']}</strong>{icon_g}</span>
                    <span>&middot;</span>
                    <span class="bank-item"><strong class="res-s">{last_pt['stone']}</strong>{icon_s}</span>
                </div>
                <div class="chart-pop-readout mono" id="{chart_id}-pop-readout">
                    <span>Total Vils: <strong>{last_vils}</strong> &middot; Military: <strong>{last_mil}</strong> (<strong>{last_pop}</strong> Pop)</span>
                    <span>|</span>
                    <span>Military Distribution: <span class="army-badge">{last_dist}</span></span>
                </div>
            </div>
            <div class="chart-svg-wrap">
                <svg id="{chart_id}" class="resource-chart-svg" viewBox="0 0 {width} {height}"
                     role="img" aria-label="Resource bank over time chart for {html.escape(doc.variant_label)}"
                     data-points="{pts_json}" data-max-t="{max_t}" data-max-y="{max_y}"
                     data-pad-l="{pad_l}" data-pad-r="{pad_r}" data-pad-t="{pad_t}" data-pad-b="{pad_b}"
                     data-width="{width}" data-height="{height}"
                     data-icon-dir="{html.escape(icon_dir_rel)}">
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
    repo_root = Path(__file__).resolve().parent.parent
    shared_css_path = repo_root / "styles" / "build_order.css"
    shared_icons_dir = repo_root / "styles" / "icons"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    css_rel_path = os.path.relpath(shared_css_path, output_path.parent).replace("\\", "/")
    icon_dir_rel = os.path.relpath(shared_icons_dir, output_path.parent).replace("\\", "/")

    icon_f = _res_icon_img(icon_dir_rel, "food")
    icon_w = _res_icon_img(icon_dir_rel, "wood")
    icon_g = _res_icon_img(icon_dir_rel, "gold")
    icon_s = _res_icon_img(icon_dir_rel, "stone")

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
                action_html = _replace_res_abbr_with_icons(html.escape(r.action), icon_dir_rel)
                notes_body_html = _replace_res_abbr_with_icons(html.escape(r.notes), icon_dir_rel)
                notes_html = f"{army_badge_html}{notes_body_html}"
                bank_cell_html = (
                    f'<span class="bank-item"><span class="res-f">{r.bank_food:.0f}</span>{icon_f}</span>'
                    f'<span class="bank-sep">/</span>'
                    f'<span class="bank-item"><span class="res-w">{r.bank_wood:.0f}</span>{icon_w}</span>'
                    f'<span class="bank-sep">/</span>'
                    f'<span class="bank-item"><span class="res-g">{r.bank_gold:.0f}</span>{icon_g}</span>'
                    f'<span class="bank-sep">/</span>'
                    f'<span class="bank-item"><span class="res-s">{r.bank_stone:.0f}</span>{icon_s}</span>'
                )
                rows_html.append(
                    f"""
                    <tr>
                        <td class="mono center">{html.escape(r.pop)}</td>
                        <td class="mono center">{html.escape(r.timestamp)}</td>
                        <td>{action_html}</td>
                        <td class="mono center res-f-sub">{fmt_sub(r.sheep_vils)}</td>
                        <td class="mono center res-f-sub">{fmt_sub(r.boar_vils)}</td>
                        <td class="mono center res-f-sub">{fmt_sub(deer_or_chk)}</td>
                        <td class="mono center res-f-sub">{fmt_sub(r.berry_vils)}</td>
                        <td class="mono center res-f-sub">{fmt_sub(r.farm_vils)}</td>
                        <td class="mono center res-f">{r.food_vils}</td>
                        <td class="mono center res-w">{r.wood_vils}</td>
                        <td class="mono center res-g">{r.gold_vils}</td>
                        <td class="mono center res-s">{r.stone_vils}</td>
                        <td class="mono center bank-cell">{bank_cell_html}</td>
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
                                        <th rowspan="2" class="center">Vils/Pop</th>
                                        <th rowspan="2" class="center">Time</th>
                                        <th rowspan="2">Villager Assignment / Action</th>
                                        <th colspan="6" class="center food-group-hdr">Food Villagers Breakdown</th>
                                        <th rowspan="2" class="center">Wood {icon_w}</th>
                                        <th rowspan="2" class="center">Gold {icon_g}</th>
                                        <th rowspan="2" class="center">Stone {icon_s}</th>
                                        <th rowspan="2" class="center">Resource Bank</th>
                                        <th rowspan="2">Notes, Buildings &amp; Army</th>
                                    </tr>
                                    <tr>
                                        <th class="center sub-hdr">Sheep</th>
                                        <th class="center sub-hdr">Boar</th>
                                        <th class="center sub-hdr">Deer/Chk</th>
                                        <th class="center sub-hdr">Berries</th>
                                        <th class="center sub-hdr">Farms</th>
                                        <th class="center sub-hdr">Total {icon_f}</th>
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
                f"Sheep: {rot_info.get('sheep', 0)}{icon_f} &middot; "
                f"Boar: {rot_info.get('boar', 0)}{icon_f} &middot; "
                f"Deer: {rot_info.get('deer', 0)}{icon_f} &middot; "
                f"Chicken: {rot_info.get('chicken', 0)}{icon_f} "
                f"(Total Rot: <strong>{tot_rot}</strong>{icon_f})"
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
                            <span class="res-f">{rec.get('food', 0)} Food</span>{icon_f} &middot;
                            <span class="res-w">{rec.get('wood', 0)} Wood</span>{icon_w} &middot;
                            <span class="res-g">{rec.get('gold', 0)} Gold</span>{icon_g} &middot;
                            <span class="res-s">{rec.get('stone', 0)} Stone</span>{icon_s}
                            (Total: <strong>{rec.get('total', 0)}</strong> vils; exact:
                            {ex.get('food', 0)}{icon_f} / {ex.get('wood', 0)}{icon_w} / {ex.get('gold', 0)}{icon_g} / {ex.get('stone', 0)}{icon_s})
                        </p>
                        {f'<p><strong>Simulated Animal Rot Telemetry:</strong> {rot_str}</p>' if rot_str else ''}
                        {final_army_html}
                    </div>
                </div>
            </details>
            """

        chart_html = _build_resource_chart_html(doc, idx, icon_dir_rel)

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
                <p class="desc">{_replace_res_abbr_with_icons(html.escape(doc.description), icon_dir_rel)}</p>
                {ss_html}
                {chart_html}
                {''.join(phase_sections_html)}
            </section>
            """
        )

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

        // 4. Interactive Resource Bank Chart: Series Toggles & Dual-Line Hover Readout
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
            const iconDir = svg.getAttribute('data-icon-dir') || '../../styles/icons';
            const plotW = width - padL - padR;
            const plotH = height - padT - padB;

            const hline = document.getElementById(`${{svg.id}}-hline`);
            const dotF = document.getElementById(`${{svg.id}}-dot-food`);
            const dotW = document.getElementById(`${{svg.id}}-dot-wood`);
            const dotG = document.getElementById(`${{svg.id}}-dot-gold`);
            const dotS = document.getElementById(`${{svg.id}}-dot-stone`);
            const readout = document.getElementById(`${{svg.id}}-readout`);
            const popReadout = document.getElementById(`${{svg.id}}-pop-readout`);

            const iconHtml = (res, alt) =>
                `<img src="${{iconDir}}/${{res}}.png" alt="${{alt}}" title="${{alt}}" class="res-icon" width="15" height="15">`;

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
                    readout.innerHTML =
                        `<span>Time: <strong>${{best.ts}}</strong></span>` +
                        `<span>|</span>` +
                        `<span class="bank-item"><strong class="res-f">${{best.food}}</strong>${{iconHtml('food', 'Food')}}</span>` +
                        `<span>&middot;</span>` +
                        `<span class="bank-item"><strong class="res-w">${{best.wood}}</strong>${{iconHtml('wood', 'Wood')}}</span>` +
                        `<span>&middot;</span>` +
                        `<span class="bank-item"><strong class="res-g">${{best.gold}}</strong>${{iconHtml('gold', 'Gold')}}</span>` +
                        `<span>&middot;</span>` +
                        `<span class="bank-item"><strong class="res-s">${{best.stone}}</strong>${{iconHtml('stone', 'Stone')}}</span>`;
                }}
                if (popReadout) {{
                    const vils = best.vils || 0;
                    const mil = best.mil || 0;
                    const pop = vils + mil;
                    const dist = best.army_dist || 'None';
                    popReadout.innerHTML =
                        `<span>Total Vils: <strong>${{vils}}</strong> &middot; Military: <strong>${{mil}}</strong> (<strong>${{pop}}</strong> Pop)</span>` +
                        `<span>|</span>` +
                        `<span>Military Distribution: <span class="army-badge">${{dist}}</span></span>`;
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

#!/usr/bin/env python3
"""
Generator & 1-Second Discrete-Event Simulator for:
Italians Arena Fast Castle Build Orders (3 Deer Pushed, No Chickens)

Refactored into 2 distinct strategies displayed in top-level HTML tabs + separate JSONs:
1. Strategy 1: 1 TC Heavy Army Push (`1tc_push`):
   - 26+2 FC -> Defensive Castle (0s wait <= 10s max on Castle arrival) -> Genoese + Light Cav
   - Early Wood upgrades (Double-Bit Axe, Bow Saw), Horse Collar, Archer & Cav upgrades
   - Monastery + 2 Monks (conservatively assume max 1 Relic secured = +30G/min)
   - Never idle TC for military; occasional brief military pauses allowed to keep TC continuous
   - At 30+ army: Forward Siege Workshop + 3-4 Battering Rams to push
   - Stick strictly to 1 TC until clicking Imperial Age, then add TC #2 & TC #3 after Imp click
   - Occasional Market usage per rules.md (~70G Feudal, ~50G early-mid Castle, ~30G late Castle, ~15G Imp)

2. Strategy 2: Balanced 3 TC Boom (`3tc_balanced`):
   - 26+2 FC -> Defensive Castle (0s wait <= 10s max on Castle arrival) -> ~20 army (10-15 Genoese, 6-10 Light Cav)
   - Early Wood upgrades (Double-Bit Axe, Bow Saw), Horse Collar, Archer & Cav upgrades
   - Pause/slow military at ~20 army -> Expand to 3 TCs and prioritize Villagers until 3-TC continuous vils are set up
   - Then maximize army production with full upgrades (Blacksmith, Pavise, Silk Armor, Ballistics, Hussar, Elite Genoese, BBCs, Trebs)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))
sys.path.insert(0, str(THIS_DIR.parents[1] / "scripts"))

from aoe2_data import ResourceBundle
from backward_planner import BackwardPlanner, ContinuousProductionItem
from exporters import (
    BuildOrderDocument,
    DetailedBuildRow,
    RTS_ICONS,
    RTSOverlayStep,
    export_build_order_html,
    export_rts_overlay_json,
    format_army_counts,
)
from sim_italians_arena_fc_genoese import ItaliansArenaSimulator

OUT_DIR = THIS_DIR


def run_italians_arena_strategy(strategy: str) -> Tuple[BuildOrderDocument, Dict[str, object]]:
    """
    Runs a 1-second resolution simulation for either:
      - strategy == "1tc_push"
      - strategy == "3tc_balanced"
    """
    if strategy not in ("1tc_push", "3tc_balanced"):
        raise ValueError(f"Unknown strategy: {strategy}")

    is_1tc = strategy == "1tc_push"
    dark_vils = 26
    sim = ItaliansArenaSimulator(dark_vils=dark_vils)
    planner = BackwardPlanner(sim.db, sim.rules)

    variant_label = (
        "Strategy 1: 1 TC Heavy Army Push (Genoese + Light Cav + Monks + Rams -> Imp TCs)"
        if is_1tc
        else "Strategy 2: Balanced 3 TC Boom (~20 Army -> 3 TCs -> Max Upgraded Army)"
    )

    rows: List[DetailedBuildRow] = []
    resource_timeline: List[Dict[str, object]] = []
    milestones: Dict[str, object] = {
        "strategy": strategy,
        "variant": variant_label,
        "dark_vils": dark_vils,
        "castle_click_vils": dark_vils + 2,
    }

    def total_pop() -> int:
        return len(sim.vils) + sum(sim.military_units.values())

    def army_combat_count() -> int:
        return (
            sim.military_units["genoese"]
            + sim.military_units["light_cav"]
            + sim.military_units["monk"]
            + sim.military_units["battering_ram"]
            + sim.military_units["trebuchet"]
            + sim.military_units["bombard_cannon"]
        )

    def record_timeline_point() -> None:
        resource_timeline.append(
            {
                "t": sim.time_s,
                "ts": sim.fmt_time(),
                "food": round(sim.bank.food),
                "wood": round(sim.bank.wood),
                "gold": round(sim.bank.gold),
                "stone": round(sim.bank.stone),
                "vils": len(sim.vils),
                "mil": sum(sim.military_units.values()),
                "army": format_army_counts(sim.military_units),
            }
        )

    def add_row(pop_str: str, phase: str, action: str, notes: str = "") -> None:
        alloc = sim.current_macro_alloc()
        fb = sim.current_food_breakdown()
        rows.append(
            DetailedBuildRow(
                pop=pop_str,
                timestamp=sim.fmt_time(),
                age=phase,
                action=action,
                food_vils=alloc["food"],
                wood_vils=alloc["wood"],
                gold_vils=alloc["gold"],
                stone_vils=alloc["stone"],
                bank_food=sim.bank.food,
                bank_wood=sim.bank.wood,
                bank_gold=sim.bank.gold,
                bank_stone=sim.bank.stone,
                notes=notes,
                sheep_vils=fb["sheep"],
                boar_vils=fb["boar"],
                deer_vils=fb["deer"],
                chicken_vils=fb["chicken"],
                berry_vils=fb["berries"],
                farm_vils=fb["farm"],
                army_counts=dict(sim.military_units),
            )
        )
        record_timeline_point()

    # t = 0:00 initial state (3 vils build 2 houses, TC queues Vil 4)
    sim.bank = sim.bank - ResourceBundle(food=50)
    sim.tc_busy_until[0] = 25
    sim.tc_action[0] = "vil_4"
    sim.lc_count = 0
    add_row(
        "3v (4 pop)",
        "Dark Age",
        "Vils 1-2 build House #1 (18.75s), Vil 3 builds House #2 (25s), then gather Sheep (5s return walk). Queue Vil #4.",
        "Start: 200F, 200W, 100G, 200S (-50F Vil 4, -50W 2 Houses). Push 3 Deer inside Arena walls; delay Loom.",
    )

    feudal_clicked = False
    feudal_vils_queued = 0
    market_started = False
    market_ready_t: Optional[int] = None
    bs_started = False
    bs_ready_t: Optional[int] = None
    stone_sold = False
    castle_clicked = False
    castle_click_t = 0
    castle_reached_t: Optional[int] = None

    dba_started = False
    hc_started = False
    gold_mc_started = False
    gold_mining_started = False
    lc2_rebuilt = False
    lc3_rebuilt = False
    lc4_rebuilt = False
    lc5_rebuilt = False
    farms_seeded = 0
    houses_built = 5
    house_busy_until = 0

    def_castle_started = False
    def_castle_ready_t: Optional[int] = None
    castle_count = 0
    castle_busy_until: List[int] = [0, 0, 0]

    bow_saw_started = False
    two_man_saw_started = False
    fletching_started = False
    bodkin_started = False
    bracer_started = False
    padded_archer_started = False
    leather_archer_started = False
    ring_archer_started = False

    bloodlines_started = False
    husbandry_started = False
    scale_barding_started = False
    chain_barding_started = False
    plate_barding_started = False
    forging_started = False
    iron_casting_started = False
    blast_furnace_started = False
    pavise_started = False
    silk_armor_started = False

    barracks_started = False
    barracks_ready_t: Optional[int] = None
    stable_started = False
    stable_ready_t: Optional[int] = None
    stable_count = 0
    stable_busy_until: List[int] = [0, 0, 0, 0, 0, 0]
    lcav_upg_started = False

    monastery_started = False
    monastery_ready_t: Optional[int] = None
    monastery_busy_until = 0
    monks_trained = 0
    relic1_time: Optional[int] = None

    loom_started = False
    wheelbarrow_started = False
    heavy_plow_started = False
    crop_rotation_started = False
    hand_cart_started = False
    gold_shaft_started = False
    stone_mining_started = False
    stone_shaft_started = False
    stone_adjusted_early = False

    army20_reached = False
    boom3tc_ready_logged = False

    army30_reached = False
    fwd_sw_dispatched = False
    fwd_sw_arrive_t: Optional[int] = None
    rams_trained = 0
    capped_ram_started = False

    tc2_started = False
    tc2_ready_t: Optional[int] = None
    tc3_started = False
    tc3_ready_t: Optional[int] = None
    tc4_started = False
    tc4_ready_t: Optional[int] = None

    univ_started = False
    univ_ready_t: Optional[int] = None
    ballistics_started = False
    ballistics_ready_t: Optional[int] = None
    masonry_started = False
    chemistry_started = False
    chemistry_ready_t: Optional[int] = None
    siege_engineers_started = False

    fwd_vils_dispatched = False
    fwd_vils_arrive_t: Optional[int] = None
    fwd_castle2_started = False
    fwd_castle2_ready_t: Optional[int] = None
    fwd_castle3_started = False
    fwd_castle3_ready_t: Optional[int] = None
    fwd_sw1_started = False
    fwd_sw1_ready_t: Optional[int] = None
    fwd_sw2_started = False
    fwd_sw2_ready_t: Optional[int] = None
    sw_busy_until: List[int] = [0, 0]

    imp_clicked = False
    imp_click_t = 0
    conscription_started = False
    elite_genoese_started = False
    hussar_started = False
    treb_count_trained = 0
    bbc_count_trained = 0
    market_trades_castle = 0
    last_market_trade_t = -999
    target_vils_logged = False

    max_sim_t = 2700
    for t in range(1, max_sim_t + 1):
        sim.time_s = t
        current_phase = (
            "Dark Age"
            if (sim.age == 1 and not feudal_clicked)
            else "Feudal Transition"
            if (sim.age == 1 and feudal_clicked)
            else "Feudal Age"
            if (sim.age == 2 and not castle_clicked)
            else "Castle Transition"
            if (sim.age == 2 and castle_clicked)
            else "Castle Age"
            if (sim.age == 3 and not imp_clicked)
            else "Imperial Transition"
            if (sim.age == 3 and imp_clicked)
            else "Imperial Age"
        )

        # Track TC #1 idle time prior to Imperial Click
        if not imp_clicked and sim.tc_action[0] == "idle":
            sim.tc1_idle_before_imp_s += 1

        # Boar #1 + Sheep #4 transition
        if t >= 205 and sim.remaining_animals["sheep"] == 4 and sim.active_carcass_food["sheep"] <= 1e-6:
            for v in sim.vils:
                if v["role"] == "sheep":
                    v["role"] = "boar"

        # Boar #2 lure at t=283 (04:43)
        if t == 283:
            for v in sim.vils:
                if v["role"] == "boar":
                    v["busy_until"] = t + 30
                    break

        # Strategy 1: Only assume 1 Relic is secured!
        if is_1tc and relic1_time is not None and t == relic1_time:
            sim.relics_garrisoned = 1
            milestones["relic1_str"] = sim.fmt_time(t)
            add_row(
                f"{len(sim.vils)}v ({total_pop()} pop)",
                current_phase,
                "Monk #1 garrisons Relic #1 in Monastery (+30 Gold/min; conservatively assume max 1 Relic secured).",
                "Monk #2 contests remaining Relics, but build assumes only 1 Relic (+0.50 G/s).",
            )

        # Check TC completions
        for tc_idx in range(sim.tc_count):
            if t == sim.tc_busy_until[tc_idx] and sim.tc_action[tc_idx] != "idle":
                act = sim.tc_action[tc_idx]
                sim.tc_action[tc_idx] = "idle"

                if act.startswith("vil_"):
                    vid = len(sim.vils) + 1
                    action_text = ""
                    note_text = ""

                    if sim.age == 1:
                        if vid in (4, 5, 6):
                            sim.vils.append({"id": vid, "role": "sheep", "busy_until": t})
                            action_text = f"Vil #{vid} -> Sheep under TC (0s walk)"
                            if vid == 6:
                                note_text = "6/6 ideal vils on Sheep."
                        elif vid == 7:
                            sim.bank = sim.bank - ResourceBundle(wood=100)
                            sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 50})
                            sim.lc_completed_s = t + 50
                            sim.lc_count = 1
                            action_text = "Vil #7 -> Walk 15s + Build Lumber Camp #1 (-100W, 35s) -> Wood"
                            note_text = "LC #1 completes at 02:30 (100% wood efficiency; -1% decay per 20s)."
                        elif vid in (8, 9):
                            sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 15})
                            action_text = f"Vil #{vid} -> Wood at Lumber Camp #1 (15s walk)"
                        elif vid == 10:
                            sim.vils.append({"id": vid, "role": "boar", "busy_until": t + 30})
                            action_text = "Vil #10 -> Lure Boar #1 (15s walk out + 15s lure back)"
                            note_text = "Boar #1 arrives under TC at 03:25; 6 shepherds finish Sheep #4 at 03:34 then join Boar #1."
                        elif vid == 11:
                            sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 15})
                            action_text = "Vil #11 -> Wood at Lumber Camp #1 (15s walk)"
                            note_text = "4/4 initial vils on Wood."
                        elif vid == 12:
                            sim.bank = sim.bank - ResourceBundle(wood=25)
                            sim.vils.append({"id": vid, "role": "deer", "busy_until": t + 35})
                            action_text = "Vil #12 -> Build House #3 (-25W, 5s+25s+5s) -> Pushed Deer #1 under TC"
                            note_text = "Start harvesting 3 Pushed Deer under TC (no Chickens)."
                        elif vid in (13, 14, 15):
                            sim.vils.append({"id": vid, "role": "deer", "busy_until": t})
                            action_text = f"Vil #{vid} -> Pushed Deer under TC (0s walk)"
                            if vid == 15:
                                note_text = "7 on Boar + 4 on Pushed Deer. At 04:43, 1 hunter lures Boar #2 (arrives 05:13)."
                        elif vid == 16:
                            sim.bank = sim.bank - ResourceBundle(wood=100)
                            sim.vils.append({"id": vid, "role": "berries", "busy_until": t + 50})
                            action_text = "Vil #16 -> Walk 15s + Build Mill on Berries (-100W, 35s) -> Berries"
                        elif vid == 17:
                            sim.vils.append({"id": vid, "role": "berries", "busy_until": t + 15})
                            action_text = "Vil #17 -> Berries at Mill (15s walk)"
                        elif vid == 18:
                            sim.bank = sim.bank - ResourceBundle(wood=25)
                            sim.vils.append({"id": vid, "role": "berries", "busy_until": t + 45})
                            action_text = "Vil #18 -> Build House #4 (-25W, 30s) -> Berries at Mill (15s walk)"
                        elif vid == 19:
                            sim.vils.append({"id": vid, "role": "berries", "busy_until": t + 15})
                            action_text = "Vil #19 -> Berries at Mill (15s walk; 4/4 on Berries)"
                        elif vid == 20:
                            sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 15})
                            action_text = "Vil #20 -> Wood at Lumber Camp #1 (15s walk; 5 on Wood)"
                        elif vid == 21:
                            sim.bank = sim.bank - ResourceBundle(wood=100)
                            sim.vils.append({"id": vid, "role": "stone", "busy_until": t + 50})
                            action_text = "Vil #21 -> Walk 15s + Build Mining Camp on Stone (-100W, 35s) -> Stone"
                            note_text = "Stone MC finishes at 08:20."
                        elif vid in (22, 23):
                            sim.vils.append({"id": vid, "role": "stone", "busy_until": t + 15})
                            s_cnt = sum(1 for v in sim.vils if v["role"] == "stone")
                            action_text = f"Vil #{vid} -> Stone at Mining Camp (15s walk; {s_cnt}/4 on Stone)"
                        elif vid == 24:
                            sim.bank = sim.bank - ResourceBundle(wood=25)
                            sim.vils.append({"id": vid, "role": "stone", "busy_until": t + 45})
                            action_text = "Vil #24 -> Build House #5 (-25W, 30s) -> Stone at Mining Camp (15s walk; 4/4 on Stone)"
                            note_text = "4/4 Dark Age Stone miners active for Castle drop on Castle Age arrival."
                        elif vid in (25, 26):
                            sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 15})
                            w_cnt = sum(1 for v in sim.vils if v["role"] == "wood")
                            action_text = f"Vil #{vid} -> Wood at Lumber Camp #1 (15s walk; {w_cnt}/7 on Wood)"
                            if vid == 26:
                                note_text = "26 Dark Age vils complete (7 on LC #1 <= 8 max); click Feudal Age (425F) with 0s TC idle."

                        if vid < dark_vils:
                            sim.bank = sim.bank - ResourceBundle(food=50)
                            sim.tc_busy_until[0] = t + 25
                            sim.tc_action[0] = f"vil_{vid+1}"
                        add_row(f"{len(sim.vils)}v ({total_pop()} pop)", current_phase, action_text, note_text)

                    elif sim.age == 2:
                        if not gold_mc_started:
                            gold_mc_started = True
                            sim.bank = sim.bank - ResourceBundle(wood=100)
                            sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 50})
                            action_text = f"Vil #{vid} -> Walk 15s + Build Mining Camp on Gold (-100W, 35s) -> Gold"
                            note_text = "1st of +2 Feudal villagers establishes Gold Mining Camp."
                        else:
                            sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                            action_text = f"Vil #{vid} -> Gold at Mining Camp (15s walk)"
                            note_text = "2nd of +2 Feudal villagers complete! Market & Blacksmith finish simultaneously."
                        add_row(f"{len(sim.vils)}v ({total_pop()} pop)", current_phase, action_text, note_text)

                    else:
                        g_cnt = sum(1 for v in sim.vils if v["role"] == "gold")
                        w_cnt = sum(1 for v in sim.vils if v["role"] in ("wood", "straggler"))
                        f_cnt = sum(1 for v in sim.vils if v["role"] == "farm")
                        s_cnt = sum(1 for v in sim.vils if v["role"] == "stone")

                        if is_1tc:
                            saving_wood_for_bldg = (
                                (not monastery_started and sim.bank.wood < 175)
                                or (army_combat_count() >= 18 and not univ_started and sim.bank.wood < 200)
                                or (univ_ready_t is not None and t >= univ_ready_t and not ballistics_started and sim.bank.wood < 201)
                                or (army30_reached and not fwd_sw1_started and sim.bank.wood < 200)
                                or (imp_clicked and not tc2_started and sim.bank.stone >= 100 and sim.bank.wood < 275)
                                or (imp_clicked and tc2_started and not tc3_started and sim.bank.stone >= 100 and sim.bank.wood < 275)
                            )
                            gold_target = 7 if not imp_clicked else (14 if len(sim.vils) < 75 else 22)
                            farm_target_early = 15 if not imp_clicked else 28
                            wood_target_early = 16 if not imp_clicked else 32
                            stone_target = 2 if not imp_clicked else 2

                            if f_cnt < 12 and sim.bank.wood >= 60 and not saving_wood_for_bldg:
                                sim.bank = sim.bank - ResourceBundle(wood=60)
                                farms_seeded += 1
                                sim.register_new_farm()
                                sim.vils.append({"id": vid, "role": "farm", "busy_until": t + 20})
                                action_text = f"Vil #{vid} (TC #{tc_idx+1}) -> Seed Farm #{farms_seeded} (-60W; {f_cnt+1} Farms)"
                            elif w_cnt < wood_target_early:
                                sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 15})
                                action_text = f"Vil #{vid} (TC #{tc_idx+1}) -> Wood ({w_cnt+1} on Wood)"
                            elif g_cnt < gold_target and sim.bank.gold < 600:
                                sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                                action_text = f"Vil #{vid} (TC #{tc_idx+1}) -> Gold ({g_cnt+1}/{gold_target} on Gold)"
                            elif f_cnt < farm_target_early and sim.bank.wood >= 60 and not saving_wood_for_bldg:
                                sim.bank = sim.bank - ResourceBundle(wood=60)
                                farms_seeded += 1
                                sim.register_new_farm()
                                sim.vils.append({"id": vid, "role": "farm", "busy_until": t + 20})
                                action_text = f"Vil #{vid} (TC #{tc_idx+1}) -> Seed Farm #{farms_seeded} (-60W; {f_cnt+1} Farms)"
                            elif s_cnt < stone_target and sim.bank.stone < 250:
                                sim.vils.append({"id": vid, "role": "stone", "busy_until": t + 15})
                                action_text = f"Vil #{vid} (TC #{tc_idx+1}) -> Stone ({s_cnt+1}/{stone_target} on Stone)"
                            elif f_cnt < 34 and sim.bank.wood >= 60 and not saving_wood_for_bldg and sim.bank.food < 1100:
                                sim.bank = sim.bank - ResourceBundle(wood=60)
                                farms_seeded += 1
                                sim.register_new_farm()
                                sim.vils.append({"id": vid, "role": "farm", "busy_until": t + 20})
                                action_text = f"Vil #{vid} (TC #{tc_idx+1}) -> Seed Farm #{farms_seeded} (-60W; {f_cnt+1} Farms)"
                            elif g_cnt < 24 and sim.bank.gold < 750:
                                sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                                action_text = f"Vil #{vid} (TC #{tc_idx+1}) -> Gold ({g_cnt+1} on Gold)"
                            else:
                                sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 15})
                                action_text = f"Vil #{vid} (TC #{tc_idx+1}) -> Wood ({w_cnt+1} on Wood)"

                            if sim.tc_count == 1:
                                add_row(f"{len(sim.vils)}v ({total_pop()} pop)", current_phase, action_text, note_text)
                            elif vid in (65, 85, 100):
                                add_row(
                                    f"Wave -> {len(sim.vils)}v ({total_pop()} pop)",
                                    current_phase,
                                    f"Post-Imp-Click 3-TC Boom reaches {len(sim.vils)} Villagers ({f_cnt} Farms, {w_cnt} Wood, {g_cnt} Gold, {s_cnt} Stone).",
                                    "Sustains full Imperial upgrades + continuous Genoese, Hussars & Bombard Cannons.",
                                )
                        else:
                            # Strategy 2 (Balanced 3 TC Boom)
                            saving_wood_for_bldg = (
                                (army20_reached and not tc2_started and sim.bank.stone >= 80 and sim.bank.wood < 275)
                                or (tc2_started and not tc3_started and sim.bank.stone >= 90 and sim.bank.wood < 275)
                                or (boom3tc_ready_logged and not univ_started and sim.bank.wood < 200)
                                or (univ_ready_t is not None and t >= univ_ready_t and not ballistics_started and sim.bank.wood < 201)
                                or (fwd_vils_arrive_t is not None and t >= fwd_vils_arrive_t and not tc4_started and sim.bank.stone >= 100 and sim.bank.wood < 275)
                            )
                            gold_target_early = 6 if not army20_reached else (5 if not boom3tc_ready_logged else 15)
                            if f_cnt < 12 and sim.bank.wood >= 60 and not saving_wood_for_bldg:
                                sim.bank = sim.bank - ResourceBundle(wood=60)
                                farms_seeded += 1
                                sim.register_new_farm()
                                sim.vils.append({"id": vid, "role": "farm", "busy_until": t + 20})
                                action_text = f"Vil #{vid} (TC #{tc_idx+1}) -> Seed Farm #{farms_seeded} (-60W; {f_cnt+1} Farms)"
                            elif g_cnt < gold_target_early and sim.bank.gold < 260:
                                sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                                action_text = f"Vil #{vid} (TC #{tc_idx+1}) -> Gold ({g_cnt+1}/{gold_target_early} on Gold)"
                            elif w_cnt < 14:
                                sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 15})
                                action_text = f"Vil #{vid} (TC #{tc_idx+1}) -> Wood ({w_cnt+1} on Wood)"
                            elif f_cnt < 22 and sim.bank.wood >= 60 and not saving_wood_for_bldg:
                                sim.bank = sim.bank - ResourceBundle(wood=60)
                                farms_seeded += 1
                                sim.register_new_farm()
                                sim.vils.append({"id": vid, "role": "farm", "busy_until": t + 20})
                                action_text = f"Vil #{vid} (TC #{tc_idx+1}) -> Seed Farm #{farms_seeded} (-60W; {f_cnt+1} Farms)"
                            elif tc3_ready_t is not None and t >= tc3_ready_t and len(sim.vils) >= 48 and s_cnt < 6 and not fwd_castle3_started and sim.bank.stone < 800:
                                sim.vils.append({"id": vid, "role": "stone", "busy_until": t + 15})
                                action_text = f"Vil #{vid} (TC #{tc_idx+1}) -> Stone ({s_cnt+1}/6 on Stone for Forward Castles & TC #4)"
                            elif w_cnt < 28:
                                sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 15})
                                action_text = f"Vil #{vid} (TC #{tc_idx+1}) -> Wood ({w_cnt+1} on Wood)"
                            elif f_cnt < 30 and sim.bank.wood >= 60 and not saving_wood_for_bldg:
                                sim.bank = sim.bank - ResourceBundle(wood=60)
                                farms_seeded += 1
                                sim.register_new_farm()
                                sim.vils.append({"id": vid, "role": "farm", "busy_until": t + 20})
                                action_text = f"Vil #{vid} (TC #{tc_idx+1}) -> Seed Farm #{farms_seeded} (-60W; {f_cnt+1} Farms)"
                            elif g_cnt < 22 and f_cnt >= 22 and sim.bank.gold < 750:
                                sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                                action_text = f"Vil #{vid} (TC #{tc_idx+1}) -> Gold ({g_cnt+1} on Gold)"
                            elif w_cnt < 42:
                                sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 15})
                                action_text = f"Vil #{vid} (TC #{tc_idx+1}) -> Wood ({w_cnt+1} on Wood)"
                            elif f_cnt < 44 and sim.bank.wood >= 60 and not saving_wood_for_bldg and sim.bank.food < 1100:
                                sim.bank = sim.bank - ResourceBundle(wood=60)
                                farms_seeded += 1
                                sim.register_new_farm()
                                sim.vils.append({"id": vid, "role": "farm", "busy_until": t + 20})
                                action_text = f"Vil #{vid} (TC #{tc_idx+1}) -> Seed Farm #{farms_seeded} (-60W; {f_cnt+1} Farms)"
                            else:
                                sim.vils.append({"id": vid, "role": "gold" if sim.bank.gold < 750 else "wood", "busy_until": t + 15})
                                action_text = f"Vil #{vid} (TC #{tc_idx+1}) -> Outside Gold/Wood"

                            if sim.tc_count == 1:
                                add_row(f"{len(sim.vils)}v ({total_pop()} pop)", current_phase, action_text, note_text)
                            elif vid == 50:
                                add_row(
                                    f"-> 50v ({total_pop()} pop)",
                                    current_phase,
                                    f"3-TC Boom reaches 50 Villagers ({f_cnt} Farms, {w_cnt} Wood, {g_cnt} Gold, {s_cnt} Stone).",
                                    "Continuous 3-TC villager production running smoothly.",
                                )
                            elif vid == 75:
                                add_row(
                                    f"-> 75v ({total_pop()} pop)",
                                    current_phase,
                                    f"3-TC Boom reaches 75 Villagers ({f_cnt} Farms, {w_cnt} Wood, {g_cnt} Gold, {s_cnt} Stone).",
                                    "Full Castle upgrades & multi-building military scaling.",
                                )
                            elif vid == 105:
                                add_row(
                                    f"-> 105v ({total_pop()} pop)",
                                    current_phase,
                                    f"4-TC Boom reaches 105 Villagers ({f_cnt} Farms, {w_cnt} Wood, {g_cnt} Gold, {s_cnt} Stone).",
                                    "Outside TC #4 fueling Imperial upgrades and multi-building flood.",
                                )
                            elif vid == 130 and not target_vils_logged:
                                target_vils_logged = True
                                milestones["vils_130_reached_str"] = sim.fmt_time(t)
                                add_row(
                                    f"-> 130v ({total_pop()} pop)",
                                    current_phase,
                                    f"130 VILLAGER TARGET REACHED ({f_cnt} Farms, {w_cnt} Wood, {g_cnt} Gold, {s_cnt} Stone)!",
                                    "Full 130-villager economy supporting 200/200 pop max-upgraded army!",
                                )

                elif act == "feudal":
                    sim.age = 2
                    current_phase = "Feudal Age"
                    milestones["feudal_reached_s"] = t
                    milestones["feudal_reached_str"] = sim.fmt_time(t)
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        "Feudal Age",
                        "REACHED FEUDAL AGE! Queue 1st Feudal Vil (-50F, 25s -> builds Gold Mining Camp).",
                        f"Bank: {sim.bank.food:.0f}F, {sim.bank.wood:.0f}W, {sim.bank.gold:.0f}G, {sim.bank.stone:.0f}S.",
                    )
                    sim.bank = sim.bank - ResourceBundle(food=50)
                    sim.tc_busy_until[0] = t + 25
                    sim.tc_action[0] = f"vil_{len(sim.vils)+1}"
                    feudal_vils_queued = 1

                    market_started = True
                    bs_started = True
                    sim.bank = sim.bank - ResourceBundle(wood=325)
                    market_ready_t = t + 46
                    bs_ready_t = t + 50
                    builders_assigned = 0
                    for v in sim.vils:
                        if v["role"] in ("straggler", "wood") and int(v["busy_until"]) <= t:
                            if builders_assigned < 3:
                                v["busy_until"] = t + 46
                                builders_assigned += 1
                            elif builders_assigned == 3:
                                v["busy_until"] = t + 50
                                builders_assigned += 1
                                break
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        "Feudal Age",
                        "3 vils build Market (-175W, 10s+36s) & 1 vil builds Blacksmith (-150W, 10s+40s).",
                        "Both finish within 50s right as 2nd Feudal villager completes (0s TC idle).",
                    )

                elif act == "castle":
                    sim.age = 3
                    castle_reached_t = t
                    current_phase = "Castle Age"
                    milestones["castle_reached_s"] = t
                    milestones["castle_reached_str"] = sim.fmt_time(t)
                    milestones["castle_arrival_bank"] = sim.bank.to_dict()
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        "Castle Age",
                        f"REACHED CASTLE AGE! Bank: {sim.bank.food:.0f}F / {sim.bank.wood:.0f}W / {sim.bank.gold:.0f}G / {sim.bank.stone:.0f}S.",
                        "650+ Stone ready on Frame 1: drop Defensive Castle immediately (0s wait <= 10s max)!",
                    )
                    def_castle_started = True
                    sim.bank = sim.bank - ResourceBundle(stone=650)
                    def_castle_ready_t = t + 85
                    milestones["def_castle_started_str"] = sim.fmt_time(t)
                    milestones["castle_wait_s"] = 0
                    c_builders = 0
                    for pref_role in ("straggler", "berries", "farm", "gold"):
                        for v in sim.vils:
                            if v["role"] == pref_role and int(v["busy_until"]) <= t and c_builders < 6:
                                v["busy_until"] = t + 85
                                c_builders += 1
                    sim.bank = sim.bank - ResourceBundle(food=50)
                    sim.tc_busy_until[0] = t + 25
                    sim.tc_action[0] = f"vil_{len(sim.vils)+1}"
                    if sim.bank.food >= 150 and sim.bank.wood >= 100:
                        bow_saw_started = True
                        sim.bank = sim.bank - ResourceBundle(food=150, wood=100)
                        sim.upgrades.add("bow saw")
                        add_row(
                            f"{len(sim.vils)}v ({total_pop()} pop)",
                            "Castle Age",
                            f"Drop Defensive Castle at home with 6 vils (-650S, 10s+75s -> ready {sim.fmt_time(t+85)}), research Bow Saw (-150F, -100W), queue Vil #{len(sim.vils)+1} (-50F, 25s).",
                            "Zero wait (0s <= 10s max) on Castle drop; Double-Bit Axe, Horse Collar & Bow Saw all active!",
                        )
                    else:
                        add_row(
                            f"{len(sim.vils)}v ({total_pop()} pop)",
                            "Castle Age",
                            f"Drop Defensive Castle at home with 6 vils (-650S, 10s+75s -> ready {sim.fmt_time(t+85)}), queue Vil #{len(sim.vils)+1} (-50F, 25s).",
                            "Zero wait (0s <= 10s max) on Castle drop; Bow Saw queues next without idling TC #1.",
                        )

                elif act == "loom":
                    sim.upgrades.add("loom")
                    milestones["loom_done_str"] = sim.fmt_time(t)
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        current_phase,
                        "Loom completes (+15 HP, +1/+2 armor on all Villagers before forward builders march out).",
                        "",
                    )

                elif act == "wheelbarrow":
                    sim.upgrades.add("wheelbarrow")
                    milestones["wheelbarrow_done_s"] = t
                    milestones["wheelbarrow_done_str"] = sim.fmt_time(t)
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        current_phase,
                        "Wheelbarrow completes! Farmer gather rate rises to 23.03 F/min (+13.4%).",
                        "",
                    )

                elif act == "hand_cart":
                    sim.upgrades.add("hand cart")
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        current_phase,
                        "Hand Cart completes! Farmer gather rate reaches 24.00 F/min maximum.",
                        "",
                    )

                elif act == "imperial":
                    sim.age = 4
                    current_phase = "Imperial Age"
                    milestones["imp_reached_s"] = t
                    milestones["imp_reached_str"] = sim.fmt_time(t)
                    milestones["imp_arrival_bank"] = sim.bank.to_dict()
                    milestones["imp_arrival_army"] = dict(sim.military_units)
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        "Imperial Age",
                        f"REACHED IMPERIAL AGE! Bank: {sim.bank.food:.0f}F / {sim.bank.wood:.0f}W / {sim.bank.gold:.0f}G / {sim.bank.stone:.0f}S.",
                        "Immediately research Chemistry, Conscription & Bracer; upgrade Siege & produce Bombard Cannons / Trebuchets!",
                    )
                    chem_cost, chem_time = sim.db.get_upgrade_spec("chemistry", "Italians")
                    if sim.bank.food >= chem_cost.food + 150 and sim.bank.gold >= chem_cost.gold + 150:
                        chemistry_started = True
                        conscription_started = True
                        sim.bank = sim.bank - chem_cost - ResourceBundle(food=150, gold=150)
                        chemistry_ready_t = t + int(chem_time)
                        sim.upgrades.add("conscription")
                        add_row(
                            f"{len(sim.vils)}v ({total_pop()} pop)",
                            "Imperial Age",
                            f"Immediately research Conscription (-150F, -150G) & Chemistry (-{chem_cost.food:.0f}F, -{chem_cost.gold:.0f}G Italians -33%)!",
                            "+33% faster production across Castles & Stables.",
                        )
                    elif sim.bank.food >= 150 and sim.bank.gold >= 150:
                        conscription_started = True
                        sim.bank = sim.bank - ResourceBundle(food=150, gold=150)
                        sim.upgrades.add("conscription")
                        add_row(
                            f"{len(sim.vils)}v ({total_pop()} pop)",
                            "Imperial Age",
                            "Immediately research Conscription at Castle (-150F, -150G)!",
                            "",
                        )

        # Click Feudal Age
        if sim.age == 1 and not feudal_clicked and sim.tc_action[0] == "idle" and len(sim.vils) == dark_vils:
            if sim.bank.food >= 425:
                feudal_clicked = True
                current_phase = "Feudal Transition"
                milestones["feudal_click_s"] = t
                milestones["feudal_click_str"] = sim.fmt_time(t)
                sim.bank = sim.bank - ResourceBundle(food=425)
                sim.tc_busy_until[0] = t + 130
                sim.tc_action[0] = "feudal"
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    "Feudal Transition",
                    "CLICK FEUDAL AGE (-425F Italians -15% cost, 130s, 0s TC idle)!",
                    f"Reaches Feudal Age at {sim.fmt_time(t + 130)}. 4 Stone miners actively gathering toward Castle drop.",
                )

        # Feudal Transition: Sheep #8 finishes -> seed 2 Farms & cap LC #1 at 8
        if feudal_clicked and sim.age == 1 and farms_seeded < 2 and sim.remaining_animals["sheep"] == 0 and sim.active_carcass_food["sheep"] <= 1e-6:
            for v in sim.vils:
                if v["role"] == "straggler" and int(v["busy_until"]) <= t and farms_seeded < 2 and sim.bank.wood >= 60:
                    sim.bank = sim.bank - ResourceBundle(wood=60)
                    v["role"] = "farm"
                    v["busy_until"] = t + 20
                    farms_seeded += 1
            cur_lc_w = sum(1 for v in sim.vils if v["role"] == "wood")
            moved_w = 0
            for v in sim.vils:
                if v["role"] == "straggler" and int(v["busy_until"]) <= t and (cur_lc_w + moved_w) < 8:
                    v["role"] = "wood"
                    v["busy_until"] = t + 15
                    moved_w += 1
            add_row(
                f"{len(sim.vils)}v ({total_pop()} pop)",
                "Feudal Transition",
                f"Sheep #8 finishes under TC: seed 2 Farms (-120W), move {moved_w} TC vils to LC #1 (8/8 max on LC #1), rest on Stragglers.",
                "Wood Priority Rule: cap LC #1 at 8 vils until Market, Blacksmith, Gold MC, DBA & HC are placed.",
            )

        # Feudal Age: Queue 2nd Feudal villager
        if sim.age == 2 and not castle_clicked and sim.tc_action[0] == "idle" and feudal_vils_queued == 1:
            sim.bank = sim.bank - ResourceBundle(food=50)
            sim.tc_busy_until[0] = t + 25
            sim.tc_action[0] = f"vil_{len(sim.vils)+1}"
            feudal_vils_queued = 2

        # Feudal Age Market trade: Sell 100 Stone for +70 Gold (high Feudal price)
        if market_ready_t is not None and t >= market_ready_t and not stone_sold:
            stone_sold = True
            g_gain = sim.sell_at_market("stone", 100, castle_reached_t)
            add_row(
                f"{len(sim.vils)}v ({total_pop()} pop)",
                "Feudal Age",
                f"Market completes! Sell 100 Stone at high Feudal price for +{g_gain} Gold (Bank: {sim.bank.gold:.0f}G).",
                "100 starting Gold + 70 Gold from Market = exact 170 Gold needed for Italians Castle Age!",
            )

        # Click Castle Age (0s TC idle)
        if (
            sim.age == 2
            and not castle_clicked
            and feudal_vils_queued == 2
            and sim.tc_action[0] == "idle"
            and bs_ready_t is not None
            and t >= bs_ready_t
            and stone_sold
            and sim.bank.food >= 680
            and sim.bank.gold >= 170
        ):
            castle_clicked = True
            castle_click_t = t
            current_phase = "Castle Transition"
            milestones["castle_click_s"] = t
            milestones["castle_click_str"] = sim.fmt_time(t)
            sim.bank = sim.bank - ResourceBundle(food=680, gold=170)
            sim.tc_busy_until[0] = t + 160
            sim.tc_action[0] = "castle"
            add_row(
                f"{len(sim.vils)}v ({total_pop()} pop)",
                "Castle Transition",
                "CLICK CASTLE AGE (-680F, -170G Italians -15% cost, 160s, 0s TC idle)!",
                f"Reaches Castle Age at {sim.fmt_time(t + 160)}.",
            )
            moved_g = 0
            for v in sim.vils:
                if v["role"] in ("straggler", "wood") and int(v["busy_until"]) <= t and moved_g < 3:
                    v["role"] = "gold"
                    v["busy_until"] = t + 15
                    moved_g += 1
            tot_g_now = sum(1 for v in sim.vils if v["role"] == "gold")
            add_row(
                f"{len(sim.vils)}v ({total_pop()} pop)",
                "Castle Transition",
                f"Move {moved_g} Market/Blacksmith builders to Gold ({tot_g_now} on Gold) & return remaining builder to Wood.",
                "Funds early Castle Genoese Xbows, Blacksmith upgrades, and Light Cav.",
            )

        # Castle Transition & early Castle follow-through: DBA, Horse Collar, Farms #3-#5, Gold Mining, LC #2, Barracks -> Stable #1, early Fletching!
        if castle_clicked and sim.age >= 2 and t >= castle_click_t + 1:
            if not dba_started and sim.bank.food >= 100 and sim.bank.wood >= 50:
                dba_started = True
                sim.bank = sim.bank - ResourceBundle(food=100, wood=50)
                sim.upgrades.add("double-bit axe")
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    "Research Double-Bit Axe at Lumber Camp (-100F, -50W, 25s)!",
                    "Early wood upgrade immediately upon clicking Castle Age.",
                )
            if dba_started and not hc_started and sim.bank.food >= 75 and sim.bank.wood >= 75:
                hc_started = True
                sim.bank = sim.bank - ResourceBundle(food=75, wood=75)
                sim.upgrades.add("horse collar")
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    "Research Horse Collar at Mill (-75F, -75W, 20s) before seeding transition Farms!",
                    "+75F Farm capacity (250F total) for all Castle-transition Farms.",
                )
            if hc_started and sim.age == 2 and farms_seeded < 5 and sim.bank.wood >= 150:
                for v in sim.vils:
                    if v["role"] in ("straggler", "wood") and int(v["busy_until"]) <= t:
                        sim.bank = sim.bank - ResourceBundle(wood=60)
                        v["role"] = "farm"
                        v["busy_until"] = t + 20
                        farms_seeded += 1
                        add_row(
                            f"{len(sim.vils)}v ({total_pop()} pop)",
                            current_phase,
                            f"Seed Horse Collar Farm #{farms_seeded} (-60W, 5s walk + 15s build).",
                            "250F Farm capacity with Horse Collar.",
                        )
                        break
            if not gold_mining_started and hc_started and (farms_seeded >= 5 or sim.age >= 3) and sim.bank.food >= 150 and sim.bank.wood >= 75:
                gold_mining_started = True
                sim.bank = sim.bank - ResourceBundle(food=100, wood=75)
                sim.upgrades.add("gold mining")
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    "Research Gold Mining at Mining Camp (-100F, -75W, 30s).",
                    "+15% gold gather rate before Castle Age.",
                )
            if not lc2_rebuilt and gold_mining_started and sim.bank.wood >= 180:
                lc2_rebuilt = True
                sim.bank = sim.bank - ResourceBundle(wood=100)
                sim.lc_completed_s = t + 35
                sim.lc_count = 2
                for v in sim.vils:
                    if v["role"] == "straggler" and int(v["busy_until"]) <= t:
                        v["role"] = "wood"
                milestones["lc2_rebuilt_str"] = sim.fmt_time(t)
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    "Build Lumber Camp #2 (-100W, 35s) to split woodcutters (<= 5 per LC) & reset wood efficiency to 100%.",
                    "Wood Priority & Density Rule.",
                )
            if lc2_rebuilt and not barracks_started and sim.bank.wood >= 200:
                barracks_started = True
                sim.bank = sim.bank - ResourceBundle(wood=175)
                barracks_ready_t = t + 60
                for v in sim.vils:
                    if v["role"] in ("wood", "straggler") and int(v["busy_until"]) <= t:
                        v["busy_until"] = t + 60
                        break
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    f"Build Barracks (-175W, 10s walk + 50s build -> ready at {sim.fmt_time(t+60)}).",
                    "Pre-builds Barracks using surplus Wood for immediate Stable.",
                )
            if barracks_ready_t is not None and t >= barracks_ready_t and not stable_started and sim.bank.wood >= 175:
                stable_started = True
                sim.bank = sim.bank - ResourceBundle(wood=175)
                stable_ready_t = t + 50
                milestones["stable_ready_str"] = sim.fmt_time(t + 50)
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    f"Barracks completes! Same builder chains Stable #1 (-175W, 0s walk + 50s build -> ready at {sim.fmt_time(t+50)}).",
                    "Sequential building rule saves 20s walk; unlocks Light Cav immediately after Castle!",
                )
            if (
                sim.age == 2
                and not fletching_started
                and gold_mining_started
                and t >= castle_click_t + 115
                and sim.bank.food >= 220
                and sim.bank.gold >= 70
            ):
                fletching_started = True
                sim.bank = sim.bank - ResourceBundle(food=100, gold=50)
                sim.upgrades.add("fletching")
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    "Research Fletching at Blacksmith (-100F, -50G, 30s) before Castle Age!",
                    "First Genoese Crossbowmen spawn with +1 attack & +1 range immediately.",
                )

        if sim.age >= 3 and not bow_saw_started and sim.bank.food >= 200 and sim.bank.wood >= 100:
            bow_saw_started = True
            sim.bank = sim.bank - ResourceBundle(food=150, wood=100)
            sim.upgrades.add("bow saw")
            add_row(
                f"{len(sim.vils)}v ({total_pop()} pop)",
                current_phase,
                "Research Bow Saw at Lumber Camp (-150F, -100W, 50s) without idling TC #1!",
                "Early Castle wood upgrade (+20% gather rate).",
            )

        if stable_ready_t is not None and t == stable_ready_t and stable_count == 0:
            stable_count = 1

        # Houses ahead of pop cap
        cur_pop = total_pop()
        pop_cap = (
            5 * sim.tc_count
            + houses_built * 5
            + (20 if def_castle_ready_t and t >= def_castle_ready_t else 0)
            + (20 if fwd_castle2_ready_t and t >= fwd_castle2_ready_t else 0)
            + (20 if fwd_castle3_ready_t and t >= fwd_castle3_ready_t else 0)
        )
        if sim.age >= 2 and cur_pop + 6 >= pop_cap and t >= house_busy_until and sim.bank.wood >= 25 and pop_cap < 200:
            houses_built += 1
            house_busy_until = t + 25
            sim.bank = sim.bank - ResourceBundle(wood=25)
            for v in sim.vils:
                if v["role"] in ("wood", "straggler") and int(v["busy_until"]) <= t:
                    v["busy_until"] = t + 25
                    break

        # === CASTLE AGE & IMPERIAL AGE ===
        if sim.age >= 3:
            # Activate TC #2, TC #3, TC #4 on completion
            if tc2_ready_t is not None and t == tc2_ready_t:
                sim.tc_count = 2
                sim.tc_busy_until.append(t)
                sim.tc_action.append("idle")
                milestones["tc2_ready_str"] = sim.fmt_time(t)
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    "Town Center #2 completes! Now producing Villagers from 2 TCs.",
                    "",
                )
            if tc3_ready_t is not None and t == tc3_ready_t:
                sim.tc_count = 3
                sim.tc_busy_until.append(t)
                sim.tc_action.append("idle")
                milestones["tc3_ready_str"] = sim.fmt_time(t)
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    "Town Center #3 completes! Now booming on 3 TCs.",
                    "",
                )
            if tc4_ready_t is not None and t == tc4_ready_t:
                sim.tc_count = 4
                sim.tc_busy_until.append(t)
                sim.tc_action.append("idle")
                milestones["tc4_ready_str"] = sim.fmt_time(t)
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    "Town Center #4 completes on outside resources! Now booming on 4 TCs.",
                    "",
                )

            # Activate Castles on completion
            if def_castle_ready_t is not None and t == def_castle_ready_t:
                castle_count = 1
                milestones["def_castle_ready_str"] = sim.fmt_time(t)
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    "Defensive Castle #1 completes (+20 pop room)! Immediately start Genoese Crossbowman production (-45W, -40G, 14s).",
                    "6 Castle builders return to work.",
                )
                if is_1tc and not stone_adjusted_early:
                    stone_adjusted_early = True
                    moved_s = 0
                    for v in sim.vils:
                        if v["role"] == "stone" and int(v["busy_until"]) <= t and moved_s < 2:
                            v["role"] = "wood"
                            v["busy_until"] = t + 15
                            moved_s += 1
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        current_phase,
                        "Reassign 2 Stone miners -> Wood (keep 2 on Stone).",
                        "2 Stone miners quietly bank 200+ Stone by Imperial click for TC #2 & TC #3.",
                    )
            if fwd_castle2_ready_t is not None and t == fwd_castle2_ready_t:
                castle_count = 2
                milestones["fwd_castle2_ready_str"] = sim.fmt_time(t)
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    "Forward Castle #2 completes! Now producing Genoese Crossbowmen from 2 Castles.",
                    "",
                )
            if fwd_castle3_ready_t is not None and t == fwd_castle3_ready_t:
                castle_count = 3
                milestones["fwd_castle3_ready_str"] = sim.fmt_time(t)
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    "Forward Castle #3 completes! 3 Castles producing Elite Genoese Crossbowmen.",
                    "",
                )

            # Dynamic Resource Rebalancing (every 15s)
            if t % 15 == 0 and t >= (castle_reached_t or 0) + 120:
                g_cnt_r = sum(1 for v in sim.vils if v["role"] == "gold")
                w_cnt_r = sum(1 for v in sim.vils if v["role"] in ("wood", "straggler"))
                f_cnt_r = sum(1 for v in sim.vils if v["role"] == "farm")
                imp_f_cap = 42 if is_1tc else 48
                # Shift excess Food -> Wood if Food > 1150 and Wood < 450
                if sim.bank.food > 1150 and sim.bank.wood < 450 and f_cnt_r > 20:
                    moved = 0
                    for v in sim.vils:
                        if v["role"] == "farm" and int(v["busy_until"]) <= t and moved < 3:
                            v["role"] = "wood"
                            v["busy_until"] = t + 15
                            moved += 1
                # Shift excess Gold -> Wood if Gold > 750 (before Imp) or > 1100 (in Imp) and Wood < 450
                elif sim.bank.gold > (750 if not imp_clicked else 1100) and sim.bank.wood < 450 and g_cnt_r > 5:
                    moved = 0
                    for v in sim.vils:
                        if v["role"] == "gold" and int(v["busy_until"]) <= t and moved < 2:
                            v["role"] = "wood"
                            v["busy_until"] = t + 15
                            moved += 1
                # Shift Wood/Food -> Gold if Gold < 600 and Wood/Food > 650 (or Imperial upgrade saving)
                elif sim.bank.gold < (450 if sim.age < 4 else 800) and (sim.bank.wood > 650 or sim.bank.food > 1050) and g_cnt_r < 30:
                    src_role = "farm" if (sim.bank.food > 1150 and f_cnt_r > 24) else ("wood" if w_cnt_r > 20 else None)
                    if src_role:
                        moved = 0
                        for v in sim.vils:
                            if v["role"] == src_role and int(v["busy_until"]) <= t and moved < 4:
                                v["role"] = "gold"
                                v["busy_until"] = t + 15
                                moved += 1
                # Convert excess Woodcutters into Farms when floating Wood & low Food
                elif sim.bank.wood > 700 and sim.bank.food < 1100 and w_cnt_r > 22 and f_cnt_r < imp_f_cap and (not is_1tc or tc3_started):
                    moved = 0
                    for v in sim.vils:
                        if v["role"] == "wood" and int(v["busy_until"]) <= t and moved < 3:
                            sim.bank = sim.bank - ResourceBundle(wood=60)
                            v["role"] = "farm"
                            v["busy_until"] = t + 20
                            farms_seeded += 1
                            sim.register_new_farm()
                            moved += 1
                            if moved >= 3 or sim.bank.wood < 600:
                                break
                # Cap Stone miners once Stone target is banked
                if is_1tc and tc3_started and sim.bank.stone >= 250 and sum(1 for v in sim.vils if v["role"] == "stone") > 0:
                    for v in sim.vils:
                        if v["role"] == "stone" and int(v["busy_until"]) <= t:
                            v["role"] = "wood" if sim.bank.wood < sim.bank.gold else "gold"
                            v["busy_until"] = t + 15
                if not is_1tc and (fwd_castle3_started or sim.bank.stone >= 850) and sum(1 for v in sim.vils if v["role"] == "stone") > 2:
                    moved = 0
                    for v in sim.vils:
                        if v["role"] == "stone" and int(v["busy_until"]) <= t:
                            v["role"] = "wood" if sim.bank.wood < sim.bank.gold else "gold"
                            v["busy_until"] = t + 15
                            moved += 1
                            if sum(1 for vv in sim.vils if vv["role"] == "stone") <= 2:
                                break

            # =========================================================
            # STRATEGY 1: 1 TC HEAVY ARMY PUSH SPECIFIC LOGIC
            # =========================================================
            if is_1tc:
                if not monastery_started and def_castle_started and sim.bank.wood >= 175:
                    monastery_started = True
                    sim.bank = sim.bank - ResourceBundle(wood=175)
                    monastery_ready_t = t + 50
                    milestones["monastery_ready_str"] = sim.fmt_time(t + 50)
                    for v in sim.vils:
                        if v["role"] in ("wood", "straggler", "gold") and int(v["busy_until"]) <= t:
                            v["busy_until"] = t + 50
                            break
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        current_phase,
                        f"Build Monastery (-175W, 10s+40s -> ready {sim.fmt_time(t+50)}) for 2 Monks & Relic control.",
                        "Conservatively assume we secure at most 1 Relic (+30G/min).",
                    )
                if (
                    monastery_ready_t is not None
                    and t >= monastery_ready_t
                    and monks_trained < 2
                    and t >= monastery_busy_until
                    and sim.bank.gold >= 100
                ):
                    monks_trained += 1
                    sim.bank = sim.bank - ResourceBundle(gold=100)
                    sim.military_units["monk"] += 1
                    monastery_busy_until = t + 51
                    if monks_trained == 1:
                        relic1_time = t + 51 + 50
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        current_phase,
                        f"Queue Monk #{monks_trained} at Monastery (-100G, 51s -> ready {sim.fmt_time(t+51)}).",
                        "Only 1 Relic assumed secured; Monk #2 supports push/healing.",
                    )

                # Occasional Market Usage in Strategy 1 (rules.md 1.4)
                if (
                    sim.age == 3
                    and not imp_clicked
                    and (t - last_market_trade_t) >= 60
                    and market_trades_castle < 4
                ):
                    if sim.bank.wood >= 400 and sim.bank.gold < 160 and (t - castle_reached_t) < 480:
                        last_market_trade_t = t
                        market_trades_castle += 1
                        g_gain = sim.sell_at_market("wood", 100, castle_reached_t)
                        add_row(
                            f"{len(sim.vils)}v ({total_pop()} pop)",
                            current_phase,
                            f"Market trade: Sell 100 excess Wood for +{g_gain} Gold (early/mid Castle rate: {g_gain}G/100).",
                            "Converts floating Wood into Gold for continuous Genoese, Monks & upgrades.",
                        )
                    elif sim.bank.food >= 900 and 560 <= sim.bank.gold < 680 and sim.bank.wood >= 320:
                        last_market_trade_t = t
                        market_trades_castle += 1
                        g_gain = sim.sell_at_market("wood", 100, castle_reached_t)
                        add_row(
                            f"{len(sim.vils)}v ({total_pop()} pop)",
                            current_phase,
                            f"Market trade: Sell 100 Wood for +{g_gain} Gold (rate: {g_gain}G/100) to accelerate Imperial Age click!",
                            "rules.md 1.4 Market optimization.",
                        )
                    elif sim.bank.food >= 1050 and 560 <= sim.bank.gold < 680:
                        last_market_trade_t = t
                        market_trades_castle += 1
                        g_gain = sim.sell_at_market("food", 100, castle_reached_t)
                        add_row(
                            f"{len(sim.vils)}v ({total_pop()} pop)",
                            current_phase,
                            f"Market trade: Sell 100 surplus Food for +{g_gain} Gold (rate: {g_gain}G/100) to click Imperial Age!",
                            "rules.md 1.4 Market optimization.",
                        )

                # Forward Siege Workshop + Rams once 30+ army is reached!
                if not army30_reached and army_combat_count() >= 30:
                    army30_reached = True
                    milestones["army30_str"] = sim.fmt_time(t)
                    milestones["army30_comp"] = dict(sim.military_units)
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        current_phase,
                        f"30+ ARMY REACHED ({army_combat_count()} units: {sim.military_units['genoese']} Genoese, {sim.military_units['light_cav']} Light Cav, {sim.military_units['monk']} Monks)! Dispatch forward Villager for Siege Workshop & Rams!",
                        "Trigger threshold met for forward Siege push.",
                    )
                if army30_reached and not fwd_sw_dispatched and "loom" in sim.upgrades:
                    fwd_sw_dispatched = True
                    fwd_sw_arrive_t = t + 75
                    for v in sim.vils:
                        if v["role"] in ("wood", "farm") and int(v["busy_until"]) <= t:
                            v["busy_until"] = t + 75
                            break
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        current_phase,
                        f"Send forward Villager across Arena (75s walk -> arrives {sim.fmt_time(t+75)}) to build Forward Siege Workshop.",
                        "Protected by 30+ Genoese & Light Cav push.",
                    )
                if fwd_sw_arrive_t is not None and t >= fwd_sw_arrive_t and not fwd_sw1_started and sim.bank.wood >= 200:
                    fwd_sw1_started = True
                    sim.bank = sim.bank - ResourceBundle(wood=200)
                    fwd_sw1_ready_t = t + 40
                    milestones["fwd_sw_ready_str"] = sim.fmt_time(t + 40)
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        current_phase,
                        f"Forward Villager builds Forward Siege Workshop (-200W, 40s -> ready {sim.fmt_time(t+40)})!",
                        "Produces 3-4 Battering Rams to break Arena walls & enemy Castles/TCs.",
                    )
                if (
                    fwd_sw1_ready_t is not None
                    and t >= fwd_sw1_ready_t
                    and rams_trained < 4
                    and t >= sw_busy_until[0]
                    and sim.bank.wood >= 160
                    and sim.bank.gold >= 75
                ):
                    rams_trained += 1
                    sim.bank = sim.bank - ResourceBundle(wood=160, gold=75)
                    sw_busy_until[0] = t + 36
                    sim.military_units["battering_ram"] += 1
                    if rams_trained == 1:
                        milestones["ram1_str"] = sim.fmt_time(t)
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        current_phase,
                        f"Queue Battering Ram #{rams_trained} at Forward Siege Workshop (-160W, -75G, 36s).",
                        f"{rams_trained}/4 Battering Rams for the 1-TC Castle Age push.",
                    )

                # Stick strictly to 1 TC until clicking Imp -> Add TC #2 and TC #3 AFTER clicking Imperial Age!
                if imp_clicked and not tc2_started and sim.bank.wood >= 275 and sim.bank.stone >= 100:
                    tc2_started = True
                    sim.bank = sim.bank - ResourceBundle(wood=275, stone=100)
                    tc2_ready_t = t + 145
                    milestones["tc2_started_str"] = sim.fmt_time(t)
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        current_phase,
                        f"Imperial clicked! Now add Town Center #2 (-275W, -100S, 145s -> ready {sim.fmt_time(t+145)}).",
                        "Stayed strictly on 1 TC until clicking Imp; now expanding economy during Imperial Transition.",
                    )
                if imp_clicked and tc2_started and not tc3_started and sim.bank.wood >= 275 and sim.bank.stone >= 100:
                    tc3_started = True
                    sim.bank = sim.bank - ResourceBundle(wood=275, stone=100)
                    tc3_ready_t = t + 145
                    milestones["tc3_started_str"] = sim.fmt_time(t)
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        current_phase,
                        f"Add Town Center #3 (-275W, -100S, 145s -> ready {sim.fmt_time(t+145)}).",
                        "Expands to 3 TCs while advancing to Imperial Age.",
                    )

            # =========================================================
            # STRATEGY 2: BALANCED 3 TC BOOM SPECIFIC LOGIC
            # =========================================================
            else:
                if (
                    not army20_reached
                    and sim.military_units["genoese"] >= 12
                    and sim.military_units["light_cav"] >= 7
                    and (sim.military_units["genoese"] + sim.military_units["light_cav"]) >= 19
                ):
                    army20_reached = True
                    milestones["army20_reached_str"] = sim.fmt_time(t)
                    milestones["army20_comp"] = dict(sim.military_units)
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        current_phase,
                        f"~20 ARMY TARGET REACHED ({sim.military_units['genoese']} Genoese + {sim.military_units['light_cav']} Light Cav = {sim.military_units['genoese'] + sim.military_units['light_cav']} units)! Pause military production & switch to 3-TC expansion!",
                        "Prioritize Villagers, Farms & Wheelbarrow until 3-TC continuous villager production is set up.",
                    )

                if army20_reached and not tc2_started and sim.bank.wood >= 275 and sim.bank.stone >= 100:
                    tc2_started = True
                    sim.bank = sim.bank - ResourceBundle(wood=275, stone=100)
                    tc2_ready_t = t + 145
                    milestones["tc2_started_str"] = sim.fmt_time(t)
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        current_phase,
                        f"Build Town Center #2 with 4 vils (-275W, -100S, 145s -> ready {sim.fmt_time(t+145)}).",
                        "Military paused while expanding to 3 TCs.",
                    )
                if tc2_started and not tc3_started and sim.bank.wood >= 275 and sim.bank.stone >= 100:
                    tc3_started = True
                    sim.bank = sim.bank - ResourceBundle(wood=275, stone=100)
                    tc3_ready_t = t + 145
                    milestones["tc3_started_str"] = sim.fmt_time(t)
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        current_phase,
                        f"Build Town Center #3 with 4 vils (-275W, -100S, 145s -> ready {sim.fmt_time(t+145)}).",
                        "3 TCs placed! Prioritize Farms & Wheelbarrow to keep all 3 TCs producing continuously.",
                    )

                f_cnt_s2 = sum(1 for v in sim.vils if v["role"] == "farm")
                boom3tc_ready = (
                    tc3_ready_t is not None
                    and t >= tc3_ready_t
                    and f_cnt_s2 >= 22
                    and wheelbarrow_started
                )
                if boom3tc_ready and not boom3tc_ready_logged:
                    boom3tc_ready_logged = True
                    milestones["boom3tc_setup_str"] = sim.fmt_time(t)
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        current_phase,
                        f"3-TC BOOM ESTABLISHED (3 TCs active, {f_cnt_s2} Farms, Wheelbarrow)! Resume & maximize army production with full upgrades!",
                        "Transition from boom setup into full multi-building Genoese + Light Cav flood & University/Blacksmith upgrades.",
                    )

                # Occasional Market usage in Strategy 2 (rules.md 1.4)
                if (
                    sim.age == 3
                    and boom3tc_ready
                    and not imp_clicked
                    and (t - last_market_trade_t) >= 90
                    and market_trades_castle < 3
                ):
                    if sim.bank.food >= 850 and 560 <= sim.bank.gold < 680 and sim.bank.wood >= 350:
                        last_market_trade_t = t
                        market_trades_castle += 1
                        g_gain = sim.sell_at_market("wood", 100, castle_reached_t)
                        add_row(
                            f"{len(sim.vils)}v ({total_pop()} pop)",
                            current_phase,
                            f"Market trade: Sell 100 Wood for +{g_gain} Gold (rate: {g_gain}G/100) to hit Imperial Age click!",
                            "rules.md 1.4 Market optimization.",
                        )

                # Forward Expedition (8 vils, 90s walk) once 3-TC boom is established & Stone >= 700
                if (
                    boom3tc_ready
                    and not fwd_vils_dispatched
                    and "loom" in sim.upgrades
                    and sim.bank.stone >= 700
                ):
                    fwd_vils_dispatched = True
                    fwd_vils_arrive_t = t + 90
                    milestones["fwd_vils_dispatched_str"] = sim.fmt_time(t)
                    fwd_assigned = 0
                    for v in sim.vils:
                        if v["role"] in ("wood", "farm") and int(v["busy_until"]) <= t and fwd_assigned < 8:
                            v["busy_until"] = t + 90
                            fwd_assigned += 1
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        current_phase,
                        f"700+ Stone banked! Send 8 Loom-protected Villagers forward (90s walk -> arrive {sim.fmt_time(t+90)}).",
                        "Will build Forward Castle #2, TC #4 on outside resources, Forward Siege Workshops & Forward Stables.",
                    )
                if fwd_vils_arrive_t is not None and t >= fwd_vils_arrive_t and not fwd_castle2_started and sim.bank.stone >= 650:
                    fwd_castle2_started = True
                    sim.bank = sim.bank - ResourceBundle(stone=650)
                    fwd_castle2_ready_t = t + 60
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        current_phase,
                        f"Forward Villagers drop Forward Castle #2 (-650S, 60s -> ready {sim.fmt_time(t+60)}).",
                        "",
                    )
                if fwd_castle2_started and not tc4_started and sim.bank.wood >= 275 and sim.bank.stone >= 100:
                    tc4_started = True
                    sim.bank = sim.bank - ResourceBundle(wood=275, stone=100)
                    tc4_ready_t = t + 75
                    milestones["tc4_ready_str"] = sim.fmt_time(t + 75)
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        current_phase,
                        f"Forward Villagers build Town Center #4 on outside Gold/Wood (-275W, -100S -> ready {sim.fmt_time(t+75)}).",
                        "",
                    )
                if fwd_castle2_started and tc4_started and not fwd_sw1_started and sim.bank.wood >= 200:
                    fwd_sw1_started = True
                    sim.bank = sim.bank - ResourceBundle(wood=200)
                    fwd_sw1_ready_t = t + 40
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        current_phase,
                        f"Forward Villagers build Forward Siege Workshop #1 (-200W -> ready {sim.fmt_time(t+40)}).",
                        "",
                    )
                if sim.age == 4 and fwd_sw1_started and not fwd_sw2_started and sim.bank.wood >= 250:
                    fwd_sw2_started = True
                    sim.bank = sim.bank - ResourceBundle(wood=200)
                    fwd_sw2_ready_t = t + 40
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        current_phase,
                        f"Forward Villagers build Forward Siege Workshop #2 (-200W -> ready {sim.fmt_time(t+40)}).",
                        "",
                    )
                if fwd_castle2_ready_t is not None and t >= fwd_castle2_ready_t and tc4_started and not fwd_castle3_started and sim.bank.stone >= 720:
                    fwd_castle3_started = True
                    sim.bank = sim.bank - ResourceBundle(stone=650)
                    fwd_castle3_ready_t = t + 60
                    moved_off_s = 0
                    for v in sim.vils:
                        if v["role"] == "stone" and moved_off_s < 4:
                            v["role"] = "gold"
                            v["busy_until"] = t + 15
                            moved_off_s += 1
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        current_phase,
                        f"Drop Forward Castle #3 (-650S -> ready {sim.fmt_time(t+60)}) & shift 4 Stone miners to Gold (keep 2 on Stone).",
                        "Maintains 200-500S repair reserve.",
                    )
                if fwd_castle3_started and sim.bank.stone > 450:
                    for v in sim.vils:
                        if v["role"] == "stone":
                            v["role"] = "gold" if sim.bank.gold < sim.bank.wood else "wood"
                            v["busy_until"] = t + 10

            # =========================================================
            # SHARED TC QUEUE MANAGEMENT (NO UNPLANNED IDLE TCs!)
            # =========================================================
            for tc_idx in range(sim.tc_count):
                if sim.tc_action[tc_idx] == "idle":
                    f_cnt_now = sum(1 for v in sim.vils if v["role"] == "farm")
                    can_click_imp = (
                        (
                            is_1tc
                            and ballistics_started
                            and fwd_sw1_started
                            and rams_trained >= 3
                            and sim.bank.food >= 850
                            and sim.bank.gold >= 680
                        )
                        or (
                            not is_1tc
                            and ballistics_started
                            and tc3_ready_t is not None
                            and t >= tc3_ready_t
                            and f_cnt_now >= 28
                            and sim.bank.food >= 850
                            and sim.bank.gold >= 680
                        )
                    )
                    if tc_idx == 0 and not imp_clicked and can_click_imp:
                        imp_clicked = True
                        imp_click_t = t
                        current_phase = "Imperial Transition"
                        milestones["imp_click_s"] = t
                        milestones["imp_click_str"] = sim.fmt_time(t)
                        milestones["imp_click_vils"] = len(sim.vils)
                        milestones["imp_click_army"] = dict(sim.military_units)
                        sim.bank = sim.bank - ResourceBundle(food=850, gold=680)
                        sim.tc_busy_until[0] = t + 190
                        sim.tc_action[0] = "imperial"
                        add_row(
                            f"{len(sim.vils)}v ({total_pop()} pop)",
                            "Imperial Transition",
                            f"CLICK IMPERIAL AGE (-850F, -680G Italians -15%, 190s)! Army: {format_army_counts(sim.military_units).replace('Army: ', '')}.",
                            (
                                "Now add TC #2 & TC #3 during Imperial Transition as resources allow!"
                                if is_1tc
                                else f"Reaches Imperial Age at {sim.fmt_time(t + 190)} while 3 TCs continue booming."
                            ),
                        )
                    elif (
                        tc_idx == 0
                        and not wheelbarrow_started
                        and f_cnt_now >= 15
                        and (is_1tc or army20_reached)
                        and sim.bank.food >= 175
                        and sim.bank.wood >= 50
                    ):
                        wheelbarrow_started = True
                        sim.bank = sim.bank - ResourceBundle(food=175, wood=50)
                        sim.tc_busy_until[0] = t + 75
                        sim.tc_action[0] = "wheelbarrow"
                        add_row(
                            f"{len(sim.vils)}v ({total_pop()} pop)",
                            current_phase,
                            "Research Wheelbarrow at TC #1 (-175F, -50W, 75s).",
                            "Boosts Farmer efficiency (+13.4%) as Farms scale past 15.",
                        )
                    elif (
                        not loom_started
                        and (
                            (is_1tc and army_combat_count() >= 26 and tc_idx == 0)
                            or (not is_1tc and tc3_ready_t is not None and t >= tc3_ready_t and tc_idx > 0)
                        )
                        and sim.bank.gold >= 50
                    ):
                        loom_started = True
                        sim.bank = sim.bank - ResourceBundle(gold=50)
                        sim.tc_busy_until[tc_idx] = t + 25
                        sim.tc_action[tc_idx] = "loom"
                        add_row(
                            f"{len(sim.vils)}v ({total_pop()} pop)",
                            current_phase,
                            f"Research Loom at TC #{tc_idx+1} (-50G, 25s) before sending Villagers forward.",
                            "",
                        )
                    elif (
                        tc_idx == 0
                        and wheelbarrow_started
                        and "wheelbarrow" in sim.upgrades
                        and not hand_cart_started
                        and f_cnt_now >= 22
                        and sim.tc_count >= 3
                        and sim.bank.food >= 320
                        and sim.bank.wood >= 200
                    ):
                        hand_cart_started = True
                        sim.bank = sim.bank - ResourceBundle(food=300, wood=200)
                        sim.tc_busy_until[0] = t + 55
                        sim.tc_action[0] = "hand_cart"
                        add_row(
                            f"{len(sim.vils)}v ({total_pop()} pop)",
                            current_phase,
                            "Research Hand Cart at TC #1 (-300F, -200W, 55s).",
                            "Max Farmer gather rate (24.0 F/min).",
                        )
                    else:
                        max_vils_cap = 105 if is_1tc else 130
                        in_flight_vils = sum(1 for a in sim.tc_action if a.startswith("vil_"))
                        hold_for_imp = (
                            tc_idx == 0
                            and not imp_clicked
                            and ballistics_started
                            and sim.bank.gold >= 680
                            and sim.bank.food >= 820
                            and (is_1tc and rams_trained >= 3 or not is_1tc and f_cnt_now >= 28)
                        )
                        if not hold_for_imp and (len(sim.vils) + in_flight_vils) < max_vils_cap and sim.bank.food >= 50:
                            sim.bank = sim.bank - ResourceBundle(food=50)
                            sim.tc_busy_until[tc_idx] = t + 25
                            sim.tc_action[tc_idx] = f"vil_{len(sim.vils) + in_flight_vils + 1}"

            # =========================================================
            # WOOD & FOOD RESERVATIONS + MILITARY PRODUCTION
            # =========================================================
            f_cnt_cur = sum(1 for v in sim.vils if v["role"] == "farm")

            tc_food_reserve = 0
            for tc_idx in range(sim.tc_count):
                if sim.tc_action[tc_idx] == "idle" or (sim.tc_busy_until[tc_idx] - t) <= 10:
                    tc_food_reserve += 50

            univ_trigger = (
                (is_1tc and bodkin_started and army_combat_count() >= 18)
                or (not is_1tc and boom3tc_ready_logged and tc3_started)
            )
            tc_w_res = (
                (275 if (not is_1tc and army20_reached and not tc2_started) else 0)
                + (275 if (not is_1tc and tc2_started and not tc3_started) else 0)
                + (275 if (is_1tc and imp_clicked and not tc2_started) else 0)
                + (275 if (is_1tc and imp_clicked and tc2_started and not tc3_started) else 0)
                + (275 if (not is_1tc and fwd_castle2_started and not tc4_started) else 0)
            )
            univ_w_res = 200 if (univ_trigger and not univ_started) else (201 if (univ_started and not ballistics_started) else 0)
            sw_w_res = (
                (200 if (is_1tc and army30_reached and not fwd_sw1_started) else 0)
                + (200 if (not is_1tc and tc4_started and not fwd_sw1_started) else 0)
                + (200 if (not is_1tc and sim.age == 4 and fwd_sw1_started and not fwd_sw2_started) else 0)
            )
            ram_w_res = 160 if (is_1tc and fwd_sw1_ready_t is not None and t >= fwd_sw1_ready_t and rams_trained < 4 and t >= sw_busy_until[0] - 8) else 0
            ram_g_res = 75 if ram_w_res > 0 else 0
            bbc_w_res = 180 if (sim.age == 4 and chemistry_ready_t is not None and t >= chemistry_ready_t and bbc_count_trained < 3 and fwd_sw1_ready_t is not None and t >= fwd_sw1_ready_t) else 0
            wb_w_res = 50 if (f_cnt_cur >= 15 and not wheelbarrow_started) else 0
            monk_g_res = 100 if (is_1tc and monastery_ready_t is not None and t >= monastery_ready_t and monks_trained < 2 and t >= monastery_busy_until - 8) else 0

            if is_1tc:
                genoese_allowed = not (
                    not imp_clicked
                    and ballistics_started
                    and rams_trained >= 3
                    and sim.bank.food >= 750
                    and sim.bank.gold < 680
                )
                lcav_allowed = (
                    (imp_clicked or sim.military_units["light_cav"] < 20)
                    and not (
                        not imp_clicked
                        and ballistics_started
                        and rams_trained >= 3
                        and sim.bank.gold >= 580
                        and sim.bank.food < 850
                    )
                )
            else:
                boom3tc_ready_now = (
                    tc3_ready_t is not None
                    and t >= tc3_ready_t
                    and f_cnt_cur >= 22
                    and wheelbarrow_started
                )
                want_genoese_phase1 = (not army20_reached) and (sim.military_units["genoese"] < 13)
                want_lcav_phase1 = (not army20_reached) and (sim.military_units["light_cav"] < 7)
                genoese_allowed = (
                    (want_genoese_phase1 or boom3tc_ready_now)
                    and not (army20_reached and not boom3tc_ready_now)
                    and not (not imp_clicked and ballistics_started and f_cnt_cur >= 28 and sim.bank.food >= 700 and sim.bank.gold < 680)
                )
                lcav_allowed = (
                    (want_lcav_phase1 or boom3tc_ready_now)
                    and not (army20_reached and not boom3tc_ready_now)
                    and not (not imp_clicked and ballistics_started and f_cnt_cur >= 28 and sim.bank.gold >= 550 and sim.bank.food < 850)
                )

            genoese_train_s = 11 if "conscription" in sim.upgrades else 14
            total_w_res = tc_w_res + univ_w_res + sw_w_res + ram_w_res + bbc_w_res + wb_w_res
            hold_genoese_for_elite = (sim.age == 4 and sim.military_units["genoese"] >= 45 and not elite_genoese_started)
            for c_idx in range(castle_count):
                if t >= castle_busy_until[c_idx] and genoese_allowed and not hold_genoese_for_elite:
                    if sim.bank.wood >= (45 + total_w_res) and sim.bank.gold >= (40 + monk_g_res + ram_g_res):
                        sim.bank = sim.bank - ResourceBundle(wood=45, gold=40)
                        castle_busy_until[c_idx] = t + genoese_train_s
                        if sim.military_units["genoese"] >= 45 or total_pop() >= 200:
                            sim.casualties["genoese"] += 1
                        else:
                            sim.military_units["genoese"] += 1

            # Light Cavalry upgrade + training
            if stable_ready_t is not None and t >= stable_ready_t:
                if not lcav_upg_started and bow_saw_started and def_castle_ready_t is not None and t >= def_castle_ready_t and t >= stable_busy_until[0]:
                    if sim.bank.food >= (150 + tc_food_reserve) and sim.bank.gold >= 50:
                        lcav_upg_started = True
                        sim.bank = sim.bank - ResourceBundle(food=150, gold=50)
                        stable_busy_until[0] = t + 45
                        sim.upgrades.add("light cavalry")
                        if sim.military_units["scout"] > 0:
                            sim.military_units["scout"] -= 1
                            sim.military_units["light_cav"] += 1
                        milestones["lcav_started_str"] = sim.fmt_time(t)
                        add_row(
                            f"{len(sim.vils)}v ({total_pop()} pop)",
                            current_phase,
                            "Research Light Cavalry upgrade at Stable #1 (-150F, -50G, 45s; upgrades starting Scout to Light Cav #1).",
                            "Starts Light Cavalry production right after Genoese begins.",
                        )

                # Scale Stables (never starve TC #2/#3 or Siege Workshop!)
                if is_1tc:
                    if stable_count == 1 and f_cnt_cur >= 16 and sim.bank.wood >= (175 + total_w_res + 100):
                        stable_count = 2
                        sim.bank = sim.bank - ResourceBundle(wood=175)
                        stable_busy_until[1] = t + 50
                        add_row(
                            f"{len(sim.vils)}v ({total_pop()} pop)",
                            current_phase,
                            "Build Stable #2 (-175W, 50s) to accelerate 1-TC Light Cavalry mass!",
                            "",
                        )
                    if stable_count == 2 and sim.age == 4 and tc3_started and len(sim.vils) >= 75 and sim.bank.wood >= (350 + total_w_res):
                        stable_count = 4
                        sim.bank = sim.bank - ResourceBundle(wood=350)
                        stable_busy_until[2] = t + 50
                        stable_busy_until[3] = t + 50
                else:
                    if stable_count == 1 and boom3tc_ready_logged and f_cnt_cur >= 24 and sim.bank.wood >= (175 + total_w_res + 100):
                        stable_count = 2
                        sim.bank = sim.bank - ResourceBundle(wood=175)
                        stable_busy_until[1] = t + 50
                        add_row(
                            f"{len(sim.vils)}v ({total_pop()} pop)",
                            current_phase,
                            "Build Stable #2 (-175W, 50s) as 3-TC economy ramps up Light Cavalry!",
                            "",
                        )
                    if stable_count == 2 and fwd_castle2_started and tc4_started and fwd_sw1_started and sim.bank.wood >= (175 + total_w_res):
                        stable_count = 3
                        sim.bank = sim.bank - ResourceBundle(wood=175)
                        stable_busy_until[2] = t + 35
                    if stable_count == 3 and (imp_clicked or sim.age == 4) and f_cnt_cur >= 34 and sim.bank.wood >= (175 + total_w_res):
                        stable_count = 4
                        sim.bank = sim.bank - ResourceBundle(wood=175)
                        stable_busy_until[3] = t + 35
                    if stable_count == 4 and sim.age == 4 and len(sim.vils) >= 110 and sim.bank.wood >= (350 + total_w_res):
                        stable_count = 6
                        sim.bank = sim.bank - ResourceBundle(wood=350)
                        stable_busy_until[4] = t + 35
                        stable_busy_until[5] = t + 35

                lcav_train_s = 23 if "conscription" in sim.upgrades else 30
                wb_food_res = (175 if (f_cnt_cur >= 15 and not wheelbarrow_started and (is_1tc or army20_reached)) else 0) + (150 if not bow_saw_started else 0)
                hold_lcav_for_upg = (sim.age == 4 and sim.military_units["light_cav"] >= 25 and not (hussar_started and elite_genoese_started))
                for s_idx in range(stable_count):
                    if (
                        lcav_upg_started
                        and t >= stable_busy_until[s_idx]
                        and lcav_allowed
                        and not hold_lcav_for_upg
                        and sim.bank.food >= (80 + tc_food_reserve + wb_food_res)
                    ):
                        sim.bank = sim.bank - ResourceBundle(food=80)
                        stable_busy_until[s_idx] = t + lcav_train_s
                        if total_pop() >= 200 or sim.military_units["light_cav"] >= 30:
                            sim.casualties["light_cav"] += 1
                        else:
                            sim.military_units["light_cav"] += 1

            # =========================================================
            # ARCHER, CAVALRY, ECO & UNIVERSITY UPGRADES (EARLY!)
            # =========================================================
            if not fletching_started and (sim.age == 2 or bow_saw_started) and sim.bank.food >= (100 + tc_food_reserve) and sim.bank.gold >= 50:
                fletching_started = True
                sim.bank = sim.bank - ResourceBundle(food=100, gold=50)
                sim.upgrades.add("fletching")
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    "Research Fletching at Blacksmith (-100F, -50G, 30s).",
                    "+1 attack, +1 range for Genoese Crossbowmen.",
                )
            if not padded_archer_started and fletching_started and lcav_upg_started and sim.bank.food >= (100 + tc_food_reserve):
                padded_archer_started = True
                sim.bank = sim.bank - ResourceBundle(food=100)
                sim.upgrades.add("padded archer armor")
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    "Research Padded Archer Armor at Blacksmith (-100F, 40s).",
                    "Early +1/+1 armor for Genoese Crossbowmen.",
                )
            if not scale_barding_started and lcav_upg_started and sim.bank.food >= (150 + tc_food_reserve):
                scale_barding_started = True
                sim.bank = sim.bank - ResourceBundle(food=150)
                sim.upgrades.add("scale barding armor")
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    "Research Scale Barding Armor at Blacksmith (-150F, 45s).",
                    "Early +1/+1 armor for Light Cavalry.",
                )
            if (
                fletching_started
                and not bodkin_started
                and (not is_1tc or monks_trained >= 2)
                and sim.bank.food >= (200 + tc_food_reserve)
                and sim.bank.gold >= 100
            ):
                bodkin_started = True
                sim.bank = sim.bank - ResourceBundle(food=200, gold=100)
                sim.upgrades.add("bodkin arrow")
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    "Research Bodkin Arrow at Blacksmith (-200F, -100G, 35s).",
                    "+2 attack, +2 range for Genoese Crossbowmen.",
                )
            if (
                not bloodlines_started
                and lcav_upg_started
                and scale_barding_started
                and (is_1tc or boom3tc_ready_logged or sim.military_units["light_cav"] >= 5)
                and sim.bank.food >= (150 + tc_food_reserve)
                and sim.bank.gold >= 100
            ):
                bloodlines_started = True
                sim.bank = sim.bank - ResourceBundle(food=150, gold=100)
                sim.upgrades.add("bloodlines")
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    "Research Bloodlines at Stable (-150F, -100G, 50s).",
                    "+20 HP for Light Cavalry (65 HP).",
                )
            if not forging_started and scale_barding_started and (is_1tc or boom3tc_ready_logged) and sim.bank.food >= (150 + tc_food_reserve):
                forging_started = True
                sim.bank = sim.bank - ResourceBundle(food=150)
                sim.upgrades.add("forging")
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    "Research Forging at Blacksmith (-150F, 50s).",
                    "+1 melee attack for Light Cavalry.",
                )
            if not husbandry_started and bloodlines_started and (is_1tc or boom3tc_ready_logged) and sim.bank.food >= (150 + tc_food_reserve):
                husbandry_started = True
                sim.bank = sim.bank - ResourceBundle(food=150)
                sim.upgrades.add("husbandry")
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    "Research Husbandry at Stable (-150F, 40s).",
                    "+10% speed for Light Cavalry.",
                )
            if not leather_archer_started and bodkin_started and (is_1tc or boom3tc_ready_logged) and sim.bank.food >= (150 + tc_food_reserve) and sim.bank.gold >= 150:
                leather_archer_started = True
                sim.bank = sim.bank - ResourceBundle(food=150, gold=150)
                sim.upgrades.add("leather archer armor")
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    "Research Leather Archer Armor at Blacksmith (-150F, -150G, 55s).",
                    "+2/+2 armor for Genoese Crossbowmen.",
                )
            if not chain_barding_started and forging_started and (is_1tc or boom3tc_ready_logged) and sim.bank.food >= (250 + tc_food_reserve) and sim.bank.gold >= 150:
                chain_barding_started = True
                sim.bank = sim.bank - ResourceBundle(food=250, gold=150)
                sim.upgrades.add("chain barding armor")
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    "Research Chain Barding Armor at Blacksmith (-250F, -150G, 60s).",
                    "+2/+2 armor for Light Cavalry.",
                )
            if not iron_casting_started and chain_barding_started and (is_1tc or boom3tc_ready_logged) and sim.bank.food >= (220 + tc_food_reserve) and sim.bank.gold >= 120:
                iron_casting_started = True
                sim.bank = sim.bank - ResourceBundle(food=220, gold=120)
                sim.upgrades.add("iron casting")
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    "Research Iron Casting at Blacksmith (-220F, -120G, 75s).",
                    "+2 melee attack for Light Cavalry.",
                )

            # University & Ballistics (-33% Italians)
            if univ_trigger and not univ_started and sim.bank.wood >= (200 + tc_w_res + sw_w_res):
                univ_started = True
                sim.bank = sim.bank - ResourceBundle(wood=200)
                univ_ready_t = t + 70
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    f"Build University (-200W, 10s+60s -> ready {sim.fmt_time(t+70)}).",
                    "Unlocks -33% discounted Italians Ballistics, Masonry, Chemistry & Siege Engineers.",
                )
            if univ_ready_t is not None and t >= univ_ready_t and not ballistics_started:
                bal_cost, bal_time = sim.db.get_upgrade_spec("ballistics", "Italians")
                if sim.bank.wood >= (bal_cost.wood + tc_w_res + sw_w_res) and sim.bank.gold >= bal_cost.gold:
                    ballistics_started = True
                    sim.bank = sim.bank - bal_cost
                    ballistics_ready_t = t + int(bal_time)
                    sim.upgrades.add("ballistics")
                    milestones["ballistics_str"] = sim.fmt_time(t + int(bal_time))
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        current_phase,
                        f"Research Ballistics at University (-{bal_cost.wood:.0f}W, -{bal_cost.gold:.0f}G Italians -33%, 60s).",
                        "Essential accuracy boost for Genoese Crossbowmen.",
                    )

            # Eco upgrades in Castle Age
            if ballistics_started and not heavy_plow_started and sim.bank.food >= (125 + tc_food_reserve) and sim.bank.wood >= (125 + total_w_res):
                heavy_plow_started = True
                sim.bank = sim.bank - ResourceBundle(food=125, wood=125)
                sim.upgrades.add("heavy plow")
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    "Research Heavy Plow at Mill (-125F, -125W, 40s).",
                    "Farms hold 375 Food.",
                )
            if not is_1tc and tc3_started and not stone_mining_started and sim.bank.food >= (100 + tc_food_reserve) and sim.bank.wood >= (75 + tc_w_res):
                stone_mining_started = True
                sim.bank = sim.bank - ResourceBundle(food=100, wood=75)
                sim.upgrades.add("stone mining")
            if not is_1tc and heavy_plow_started and not stone_shaft_started and len(sim.vils) >= 54 and sim.bank.food >= (175 + tc_food_reserve) and sim.bank.wood >= (75 + tc_w_res):
                stone_shaft_started = True
                sim.bank = sim.bank - ResourceBundle(food=175, wood=75)
                sim.upgrades.add("stone shaft mining")
            if heavy_plow_started and not gold_shaft_started and len(sim.vils) >= 48 and sim.bank.food >= (175 + tc_food_reserve) and sim.bank.wood >= (75 + total_w_res):
                gold_shaft_started = True
                sim.bank = sim.bank - ResourceBundle(food=175, wood=75)
                sim.upgrades.add("gold shaft mining")

            # Pavise (Italians Castle UT) — wait for post-Imp TCs to be placed first!
            if ballistics_started and not pavise_started and (not is_1tc or tc3_started) and (imp_clicked or sim.age == 4) and sim.bank.wood >= (200 + total_w_res) and sim.bank.gold >= 160:
                pavise_started = True
                sim.bank = sim.bank - ResourceBundle(wood=200, gold=150)
                sim.upgrades.add("pavise")
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    "Research Pavise at Castle (-200W, -150G, 40s)!",
                    "Italians Unique Tech: +1/+1 armor for Genoese Crossbowmen.",
                )

            if imp_clicked and not masonry_started and (not is_1tc or tc3_started) and sim.bank.food >= 180 and sim.bank.wood >= (117 + total_w_res):
                masonry_started = True
                sim.bank = sim.bank - ResourceBundle(food=100, wood=117)
                sim.upgrades.add("masonry")

            # Lumber Camp refreshes
            if not lc3_rebuilt and sim.wood_efficiency() <= 0.68 and sim.bank.wood >= (150 + tc_w_res + univ_w_res + sw_w_res):
                lc3_rebuilt = True
                sim.bank = sim.bank - ResourceBundle(wood=100)
                sim.lc_completed_s = t + 35
                sim.lc_count = 3
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    current_phase,
                    "Build refreshing Lumber Camp #3 (-100W, 35s) as wood efficiency drops below 68%.",
                    "Resets wood efficiency to 100%.",
                )
            if lc3_rebuilt and not lc4_rebuilt and sum(1 for v in sim.vils if v["role"] == "wood") >= 22 and sim.bank.wood >= (100 + total_w_res):
                lc4_rebuilt = True
                sim.bank = sim.bank - ResourceBundle(wood=100)
                sim.lc_completed_s = t + 35
                sim.lc_count = 4
            if lc4_rebuilt and not lc5_rebuilt and sum(1 for v in sim.vils if v["role"] == "wood") >= 30 and sim.bank.wood >= (100 + total_w_res):
                lc5_rebuilt = True
                sim.bank = sim.bank - ResourceBundle(wood=100)
                sim.lc_completed_s = t + 35
                sim.lc_count = 5

            # Farm conversion from excess Wood
            reserve_w = total_w_res + (175 if (is_1tc and not monastery_started) else 0)
            min_wood_keep = 12 if f_cnt_cur < 15 else (15 if f_cnt_cur < 26 else (20 if f_cnt_cur < 38 else 26))
            max_f_cap = 20 if (is_1tc and not imp_clicked) else (42 if is_1tc else 50)
            if f_cnt_cur < max_f_cap and sim.bank.wood >= (60 + reserve_w) and sim.bank.food < 1050:
                w_cnt_cur = sum(1 for v in sim.vils if v["role"] in ("wood", "straggler"))
                for v in sim.vils:
                    if (v["role"] == "straggler" or (v["role"] == "wood" and w_cnt_cur > min_wood_keep)) and int(v["busy_until"]) <= t:
                        sim.bank = sim.bank - ResourceBundle(wood=60)
                        v["role"] = "farm"
                        v["busy_until"] = t + 20
                        farms_seeded += 1
                        sim.register_new_farm()
                        if f_cnt_cur + 1 in (12, 15, 22, 30, 42):
                            add_row(
                                f"{len(sim.vils)}v ({total_pop()} pop)",
                                current_phase,
                                f"Transition villager to Farm #{farms_seeded} (-60W; {f_cnt_cur + 1} Active Farms).",
                                "Unlocks Wheelbarrow!" if (f_cnt_cur + 1 == 15) else "",
                            )
                        break

        # === IMPERIAL AGE FULL UPGRADES & SIEGE ===
        if sim.age == 4:
            if not conscription_started and sim.bank.food >= 150 and sim.bank.gold >= 150:
                conscription_started = True
                sim.bank = sim.bank - ResourceBundle(food=150, gold=150)
                sim.upgrades.add("conscription")
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    "Imperial Age",
                    "Research Conscription at Castle (-150F, -150G, 60s)!",
                    "+33% faster production across Castles & Stables.",
                )
            if not chemistry_started and sim.bank.food >= 201 and sim.bank.gold >= 134:
                chemistry_started = True
                chem_cost, chem_time = sim.db.get_upgrade_spec("chemistry", "Italians")
                sim.bank = sim.bank - chem_cost
                chemistry_ready_t = t + int(chem_time)
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    "Imperial Age",
                    f"Research Chemistry at University (-{chem_cost.food:.0f}F, -{chem_cost.gold:.0f}G Italians -33%, 100s).",
                    "Unlocks Bombard Cannons & +1 attack on Genoese.",
                )
            if not bracer_started and sim.bank.food >= 300 and sim.bank.gold >= 200:
                bracer_started = True
                sim.bank = sim.bank - ResourceBundle(food=300, gold=200)
                sim.upgrades.add("bracer")
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    "Imperial Age",
                    "Research Bracer at Blacksmith (-300F, -200G, 40s)!",
                    "Full +4 attack & +3 range on Genoese Crossbowmen.",
                )
            if not two_man_saw_started and (not is_1tc or tc3_started) and sim.bank.food >= 300 and sim.bank.wood >= (200 + total_w_res):
                two_man_saw_started = True
                sim.bank = sim.bank - ResourceBundle(food=300, wood=200)
                sim.upgrades.add("two-man saw")
            if is_1tc and not capped_ram_started and sim.bank.food >= 300:
                capped_ram_started = True
                sim.bank = sim.bank - ResourceBundle(food=300)
                sim.upgrades.add("capped ram")
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    "Imperial Age",
                    "Research Capped Ram at Forward Siege Workshop (-300F, 50s)!",
                    "Upgrades our forward Battering Rams into Capped Rams.",
                )
            if not ring_archer_started and bracer_started and sim.bank.food >= 250 and sim.bank.gold >= 250:
                ring_archer_started = True
                sim.bank = sim.bank - ResourceBundle(food=250, gold=250)
                sim.upgrades.add("ring archer armor")
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    "Imperial Age",
                    "Research Ring Archer Armor at Blacksmith (-250F, -250G, 70s).",
                    "",
                )
            if not plate_barding_started and ring_archer_started and sim.bank.food >= 350 and sim.bank.gold >= 200:
                plate_barding_started = True
                sim.bank = sim.bank - ResourceBundle(food=350, gold=200)
                sim.upgrades.add("plate barding armor")
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    "Imperial Age",
                    "Research Plate Barding Armor at Blacksmith (-350F, -200G, 75s).",
                    "",
                )
            if not blast_furnace_started and plate_barding_started and sim.bank.food >= 275 and sim.bank.gold >= 225:
                blast_furnace_started = True
                sim.bank = sim.bank - ResourceBundle(food=275, gold=225)
                sim.upgrades.add("blast furnace")
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    "Imperial Age",
                    "Research Blast Furnace at Blacksmith (-275F, -225G, 100s).",
                    "All Blacksmith upgrades complete!",
                )
            if not silk_armor_started and blast_furnace_started and sim.bank.wood >= (400 + total_w_res) and sim.bank.gold >= 300:
                silk_armor_started = True
                sim.bank = sim.bank - ResourceBundle(wood=400, gold=300)
                sim.upgrades.add("silk armor")
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    "Imperial Age",
                    "Research Silk Armor at Castle (-400W, -300G, 40s)!",
                    "Italians Imperial UT: +1/+1 armor for Light Cavalry / Hussars!",
                )
            if not siege_engineers_started and sim.bank.food >= 335 and sim.bank.wood >= (402 + total_w_res):
                siege_engineers_started = True
                sim.bank = sim.bank - ResourceBundle(food=335, wood=402)
                sim.upgrades.add("siege engineers")
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    "Imperial Age",
                    "Research Siege Engineers at University (-335F, -402W Italians -33%, 45s).",
                    "",
                )
            if blast_furnace_started and not hussar_started and sim.bank.food >= 500 and sim.bank.gold >= 600:
                hussar_started = True
                sim.bank = sim.bank - ResourceBundle(food=500, gold=600)
                sim.upgrades.add("hussar")
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    "Imperial Age",
                    "Research Hussar upgrade at Stable (-500F, -600G, 50s)!",
                    "Upgrades Light Cavalry to fully upgraded Hussars.",
                )
            if hussar_started and not elite_genoese_started and sim.bank.food >= 900 and sim.bank.gold >= 750:
                elite_genoese_started = True
                sim.bank = sim.bank - ResourceBundle(food=900, gold=750)
                sim.upgrades.add("elite genoese crossbowman")
                milestones["elite_genoese_str"] = sim.fmt_time(t)
                add_row(
                    f"{len(sim.vils)}v ({total_pop()} pop)",
                    "Imperial Age",
                    "Research Elite Genoese Crossbowman at Castle (-900F, -750G, 60s)!",
                    "Full Imperial composition online!",
                )
            if siege_engineers_started and not crop_rotation_started and sim.bank.food >= 250 and sim.bank.wood >= (250 + total_w_res):
                crop_rotation_started = True
                sim.bank = sim.bank - ResourceBundle(food=250, wood=250)
                sim.upgrades.add("crop rotation")

            # Bombard Cannons after Chemistry (produce first 2 immediately, then finish Hussar/Elite Genoese before #3-#4)
            if chemistry_ready_t is not None and t >= chemistry_ready_t:
                active_sws = (1 if (fwd_sw1_ready_t and t >= fwd_sw1_ready_t) else 0) + (1 if (fwd_sw2_ready_t and t >= fwd_sw2_ready_t) else 0)
                max_bbc_now = 4 if (hussar_started and elite_genoese_started) else 2
                for sw_idx in range(active_sws):
                    if t >= sw_busy_until[sw_idx] and bbc_count_trained < max_bbc_now and sim.bank.wood >= 180 and sim.bank.gold >= 180:
                        bbc_count_trained += 1
                        sim.bank = sim.bank - ResourceBundle(wood=180, gold=180)
                        sw_busy_until[sw_idx] = t + 56
                        sim.military_units["bombard_cannon"] += 1
                        if bbc_count_trained == 1:
                            milestones["bbc_queued_str"] = sim.fmt_time(t)
                            add_row(
                                f"{len(sim.vils)}v ({total_pop()} pop)",
                                "Imperial Age",
                                "Chemistry complete! Queue Bombard Cannon #1 at Forward Siege Workshop (-180W, -180G Italians -20%, 56s)!",
                                "",
                            )

            # Trebuchets from Forward Castles in Strategy 2 (1st immediately, extra after key unit upgrades)
            max_treb_now = 2 if (hussar_started and elite_genoese_started) else 1
            if not is_1tc and castle_count >= 2 and treb_count_trained < max_treb_now and sim.bank.wood >= (200 + sw_w_res) and sim.bank.gold >= 200:
                treb_count_trained += 1
                sim.bank = sim.bank - ResourceBundle(wood=200, gold=200)
                sim.military_units["trebuchet"] += 1
                if treb_count_trained == 1:
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        "Imperial Age",
                        "Queue Trebuchet #1 from Forward Castle (-200W, -200G).",
                        "",
                    )

            # Imperial Market trade if one resource floats heavily (15G per 100 sold per rules.md)
            if (t - last_market_trade_t) >= 90 and not elite_genoese_started and sim.bank.gold < 750:
                if sim.bank.wood >= 950:
                    last_market_trade_t = t
                    g_gain = sim.sell_at_market("wood", 200, castle_reached_t)
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        "Imperial Age",
                        f"Imperial Market trade: Sell 200 excess Wood for +{g_gain} Gold (Imp rate: 15G/100).",
                        "",
                    )
                elif sim.bank.food >= 1400:
                    last_market_trade_t = t
                    g_gain = sim.sell_at_market("food", 200, castle_reached_t)
                    add_row(
                        f"{len(sim.vils)}v ({total_pop()} pop)",
                        "Imperial Age",
                        f"Imperial Market trade: Sell 200 excess Food for +{g_gain} Gold (Imp rate: 15G/100).",
                        "",
                    )

        # Completion criterion
        done_1tc = (
            is_1tc
            and sim.age == 4
            and tc3_ready_t is not None
            and t >= tc3_ready_t
            and elite_genoese_started
            and hussar_started
            and bbc_count_trained >= 2
        )
        done_3tc = (
            not is_1tc
            and sim.age == 4
            and len(sim.vils) >= 120
            and elite_genoese_started
            and hussar_started
            and silk_armor_started
            and bbc_count_trained >= 2
        )
        if done_1tc or done_3tc:
            milestones["full_push_str"] = sim.fmt_time(t)
            milestones["final_vils"] = len(sim.vils)
            milestones["final_army"] = dict(sim.military_units)
            milestones["final_bank"] = sim.bank.to_dict()
            milestones["tc1_idle_before_imp_s"] = sim.tc1_idle_before_imp_s
            milestones["market_trades"] = sim.market_trades
            add_row(
                f"{len(sim.vils)}v ({total_pop()} pop)",
                "Imperial Age",
                f"FULL IMPERIAL COMPOSITION ONLINE! ({len(sim.vils)} Vils + {sum(sim.military_units.values())} Military = {total_pop()} Pop): {format_army_counts(sim.military_units).replace('Army: ', '')}.",
                f"Upgrades complete: Elite Genoese, Hussar, Bracer, Ballistics, Chemistry, Pavise, Silk Armor, full Blacksmith. TC #1 unplanned idle before Imp click: {sim.tc1_idle_before_imp_s}s.",
            )
            break

        sim.tick_gather()
        if t % 10 == 0:
            record_timeline_point()

    # Steady-state summary tailored to each strategy
    steady_state = planner.compute_steady_state_vils(
        items=[
            ContinuousProductionItem("villager", 1 if is_1tc else 3),
            ContinuousProductionItem("genoese crossbowman", 1 if is_1tc else 2),
            ContinuousProductionItem("scout cavalry", 1 if is_1tc else 2),
        ],
        civ="Italians",
        age=3,
        upgrades=["double-bit axe", "bow saw", "horse collar", "wheelbarrow", "gold mining"],
        food_source="farmer",
        wood_minutes_since_lc=1.0,
    )
    steady_state["title"] = (
        "Steady-State Target (1 TC Vils + 1 Castle Genoese + 1 Stable Light Cav + Farm Reseed)"
        if is_1tc
        else "Steady-State Target (3 TC Vils + 2 Castles Genoese + 2 Stables Light Cav + Farm Reseed)"
    )

    I = RTS_ICONS
    if is_1tc:
        castle_steps = [
            RTSOverlayStep(
                villager_count=28,
                age=3,
                wood=10,
                food=9,
                gold=5,
                stone=4,
                notes=[
                    f"Upon clicking {I['castle_age']}: research {I['double_bit_axe']} & {I['horse_collar']}. Seed Farms #3-#5, Gold Mining, {I['lumber_camp']} #2, {I['barracks']} -> {I['stable']} #1 & Fletching.",
                    f"On reaching {I['castle_age']} (650+ {I['stone']} ready!): immediately drop Defensive {I['castle']} (0s wait <= 10s max), research {I['bow_saw']}, and keep 1 {I['town_center']} continuous.",
                ],
            ),
            RTSOverlayStep(
                villager_count=38,
                age=3,
                wood=16,
                food=14,
                gold=6,
                stone=2,
                notes=[
                    f"Start Genoese Xbows at {I['castle']}, then {I['light_cavalry']} at {I['stable']} (never idle TC; drop to 2 on {I['stone']}).",
                    f"{I['build']} {I['monastery']} (-175W) and train 2 Monks (assume max 1 Relic secured = +30G/min).",
                    f"Get early Archer & Cav upgrades (Padded Archer, Bodkin, Scale Barding, Bloodlines, Forging); use {I['market']} (~50G/100 early-mid Castle) if Wood floats.",
                ],
            ),
            RTSOverlayStep(
                villager_count=52,
                age=3,
                wood=20,
                food=20,
                gold=10,
                stone=2,
                notes=[
                    f"At 30+ Army: send forward {I['villager']} to {I['build']} Forward {I['siege_workshop']} & train 3-4 {I['battering_ram']}s to push!",
                    f"Add {I['university']} ({I['ballistics']}), {I['wheelbarrow']}, Stable #2, and stick strictly to 1 {I['town_center']} until clicking {I['imperial_age']} (use {I['market']} at ~30G/100 if needed).",
                ],
            ),
            RTSOverlayStep(
                villager_count=90,
                age=4,
                wood=34,
                food=32,
                gold=22,
                stone=2,
                notes=[
                    f"After clicking {I['imperial_age']}: add {I['town_center']} #2 & #3 as soon as affordable!",
                    f"Research {I['chemistry']}, Conscription, Bracer, Capped Ram, Hussar, Elite Genoese, Pavise & Silk Armor + {I['bombard_cannon']}s!",
                ],
            ),
        ]
    else:
        castle_steps = [
            RTSOverlayStep(
                villager_count=28,
                age=3,
                wood=10,
                food=9,
                gold=5,
                stone=4,
                notes=[
                    f"Upon clicking {I['castle_age']}: research {I['double_bit_axe']} & {I['horse_collar']}. Seed Farms #3-#5, Gold Mining, {I['lumber_camp']} #2, {I['barracks']} -> {I['stable']} #1 & Fletching.",
                    f"On reaching {I['castle_age']} (650+ {I['stone']} ready!): immediately drop Defensive {I['castle']} (0s wait <= 10s max), research {I['bow_saw']}, and keep {I['town_center']} #1 continuous.",
                ],
            ),
            RTSOverlayStep(
                villager_count=38,
                age=3,
                wood=14,
                food=14,
                gold=6,
                stone=4,
                notes=[
                    f"Build ~20 Army (10-15 Genoese + 6-10 {I['light_cavalry']}) with early upgrades (Fletching, Padded Archer, Scale Barding, Bloodlines, Bodkin).",
                    f"At ~20 Army: PAUSE military production, drop {I['town_center']} #2 & #3, and prioritize Villagers, {I['farm']}s (22+), & {I['wheelbarrow']}.",
                ],
            ),
            RTSOverlayStep(
                villager_count=75,
                age=3,
                wood=26,
                food=28,
                gold=15,
                stone=6,
                notes=[
                    f"Once 3-TC continuous vil boom is set up: maximize Genoese + {I['light_cavalry']} across multiple Castles & Stables!",
                    f"Research {I['university']} ({I['ballistics']}), full Blacksmith upgrades, Husbandry, Pavise, Heavy Plow & {I['hand_cart']}; send forward vils for Castle #2, TC #4 & {I['siege_workshop']}s.",
                ],
            ),
            RTSOverlayStep(
                villager_count=125,
                age=4,
                wood=44,
                food=45,
                gold=34,
                stone=2,
                notes=[
                    f"Click {I['imperial_age']} (use {I['market']} at ~30G/100 if helpful), research {I['chemistry']}, Bracer, Ring Archer, Plate Barding, Blast Furnace, Hussar, Elite Genoese, Silk Armor & Siege Engineers!",
                    f"Flood 200/200 Pop with Elite Genoese, Hussars, {I['bombard_cannon']}s & {I['trebuchet']}s.",
                ],
            ),
        ]

    rts_steps = [
        RTSOverlayStep(
            villager_count=6,
            age=1,
            wood=0,
            food=6,
            gold=0,
            stone=0,
            notes=[
                f"Vils #1-#3 {I['build']} 2 Houses at 0:00 then {I['sheep']} (5s walk). Vils #4-#6 to {I['sheep']}. Push 3 {I['deer']} (no Chickens).",
            ],
        ),
        RTSOverlayStep(
            villager_count=7,
            age=1,
            wood=1,
            food=6,
            gold=0,
            stone=0,
            notes=[f"Vil #7 walks 15s + {I['build']} {I['lumber_camp']} #1 -> {I['wood']}."],
        ),
        RTSOverlayStep(
            villager_count=9,
            age=1,
            wood=3,
            food=6,
            gold=0,
            stone=0,
            notes=[f"Vils #8-#9 to {I['wood']} at {I['lumber_camp']} #1."],
        ),
        RTSOverlayStep(
            villager_count=10,
            age=1,
            wood=3,
            food=7,
            gold=0,
            stone=0,
            notes=[f"Vil #10 lures 1st {I['boar']} (arrives 03:25)."],
        ),
        RTSOverlayStep(
            villager_count=11,
            age=1,
            wood=4,
            food=7,
            gold=0,
            stone=0,
            notes=[f"Vil #11 to {I['wood']} at {I['lumber_camp']} #1 (4 on Wood)."],
        ),
        RTSOverlayStep(
            villager_count=12,
            age=1,
            wood=4,
            food=8,
            gold=0,
            stone=0,
            notes=[f"Vil #12 {I['build']} House #3 -> Pushed {I['deer']} under TC."],
        ),
        RTSOverlayStep(
            villager_count=15,
            age=1,
            wood=4,
            food=11,
            gold=0,
            stone=0,
            notes=[f"Vils #13-#15 to Pushed {I['deer']} under TC (4 on Deer + 7 on Boar). Lure 2nd {I['boar']} at 04:43."],
        ),
        RTSOverlayStep(
            villager_count=16,
            age=1,
            wood=4,
            food=12,
            gold=0,
            stone=0,
            notes=[f"Vil #16 {I['build']} {I['mill']} on {I['berries']} -> {I['berries']}."],
        ),
        RTSOverlayStep(
            villager_count=19,
            age=1,
            wood=4,
            food=15,
            gold=0,
            stone=0,
            notes=[f"Vils #17-#19 to {I['berries']} (Vil #18 builds House #4 first; 4/4 on Berries)."],
        ),
        RTSOverlayStep(
            villager_count=20,
            age=1,
            wood=5,
            food=15,
            gold=0,
            stone=0,
            notes=[f"Vil #20 to {I['wood']} at {I['lumber_camp']} #1 (5 on Wood)."],
        ),
        RTSOverlayStep(
            villager_count=21,
            age=1,
            wood=5,
            food=15,
            gold=0,
            stone=1,
            notes=[f"Vil #21 {I['build']} {I['mining_camp']} on {I['stone']} -> {I['stone']}."],
        ),
        RTSOverlayStep(
            villager_count=24,
            age=1,
            wood=5,
            food=15,
            gold=0,
            stone=4,
            notes=[f"Vils #22-#24 to {I['stone']} (Vil #24 builds House #5 first; 4/4 on Stone)."],
        ),
        RTSOverlayStep(
            villager_count=26,
            age=1,
            wood=7,
            food=15,
            gold=0,
            stone=4,
            notes=[
                f"Vils #25-#26 to {I['wood']} (7 on LC #1). Click {I['feudal_age']} (425F, 0s TC idle).",
            ],
        ),
        RTSOverlayStep(
            villager_count=28,
            age=2,
            wood=11,
            food=11,
            gold=2,
            stone=4,
            notes=[
                f"In {I['feudal_age']}: queue +2 {I['villager']}s to {I['gold']} MC; 3 vils {I['build']} {I['market']} & 1 vil {I['build']} {I['blacksmith']}.",
                f"Sell 100 {I['stone']} at {I['market']} (+70G high Feudal price) & click {I['castle_age']} (680F, 170G).",
            ],
        ),
        *castle_steps,
    ]

    desc = (
        "Italians Arena Strategy 1 (3 Deer, No Chickens): 26+2 Fast Castle -> Defensive Castle (0s wait) -> "
        "Genoese Crossbowmen + Light Cavalry (never idling TC) + Monastery & 2 Monks (max 1 Relic assumed) -> "
        "Forward Siege Workshop & Battering Rams at 30+ army -> Stick to 1 TC until clicking Imperial Age, then add TCs & push!"
        if is_1tc
        else "Italians Arena Strategy 2 (3 Deer, No Chickens): 26+2 Fast Castle -> Defensive Castle (0s wait) -> "
        "~20 Army (10-15 Genoese, 6-10 Light Cav) -> Pause military & expand to 3 TCs with continuous Villagers -> "
        "Maximize army production with full upgrades (Ballistics, Pavise, Silk Armor, Elite Genoese, Hussars, BBCs, Trebs)."
    )

    doc = BuildOrderDocument(
        name="Italians Arena Fast Castle",
        civilization="Italians",
        variant_label=variant_label,
        description=desc,
        rows=rows,
        rts_steps=rts_steps,
        steady_state_summary=steady_state,
        telemetry_summary={
            "rotted_food": {k: round(v, 1) for k, v in sim.rotted_food.items()},
            "total_rotted_food": round(sum(sim.rotted_food.values()), 1),
        },
        resource_timeline=resource_timeline,
    )
    return doc, milestones


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    strategies = [
        ("1tc_push", "italians_arena_fc_genoese_1tc_push.json"),
        ("3tc_balanced", "italians_arena_fc_genoese_3tc_balanced.json"),
    ]

    docs: List[BuildOrderDocument] = []
    for strat, json_name in strategies:
        doc, ms = run_italians_arena_strategy(strat)
        docs.append(doc)
        json_path = export_rts_overlay_json(doc, OUT_DIR / json_name)
        print(f"=== {ms['variant']} ===")
        for k, v in ms.items():
            if k != "variant":
                print(f"  {k}: {v}")
        print(f"  Rot telemetry: {doc.telemetry_summary['rotted_food']} (Total: {doc.telemetry_summary['total_rotted_food']}F)")
        print(f"  Wrote RTS Overlay JSON: {json_path} ({len(doc.rts_steps)} steps)\n")

    html_path = export_build_order_html(
        docs,
        title="Italians Arena Fast Castle: 1 TC Heavy Army Push vs Balanced 3 TC Boom (3 Deer)",
        output_path=OUT_DIR / "italians_arena_fc_genoese.html",
    )
    print(f"Wrote HTML report: {html_path}")


if __name__ == "__main__":
    main()

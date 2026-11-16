#!/usr/bin/env python3
"""
Generator & 1-Second Discrete-Event Simulator for:
Italians Arena Fast Castle Build Orders (3 Deer Pushed, No Chickens)

2 Distinct Strategies displayed in top-level HTML tabs + Strategy Comparison chart + separate JSONs:
1. Strategy 1: 1 TC Heavy Army Push (`1tc_push`):
   - 26+2 FC -> Defensive Castle (0s wait <= 10s max) -> Genoese + Light Cav
   - Monastery + 2 Monks (conservatively assume max 1 Relic secured = +30G/min)
   - Ballistics priority at 20+ Genoese -> Forward Siege Workshop & 3-4 Rams at 30+ army
   - Stick strictly to 1 TC until clicking Imperial Age (<40:00 goal), then add TC #2 & #3
2. Strategy 2: Balanced 3 TC Boom (`3tc_balanced`):
   - 26+2 FC -> Defensive Castle (0s wait <= 10s max) -> ~20 Army (13 Genoese + 7 Light Cav)
   - Pause military -> Expand to 3 TCs with continuous Villagers until 3-TC boom is set up
   - Resume & maximize Genoese + Light Cav -> Ballistics priority at 20+ Genoese ->
     Forward Castle #2/#3, TC #4 & Siege Workshops -> Imperial Age (<40:00) with <500-1000 float

Enforces all updated rules from `rules.md` and `output.md`:
- Boar shooting TC-garrison idling (7 TC vils x 5s per boar) + post-kill transition
- Animal villager caps (<=7 Sheep, 7-8 Boar / 10 transition, 4-7 Deer)
- Later-stage imperfect execution buffers (92% Feudal, 90% Castle+)
- Combined same-resource rows for Dark/Feudal/Castle-Click + high-level macro blocks for Castle+
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
    """Runs a 1-second resolution simulation for `1tc_push` or `3tc_balanced`."""
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

    def add_row(pop_str: str, time_str: str, phase: str, action: str, notes: str = "") -> None:
        alloc = sim.current_macro_alloc()
        fb = sim.current_food_breakdown()
        rows.append(
            DetailedBuildRow(
                pop=pop_str,
                timestamp=time_str,
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

    # t = 0:00 initial state (3 vils build 2 houses, TC queues Vil #4)
    sim.bank = sim.bank - ResourceBundle(food=50)
    sim.tc_busy_until[0] = 25
    sim.tc_action[0] = "vil_4"
    sim.lc_count = 0
    record_timeline_point()

    boar1_shot = False
    boar2_lured = False
    boar2_shot = False

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
    castle_busy_until: List[int] = [0, 0, 0, 0]

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
    army20_t: Optional[int] = None
    boom3tc_ready_logged = False
    boom3tc_setup_t: Optional[int] = None

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

    imp_prep_started = False
    imp_prep_t: Optional[int] = None
    imp_clicked = False
    imp_click_t = 0
    imp_reached_t: Optional[int] = None
    conscription_started = False
    elite_genoese_started = False
    hussar_started = False
    treb_count_trained = 0
    bbc_count_trained = 0
    market_trades_castle = 0
    last_market_trade_t = -999

    castle_loop1_logged = False
    castle_loop2_logged = False
    imp_loop_logged = False
    max_castle_float = {"food": 0.0, "wood": 0.0, "gold": 0.0}

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

        # Boar #1 arrival at 03:25 (t=205): 7 TC vils garrison for 5s to shoot boar down
        if not boar1_shot and t == 205:
            boar1_shot = True
            garr = 0
            for v in sim.vils:
                if v["role"] in ("sheep", "boar") and garr < sim.rules.boar_garrison_vils:
                    v["busy_until"] = max(int(v["busy_until"]), t + int(sim.rules.boar_garrison_seconds))
                    garr += 1
            if sim.active_carcass_food["sheep"] <= 40.0:
                kept_one = False
                for v in sim.vils:
                    if v["role"] == "sheep":
                        if not kept_one and sim.active_carcass_food["sheep"] > 5.0:
                            kept_one = True
                        else:
                            v["role"] = "boar"

        # Sheep #4 finishes -> remaining shepherd joins Boar #1
        if t >= 205 and sim.remaining_animals["sheep"] == 4 and sim.active_carcass_food["sheep"] <= 1e-6:
            for v in sim.vils:
                if v["role"] == "sheep":
                    v["role"] = "boar"

        # Boar #2 lure at t=283 (04:43) -> arrives at t=313 (05:13)
        if not boar2_lured and t == 283:
            boar2_lured = True
            for v in sim.vils:
                if v["role"] == "boar":
                    v["busy_until"] = t + 30
                    break
        if not boar2_shot and t == 313:
            boar2_shot = True
            garr = 0
            for v in sim.vils:
                if v["role"] in ("sheep", "boar") and garr < sim.rules.boar_garrison_vils:
                    v["busy_until"] = max(int(v["busy_until"]), t + int(sim.rules.boar_garrison_seconds))
                    garr += 1

        # Strategy 1: Only assume 1 Relic is secured
        if is_1tc and relic1_time is not None and t == relic1_time:
            sim.relics_garrisoned = 1
            milestones["relic1_str"] = sim.fmt_time(t)

        # Check TC completions
        for tc_idx in range(sim.tc_count):
            if t == sim.tc_busy_until[tc_idx] and sim.tc_action[tc_idx] != "idle":
                act = sim.tc_action[tc_idx]
                sim.tc_action[tc_idx] = "idle"

                if act.startswith("vil_"):
                    vid = len(sim.vils) + 1

                    if sim.age == 1:
                        if vid in (4, 5, 6):
                            sim.vils.append({"id": vid, "role": "sheep", "busy_until": t})
                            if vid == 6:
                                add_row(
                                    "3–6 (4–7)",
                                    "00:00 – 01:15",
                                    "Dark Age",
                                    "Vils #1–#6 (6 vils) -> Build 2 Houses (-50W), then all 6 on Sheep under TC.",
                                    "Start 200F, 200W, 100G, 200S. Max 7 on Sheep; push 3 Deer inside Arena walls; delay Loom.",
                                )
                        elif vid == 7:
                            sim.bank = sim.bank - ResourceBundle(wood=100)
                            sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 50})
                            sim.lc_completed_s = t + 50
                            sim.lc_count = 1
                        elif vid in (8, 9):
                            sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 15})
                            if vid == 9:
                                add_row(
                                    "7–9 (8–10)",
                                    "01:40 – 02:30",
                                    "Dark Age",
                                    "Vils #7–#9 (3 vils) -> Wood (1st vil walks 15s + builds Lumber Camp #1 [-100W, 35s], then all 3 on Wood).",
                                    "LC #1 completes at 02:30 (100% wood efficiency; -1% decay per 20s).",
                                )
                        elif vid == 10:
                            sim.vils.append({"id": vid, "role": "boar", "busy_until": t + 30})
                            add_row(
                                "10 (11)",
                                "02:55",
                                "Dark Age",
                                "Vil #10 -> Lure Boar #1 (15s out + 15s back).",
                                "Boar #1 arrives 03:25 -> garrison 7 TC vils 5s to shoot boar; put 6+ vils on Boar (1 vil finishes ~24F on Sheep #4).",
                            )
                        elif vid == 11:
                            sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 15})
                            add_row(
                                "11 (12)",
                                "03:20",
                                "Dark Age",
                                "Vil #11 -> Wood at Lumber Camp #1 (15s walk; 4 on Wood).",
                                "",
                            )
                        elif vid == 12:
                            sim.bank = sim.bank - ResourceBundle(wood=25)
                            sim.vils.append({"id": vid, "role": "deer", "busy_until": t + 35})
                        elif vid in (13, 14, 15):
                            sim.vils.append({"id": vid, "role": "deer", "busy_until": t})
                            if vid == 15:
                                add_row(
                                    "12–15 (13–16)",
                                    "03:45 – 05:00",
                                    "Dark Age",
                                    "Vils #12–#15 (4 vils) -> Pushed Deer under TC (1st vil builds House #3 [-25W], then all 4 on Deer).",
                                    "7 on Boar + 4 on Deer. At 04:43, 1 hunter lures Boar #2 (arrives 05:13; garrison 7 TC vils 5s to shoot).",
                                )
                        elif vid == 16:
                            sim.bank = sim.bank - ResourceBundle(wood=100)
                            sim.vils.append({"id": vid, "role": "berries", "busy_until": t + 50})
                        elif vid == 17:
                            sim.vils.append({"id": vid, "role": "berries", "busy_until": t + 15})
                        elif vid == 18:
                            sim.bank = sim.bank - ResourceBundle(wood=25)
                            sim.vils.append({"id": vid, "role": "berries", "busy_until": t + 45})
                        elif vid == 19:
                            sim.vils.append({"id": vid, "role": "berries", "busy_until": t + 15})
                            add_row(
                                "16–19 (17–20)",
                                "05:25 – 06:40",
                                "Dark Age",
                                "Vils #16–#19 (4 vils) -> Berries at Mill (1st vil builds Mill [-100W, 50s], 3rd vil builds House #4 [-25W], all 4 on Berries).",
                                "4/4 on Berries.",
                            )
                        elif vid == 20:
                            sim.bank = sim.bank - ResourceBundle(wood=100)
                            sim.vils.append({"id": vid, "role": "stone", "busy_until": t + 50})
                        elif vid in (21, 22):
                            sim.vils.append({"id": vid, "role": "stone", "busy_until": t + 15})
                        elif vid == 23:
                            sim.bank = sim.bank - ResourceBundle(wood=25)
                            sim.vils.append({"id": vid, "role": "stone", "busy_until": t + 45})
                            add_row(
                                "20–23 (21–24)",
                                "07:05 – 08:20",
                                "Dark Age",
                                "Vils #20–#23 (4 vils) -> Stone at Mining Camp (1st vil builds Stone MC [-100W, 50s], 4th vil builds House #5 [-25W], all 4 on Stone).",
                                "4/4 Dark Age Stone miners fund instant 0s-wait Defensive Castle on Castle Age arrival.",
                            )
                        elif vid in (24, 25):
                            sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 15})
                        elif vid == 26:
                            sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 15})
                            add_row(
                                "24–26 (25–27)",
                                "08:45 – 09:35",
                                "Dark Age",
                                "Vils #24–#26 (3 vils) -> Wood at Lumber Camp #1 (15s walk; 7 on Wood).",
                                "26 Dark Age vils complete (7 on LC #1 <= 8 max); ready to click Feudal Age (425F) with 0s TC idle.",
                            )

                        if vid < dark_vils:
                            sim.bank = sim.bank - ResourceBundle(food=50)
                            sim.tc_busy_until[0] = t + 25
                            sim.tc_action[0] = f"vil_{vid+1}"

                    elif sim.age == 2:
                        if not gold_mc_started:
                            gold_mc_started = True
                            sim.bank = sim.bank - ResourceBundle(wood=100)
                            sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 50})
                        else:
                            sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                            add_row(
                                "27–28 (28–29)",
                                "12:10 – 12:35",
                                "Feudal Age",
                                "Vils #27–#28 (2 vils) -> Gold (1st vil builds Mining Camp [-100W, 50s], then both on Gold); Market sells 100 Stone (+70G high Feudal price).",
                                "100 starting Gold + 70G Market sale = exact 170G for Italians Castle Age; Market & Blacksmith complete cleanly.",
                            )

                    else:
                        g_cnt = sim.count_role("gold")
                        w_cnt = sim.count_role("wood", "straggler")
                        f_cnt = sim.count_role("farm")
                        s_cnt = sim.count_role("stone")

                        if is_1tc:
                            saving_wood_for_bldg = (
                                (not monastery_started and sim.bank.wood < 175)
                                or (sim.military_units["genoese"] >= 20 and not univ_started and sim.bank.wood < 200)
                                or (univ_ready_t is not None and t >= univ_ready_t and not ballistics_started and sim.bank.wood < 201)
                                or (army30_reached and not fwd_sw1_started and sim.bank.wood < 200)
                                or (imp_clicked and not tc2_started and sim.bank.stone >= 100 and sim.bank.wood < 275)
                                or (imp_clicked and tc2_started and not tc3_started and sim.bank.stone >= 100 and sim.bank.wood < 275)
                            )
                            gold_target = 10 if not imp_clicked else (18 if len(sim.vils) < 75 else 24)
                            farm_target_early = 18 if not imp_clicked else 32
                            wood_target_early = 15 if not imp_clicked else 26
                            stone_target = 2 if not tc3_started else 0

                            if f_cnt < 12 and sim.bank.wood >= 60 and not saving_wood_for_bldg:
                                sim.bank = sim.bank - ResourceBundle(wood=60)
                                farms_seeded += 1
                                sim.register_new_farm()
                                sim.vils.append({"id": vid, "role": "farm", "busy_until": t + 20})
                            elif w_cnt < wood_target_early:
                                sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 15})
                            elif g_cnt < gold_target and sim.bank.gold < 700:
                                sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                            elif f_cnt < farm_target_early and sim.bank.wood >= 60 and not saving_wood_for_bldg:
                                sim.bank = sim.bank - ResourceBundle(wood=60)
                                farms_seeded += 1
                                sim.register_new_farm()
                                sim.vils.append({"id": vid, "role": "farm", "busy_until": t + 20})
                            elif s_cnt < stone_target and sim.bank.stone < 250:
                                sim.vils.append({"id": vid, "role": "stone", "busy_until": t + 15})
                            elif f_cnt < 36 and sim.bank.wood >= 60 and not saving_wood_for_bldg and sim.bank.food < 950:
                                sim.bank = sim.bank - ResourceBundle(wood=60)
                                farms_seeded += 1
                                sim.register_new_farm()
                                sim.vils.append({"id": vid, "role": "farm", "busy_until": t + 20})
                            elif g_cnt < 26 and sim.bank.gold < 750:
                                sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                            else:
                                sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 15})
                        else:
                            saving_wood_for_bldg = (
                                (army20_reached and not tc2_started and sim.bank.stone >= 80 and sim.bank.wood < 275)
                                or (tc2_started and not tc3_started and sim.bank.stone >= 90 and sim.bank.wood < 275)
                                or (boom3tc_ready_logged and sim.military_units["genoese"] >= 20 and not univ_started and sim.bank.wood < 200)
                                or (univ_ready_t is not None and t >= univ_ready_t and not ballistics_started and sim.bank.wood < 201)
                                or (fwd_vils_arrive_t is not None and t >= fwd_vils_arrive_t and not tc4_started and sim.bank.stone >= 100 and sim.bank.wood < 275)
                            )
                            gold_target_early = 7 if not army20_reached else (6 if not boom3tc_ready_logged else 18)
                            if f_cnt < 12 and sim.bank.wood >= 60 and not saving_wood_for_bldg:
                                sim.bank = sim.bank - ResourceBundle(wood=60)
                                farms_seeded += 1
                                sim.register_new_farm()
                                sim.vils.append({"id": vid, "role": "farm", "busy_until": t + 20})
                            elif g_cnt < gold_target_early and sim.bank.gold < 320:
                                sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                            elif w_cnt < 14:
                                sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 15})
                            elif f_cnt < 22 and sim.bank.wood >= 60 and not saving_wood_for_bldg:
                                sim.bank = sim.bank - ResourceBundle(wood=60)
                                farms_seeded += 1
                                sim.register_new_farm()
                                sim.vils.append({"id": vid, "role": "farm", "busy_until": t + 20})
                            elif tc3_ready_t is not None and t >= tc3_ready_t and len(sim.vils) >= 48 and s_cnt < 6 and not fwd_castle3_started and sim.bank.stone < 800:
                                sim.vils.append({"id": vid, "role": "stone", "busy_until": t + 15})
                            elif w_cnt < 24:
                                sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 15})
                            elif f_cnt < 32 and sim.bank.wood >= 60 and not saving_wood_for_bldg and sim.bank.food < 950:
                                sim.bank = sim.bank - ResourceBundle(wood=60)
                                farms_seeded += 1
                                sim.register_new_farm()
                                sim.vils.append({"id": vid, "role": "farm", "busy_until": t + 20})
                            elif g_cnt < 26 and f_cnt >= 22 and sim.bank.gold < 800:
                                sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                            elif f_cnt < 44 and sim.bank.wood >= 60 and not saving_wood_for_bldg and sim.bank.food < 950:
                                sim.bank = sim.bank - ResourceBundle(wood=60)
                                farms_seeded += 1
                                sim.register_new_farm()
                                sim.vils.append({"id": vid, "role": "farm", "busy_until": t + 20})
                            else:
                                sim.vils.append({"id": vid, "role": "gold" if sim.bank.gold < 800 else "wood", "busy_until": t + 15})

                elif act == "feudal":
                    sim.age = 2
                    milestones["feudal_reached_s"] = t
                    milestones["feudal_reached_str"] = sim.fmt_time()

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
                        f"{len(sim.vils)} ({total_pop()})",
                        sim.fmt_time(),
                        "Feudal Age",
                        "REACHED FEUDAL AGE! Queue +2 Feudal Vils -> Gold MC; 3 vils build Market (-175W, 46s) & 1 vil builds Blacksmith (-150W, 50s).",
                        "92% Feudal macro efficiency buffer active. Both buildings finish cleanly in 50s.",
                    )

                elif act == "castle":
                    sim.age = 3
                    castle_reached_t = t
                    milestones["castle_reached_s"] = t
                    milestones["castle_reached_str"] = sim.fmt_time()
                    milestones["castle_arrival_bank"] = sim.bank.to_dict()

                    # Log single consolidated Castle Transition macro row ending right at Castle Age
                    add_row(
                        f"{len(sim.vils)} ({total_pop()})",
                        f"{sim.fmt_time(castle_click_t)} – {sim.fmt_time()}",
                        "Castle Transition",
                        "Castle Transition Macro: Research Double-Bit Axe (-100F, -50W) & Horse Collar (-75F, -75W), seed Farms #3–#5 (-60W each), research Gold Mining (-100F, -75W), build Lumber Camp #2 (-100W, resets wood eff. to 100%), build Barracks (-175W) -> chain Stable #1 (-175W, 0s walk), and research Fletching (-100F, -50G).",
                        "Sequential Barracks -> Stable #1 saves 20s walk; arrives Castle Age with 650+ Stone & full eco upgrades.",
                    )

                    # Queue Vil #29 + Bow Saw (if affordable); drop Defensive Castle as soon as 650S is banked (0s-wait if >= 650S)
                    sim.bank = sim.bank - ResourceBundle(food=50)
                    sim.tc_busy_until[0] = t + 25
                    sim.tc_action[0] = f"vil_{len(sim.vils)+1}"

                    bow_saw_note = ""
                    if sim.bank.food >= 150 and sim.bank.wood >= 100:
                        bow_saw_started = True
                        sim.bank = sim.bank - ResourceBundle(food=150, wood=100)
                        sim.upgrades.add("bow saw")
                        bow_saw_note = " & research Bow Saw (-150F, -100W)"

                    if sim.bank.stone >= 650:
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
                        add_row(
                            f"{len(sim.vils)} ({total_pop()})",
                            sim.fmt_time(),
                            "Castle Age",
                            f"REACHED CASTLE AGE! Drop Defensive Castle with 6 vils (-650S, 0s wait <= 10s max -> ready {sim.fmt_time(t+85)}){bow_saw_note}; keep TC #1 continuous.",
                            "90% Castle+ macro efficiency buffer active. Defensive Castle secures Arena map & starts Genoese production.",
                        )
                    else:
                        add_row(
                            f"{len(sim.vils)} ({total_pop()})",
                            sim.fmt_time(),
                            "Castle Age",
                            f"REACHED CASTLE AGE! Queue Vil #{len(sim.vils)+1}{bow_saw_note}; drop Defensive Castle as soon as 650 Stone arrives.",
                            "90% Castle+ macro efficiency buffer active.",
                        )

                elif act == "loom":
                    sim.upgrades.add("loom")
                    milestones["loom_done_str"] = sim.fmt_time(t)

                elif act == "wheelbarrow":
                    sim.upgrades.add("wheelbarrow")
                    milestones["wheelbarrow_done_s"] = t
                    milestones["wheelbarrow_done_str"] = sim.fmt_time(t)

                elif act == "hand_cart":
                    sim.upgrades.add("hand cart")
                    milestones["hand_cart_done_str"] = sim.fmt_time(t)

                elif act == "imperial":
                    sim.age = 4
                    imp_reached_t = t
                    milestones["imp_reached_s"] = t
                    milestones["imp_reached_str"] = sim.fmt_time(t)
                    milestones["imp_arrival_bank"] = sim.bank.to_dict()
                    milestones["imp_arrival_army"] = dict(sim.military_units)

                    # Log Imperial Transition summary row
                    trans_txt = (
                        f"Imperial Transition (190s): Add TC #2 & TC #3 (-275W, -100S each) using banked Stone while keeping Genoese, Light Cav & Rams scaling."
                        if is_1tc
                        else f"Imperial Transition (190s): Continue multi-TC boom to {len(sim.vils)} vils, add Forward Castles / SW #2 & keep military scaling."
                    )
                    add_row(
                        f"{len(sim.vils)} ({total_pop()})",
                        f"{sim.fmt_time(imp_click_t)} – {sim.fmt_time()}",
                        "Imperial Transition",
                        trans_txt,
                        f"Arrives Imperial Age at {sim.fmt_time()} (<40:00 goal!).",
                    )

                    chem_cost, chem_time = sim.db.get_upgrade_spec("chemistry", "Italians")
                    if sim.bank.food >= chem_cost.food + 150 and sim.bank.gold >= chem_cost.gold + 150:
                        chemistry_started = True
                        conscription_started = True
                        sim.bank = sim.bank - chem_cost - ResourceBundle(food=150, gold=150)
                        chemistry_ready_t = t + int(chem_time)
                        sim.upgrades.add("conscription")
                    elif sim.bank.food >= 150 and sim.bank.gold >= 150:
                        conscription_started = True
                        sim.bank = sim.bank - ResourceBundle(food=150, gold=150)
                        sim.upgrades.add("conscription")

                    add_row(
                        f"{len(sim.vils)} ({total_pop()})",
                        sim.fmt_time(),
                        "Imperial Age",
                        f"REACHED IMPERIAL AGE! Research Conscription (-150F, -150G), Chemistry (-{chem_cost.food:.0f}F, -{chem_cost.gold:.0f}G Italians -33%), Bracer, Elite Genoese, Hussar, Pavise, Silk Armor & Siege Engineers; produce Bombard Cannons (-180W, -180G).",
                        f"Bank on Imp arrival: {sim.bank.food:.0f}F / {sim.bank.wood:.0f}W / {sim.bank.gold:.0f}G / {sim.bank.stone:.0f}S.",
                    )
                    imp_loop_logged = True

        # Click Feudal Age
        if sim.age == 1 and not feudal_clicked and sim.tc_action[0] == "idle" and len(sim.vils) == dark_vils:
            if sim.bank.food >= 425:
                feudal_clicked = True
                milestones["feudal_click_s"] = t
                milestones["feudal_click_str"] = sim.fmt_time(t)
                sim.bank = sim.bank - ResourceBundle(food=425)
                sim.tc_busy_until[0] = t + 130
                sim.tc_action[0] = "feudal"
                add_row(
                    f"{len(sim.vils)} ({total_pop()})",
                    sim.fmt_time(),
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
                    sim.register_new_farm()
            cur_lc_w = sim.count_role("wood")
            moved_w = 0
            for v in sim.vils:
                if v["role"] == "straggler" and int(v["busy_until"]) <= t and (cur_lc_w + moved_w) < 8:
                    v["role"] = "wood"
                    v["busy_until"] = t + 15
                    moved_w += 1
            add_row(
                f"{len(sim.vils)} ({total_pop()})",
                sim.fmt_time(),
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
            sim.sell_at_market("stone", 100, castle_reached_t)

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
            milestones["castle_click_s"] = t
            milestones["castle_click_str"] = sim.fmt_time(t)
            sim.bank = sim.bank - ResourceBundle(food=680, gold=170)
            sim.tc_busy_until[0] = t + 160
            sim.tc_action[0] = "castle"
            moved_g = 0
            for v in sim.vils:
                if v["role"] in ("straggler", "wood") and int(v["busy_until"]) <= t and moved_g < 3:
                    v["role"] = "gold"
                    v["busy_until"] = t + 15
                    moved_g += 1
            tot_g_now = sim.count_role("gold")
            add_row(
                f"{len(sim.vils)} ({total_pop()})",
                sim.fmt_time(),
                "Feudal Age",
                f"CLICK CASTLE AGE (-680F, -170G Italians -15%, 160s, 0s TC idle) -> move {moved_g} Market/BS builders to Gold ({tot_g_now} on Gold).",
                f"Reaches Castle Age at {sim.fmt_time(t + 160)}.",
            )

        # Castle Transition hidden execution: DBA, Horse Collar, Farms #3-#5, Gold Mining, LC #2, Barracks -> Stable #1, Fletching
        if castle_clicked and sim.age >= 2 and t >= castle_click_t + 1:
            if not dba_started and sim.bank.food >= 100 and sim.bank.wood >= 50:
                dba_started = True
                sim.bank = sim.bank - ResourceBundle(food=100, wood=50)
                sim.upgrades.add("double-bit axe")
            if dba_started and not hc_started and sim.bank.food >= 75 and sim.bank.wood >= 75:
                hc_started = True
                sim.bank = sim.bank - ResourceBundle(food=75, wood=75)
                sim.upgrades.add("horse collar")
            if hc_started and sim.age == 2 and farms_seeded < 5 and sim.bank.wood >= 150:
                for v in sim.vils:
                    if v["role"] in ("straggler", "wood") and int(v["busy_until"]) <= t:
                        sim.bank = sim.bank - ResourceBundle(wood=60)
                        v["role"] = "farm"
                        v["busy_until"] = t + 20
                        farms_seeded += 1
                        sim.register_new_farm()
                        break
            if not gold_mining_started and hc_started and (farms_seeded >= 5 or sim.age >= 3) and sim.bank.food >= 150 and sim.bank.wood >= 75:
                gold_mining_started = True
                sim.bank = sim.bank - ResourceBundle(food=100, wood=75)
                sim.upgrades.add("gold mining")
            if not lc2_rebuilt and gold_mining_started and sim.bank.wood >= 180:
                lc2_rebuilt = True
                sim.bank = sim.bank - ResourceBundle(wood=100)
                sim.lc_completed_s = t + 35
                sim.lc_count = 2
                for v in sim.vils:
                    if v["role"] == "straggler" and int(v["busy_until"]) <= t:
                        v["role"] = "wood"
                milestones["lc2_rebuilt_str"] = sim.fmt_time(t)
            if lc2_rebuilt and not barracks_started and sim.bank.wood >= 200:
                barracks_started = True
                sim.bank = sim.bank - ResourceBundle(wood=175)
                barracks_ready_t = t + 60
                for v in sim.vils:
                    if v["role"] in ("wood", "straggler") and int(v["busy_until"]) <= t:
                        v["busy_until"] = t + 60
                        break
            if barracks_ready_t is not None and t >= barracks_ready_t and not stable_started and sim.bank.wood >= 175:
                stable_started = True
                sim.bank = sim.bank - ResourceBundle(wood=175)
                stable_ready_t = t + 50
                milestones["stable_ready_str"] = sim.fmt_time(t + 50)
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

        if sim.age >= 3 and not bow_saw_started and sim.bank.food >= 200 and sim.bank.wood >= 100:
            bow_saw_started = True
            sim.bank = sim.bank - ResourceBundle(food=150, wood=100)
            sim.upgrades.add("bow saw")

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
            if not def_castle_started and sim.bank.stone >= 650:
                def_castle_started = True
                sim.bank = sim.bank - ResourceBundle(stone=650)
                def_castle_ready_t = t + 85
                milestones["def_castle_started_str"] = sim.fmt_time(t)
                milestones["castle_wait_s"] = t - (castle_reached_t or t)
                c_builders = 0
                for pref_role in ("straggler", "berries", "farm", "gold"):
                    for v in sim.vils:
                        if v["role"] == pref_role and int(v["busy_until"]) <= t and c_builders < 6:
                            v["busy_until"] = t + 85
                            c_builders += 1
            if sim.age == 3 and not imp_clicked:
                max_castle_float["food"] = max(max_castle_float["food"], sim.bank.food)
                max_castle_float["wood"] = max(max_castle_float["wood"], sim.bank.wood)
                max_castle_float["gold"] = max(max_castle_float["gold"], sim.bank.gold)

            # Activate TC #2, TC #3, TC #4 on completion
            if tc2_ready_t is not None and t == tc2_ready_t:
                sim.tc_count = 2
                sim.tc_busy_until.append(t)
                sim.tc_action.append("idle")
                milestones["tc2_ready_str"] = sim.fmt_time(t)
            if tc3_ready_t is not None and t == tc3_ready_t:
                sim.tc_count = 3
                sim.tc_busy_until.append(t)
                sim.tc_action.append("idle")
                milestones["tc3_ready_str"] = sim.fmt_time(t)
            if tc4_ready_t is not None and t == tc4_ready_t:
                sim.tc_count = 4
                sim.tc_busy_until.append(t)
                sim.tc_action.append("idle")
                milestones["tc4_ready_str"] = sim.fmt_time(t)

            # Activate Castles on completion
            if def_castle_ready_t is not None and t == def_castle_ready_t:
                castle_count = 1
                milestones["def_castle_ready_str"] = sim.fmt_time(t)
                if is_1tc and not stone_adjusted_early:
                    stone_adjusted_early = True
                    moved_s = 0
                    for v in sim.vils:
                        if v["role"] == "stone" and int(v["busy_until"]) <= t and moved_s < 2:
                            v["role"] = "wood"
                            v["busy_until"] = t + 15
                            moved_s += 1
            if fwd_castle2_ready_t is not None and t == fwd_castle2_ready_t:
                castle_count = 2
                milestones["fwd_castle2_ready_str"] = sim.fmt_time(t)
            if fwd_castle3_ready_t is not None and t == fwd_castle3_ready_t:
                castle_count = 3
                milestones["fwd_castle3_ready_str"] = sim.fmt_time(t)

            # Ballistics Priority Rule (rules.md 1.5):
            # At 20+ ranged units (Genoese), prioritize University + Ballistics ahead of extra
            # production buildings, late TCs, or secondary upgrades (unless 3-TC drop or Imp click active).
            ballistics_prio = (
                sim.age >= 3
                and sim.military_units["genoese"] >= 20
                and not ballistics_started
                and not imp_prep_started
                and (is_1tc or boom3tc_ready_logged)
            )
            saving_for_imp = imp_prep_started and not imp_clicked

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

                # Forward Siege Workshop + Rams once 30+ army is reached
                if not army30_reached and army_combat_count() >= 30:
                    army30_reached = True
                    milestones["army30_str"] = sim.fmt_time(t)
                    milestones["army30_comp"] = dict(sim.military_units)
                if army30_reached and not fwd_sw_dispatched and "loom" in sim.upgrades:
                    fwd_sw_dispatched = True
                    fwd_sw_arrive_t = t + 75
                    for v in sim.vils:
                        if v["role"] in ("wood", "farm") and int(v["busy_until"]) <= t:
                            v["busy_until"] = t + 75
                            break
                if fwd_sw_arrive_t is not None and t >= fwd_sw_arrive_t and not fwd_sw1_started and not (ballistics_prio and not univ_started) and sim.bank.wood >= 200:
                    fwd_sw1_started = True
                    sim.bank = sim.bank - ResourceBundle(wood=200)
                    fwd_sw1_ready_t = t + 40
                    milestones["fwd_sw_ready_str"] = sim.fmt_time(t + 40)
                    if not castle_loop2_logged:
                        castle_loop2_logged = True
                        add_row(
                            f"{len(sim.vils)} ({total_pop()})",
                            f"{milestones.get('ballistics_str', sim.fmt_time())} – {sim.fmt_time()}",
                            "Castle Age",
                            "Macro Loop 2 — 30+ Army Forward Siege Push: Send Loom-protected vil forward -> Forward Siege Workshop (-200W) + 3–4 Battering Rams (-160W, -75G each), add Stable #2 (-175W) & Heavy Plow, stick strictly to 1 TC until Imperial click.",
                            f"Push force scaling past 30+ army ({format_army_counts(sim.military_units).replace('Army: ', '')}).",
                        )
                if (
                    fwd_sw1_ready_t is not None
                    and t >= fwd_sw1_ready_t
                    and rams_trained < 4
                    and t >= sw_busy_until[0]
                    and not ballistics_prio
                    and sim.bank.wood >= 160
                    and sim.bank.gold >= 75
                ):
                    rams_trained += 1
                    sim.bank = sim.bank - ResourceBundle(wood=160, gold=75)
                    sw_busy_until[0] = t + 36
                    sim.military_units["battering_ram"] += 1
                    if rams_trained == 1:
                        milestones["ram1_str"] = sim.fmt_time(t)

                # Shift priority to Imperial Age once Ballistics & 3+ Rams are online
                if (
                    sim.age == 3
                    and not imp_prep_started
                    and ballistics_started
                    and rams_trained >= 3
                ):
                    imp_prep_started = True
                    imp_prep_t = t
                    milestones["imp_prep_str"] = sim.fmt_time(t)

                # Occasional Market usage in Strategy 1 (rules.md 1.4)
                if (
                    sim.age == 3
                    and not imp_clicked
                    and (t - last_market_trade_t) >= 60
                    and market_trades_castle < 4
                ):
                    if sim.bank.wood >= 450 and sim.bank.gold < 200 and (t - (castle_reached_t or t)) < 480:
                        last_market_trade_t = t
                        market_trades_castle += 1
                        sim.sell_at_market("wood", 100, castle_reached_t)
                    elif imp_prep_started and sim.bank.food >= 850 and 550 <= sim.bank.gold < 680 and sim.bank.wood >= 350:
                        last_market_trade_t = t
                        market_trades_castle += 1
                        sim.sell_at_market("wood", 100, castle_reached_t)
                    elif imp_prep_started and sim.bank.food >= 1050 and 550 <= sim.bank.gold < 680:
                        last_market_trade_t = t
                        market_trades_castle += 1
                        sim.sell_at_market("food", 100, castle_reached_t)

                # Stick strictly to 1 TC until clicking Imp -> Add TC #2 and TC #3 AFTER clicking Imp
                if imp_clicked and not tc2_started and sim.bank.wood >= 275 and sim.bank.stone >= 100:
                    tc2_started = True
                    sim.bank = sim.bank - ResourceBundle(wood=275, stone=100)
                    tc2_ready_t = t + 145
                    milestones["tc2_started_str"] = sim.fmt_time(t)
                if imp_clicked and tc2_started and not tc3_started and sim.bank.wood >= 275 and sim.bank.stone >= 100:
                    tc3_started = True
                    sim.bank = sim.bank - ResourceBundle(wood=275, stone=100)
                    tc3_ready_t = t + 145
                    milestones["tc3_started_str"] = sim.fmt_time(t)

            # =========================================================
            # STRATEGY 2: BALANCED 3 TC BOOM SPECIFIC LOGIC
            # =========================================================
            else:
                if (
                    not army20_reached
                    and sim.military_units["genoese"] >= 13
                    and sim.military_units["light_cav"] >= 7
                ):
                    army20_reached = True
                    army20_t = t
                    milestones["army20_reached_str"] = sim.fmt_time(t)
                    milestones["army20_comp"] = dict(sim.military_units)
                    add_row(
                        f"{len(sim.vils)} ({total_pop()})",
                        f"{sim.fmt_time(castle_reached_t or t)} – {sim.fmt_time()}",
                        "Castle Age",
                        f"Macro Loop 1 — ~20 Army Defense Setup: Build {sim.military_units['genoese']} Genoese + {sim.military_units['light_cav']} Light Cav with Padded Archer, Scale Barding, Bloodlines & Bodkin; scale Farms (~14), Wood (14), Gold (6–7).",
                        "~20 army complete -> pause military production & drop TC #2 & TC #3 immediately!",
                    )

                if army20_reached and not tc2_started and sim.bank.wood >= 275 and sim.bank.stone >= 100:
                    tc2_started = True
                    sim.bank = sim.bank - ResourceBundle(wood=275, stone=100)
                    tc2_ready_t = t + 145
                    milestones["tc2_started_str"] = sim.fmt_time(t)
                if tc2_started and not tc3_started and sim.bank.wood >= 275 and sim.bank.stone >= 100:
                    tc3_started = True
                    sim.bank = sim.bank - ResourceBundle(wood=275, stone=100)
                    tc3_ready_t = t + 145
                    milestones["tc3_started_str"] = sim.fmt_time(t)

                f_cnt_s2 = sim.count_role("farm")
                boom3tc_ready = (
                    tc3_ready_t is not None
                    and t >= tc3_ready_t
                    and f_cnt_s2 >= 22
                    and wheelbarrow_started
                )
                if boom3tc_ready and not boom3tc_ready_logged:
                    boom3tc_ready_logged = True
                    boom3tc_setup_t = t
                    milestones["boom3tc_setup_str"] = sim.fmt_time(t)
                    add_row(
                        f"{len(sim.vils)} ({total_pop()})",
                        f"{sim.fmt_time(army20_t or t)} – {sim.fmt_time()}",
                        "Castle Age",
                        f"Macro Loop 2 — 3-TC Expansion & Boom Setup: Pause military -> drop TC #2 & TC #3 (-275W, -100S each), prioritize 3-TC continuous Villagers, Farms (to {f_cnt_s2}+) & Wheelbarrow (-175F, -50W).",
                        "3-TC continuous villager production established -> resume & maximize army with full upgrades!",
                    )

                # Forward Expedition (8 vils, 90s walk) once 3-TC boom is established, Ballistics started, & Stone >= 700
                if (
                    boom3tc_ready
                    and ballistics_started
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
                if fwd_vils_arrive_t is not None and t >= fwd_vils_arrive_t and not fwd_castle2_started and sim.bank.stone >= 650:
                    fwd_castle2_started = True
                    sim.bank = sim.bank - ResourceBundle(stone=650)
                    fwd_castle2_ready_t = t + 60
                if fwd_castle2_started and not tc4_started and sim.bank.wood >= 275 and sim.bank.stone >= 100:
                    tc4_started = True
                    sim.bank = sim.bank - ResourceBundle(wood=275, stone=100)
                    tc4_ready_t = t + 75
                    milestones["tc4_ready_str"] = sim.fmt_time(t + 75)
                if fwd_castle2_started and tc4_started and not fwd_sw1_started and sim.bank.wood >= 200:
                    fwd_sw1_started = True
                    sim.bank = sim.bank - ResourceBundle(wood=200)
                    fwd_sw1_ready_t = t + 40
                if sim.age == 4 and fwd_sw1_started and not fwd_sw2_started and sim.bank.wood >= 250:
                    fwd_sw2_started = True
                    sim.bank = sim.bank - ResourceBundle(wood=200)
                    fwd_sw2_ready_t = t + 40
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
                if fwd_castle3_started and sim.bank.stone > 400:
                    for v in sim.vils:
                        if v["role"] == "stone":
                            v["role"] = "gold" if sim.bank.gold < sim.bank.wood else "wood"
                            v["busy_until"] = t + 10

                # Shift priority to Imperial Age once Ballistics, Forward Castle #2 started, & >=85 vils (so Imp arrives ~34:00-36:00 with <1000 float)
                if (
                    sim.age == 3
                    and not imp_prep_started
                    and ballistics_started
                    and fwd_castle2_started
                    and len(sim.vils) >= 85
                ):
                    imp_prep_started = True
                    imp_prep_t = t
                    milestones["imp_prep_str"] = sim.fmt_time(t)
                    if not castle_loop2_logged:
                        castle_loop2_logged = True
                        add_row(
                            f"{len(sim.vils)} ({total_pop()})",
                            f"{sim.fmt_time(boom3tc_setup_t or t)} – {sim.fmt_time()}",
                            "Castle Age",
                            "Macro Loop 3 — Full Flood, Ballistics & Forward Push -> Imp Prep: Maximize Genoese + Light Cav across Castles/Stables; at 20+ Genoese prioritize University + Ballistics; send 8 Loom vils forward for Castle #2/#3, TC #4 & Siege Workshop; shift priority to Imperial Age (850F, 680G).",
                            f"Army at Imp prep: {format_army_counts(sim.military_units).replace('Army: ', '')}.",
                        )

                # Occasional Market usage in Strategy 2 (rules.md 1.4)
                if (
                    sim.age == 3
                    and boom3tc_ready
                    and not imp_clicked
                    and (t - last_market_trade_t) >= 60
                    and market_trades_castle < 4
                ):
                    if imp_prep_started and sim.bank.food >= 850 and 550 <= sim.bank.gold < 680 and sim.bank.wood >= 350:
                        last_market_trade_t = t
                        market_trades_castle += 1
                        sim.sell_at_market("wood", 100, castle_reached_t)
                    elif imp_prep_started and sim.bank.food >= 1050 and 550 <= sim.bank.gold < 680:
                        last_market_trade_t = t
                        market_trades_castle += 1
                        sim.sell_at_market("food", 100, castle_reached_t)

            # =========================================================
            # ANTI-FLOAT REBALANCER (keep float < ~500-1,000, rules.md 1.5)
            # =========================================================
            if t % 15 == 0 and t >= (castle_reached_t or 0) + 120:
                g_cnt_r = sim.count_role("gold")
                w_cnt_r = sim.count_role("wood", "straggler")
                f_cnt_r = sim.count_role("farm")
                imp_f_cap = 38 if is_1tc else 46
                # Shift excess Food -> Wood if Food > 1050 and Wood < 450 (only if not saving for Imp)
                if not saving_for_imp and sim.bank.food > 1050 and sim.bank.wood < 450 and f_cnt_r > 20:
                    moved = 0
                    for v in sim.vils:
                        if v["role"] == "farm" and int(v["busy_until"]) <= t and moved < 3:
                            v["role"] = "wood"
                            v["busy_until"] = t + 15
                            moved += 1
                # Shift excess Gold -> Wood if Gold > 750 (before Imp) or > 950 (in Imp) and Wood < 450
                elif not saving_for_imp and sim.bank.gold > (750 if not imp_clicked else 950) and sim.bank.wood < 450 and g_cnt_r > 6:
                    moved = 0
                    for v in sim.vils:
                        if v["role"] == "gold" and int(v["busy_until"]) <= t and moved < 2:
                            v["role"] = "wood"
                            v["busy_until"] = t + 15
                            moved += 1
                # Shift Wood/Food -> Gold if Gold < 550 (or < 750 saving for Imp) and Wood/Food floating
                elif sim.bank.gold < (750 if saving_for_imp else (450 if sim.age < 4 else 750)) and (sim.bank.wood > 550 or sim.bank.food > 950) and g_cnt_r < 32:
                    src_role = "farm" if (sim.bank.food > 1050 and f_cnt_r > 24) else ("wood" if w_cnt_r > 16 else None)
                    if src_role:
                        moved = 0
                        for v in sim.vils:
                            if v["role"] == src_role and int(v["busy_until"]) <= t and moved < 3:
                                v["role"] = "gold"
                                v["busy_until"] = t + 15
                                moved += 1
                # Convert excess Woodcutters into Farms when Wood > 550 & Food < 950
                elif not ballistics_prio and sim.bank.wood > 550 and sim.bank.food < 950 and w_cnt_r > 16 and f_cnt_r < imp_f_cap and (not is_1tc or tc3_started or not imp_prep_started):
                    moved = 0
                    for v in sim.vils:
                        if v["role"] == "wood" and int(v["busy_until"]) <= t and moved < 3:
                            sim.bank = sim.bank - ResourceBundle(wood=60)
                            v["role"] = "farm"
                            v["busy_until"] = t + 20
                            farms_seeded += 1
                            sim.register_new_farm()
                            moved += 1
                            if moved >= 3 or sim.bank.wood < 450:
                                break
                # Cap Stone miners once Stone target is banked
                if is_1tc and tc3_started and sim.bank.stone >= 200 and sim.count_role("stone") > 0:
                    for v in sim.vils:
                        if v["role"] == "stone" and int(v["busy_until"]) <= t:
                            v["role"] = "wood" if sim.bank.wood < sim.bank.gold else "gold"
                            v["busy_until"] = t + 15
                if not is_1tc and (fwd_castle3_started or sim.bank.stone >= 800) and sim.count_role("stone") > 1:
                    for v in sim.vils:
                        if v["role"] == "stone" and int(v["busy_until"]) <= t:
                            v["role"] = "wood" if sim.bank.wood < sim.bank.gold else "gold"
                            v["busy_until"] = t + 15
                            if sim.count_role("stone") <= 1:
                                break

            # =========================================================
            # SHARED TC QUEUE MANAGEMENT
            # =========================================================
            for tc_idx in range(sim.tc_count):
                if sim.tc_action[tc_idx] == "idle":
                    f_cnt_now = sim.count_role("farm")
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
                            and imp_prep_started
                            and sim.bank.food >= 850
                            and sim.bank.gold >= 680
                        )
                    )
                    if tc_idx == 0 and not imp_clicked and can_click_imp:
                        imp_clicked = True
                        imp_click_t = t
                        milestones["imp_click_s"] = t
                        milestones["imp_click_str"] = sim.fmt_time(t)
                        milestones["imp_click_vils"] = len(sim.vils)
                        milestones["imp_click_alloc"] = sim.current_macro_alloc()
                        milestones["imp_click_army"] = dict(sim.military_units)
                        sim.bank = sim.bank - ResourceBundle(food=850, gold=680)
                        sim.tc_busy_until[0] = t + 190
                        sim.tc_action[0] = "imperial"
                        add_row(
                            f"{len(sim.vils)} ({total_pop()})",
                            sim.fmt_time(),
                            "Castle Age",
                            f"CLICK IMPERIAL AGE (-850F, -680G Italians -15%, 190s)! Army: {format_army_counts(sim.military_units).replace('Army: ', '')}.",
                            "Add TC #2 & TC #3 during Imperial Transition!" if is_1tc else "4 TCs continue booming during Imperial Transition.",
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
                    elif (
                        tc_idx == 0
                        and wheelbarrow_started
                        and "wheelbarrow" in sim.upgrades
                        and not hand_cart_started
                        and not saving_for_imp
                        and f_cnt_now >= 22
                        and sim.tc_count >= 3
                        and sim.bank.food >= 320
                        and sim.bank.wood >= 200
                    ):
                        hand_cart_started = True
                        sim.bank = sim.bank - ResourceBundle(food=300, wood=200)
                        sim.tc_busy_until[0] = t + 55
                        sim.tc_action[0] = "hand_cart"
                    else:
                        max_vils_cap = 98 if is_1tc else 112
                        in_flight_vils = sum(1 for a in sim.tc_action if a.startswith("vil_"))
                        hold_for_imp = (
                            tc_idx == 0
                            and not imp_clicked
                            and imp_prep_started
                            and sim.bank.gold >= 675
                            and sim.bank.food >= 840
                        )
                        if not hold_for_imp and (len(sim.vils) + in_flight_vils) < max_vils_cap and sim.bank.food >= 50:
                            sim.bank = sim.bank - ResourceBundle(food=50)
                            sim.tc_busy_until[tc_idx] = t + 25
                            sim.tc_action[tc_idx] = f"vil_{len(sim.vils) + in_flight_vils + 1}"

            # =========================================================
            # RESERVATIONS + MILITARY PRODUCTION + UPGRADES
            # =========================================================
            f_cnt_cur = sim.count_role("farm")

            tc_food_reserve = 0
            for tc_idx in range(sim.tc_count):
                if sim.tc_action[tc_idx] == "idle" or (sim.tc_busy_until[tc_idx] - t) <= 10:
                    tc_food_reserve += 50

            univ_trigger = (
                (is_1tc and sim.military_units["genoese"] >= 20)
                or (not is_1tc and boom3tc_ready_logged and sim.military_units["genoese"] >= 20)
            )
            tc_w_res = (
                (275 if (not is_1tc and army20_reached and not tc2_started) else 0)
                + (275 if (not is_1tc and tc2_started and not tc3_started) else 0)
                + (275 if (is_1tc and imp_clicked and not tc2_started) else 0)
                + (275 if (is_1tc and imp_clicked and tc2_started and not tc3_started) else 0)
                + (275 if (not is_1tc and fwd_castle2_started and not tc4_started) else 0)
            )
            univ_w_res = 200 if (univ_trigger and not univ_started) else (201 if (univ_started and not ballistics_started) else 0)
            univ_g_res = 117 if (univ_trigger and not ballistics_started) else 0
            sw_w_res = (
                (200 if (is_1tc and army30_reached and not fwd_sw1_started) else 0)
                + (200 if (not is_1tc and tc4_started and not fwd_sw1_started) else 0)
                + (200 if (not is_1tc and sim.age == 4 and fwd_sw1_started and not fwd_sw2_started) else 0)
            )
            ram_w_res = 160 if (is_1tc and fwd_sw1_ready_t is not None and t >= fwd_sw1_ready_t and rams_trained < 4 and t >= sw_busy_until[0] - 8) else 0
            ram_g_res = 75 if ram_w_res > 0 else 0
            bbc_w_res = 180 if (sim.age == 4 and chemistry_ready_t is not None and t >= chemistry_ready_t and bbc_count_trained < 4 and fwd_sw1_ready_t is not None and t >= fwd_sw1_ready_t) else 0
            wb_w_res = 50 if (f_cnt_cur >= 15 and not wheelbarrow_started) else 0
            monk_g_res = 100 if (is_1tc and monastery_ready_t is not None and t >= monastery_ready_t and monks_trained < 2 and t >= monastery_busy_until - 8) else 0

            total_w_res = tc_w_res + univ_w_res + sw_w_res + ram_w_res + bbc_w_res + wb_w_res
            total_g_res = monk_g_res + ram_g_res + univ_g_res

            # Pause/throttle military when saving for Imperial Click or Ballistics priority
            if is_1tc:
                genoese_allowed = not (saving_for_imp and sim.bank.gold < 680) and not (ballistics_prio and sim.bank.gold < 157)
                lcav_allowed = (imp_clicked or sim.military_units["light_cav"] < 20) and not (saving_for_imp and sim.bank.food < 850)
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
                    and not (saving_for_imp and sim.bank.gold < 680)
                    and not (ballistics_prio and sim.bank.gold < 157)
                )
                lcav_allowed = (
                    (want_lcav_phase1 or boom3tc_ready_now)
                    and not (army20_reached and not boom3tc_ready_now)
                    and not (saving_for_imp and sim.bank.food < 850)
                )

            genoese_train_s = 11 if "conscription" in sim.upgrades else 14
            hold_genoese_for_elite = (sim.age == 4 and sim.military_units["genoese"] >= 45 and not elite_genoese_started)
            genoese_pop_cap = 70 if is_1tc else 48
            army_pop_limit = 194 if ((imp_clicked or sim.age == 4) and bbc_count_trained < 3) else 200
            for c_idx in range(castle_count):
                if t >= castle_busy_until[c_idx] and genoese_allowed and not hold_genoese_for_elite and total_pop() < army_pop_limit:
                    if sim.bank.wood >= (45 + total_w_res) and sim.bank.gold >= (40 + total_g_res):
                        sim.bank = sim.bank - ResourceBundle(wood=45, gold=40)
                        castle_busy_until[c_idx] = t + genoese_train_s
                        if sim.military_units["genoese"] >= genoese_pop_cap or total_pop() >= army_pop_limit - 1:
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

                # Scale Stables dynamically (never starve Ballistics, TC #2/#3, or Siege Workshop!)
                if is_1tc:
                    if stable_count == 1 and not ballistics_prio and ballistics_started and f_cnt_cur >= 16 and sim.bank.wood >= (175 + total_w_res + 80):
                        stable_count = 2
                        sim.bank = sim.bank - ResourceBundle(wood=175)
                        stable_busy_until[1] = t + 50
                    if stable_count == 2 and sim.age == 4 and tc3_started and len(sim.vils) >= 70 and sim.bank.wood >= (350 + total_w_res):
                        stable_count = 4
                        sim.bank = sim.bank - ResourceBundle(wood=350)
                        stable_busy_until[2] = t + 50
                        stable_busy_until[3] = t + 50
                    if stable_count == 4 and sim.age == 4 and sim.bank.wood >= (450 + total_w_res):
                        stable_count = 6
                        sim.bank = sim.bank - ResourceBundle(wood=350)
                        stable_busy_until[4] = t + 35
                        stable_busy_until[5] = t + 35
                    if sim.age == 4 and fwd_sw1_started and not fwd_sw2_started and sim.bank.wood >= (450 + total_w_res):
                        fwd_sw2_started = True
                        sim.bank = sim.bank - ResourceBundle(wood=200)
                        fwd_sw2_ready_t = t + 40
                else:
                    if stable_count == 1 and boom3tc_ready_logged and not ballistics_prio and f_cnt_cur >= 24 and sim.bank.wood >= (175 + total_w_res + 80):
                        stable_count = 2
                        sim.bank = sim.bank - ResourceBundle(wood=175)
                        stable_busy_until[1] = t + 50
                    if stable_count == 2 and not ballistics_prio and fwd_castle2_started and tc4_started and fwd_sw1_started and sim.bank.wood >= (175 + total_w_res):
                        stable_count = 3
                        sim.bank = sim.bank - ResourceBundle(wood=175)
                        stable_busy_until[2] = t + 35
                    if stable_count == 3 and (imp_clicked or sim.age == 4) and f_cnt_cur >= 32 and sim.bank.wood >= (175 + total_w_res):
                        stable_count = 4
                        sim.bank = sim.bank - ResourceBundle(wood=175)
                        stable_busy_until[3] = t + 35
                    if stable_count == 4 and sim.age == 4 and len(sim.vils) >= 105 and sim.bank.wood >= (350 + total_w_res):
                        stable_count = 6
                        sim.bank = sim.bank - ResourceBundle(wood=350)
                        stable_busy_until[4] = t + 35
                        stable_busy_until[5] = t + 35

                lcav_train_s = 23 if "conscription" in sim.upgrades else 30
                wb_food_res = (175 if (f_cnt_cur >= 15 and not wheelbarrow_started and (is_1tc or army20_reached)) else 0) + (150 if not bow_saw_started else 0)
                hold_lcav_for_upg = (sim.age == 4 and sim.military_units["light_cav"] >= 25 and not (hussar_started and elite_genoese_started))
                lcav_pop_cap = 35 if is_1tc else 34
                for s_idx in range(stable_count):
                    if (
                        lcav_upg_started
                        and t >= stable_busy_until[s_idx]
                        and lcav_allowed
                        and not hold_lcav_for_upg
                        and total_pop() < army_pop_limit
                        and sim.bank.food >= (80 + tc_food_reserve + wb_food_res)
                    ):
                        sim.bank = sim.bank - ResourceBundle(food=80)
                        stable_busy_until[s_idx] = t + lcav_train_s
                        if total_pop() >= army_pop_limit - 1 or sim.military_units["light_cav"] >= lcav_pop_cap:
                            sim.casualties["light_cav"] += 1
                        else:
                            sim.military_units["light_cav"] += 1

            # =========================================================
            # UNIVERSITY & BALLISTICS (PRIORITY AT 20+ GENOESE)
            # =========================================================
            if univ_trigger and not univ_started and sim.bank.wood >= (200 + tc_w_res):
                univ_started = True
                sim.bank = sim.bank - ResourceBundle(wood=200)
                univ_ready_t = t + 70
            if univ_ready_t is not None and t >= univ_ready_t and not ballistics_started:
                bal_cost, bal_time = sim.db.get_upgrade_spec("ballistics", "Italians")
                if sim.bank.wood >= (bal_cost.wood + tc_w_res) and sim.bank.gold >= bal_cost.gold:
                    ballistics_started = True
                    sim.bank = sim.bank - bal_cost
                    ballistics_ready_t = t + int(bal_time)
                    sim.upgrades.add("ballistics")
                    milestones["ballistics_str"] = sim.fmt_time(t + int(bal_time))
                    milestones["ballistics_vils"] = len(sim.vils)
                    milestones["ballistics_alloc"] = sim.current_macro_alloc()
                    if is_1tc and not castle_loop1_logged:
                        castle_loop1_logged = True
                        add_row(
                            f"{len(sim.vils)} ({total_pop()})",
                            f"{sim.fmt_time(castle_reached_t or t)} – {sim.fmt_time()}",
                            "Castle Age",
                            f"Macro Loop 1 — Genoese + Light Cav + Monastery -> Ballistics: Build Monastery (-175W) + 2 Monks (1 Relic = +30G/min); mass Genoese & Light Cav with Padded Archer, Scale Barding, Bloodlines, Forging & Bodkin; at 20+ Genoese prioritize University (-200W) -> Ballistics (-{bal_cost.wood:.0f}W, -{bal_cost.gold:.0f}G Italians -33%).",
                            "Ballistics prioritized ahead of extra Stables/SW per 20+ ranged rule.",
                        )

            # =========================================================
            # ARCHER, CAVALRY & ECO UPGRADES
            # =========================================================
            if not saving_for_imp:
                if not fletching_started and (sim.age == 2 or bow_saw_started) and sim.bank.food >= (100 + tc_food_reserve) and sim.bank.gold >= 50:
                    fletching_started = True
                    sim.bank = sim.bank - ResourceBundle(food=100, gold=50)
                    sim.upgrades.add("fletching")
                if not padded_archer_started and fletching_started and lcav_upg_started and sim.bank.food >= (100 + tc_food_reserve):
                    padded_archer_started = True
                    sim.bank = sim.bank - ResourceBundle(food=100)
                    sim.upgrades.add("padded archer armor")
                if not scale_barding_started and lcav_upg_started and sim.bank.food >= (150 + tc_food_reserve):
                    scale_barding_started = True
                    sim.bank = sim.bank - ResourceBundle(food=150)
                    sim.upgrades.add("scale barding armor")
                if (
                    fletching_started
                    and not bodkin_started
                    and (not is_1tc or monks_trained >= 2)
                    and sim.bank.food >= (200 + tc_food_reserve)
                    and sim.bank.gold >= (100 + univ_g_res)
                ):
                    bodkin_started = True
                    sim.bank = sim.bank - ResourceBundle(food=200, gold=100)
                    sim.upgrades.add("bodkin arrow")
                if (
                    not bloodlines_started
                    and lcav_upg_started
                    and scale_barding_started
                    and (is_1tc or boom3tc_ready_logged or sim.military_units["light_cav"] >= 5)
                    and sim.bank.food >= (150 + tc_food_reserve)
                    and sim.bank.gold >= (100 + univ_g_res)
                ):
                    bloodlines_started = True
                    sim.bank = sim.bank - ResourceBundle(food=150, gold=100)
                    sim.upgrades.add("bloodlines")
                if not forging_started and scale_barding_started and (is_1tc or boom3tc_ready_logged) and sim.bank.food >= (150 + tc_food_reserve):
                    forging_started = True
                    sim.bank = sim.bank - ResourceBundle(food=150)
                    sim.upgrades.add("forging")
                if not husbandry_started and bloodlines_started and (is_1tc or boom3tc_ready_logged) and sim.bank.food >= (150 + tc_food_reserve):
                    husbandry_started = True
                    sim.bank = sim.bank - ResourceBundle(food=150)
                    sim.upgrades.add("husbandry")
                if not leather_archer_started and bodkin_started and not ballistics_prio and (is_1tc or boom3tc_ready_logged) and sim.bank.food >= (150 + tc_food_reserve) and sim.bank.gold >= (150 + univ_g_res):
                    leather_archer_started = True
                    sim.bank = sim.bank - ResourceBundle(food=150, gold=150)
                    sim.upgrades.add("leather archer armor")
                if not chain_barding_started and forging_started and not ballistics_prio and (is_1tc or boom3tc_ready_logged) and sim.bank.food >= (250 + tc_food_reserve) and sim.bank.gold >= (150 + univ_g_res):
                    chain_barding_started = True
                    sim.bank = sim.bank - ResourceBundle(food=250, gold=150)
                    sim.upgrades.add("chain barding armor")
                if not iron_casting_started and chain_barding_started and not ballistics_prio and (is_1tc or boom3tc_ready_logged) and sim.bank.food >= (220 + tc_food_reserve) and sim.bank.gold >= (120 + univ_g_res):
                    iron_casting_started = True
                    sim.bank = sim.bank - ResourceBundle(food=220, gold=120)
                    sim.upgrades.add("iron casting")

            # Eco upgrades in Castle Age
            if ballistics_started and not heavy_plow_started and not saving_for_imp and sim.bank.food >= (125 + tc_food_reserve) and sim.bank.wood >= (125 + total_w_res):
                heavy_plow_started = True
                sim.bank = sim.bank - ResourceBundle(food=125, wood=125)
                sim.upgrades.add("heavy plow")
            if not is_1tc and tc3_started and not stone_mining_started and sim.bank.food >= (100 + tc_food_reserve) and sim.bank.wood >= (75 + tc_w_res):
                stone_mining_started = True
                sim.bank = sim.bank - ResourceBundle(food=100, wood=75)
                sim.upgrades.add("stone mining")
            if not is_1tc and heavy_plow_started and not stone_shaft_started and not saving_for_imp and len(sim.vils) >= 54 and sim.bank.food >= (175 + tc_food_reserve) and sim.bank.wood >= (75 + tc_w_res):
                stone_shaft_started = True
                sim.bank = sim.bank - ResourceBundle(food=175, wood=75)
                sim.upgrades.add("stone shaft mining")
            if heavy_plow_started and not gold_shaft_started and not saving_for_imp and len(sim.vils) >= 48 and sim.bank.food >= (175 + tc_food_reserve) and sim.bank.wood >= (75 + total_w_res):
                gold_shaft_started = True
                sim.bank = sim.bank - ResourceBundle(food=175, wood=75)
                sim.upgrades.add("gold shaft mining")

            # Pavise & Masonry (wait for post-Imp TCs to be placed first in 1TC)
            if ballistics_started and not pavise_started and (not is_1tc or tc3_started) and (imp_clicked or sim.age == 4) and sim.bank.wood >= (200 + total_w_res) and sim.bank.gold >= 160:
                pavise_started = True
                sim.bank = sim.bank - ResourceBundle(wood=200, gold=150)
                sim.upgrades.add("pavise")
            if imp_clicked and not masonry_started and (not is_1tc or tc3_started) and sim.bank.food >= 180 and sim.bank.wood >= (117 + total_w_res):
                masonry_started = True
                sim.bank = sim.bank - ResourceBundle(food=100, wood=117)
                sim.upgrades.add("masonry")

            # Lumber Camp refreshes at <=65% wood efficiency (subject to Wood Priority Rule)
            if not lc3_rebuilt and sim.wood_efficiency() <= 0.65 and sim.bank.wood >= (150 + tc_w_res + univ_w_res + sw_w_res):
                lc3_rebuilt = True
                sim.bank = sim.bank - ResourceBundle(wood=100)
                sim.lc_completed_s = t + 35
                sim.lc_count = 3
                milestones["lc3_rebuilt_str"] = sim.fmt_time(t)
            if lc3_rebuilt and not lc4_rebuilt and sim.count_role("wood") >= 22 and sim.bank.wood >= (100 + total_w_res):
                lc4_rebuilt = True
                sim.bank = sim.bank - ResourceBundle(wood=100)
                sim.lc_completed_s = t + 35
                sim.lc_count = 4
            if lc4_rebuilt and not lc5_rebuilt and sim.count_role("wood") >= 30 and sim.bank.wood >= (100 + total_w_res):
                lc5_rebuilt = True
                sim.bank = sim.bank - ResourceBundle(wood=100)
                sim.lc_completed_s = t + 35
                sim.lc_count = 5

            # Farm conversion from excess Wood
            reserve_w = total_w_res + (175 if (is_1tc and not monastery_started) else 0)
            min_wood_keep = 12 if f_cnt_cur < 15 else (14 if f_cnt_cur < 26 else (18 if f_cnt_cur < 38 else 22))
            max_f_cap = 22 if (is_1tc and not imp_clicked) else (38 if is_1tc else 48)
            if f_cnt_cur < max_f_cap and sim.bank.wood >= (60 + reserve_w) and sim.bank.food < 950:
                w_cnt_cur = sim.count_role("wood", "straggler")
                for v in sim.vils:
                    if (v["role"] == "straggler" or (v["role"] == "wood" and w_cnt_cur > min_wood_keep)) and int(v["busy_until"]) <= t:
                        sim.bank = sim.bank - ResourceBundle(wood=60)
                        v["role"] = "farm"
                        v["busy_until"] = t + 20
                        farms_seeded += 1
                        sim.register_new_farm()
                        break

        # === IMPERIAL AGE FULL UPGRADES & SIEGE ===
        if sim.age == 4:
            if not conscription_started and sim.bank.food >= 150 and sim.bank.gold >= 150:
                conscription_started = True
                sim.bank = sim.bank - ResourceBundle(food=150, gold=150)
                sim.upgrades.add("conscription")
            if not chemistry_started and sim.bank.food >= 201 and sim.bank.gold >= 134:
                chemistry_started = True
                chem_cost, chem_time = sim.db.get_upgrade_spec("chemistry", "Italians")
                sim.bank = sim.bank - chem_cost
                chemistry_ready_t = t + int(chem_time)
            if not bracer_started and sim.bank.food >= 300 and sim.bank.gold >= 200:
                bracer_started = True
                sim.bank = sim.bank - ResourceBundle(food=300, gold=200)
                sim.upgrades.add("bracer")
            if not two_man_saw_started and (not is_1tc or tc3_started) and sim.bank.food >= 300 and sim.bank.wood >= (200 + total_w_res):
                two_man_saw_started = True
                sim.bank = sim.bank - ResourceBundle(food=300, wood=200)
                sim.upgrades.add("two-man saw")
            if is_1tc and not capped_ram_started and sim.bank.food >= 300:
                capped_ram_started = True
                sim.bank = sim.bank - ResourceBundle(food=300)
                sim.upgrades.add("capped ram")
            if bracer_started and not ring_archer_started and sim.bank.food >= 250 and sim.bank.gold >= 250:
                ring_archer_started = True
                sim.bank = sim.bank - ResourceBundle(food=250, gold=250)
                sim.upgrades.add("ring archer armor")
            if chain_barding_started and not plate_barding_started and sim.bank.food >= 350 and sim.bank.gold >= 200:
                plate_barding_started = True
                sim.bank = sim.bank - ResourceBundle(food=350, gold=200)
                sim.upgrades.add("plate barding armor")
            if iron_casting_started and not blast_furnace_started and sim.bank.food >= 275 and sim.bank.gold >= 225:
                blast_furnace_started = True
                sim.bank = sim.bank - ResourceBundle(food=275, gold=225)
                sim.upgrades.add("blast furnace")
            if pavise_started and not silk_armor_started and sim.bank.wood >= (400 + total_w_res) and sim.bank.gold >= 300:
                silk_armor_started = True
                sim.bank = sim.bank - ResourceBundle(wood=400, gold=300)
                sim.upgrades.add("silk armor")
            if not siege_engineers_started and sim.bank.food >= 335 and sim.bank.wood >= (402 + total_w_res):
                siege_engineers_started = True
                sim.bank = sim.bank - ResourceBundle(food=335, wood=402)
                sim.upgrades.add("siege engineers")
            if blast_furnace_started and not hussar_started and sim.bank.food >= 500 and sim.bank.gold >= 600:
                hussar_started = True
                sim.bank = sim.bank - ResourceBundle(food=500, gold=600)
                sim.upgrades.add("hussar")
            if hussar_started and not elite_genoese_started and sim.bank.food >= 900 and sim.bank.gold >= 750:
                elite_genoese_started = True
                sim.bank = sim.bank - ResourceBundle(food=900, gold=750)
                sim.upgrades.add("elite genoese crossbowman")
                milestones["elite_genoese_str"] = sim.fmt_time(t)
            if siege_engineers_started and not crop_rotation_started and sim.bank.food >= 250 and sim.bank.wood >= (250 + total_w_res):
                crop_rotation_started = True
                sim.bank = sim.bank - ResourceBundle(food=250, wood=250)
                sim.upgrades.add("crop rotation")

            # Bombard Cannons after Chemistry
            if chemistry_ready_t is not None and t >= chemistry_ready_t:
                active_sws = (1 if (fwd_sw1_ready_t and t >= fwd_sw1_ready_t) else 0) + (1 if (fwd_sw2_ready_t and t >= fwd_sw2_ready_t) else 0)
                max_bbc_now = 4 if (hussar_started and elite_genoese_started) else 2
                for sw_idx in range(active_sws):
                    if t >= sw_busy_until[sw_idx] and bbc_count_trained < max_bbc_now and total_pop() < 200 and sim.bank.wood >= 180 and sim.bank.gold >= 180:
                        bbc_count_trained += 1
                        sim.bank = sim.bank - ResourceBundle(wood=180, gold=180)
                        sw_busy_until[sw_idx] = t + 56
                        sim.military_units["bombard_cannon"] += 1
                        if bbc_count_trained == 1:
                            milestones["bbc_queued_str"] = sim.fmt_time(t)

            # Trebuchets from Forward Castles in Strategy 2 (reserve pop for at least 2 BBCs first)
            max_treb_now = 2 if (hussar_started and elite_genoese_started) else 1
            treb_pop_limit = 198 if bbc_count_trained < 2 else 200
            if not is_1tc and castle_count >= 2 and treb_count_trained < max_treb_now and total_pop() < treb_pop_limit and sim.bank.wood >= (200 + sw_w_res) and sim.bank.gold >= 200:
                treb_count_trained += 1
                sim.bank = sim.bank - ResourceBundle(wood=200, gold=200)
                sim.military_units["trebuchet"] += 1

            # Imperial Market trade if heavily skewed (15G per 100 sold per rules.md)
            if (t - last_market_trade_t) >= 90 and not elite_genoese_started and sim.bank.gold < 750:
                if sim.bank.wood >= 850:
                    last_market_trade_t = t
                    sim.sell_at_market("wood", 200, castle_reached_t)
                elif sim.bank.food >= 1200:
                    last_market_trade_t = t
                    sim.sell_at_market("food", 200, castle_reached_t)

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
            and len(sim.vils) >= 112
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
            milestones["max_castle_float"] = {k: round(v, 1) for k, v in max_castle_float.items()}
            milestones["market_trades"] = sim.market_trades
            add_row(
                f"{len(sim.vils)} ({total_pop()})",
                f"{sim.fmt_time(imp_reached_t or t)} – {sim.fmt_time()}",
                "Imperial Age",
                f"Full Imperial Composition Online ({len(sim.vils)} Vils + {sum(sim.military_units.values())} Military = {total_pop()} Pop): {format_army_counts(sim.military_units).replace('Army: ', '')}.",
                f"Full upgrades complete (Elite Genoese, Hussar, Bracer, Ballistics, Chemistry, Pavise, Silk Armor, Siege Engineers). TC #1 unplanned idle before Imp click: {sim.tc1_idle_before_imp_s}s.",
            )
            break

        sim.tick_gather()
        if t % 10 == 0:
            record_timeline_point()

    # Steady-state summary
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
    fin_vils = len(sim.vils)
    end_alloc = sim.current_macro_alloc()
    imp_c_vils = int(milestones.get("imp_click_vils", 62 if is_1tc else 104))
    imp_c_alloc = dict(milestones.get("imp_click_alloc", end_alloc))
    bal_vils = int(milestones.get("ballistics_vils", 44))
    bal_alloc = dict(milestones.get("ballistics_alloc", {"wood": 16, "food": 16, "gold": 10, "stone": 2}))
    imp_c_str = str(milestones.get("imp_click_str", "32:00"))
    imp_r_str = str(milestones.get("imp_reached_str", "35:00"))
    bal_str = str(milestones.get("ballistics_str", "24:00"))

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
                    f"Click {I['castle_age']}: {I['double_bit_axe']} + {I['horse_collar']}, Farms #3-#5, {I['gold_mining']}, {I['lumber_camp']} #2, {I['barracks']} -> {I['stable']} #1 & Fletching.",
                    f"Reach {I['castle_age']} (15:15, 650+ {I['stone']}): Drop Defensive {I['castle']} (0s wait <= 10s), {I['bow_saw']}, continuous 1 {I['town_center']}.",
                ],
            ),
            RTSOverlayStep(
                villager_count=bal_vils,
                age=3,
                wood=bal_alloc["wood"],
                food=bal_alloc["food"],
                gold=bal_alloc["gold"],
                stone=bal_alloc["stone"],
                notes=[
                    f"Build {I['monastery']} (2 Monks, max 1 Relic assumed) + Genoese & {I['light_cavalry']}; drop 2 {I['stone']} -> {I['wood']} (keep 2 on Stone).",
                    f"At 20+ Genoese: prioritize {I['university']} -> {I['ballistics']} ({bal_str}, -33% Italians) ahead of extra buildings!",
                ],
            ),
            RTSOverlayStep(
                villager_count=imp_c_vils,
                age=3,
                wood=imp_c_alloc["wood"],
                food=imp_c_alloc["food"],
                gold=imp_c_alloc["gold"],
                stone=imp_c_alloc["stone"],
                notes=[
                    f"At 30+ Army: send Loom vil forward -> Forward {I['siege_workshop']} & 3-4 {I['battering_ram']}s + Stable #2; stick to 1 {I['town_center']}!",
                    f"Shift priority to {I['imperial_age']} ({imp_c_str}, 850F/680G); immediately add {I['town_center']} #2 & #3 after clicking Imp!",
                ],
            ),
            RTSOverlayStep(
                villager_count=fin_vils,
                age=4,
                wood=end_alloc["wood"],
                food=end_alloc["food"],
                gold=end_alloc["gold"],
                stone=end_alloc["stone"],
                notes=[
                    f"Reach {I['imperial_age']} ({imp_r_str}): Conscription, {I['chemistry']} (-33%), Bracer, Elite Genoese, Hussar, Pavise, Silk Armor + {I['bombard_cannon']}s!",
                    f"Anti-Float Rule: Spend surplus into extra Stables/Castles/upgrades to keep resource float < 500-1000.",
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
                    f"Click {I['castle_age']}: {I['double_bit_axe']} + {I['horse_collar']}, Farms #3-#5, {I['gold_mining']}, {I['lumber_camp']} #2, {I['barracks']} -> {I['stable']} #1 & Fletching.",
                    f"Reach {I['castle_age']} (15:15, 650+ {I['stone']}): Drop Defensive {I['castle']} (0s wait <= 10s), {I['bow_saw']}, continuous {I['town_center']} #1.",
                ],
            ),
            RTSOverlayStep(
                villager_count=42,
                age=3,
                wood=14,
                food=18,
                gold=6,
                stone=4,
                notes=[
                    f"Build ~20 Army (13 Genoese + 7 {I['light_cavalry']}) with early upgrades; then PAUSE military & drop {I['town_center']} #2 & #3!",
                    f"Prioritize 3-TC continuous {I['villager']}s, {I['farm']}s (22+) & {I['wheelbarrow']} until 3-TC boom is established ({milestones.get('boom3tc_setup_str', '25:00')}).",
                ],
            ),
            RTSOverlayStep(
                villager_count=imp_c_vils,
                age=3,
                wood=imp_c_alloc["wood"],
                food=imp_c_alloc["food"],
                gold=imp_c_alloc["gold"],
                stone=imp_c_alloc["stone"],
                notes=[
                    f"Maximize Genoese + {I['light_cavalry']}; at 20+ Genoese prioritize {I['university']} -> {I['ballistics']} ({bal_str}, -33%); send 8 Loom vils forward for Castle #2/#3, TC #4 & {I['siege_workshop']}!",
                    f"Keep float < 500-1000 and click {I['imperial_age']} ({imp_c_str}, 850F/680G) well before 40:00.",
                ],
            ),
            RTSOverlayStep(
                villager_count=fin_vils,
                age=4,
                wood=end_alloc["wood"],
                food=end_alloc["food"],
                gold=end_alloc["gold"],
                stone=end_alloc["stone"],
                notes=[
                    f"Reach {I['imperial_age']} ({imp_r_str}): Conscription, {I['chemistry']} (-33%), Bracer, Elite Genoese, Hussar, Pavise, Silk Armor, Siege Engineers + {I['bombard_cannon']}s & {I['trebuchet']}s!",
                ],
            ),
        ]

    # Combined Dark Age + Feudal Age RTS steps (strict sum(resources) == villager_count)
    rts_steps = [
        RTSOverlayStep(
            villager_count=6,
            age=1,
            wood=0,
            food=6,
            gold=0,
            stone=0,
            notes=[
                f"Vils #1-#6: {I['build']} 2 Houses at 0:00, then all 6 on {I['sheep']} under TC (max 7 on Sheep); push 3 {I['deer']}.",
            ],
        ),
        RTSOverlayStep(
            villager_count=9,
            age=1,
            wood=3,
            food=6,
            gold=0,
            stone=0,
            notes=[
                f"Vils #7-#9 (3 vils) -> {I['wood']} (1st vil walks 15s + {I['build']} {I['lumber_camp']} #1, then all 3 on Wood).",
            ],
        ),
        RTSOverlayStep(
            villager_count=11,
            age=1,
            wood=4,
            food=7,
            gold=0,
            stone=0,
            notes=[
                f"Vil #10 lures 1st {I['boar']} (03:25 arrival -> garrison 7 TC vils 5s to shoot -> 6+ on Boar); Vil #11 to {I['wood']} (4 on Wood).",
            ],
        ),
        RTSOverlayStep(
            villager_count=15,
            age=1,
            wood=4,
            food=11,
            gold=0,
            stone=0,
            notes=[
                f"Vils #12-#15 (4 vils) -> Pushed {I['deer']} under TC (1st vil builds House #3, all 4 on Deer). Lure 2nd {I['boar']} at 04:43 (garrison 7 TC vils 5s at 05:13).",
            ],
        ),
        RTSOverlayStep(
            villager_count=19,
            age=1,
            wood=4,
            food=15,
            gold=0,
            stone=0,
            notes=[
                f"Vils #16-#19 (4 vils) -> {I['berries']} (1st vil builds {I['mill']}, 3rd builds House #4, all 4 on Berries).",
            ],
        ),
        RTSOverlayStep(
            villager_count=23,
            age=1,
            wood=4,
            food=15,
            gold=0,
            stone=4,
            notes=[
                f"Vils #20-#23 (4 vils) -> {I['stone']} (1st vil builds {I['mining_camp']}, 4th builds House #5, all 4 on Stone).",
            ],
        ),
        RTSOverlayStep(
            villager_count=26,
            age=1,
            wood=7,
            food=15,
            gold=0,
            stone=4,
            notes=[
                f"Vils #24-#26 (3 vils) -> {I['wood']} (7 on LC #1). Click {I['feudal_age']} (425F, 0s TC idle); Sheep #8 finishes -> 2 {I['farm']}s + cap LC #1 at 8.",
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
                f"In {I['feudal_age']}: Vils #27-#28 (2 vils) -> {I['gold']} (1st builds {I['mining_camp']}); 3 vils {I['build']} {I['market']} & 1 vil {I['blacksmith']}.",
                f"Sell 100 {I['stone']} at {I['market']} (+70G high Feudal price) & click {I['castle_age']} (680F, 170G).",
            ],
        ),
        *castle_steps,
    ]

    desc = (
        f"Italians Arena FC (3 Deer, No Chickens) — {variant_label}. "
        f"Includes 5s Boar-shooting TC garrison idling, updated animal caps (<=7 Sheep, 7-8 Boar / 10 transition), "
        f"combined same-resource steps for Dark/Feudal/Castle-Click, 20+ ranged Ballistics priority, and "
        f"high-level Castle+ macro loops with 92% Feudal / 90% Castle+ execution buffers."
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

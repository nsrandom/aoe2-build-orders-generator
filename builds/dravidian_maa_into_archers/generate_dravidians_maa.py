#!/usr/bin/env python3
"""
Generator & 1-Second Discrete-Event Simulator for:
Dravidians Man-at-Arms (MAA) into Archers Build Orders.

Generates:
1. Detailed HTML build order tables & telemetry in `builds/dravidian_maa_into_archers/`
2. RTS Overlay compatible JSON files in `builds/dravidian_maa_into_archers/`
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))
sys.path.insert(0, str(THIS_DIR.parents[1] / "scripts"))

from aoe2_data import ANIMALS, AoE2Database, ResourceBundle
from backward_planner import BackwardPlanner, ContinuousProductionItem
from exporters import (
    BuildOrderDocument,
    DetailedBuildRow,
    RTS_ICONS,
    RTSOverlayStep,
    export_build_order_html,
    export_rts_overlay_json,
)
from sim_dravidians_maa import DetailedEcoSimulator

OUT_DIR = THIS_DIR


def run_dravidians_maa_variant(
    variant_key: str,
    variant_label: str,
    chicken_count: int,
    click_vils: int,
) -> BuildOrderDocument:
    """
    Runs a 1-second resolution simulation for the specified Dravidians MAA -> Archers
    variant from 0:00 through Feudal Age steady state (12:00) and builds both the
    DetailedBuildRow table and the RTSOverlayStep sequence.
    """
    sim = DetailedEcoSimulator(variant_key, chicken_count=chicken_count)
    planner = BackwardPlanner(sim.db, sim.rules)

    rows: List[DetailedBuildRow] = []
    resource_timeline: List[Dict[str, object]] = []

    def current_army_dict() -> Dict[str, int]:
        inf_key = "maa" if "man-at-arms" in sim.upgrades else "militia"
        arch_key = "crossbow" if "crossbowman" in sim.upgrades else "archer"
        return {
            "scout": sim.military_units.get("scout", 1),
            inf_key: sim.military_units.get("militia", 0),
            arch_key: sim.military_units.get("archer", 0),
        }

    def record_timeline_point() -> None:
        from exporters import format_army_counts
        resource_timeline.append(
            {
                "t": sim.time_s,
                "ts": sim.fmt_time(),
                "food": round(sim.bank.food),
                "wood": round(sim.bank.wood),
                "gold": round(sim.bank.gold),
                "stone": round(sim.bank.stone),
                "army": format_army_counts(current_army_dict()),
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
                army_counts=current_army_dict(),
            )
        )
        record_timeline_point()

    # t = 0:00 initial state (3 vils build 2 houses, TC queues Vil 4)
    sim.bank = sim.bank - ResourceBundle(food=50)
    sim.tc_busy_until = 25
    sim.tc_action = "vil_4"
    add_row(
        "3v (4 pop)",
        "Dark Age",
        "Vils 1-2 build House #1 (18.75s), Vil 3 builds House #2 (25s), then gather Sheep (5s return walk). Queue Vil #4.",
        "Start: 200F, 200W, 100G, 200S (-50F Vil 4, -50W 2 Houses). Push deer / scout sheep.",
    )

    feudal_clicked = False
    feudal_click_t = 0
    barracks_ready_t: Optional[int] = None
    militia_trained = 0
    barracks_busy_until = 0
    mc_started = False
    range_ready_t: Optional[int] = None
    range_busy_until = 0
    archers_trained = 0
    bs_started = False
    bs_ready_t: Optional[int] = None
    fletching_started = False
    horse_collar_started = False
    farms_seeded = 0
    lc2_rebuilt = False
    houses_built = 5  # Houses #1-#5 accounted for up to Feudal transition (30 pop cap)
    house_busy_until = 0
    gold_mining_started = False
    wheelbarrow_started = False
    castle_clicked = False
    castle_click_t = 0
    range2_started = False
    range2_ready_t: Optional[int] = None
    range2_busy_until = 0
    padded_archer_armor_started = False

    max_sim_t = 1400
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
        )

        # Once Boar #1 is under TC (t >= 205, 03:25) and Sheep #4 finishes (t = 214, 03:34),
        # the 6 shepherds cleanly switch onto Boar #1 (7 hunters on Boar #1, 0 abandoned sheep rot)
        if t >= 205 and sim.remaining_animals["sheep"] == 4 and sim.active_carcass_food["sheep"] <= 1e-6:
            for v in sim.vils:
                if v["role"] == "sheep":
                    v["role"] = "boar"

        # Boar #2 lure starts at t=283 (04:43) -> arrives at t=313 (05:13) right as Boar #1 depletes
        if t == 283:
            for v in sim.vils:
                if v["role"] == "boar":
                    v["busy_until"] = t + 30
                    break

        # Check TC completions
        if t == sim.tc_busy_until and sim.tc_action != "idle":
            act = sim.tc_action
            sim.tc_action = "idle"

            if act.startswith("vil_"):
                vid = int(act.split("_")[1])
                phase_label = "Dark Age" if sim.age == 1 else "Feudal Age"
                action_text = ""
                note_text = ""

                if vid in (4, 5, 6):
                    sim.vils.append({"id": vid, "role": "sheep", "busy_until": t})
                    action_text = f"Vil #{vid} -> Sheep under TC (0s walk)"
                    if vid == 6:
                        note_text = "6/6 ideal vils on Sheep."
                elif vid == 7:
                    sim.bank = sim.bank - ResourceBundle(wood=100)
                    sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 50})
                    sim.lc_completed_s = t + 50
                    action_text = "Vil #7 -> Walk 15s + Build Lumber Camp (-100W, 35s) -> Wood"
                    note_text = "LC completes at 02:30 (100% wood efficiency)."
                elif vid in (8, 9):
                    sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 15})
                    action_text = f"Vil #{vid} -> Wood at Lumber Camp (15s walk)"
                elif vid == 10:
                    sim.vils.append({"id": vid, "role": "boar", "busy_until": t + 30})
                    action_text = "Vil #10 -> Lure Boar #1 (15s walk out + 15s lure back)"
                    note_text = "Boar #1 arrives under TC at 03:25; 6 shepherds finish Sheep #4 at 03:34 then join Boar #1 (7 on Boar)."
                elif vid == 11:
                    sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 15})
                    action_text = "Vil #11 -> Wood at Lumber Camp (15s walk)"
                    note_text = "4/4 initial vils on Wood."
                elif vid == 12:
                    sim.bank = sim.bank - ResourceBundle(wood=25)
                    if variant_key == "deer":
                        sim.vils.append({"id": vid, "role": "deer", "busy_until": t + 35})
                        action_text = "Vil #12 -> Build House #3 (-25W, 5s+25s+5s) -> Pushed Deer under TC"
                        note_text = "Start harvesting Pushed Deer #1 under TC."
                    elif variant_key == "chicken_mill_8":
                        sim.bank = sim.bank - ResourceBundle(wood=100)
                        sim.vils.append({"id": vid, "role": "chicken_mill", "busy_until": t + 80})
                        action_text = "Vil #12 -> Build House #3 (-25W, 30s) -> Walk 15s + Build Mill on 8 Chickens (-100W, 35s)"
                        note_text = "Milling 8 Chickens (600F pool) unlocks Feudal building #2."
                    else:
                        sim.vils.append({"id": vid, "role": "chicken_ld", "busy_until": t + 45})
                        action_text = "Vil #12 -> Build House #3 (-25W, 30s) -> Walk 15s to Long-Distance Hunt 6 Chickens"
                        note_text = "35F hunter carry capacity allows 1 chicken per trip."
                elif vid == 13:
                    if variant_key == "deer":
                        sim.vils.append({"id": vid, "role": "deer", "busy_until": t})
                        action_text = "Vil #13 -> Pushed Deer under TC (0s walk)"
                    elif variant_key == "chicken_mill_8":
                        sim.vils.append({"id": vid, "role": "chicken_mill", "busy_until": t + 15})
                        action_text = "Vil #13 -> Chickens at Mill (15s walk)"
                    else:
                        sim.vils.append({"id": vid, "role": "chicken_ld", "busy_until": t + 15})
                        action_text = "Vil #13 -> Long-Distance Hunt Chickens (15s walk; 2/2 ideal vils on Chickens)"
                elif vid in (14, 15):
                    if variant_key == "deer":
                        sim.vils.append({"id": vid, "role": "deer", "busy_until": t})
                        action_text = f"Vil #{vid} -> Pushed Deer under TC (0s walk)"
                        if vid == 15:
                            note_text = "4/4 on Pushed Deer + 7 on Boar. At 04:43, 1 Boar hunter walks out (15s each way) to lure Boar #2 (arrives 05:13 as Boar #1 finishes)."
                    elif variant_key == "chicken_mill_8":
                        sim.vils.append({"id": vid, "role": "chicken_mill", "busy_until": t + 15})
                        action_text = f"Vil #{vid} -> Chickens at Mill (15s walk; 4 vils on 8-Chicken patch)"
                        if vid == 15:
                            note_text = "At 04:43, 1 Boar hunter walks out (15s each way) to lure Boar #2 (arrives 05:13)."
                    else:
                        if vid == 14:
                            sim.bank = sim.bank - ResourceBundle(wood=100)
                            sim.vils.append({"id": vid, "role": "berries", "busy_until": t + 50})
                            action_text = "Vil #14 -> Walk 15s + Build Mill on Berries (-100W, 35s)"
                        else:
                            sim.vils.append({"id": vid, "role": "berries", "busy_until": t + 15})
                            action_text = "Vil #15 -> Berries at Mill (15s walk)"
                            note_text = "At 04:43, 1 Boar hunter walks out (15s each way) to lure Boar #2 (arrives 05:13)."
                elif vid == 16:
                    if variant_key == "deer":
                        sim.bank = sim.bank - ResourceBundle(wood=100)
                        sim.vils.append({"id": vid, "role": "berries", "busy_until": t + 50})
                        action_text = "Vil #16 -> Walk 15s + Build Mill on Berries (-100W, 35s)"
                        note_text = "2nd Dark Age building completed."
                    elif variant_key == "chicken_mill_8":
                        sim.vils.append({"id": vid, "role": "boar", "busy_until": t})
                        action_text = "Vil #16 -> Boar/Sheep under TC (0s walk; 8 on Boar #2)"
                    else:
                        sim.vils.append({"id": vid, "role": "berries", "busy_until": t + 15})
                        action_text = "Vil #16 -> Berries at Mill (15s walk)"
                elif vid == 17:
                    if variant_key == "deer":
                        sim.vils.append({"id": vid, "role": "berries", "busy_until": t + 15})
                        action_text = "Vil #17 -> Berries at Mill (15s walk)"
                    elif variant_key == "chicken_mill_8":
                        sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 15})
                        action_text = "Vil #17 -> Wood at Lumber Camp (15s walk; 5th on Wood)"
                    else:
                        sim.vils.append({"id": vid, "role": "berries", "busy_until": t + 15})
                        action_text = "Vil #17 -> Berries at Mill (15s walk; 4/4 on Berries)"
                elif vid == 18:
                    if click_vils == 18:
                        sim.bank = sim.bank - ResourceBundle(wood=25)
                        sim.vils.append({"id": vid, "role": "gold_ld", "busy_until": t + 45})
                        action_text = "Vil #18 -> Build House #4 (-25W, 30s) -> Long-Distance Mine Gold (15s walk)"
                    elif variant_key == "deer":
                        sim.vils.append({"id": vid, "role": "berries", "busy_until": t + 15})
                        action_text = "Vil #18 -> Berries at Mill (15s walk; 3 on Berries)"
                    elif variant_key == "chicken_mill_8":
                        sim.bank = sim.bank - ResourceBundle(wood=25)
                        sim.vils.append({"id": vid, "role": "gold_ld", "busy_until": t + 45})
                        action_text = "Vil #18 -> Build House #4 (-25W, 30s) -> Long-Distance Mine Gold (15s walk)"
                    else:
                        sim.bank = sim.bank - ResourceBundle(wood=25)
                        sim.vils.append({"id": vid, "role": "sheep", "busy_until": t + 35})
                        action_text = "Vil #18 -> Build House #4 (-25W, 35s) -> Sheep under TC"
                elif vid == 19 and sim.age == 1:
                    if variant_key == "deer":
                        sim.bank = sim.bank - ResourceBundle(wood=25)
                        sim.vils.append({"id": vid, "role": "gold_ld", "busy_until": t + 45})
                        action_text = "Vil #19 -> Build House #4 (-25W, 30s) -> Long-Distance Mine Gold (15s walk)"
                    else:
                        sim.vils.append({"id": vid, "role": "gold_ld", "busy_until": t + 15})
                        action_text = "Vil #19 -> Long-Distance Mine Gold (15s walk)"
                else:
                    # Feudal Age villagers:
                    # 1. Fill Gold to 4 (for 1-Range continuous Archers + Fletching)
                    # 2. Fill Wood at LC to 8
                    # 3. Seed Farms up to 12-14; once >= 11 Farms (or >= 29 vils), send 3 more vils to Gold (7 on Gold) for Castle Age (200G) + 2-Range Crossbows
                    g_cnt = sum(1 for v in sim.vils if v["role"] in ("gold", "gold_ld"))
                    w_lc_cnt = sum(1 for v in sim.vils if v["role"] == "wood")
                    f_active_cnt = sum(1 for v in sim.vils if v["role"] in ("berries", "farm"))
                    if g_cnt < 4:
                        sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                        action_text = f"Vil #{vid} -> Gold at Mining Camp (15s walk; {g_cnt+1}/4 on Gold for Archers)"
                    elif w_lc_cnt < 8:
                        sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 15})
                        action_text = f"Vil #{vid} -> Wood at Lumber Camp (15s walk; {w_lc_cnt+1} on Wood)"
                    elif (f_active_cnt >= 14 or len(sim.vils) >= 29) and g_cnt < 7:
                        sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                        action_text = f"Vil #{vid} -> Gold at Mining Camp (15s walk; {g_cnt+1}/7 on Gold for Castle Age & 2nd Range)"
                    else:
                        wb_hold = 50 if (not wheelbarrow_started and len(sim.vils) >= 31) else 0
                        if bs_started and sim.bank.wood >= (60 + wb_hold) and f_active_cnt < 18:
                            sim.bank = sim.bank - ResourceBundle(wood=60)
                            farms_seeded += 1
                            sim.vils.append({"id": vid, "role": "farm", "busy_until": t + 20})
                            action_text = f"Vil #{vid} -> Build Farm #{farms_seeded} (-60W, 5s walk + 15s build)"
                        else:
                            sim.vils.append({"id": vid, "role": "straggler", "busy_until": t + 3})
                            action_text = f"Vil #{vid} -> Straggler Tree near TC (3s walk)"

                # Queue next Dark Age vil or Loom
                if sim.age == 1:
                    if vid < click_vils:
                        sim.bank = sim.bank - ResourceBundle(food=50)
                        sim.tc_busy_until = t + 25
                        sim.tc_action = f"vil_{vid+1}"
                    else:
                        sim.bank = sim.bank - ResourceBundle(gold=50)
                        sim.tc_busy_until = t + 25
                        sim.tc_action = "loom"
                        note_text = (note_text + " " if note_text else "") + "Queue Loom (-50G, 25s)."

                add_row(f"{len(sim.vils)}v ({len(sim.vils)+1+militia_trained+archers_trained} pop)", current_phase, action_text, note_text)

            elif act == "loom":
                sim.upgrades.add("loom")
                add_row(f"{len(sim.vils)}v", "Dark Age", "Loom completes.", "Ready to click Feudal Age.")

            elif act == "feudal":
                sim.age = 2
                current_phase = "Feudal Age"
                sim.bank = sim.bank + ResourceBundle(wood=200)  # Dravidians +200W bonus
                add_row(
                    f"{len(sim.vils)}v",
                    "Feudal Age",
                    "REACHED FEUDAL AGE! Receive +200 Wood (Dravidians bonus).",
                    f"3 Militia ready in field. Wood efficiency: {sim.wood_efficiency()*100:.0f}%.",
                )
                # Immediate Feudal Age actions:
                # 1. Queue next Villager (50F)
                sim.bank = sim.bank - ResourceBundle(food=50)
                sim.tc_busy_until = t + 25
                sim.tc_action = f"vil_{len(sim.vils)+1}"
                # 2. Research Man-at-Arms (50F, 20G for Dravidians, 40s)
                sim.bank = sim.bank - ResourceBundle(food=50, gold=20)
                sim.upgrades.add("man-at-arms")
                # 3. Research Double-Bit Axe (100F, 50W, 25s)
                sim.bank = sim.bank - ResourceBundle(food=100, wood=50)
                sim.upgrades.add("double-bit axe")
                # 4. Build Archery Range (175W, 10s walk + 50s build)
                sim.bank = sim.bank - ResourceBundle(wood=175)
                range_ready_t = t + 60
                for v in sim.vils:
                    if v["role"] == "wood" and int(v["busy_until"]) <= t:
                        v["busy_until"] = t + 60
                        break
                add_row(
                    f"{len(sim.vils)}v",
                    "Feudal Age",
                    "Queue Vil (-50F), research Man-at-Arms (-50F, -20G, 40s) & Double-Bit Axe (-100F, -50W, 25s), build Archery Range (-175W, 10s+50s).",
                    "Dravidians 50% Barracks tech discount + 200W bonus funds everything on Frame 1.",
                )

            elif act == "wheelbarrow":
                sim.upgrades.add("wheelbarrow")
                add_row(
                    f"{len(sim.vils)}v ({len(sim.vils)+1+militia_trained+archers_trained} pop)",
                    "Feudal Age",
                    "Wheelbarrow completes! Farmer gather rate increases to 23.03 F/min (+13.4%).",
                    "Food bank surged during 75s research; ready to click Castle Age.",
                )

            elif act == "castle":
                sim.age = 3
                current_phase = "Castle Age"
                sim.bank = sim.bank + ResourceBundle(wood=200)  # Dravidians +200W bonus
                add_row(
                    f"{len(sim.vils)}v ({len(sim.vils)+1+militia_trained+archers_trained} pop)",
                    "Castle Age",
                    f"REACHED CASTLE AGE! Receive +200 Wood (Dravidians bonus). Army: {archers_trained} Archers + 3 MAA.",
                    f"Wood efficiency: {sim.wood_efficiency()*100:.0f}%.",
                )
                # Immediate Castle Age power-spike actions:
                sim.bank = sim.bank - ResourceBundle(food=50)
                sim.tc_busy_until = t + 25
                sim.tc_action = f"vil_{len(sim.vils)+1}"
                sim.bank = sim.bank - ResourceBundle(food=125, gold=75)
                sim.upgrades.add("crossbowman")
                sim.bank = sim.bank - ResourceBundle(food=200, gold=100)
                sim.upgrades.add("bodkin arrow")
                sim.bank = sim.bank - ResourceBundle(food=150, wood=100)
                sim.upgrades.add("bow saw")
                add_row(
                    f"{len(sim.vils)}v ({len(sim.vils)+1+militia_trained+archers_trained} pop)",
                    "Castle Age",
                    "Queue Vil (-50F), research Crossbowman (-125F, -75G), Bodkin Arrow (-200F, -100G), and Bow Saw (-150F, -100W)!",
                    "2 Archery Ranges immediately transition to continuous Crossbowman production.",
                )
                break

        # Feudal Age TC management: Click Castle Age (800F, 200G), or research Wheelbarrow (175F, 50W), or queue next Villager (50F)
        if sim.age == 2 and sim.tc_action == "idle" and not castle_clicked:
            if sim.bank.food >= 800 and sim.bank.gold >= 200 and bs_ready_t is not None and t >= bs_ready_t:
                castle_clicked = True
                castle_click_t = t
                current_phase = "Castle Transition"
                sim.bank = sim.bank - ResourceBundle(food=800, gold=200)
                sim.tc_busy_until = t + 160
                sim.tc_action = "castle"
                add_row(
                    f"{len(sim.vils)}v ({len(sim.vils)+1+militia_trained+archers_trained} pop)",
                    "Castle Transition",
                    f"CLICK CASTLE AGE (-800F, -200G, 160s) with {archers_trained} Archers in field! Keep producing Archers continuously during transition.",
                    f"Reaches Castle Age at {sim.fmt_time(t + 160)}.",
                )
            elif not wheelbarrow_started and len(sim.vils) >= 32 and sum(1 for v in sim.vils if v["role"] in ("berries", "farm")) >= 14 and sim.bank.food >= 175 and sim.bank.wood >= 50:
                wheelbarrow_started = True
                sim.bank = sim.bank - ResourceBundle(food=175, wood=50)
                sim.tc_busy_until = t + 75
                sim.tc_action = "wheelbarrow"
                add_row(
                    f"{len(sim.vils)}v ({len(sim.vils)+1+militia_trained+archers_trained} pop)",
                    "Feudal Age",
                    "Research Wheelbarrow at TC (-175F, -50W, 75s).",
                    "Boosts 12+ Farmers and banks Food toward 800F for Castle Age.",
                )
            elif not (wheelbarrow_started and sim.bank.food >= 680 and sim.bank.gold >= 165) and sim.bank.food >= 50:
                sim.bank = sim.bank - ResourceBundle(food=50)
                sim.tc_busy_until = t + 25
                sim.tc_action = f"vil_{len(sim.vils)+1}"

        # Click Feudal Age as soon as Loom finishes (within <= 5s TC idle rule)
        if "loom" in sim.upgrades and not feudal_clicked and sim.tc_action == "idle":
            if sim.bank.food >= 500:
                loom_done_t = (click_vils - 3) * 25 + 25
                idle_wait_s = max(0, t - loom_done_t)
                sim.bank = sim.bank - ResourceBundle(food=500)
                sim.tc_busy_until = t + 130
                sim.tc_action = "feudal"
                feudal_clicked = True
                feudal_click_t = t
                current_phase = "Feudal Transition"
                # Transition reallocations:
                # 1. Build Barracks (-175W, 10s walk + 50s build) + sequential House #5 (-25W, 0s walk + 25s build + 10s return)
                sim.bank = sim.bank - ResourceBundle(wood=200)
                barracks_ready_t = t + 60
                for v in sim.vils:
                    if v["role"] in ("sheep", "boar", "deer") and int(v["busy_until"]) <= t:
                        v["role"] = "wood"
                        v["busy_until"] = t + 95
                        break
                # 2. Reallocate under-TC food vils to Wood (15s walk to LC)
                n_to_wood = 2 if click_vils == 18 else 3
                moved_w = 0
                for v in sim.vils:
                    if v["role"] in ("sheep", "boar", "deer") and int(v["busy_until"]) <= t and moved_w < n_to_wood:
                        v["role"] = "wood"
                        v["busy_until"] = t + 15
                        moved_w += 1
                add_row(
                    f"{len(sim.vils)}v",
                    "Feudal Transition",
                    f"CLICK FEUDAL AGE (-500F, 130s, {idle_wait_s}s TC idle)! Move {n_to_wood} TC food vils -> Wood (15s walk). 1 vil builds Barracks (-175W, 60s) -> chains House #5 (-25W, 25s).",
                    "Sequential building rule: 0s walk between Barracks and House #5.",
                )

        # Build Mining Camp on Gold during transition (~55s after clicking up)
        if feudal_clicked and not mc_started and sim.bank.wood >= 100 and t >= feudal_click_t + 55:
            mc_started = True
            sim.bank = sim.bank - ResourceBundle(wood=100)
            for v in sim.vils:
                if v["role"] == "gold_ld":
                    v["role"] = "gold"
                    v["busy_until"] = t + 35
            for v in sim.vils:
                if v["role"] in ("sheep", "boar", "deer", "chicken_mill", "chicken_ld") and int(v["busy_until"]) <= t:
                    v["role"] = "gold"
                    v["busy_until"] = t + 50
                    break
            add_row(
                f"{len(sim.vils)}v",
                "Feudal Transition",
                "Build Mining Camp on Gold (-100W, 35s) and send 2nd vil to Gold (2 on Gold).",
                "Ensures 20G for MAA + steady Gold for Archers.",
            )

        # Train 3 Militia during Feudal transition once Barracks finishes
        if barracks_ready_t is not None and t >= barracks_ready_t and militia_trained < 3 and t >= barracks_busy_until:
            if sim.bank.food >= 60 and sim.bank.gold >= 20:
                sim.bank = sim.bank - ResourceBundle(food=60, gold=20)
                militia_trained += 1
                barracks_busy_until = t + 21
                sim.military_units["militia"] += 1
                add_row(
                    f"{len(sim.vils)}v",
                    "Feudal Transition",
                    f"Queue Militia #{militia_trained}/3 at Barracks (-60F, -20G, 21s).",
                    f"Finishes at {sim.fmt_time(t + 21)}.",
                )

        # Build Houses in Feudal Age / Castle Transition ahead of population cap (5s walk each way + 25s build = 35s)
        cur_pop = len(sim.vils) + sum(sim.military_units.values())
        pop_cap = 5 + houses_built * 5
        if sim.age >= 2 and cur_pop + 3 >= pop_cap and t >= house_busy_until and sim.bank.wood >= 25:
            houses_built += 1
            house_busy_until = t + 35
            sim.bank = sim.bank - ResourceBundle(wood=25)
            for v in sim.vils:
                if v["role"] in ("wood", "straggler") and int(v["busy_until"]) <= t:
                    v["busy_until"] = t + 35
                    break

        # In Feudal Age: Research Horse Collar before seeding farms
        if (
            sim.age == 2
            and not horse_collar_started
            and sim.bank.food >= 125
            and sim.bank.wood >= 75
        ):
            horse_collar_started = True
            sim.bank = sim.bank - ResourceBundle(food=75, wood=75)
            sim.upgrades.add("horse collar")
            add_row(
                f"{len(sim.vils)}v",
                current_phase,
                "Research Horse Collar at Mill (-75F, -75W, 20s) before seeding heavy farms.",
                "Farms now yield 250 Food instead of 175 Food.",
            )

        # Continuous Archer production from Archery Range #1 (hold 50G briefly if Fletching is due)
        fletching_gold_reserve = 50 if (bs_ready_t is not None and t >= bs_ready_t and not fletching_started and archers_trained >= 2) else 0
        if range_ready_t is not None and t >= range_ready_t and t >= range_busy_until:
            if sim.bank.wood >= 25 and sim.bank.gold >= (45 + fletching_gold_reserve):
                sim.bank = sim.bank - ResourceBundle(wood=25, gold=45)
                archers_trained += 1
                range_busy_until = t + 35
                sim.military_units["archer"] += 1
                add_row(
                    f"{len(sim.vils)}v ({len(sim.vils)+1+militia_trained+archers_trained} pop)",
                    current_phase,
                    f"Queue Archer #{archers_trained} at Archery Range #1 (-25W, -45G, 35s).",
                    f"Continuous Range #1 production (Archers queued: {archers_trained}).",
                )

        # Continuous Archer production from Archery Range #2 during Castle Transition (preserving 175G for Crossbow + Bodkin when <= 45s to Castle)
        castle_gold_reserve = 175 if (castle_clicked and (sim.tc_busy_until - t) <= 45) else 0
        if range2_ready_t is not None and t >= range2_ready_t and t >= range2_busy_until:
            if sim.bank.wood >= 25 and sim.bank.gold >= (45 + castle_gold_reserve):
                sim.bank = sim.bank - ResourceBundle(wood=25, gold=45)
                archers_trained += 1
                range2_busy_until = t + 35
                sim.military_units["archer"] += 1
                add_row(
                    f"{len(sim.vils)}v ({len(sim.vils)+1+militia_trained+archers_trained} pop)",
                    current_phase,
                    f"Queue Archer #{archers_trained} at Archery Range #2 (-25W, -45G, 35s).",
                    f"2-Range Archer production active (Archers queued: {archers_trained}).",
                )

        # Build Blacksmith once we have 150W after Range
        if sim.age == 2 and (horse_collar_started or click_vils == 18) and not bs_started and sim.bank.wood >= 150 and t >= (range_ready_t or 9999):
            bs_started = True
            sim.bank = sim.bank - ResourceBundle(wood=150)
            bs_ready_t = t + 50
            add_row(
                f"{len(sim.vils)}v",
                current_phase,
                "Build Blacksmith (-150W, 10s walk + 40s build).",
                "Feudal building #2 (unlocks Castle Age & Fletching).",
            )

        # Research Fletching once Blacksmith finishes (preserving 50F if TC villager is due within 8s)
        tc_food_reserve = 50 if (sim.tc_busy_until - t) <= 8 and not castle_clicked else 0
        if bs_ready_t is not None and t >= bs_ready_t and not fletching_started and sim.bank.food >= (100 + tc_food_reserve) and sim.bank.gold >= 50:
            fletching_started = True
            sim.bank = sim.bank - ResourceBundle(food=100, gold=50)
            sim.upgrades.add("fletching")
            add_row(
                f"{len(sim.vils)}v",
                current_phase,
                "Research Fletching at Blacksmith (-100F, -50G, 30s).",
                "+1 attack, +1 range for Archers.",
            )

        # Research Gold Mining once 6+ villagers are on Gold
        g_tot_now = sum(1 for v in sim.vils if v["role"] in ("gold", "gold_ld"))
        if sim.age == 2 and fletching_started and not gold_mining_started and g_tot_now >= 6 and sim.bank.food >= (100 + tc_food_reserve) and sim.bank.wood >= 75:
            gold_mining_started = True
            sim.bank = sim.bank - ResourceBundle(food=100, wood=75)
            sim.upgrades.add("gold mining")
            add_row(
                f"{len(sim.vils)}v",
                current_phase,
                "Research Gold Mining at Mining Camp (-100F, -75W, 30s).",
                "+15% gold gather rate to accelerate 200G for Castle Age and fund 2-Range Archers.",
            )

        # Rebuild Lumber Camp #2 when wood cutting efficiency drops to 60% (600s after LC #1 finished at -1%/15s)
        if sim.age == 2 and not lc2_rebuilt and farms_seeded >= 2 and sim.wood_efficiency() <= 0.60 and sim.bank.wood >= 100:
            lc2_rebuilt = True
            sim.bank = sim.bank - ResourceBundle(wood=100)
            sim.lc_completed_s = t + 35
            add_row(
                f"{len(sim.vils)}v",
                current_phase,
                "Build refreshing Lumber Camp #2 (-100W, 35s) as wood efficiency reaches 60%.",
                "Resets lumberjack gathering efficiency back to 100% (10:00 after LC #1 completed).",
            )

        # During Castle Transition: Build 2nd Archery Range (-175W) and research Padded Archer Armor (-100F)
        if castle_clicked and not range2_started and sim.bank.wood >= 175:
            range2_started = True
            sim.bank = sim.bank - ResourceBundle(wood=175)
            range2_ready_t = t + 60
            add_row(
                f"{len(sim.vils)}v",
                "Castle Transition",
                "Build Archery Range #2 (-175W, 10s walk + 50s build).",
                "Prepares 2-Range Crossbowman production for Castle Age.",
            )

        if castle_clicked and not padded_archer_armor_started and sim.bank.food >= 250:
            padded_archer_armor_started = True
            sim.bank = sim.bank - ResourceBundle(food=100)
            sim.upgrades.add("padded archer armor")
            add_row(
                f"{len(sim.vils)}v",
                "Castle Transition",
                "Research Padded Archer Armor at Blacksmith (-100F, 40s).",
                "+1/+1 armor for Archers before Castle Age engagement.",
            )

        # Transition sheep/hunt/straggler vils to Farms as wood allows in Feudal Age
        f_active_now = sum(1 for v in sim.vils if v["role"] in ("berries", "farm"))
        lc2_reserve = 100 if (not lc2_rebuilt and farms_seeded >= 3 and sim.wood_efficiency() <= 0.61) else 0
        range2_reserve = 175 if (castle_clicked and not range2_started) else 0
        wb_w_reserve = 85 if (not wheelbarrow_started and len(sim.vils) >= 31 and f_active_now >= 14) else 0
        archer_w_reserve = 25 if (range_ready_t is not None and (range_busy_until - t) <= 8) else 0
        early_farm_ok = horse_collar_started and farms_seeded < 1 and t <= (range_ready_t or 9999) - 25 and sim.bank.wood >= 60
        later_farm_ok = bs_started and f_active_now < 18 and sim.bank.wood >= (60 + archer_w_reserve + lc2_reserve + range2_reserve + wb_w_reserve)
        if sim.age == 2 and (early_farm_ok or later_farm_ok):
            # Prefer transitioning sheep/hunt first, then straggler
            target_vil = None
            for pref_roles in (("sheep", "boar", "deer", "chicken_mill", "chicken_ld"), ("straggler",)):
                for v in sim.vils:
                    if v["role"] in pref_roles and int(v["busy_until"]) <= t:
                        target_vil = v
                        break
                if target_vil is not None:
                    break
            if target_vil is not None:
                sim.bank = sim.bank - ResourceBundle(wood=60)
                target_vil["role"] = "farm"
                target_vil["busy_until"] = t + 20  # 5s walk + 15s build
                farms_seeded += 1
                add_row(
                    f"{len(sim.vils)}v",
                    current_phase,
                    f"Transition gatherer to Farm #{farms_seeded} (-60W, 5s walk + 15s build).",
                    "Transition decaying hunt/sheep/straggler vils onto Horse Collar farms.",
                )

        sim.tick_gather()
        if t % 10 == 0:
            record_timeline_point()

    # Steady-state calculation for 1 TC Villager + 1 Archery Range (or 2 Archery Ranges)
    steady_state = planner.compute_steady_state_vils(
        items=[
            ContinuousProductionItem("villager", 1),
            ContinuousProductionItem("archer", 1),
        ],
        civ="Dravidians",
        age=2,
        upgrades=["double-bit axe", "horse collar"],
        food_source="farmer",
        wood_minutes_since_lc=1.0,
    )

    # Build RTS Overlay steps
    I = RTS_ICONS
    if variant_key == "deer":
        hunt_note = f"Push 3 {I['deer']} under TC; put 4 {I['villager']} on {I['deer']} while 7 {I['villager']} eat {I['boar']}"
        v15_food = 11
    elif variant_key == "chicken_mill_8":
        hunt_note = f"{I['build']} {I['mill']} on 8 Chickens (600F) with 12th {I['villager']} after {I['build']} House #3; send 4 {I['villager']} to Chickens"
        v15_food = 11
    else:
        hunt_note = f"Send 12th & 13th {I['villager']} to Long-Distance Hunt 6 Chickens (2 {I['villager']} ideal); 14th & 15th {I['build']} {I['mill']} on {I['berries']}"
        v15_food = 11

    rts_steps = [
        RTSOverlayStep(
            villager_count=6,
            age=1,
            wood=0,
            food=6,
            gold=0,
            stone=0,
            notes=[
                f"{I['build']} 2 Houses at 0:00 (only 5s return walk to {I['sheep']}).",
                f"First 6 {I['villager']} on {I['sheep']} (6 ideal per carcass).",
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
                f"7th {I['villager']} walks 15s + {I['build']} {I['lumber_camp']} (finishes 02:30).",
                f"8th & 9th {I['villager']} to {I['wood']} (3 on {I['wood']}).",
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
                f"10th {I['villager']} lures 1st {I['boar']} (15s walk each way; arrives 03:25, shepherds finish 4th {I['sheep']} at 03:34 then 7 {I['villager']} eat {I['boar']}).",
                f"11th {I['villager']} to {I['wood']} (4 on {I['wood']}).",
            ],
        ),
        RTSOverlayStep(
            villager_count=15,
            age=1,
            wood=4,
            food=v15_food,
            gold=0,
            stone=0,
            notes=[
                f"12th {I['villager']} {I['build']} House #3, then: {hunt_note}.",
                f"At 04:43, 1 hunter lures 2nd {I['boar']} (arrives 05:13 right as 1st {I['boar']} finishes).",
            ],
        ),
        RTSOverlayStep(
            villager_count=click_vils,
            age=1,
            wood=5 if variant_key == "chicken_mill_8" else 4,
            food=click_vils - (6 if variant_key == "chicken_mill_8" else 5),
            gold=1,
            stone=0,
            notes=[
                f"Vils 16-{click_vils-1} to {I['berries']} / {I['food']} (and {I['build']} {I['mill']} if not milled yet).",
                f"Vil {click_vils} {I['build']} House #4 then Long-Distance Mines {I['gold']}.",
                f"Research {I['loom']} and click {I['feudal_age']} (<= 5s TC idle rule).",
            ],
        ),
        RTSOverlayStep(
            villager_count=click_vils,
            age=2,
            wood=8 if (click_vils == 19 or variant_key == "chicken_mill_8") else 7,
            food=click_vils - (10 if (click_vils == 19 or variant_key == "chicken_mill_8") else 9),
            gold=2,
            stone=0,
            notes=[
                f"During {I['feudal_age']} transition: move {2 if click_vils == 18 else 3} TC {I['food']} {I['villager']} to {I['wood']}.",
                f"1 {I['villager']} {I['build']} {I['barracks']} then chains House #5 (0s walk between).",
                f"{I['build']} {I['mining_camp']} on {I['gold']} (2 {I['villager']} on {I['gold']}).",
                f"Train 3 Militia from {I['barracks']} (finish before Feudal arrives!).",
            ],
        ),
        RTSOverlayStep(
            villager_count=click_vils + 4,
            age=2,
            wood=8,
            food=click_vils - 8,
            gold=4,
            stone=0,
            notes=[
                f"In {I['feudal_age']} (+200 {I['wood']} Dravidians bonus!): immediately research Man-at-Arms (50F, 20G) & {I['double_bit_axe']}.",
                f"{I['build']} 1st {I['archery_range']} immediately, then research {I['horse_collar']}.",
                f"Send next 2 {I['villager']} to {I['gold']} (4 on {I['gold']}) and produce continuous Archers + {I['villager']}.",
                f"{I['build']} {I['blacksmith']} -> research Fletching, and seed {I['farm']}s as hunt/sheep decay.",
            ],
        ),
        RTSOverlayStep(
            villager_count=35,
            age=2,
            wood=10,
            food=18,
            gold=7,
            stone=0,
            notes=[
                f"Refresh {I['lumber_camp']} #2 when wood efficiency hits 60% (-1%/15s = 10:00 after LC #1).",
                f"Seed up to 14-18 {I['farm']}s, send 3 more {I['villager']} to {I['gold']} (7 on {I['gold']}), and research Gold Mining.",
                f"Research {I['wheelbarrow']} at TC, then click {I['castle_age']} (800F, 200G) while producing continuous Archers.",
            ],
        ),
        RTSOverlayStep(
            villager_count=35,
            age=3,
            wood=10,
            food=18,
            gold=7,
            stone=0,
            notes=[
                f"During {I['castle_age']} transition: {I['build']} 2nd {I['archery_range']} (-175W) and research Padded Archer Armor (-100F).",
                f"Reach {I['castle_age']} (+200 {I['wood']} Dravidians bonus!) with 19-21 Archers in field.",
                f"Immediately research Crossbowman, Bodkin Arrow, and {I['bow_saw']}, and produce continuous Crossbowmen from 2 {I['archery_range']}s.",
            ],
        ),
    ]

    desc = (
        f"Dravidians {click_vils}-Vil ({click_vils+1} Pop) Man-at-Arms into Archers ({variant_label}), extended through Castle Age. "
        f"Leverages Dravidians +200W per age-up and -50% Barracks tech cost (MAA = 50F, 20G) "
        f"to fund 3 MAA, Double-Bit Axe, Horse Collar, continuous Archer production, Wheelbarrow, and a ~20:00 Castle Age timing with 20 Archers."
    )

    return BuildOrderDocument(
        name=f"Dravidians {click_vils+1} Pop MAA into Archers",
        civilization="Dravidians",
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


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Primary 18-Vil (19 Pop) variants rendered as the 3 top-level HTML tabs
    html_variants = [
        ("deer", "3 Deer Pushed (19 Pop / 18v)", 0, 18, "dravidians_maa_archers_3deer_19pop.json"),
        ("chicken_mill_8", "8 Chickens Milled (19 Pop / 18v)", 8, 18, "dravidians_maa_archers_8chicken_mill_19pop.json"),
        ("chicken_ld_6", "6 Chickens Long-Distance (19 Pop / 18v)", 6, 18, "dravidians_maa_archers_6chicken_ld_19pop.json"),
    ]
    # Also export 19-Vil (20 Pop) RTS Overlay JSON files
    extra_json_variants = [
        ("deer", "3 Deer Pushed (20 Pop / 19v)", 0, 19, "dravidians_maa_archers_3deer_20pop.json"),
        ("chicken_mill_8", "8 Chickens Milled (20 Pop / 19v)", 8, 19, "dravidians_maa_archers_8chicken_mill_20pop.json"),
        ("chicken_ld_6", "6 Chickens Long-Distance (20 Pop / 19v)", 6, 19, "dravidians_maa_archers_6chicken_ld_20pop.json"),
    ]

    docs: List[BuildOrderDocument] = []
    for v_key, v_label, c_cnt, c_vils, json_name in html_variants:
        doc = run_dravidians_maa_variant(v_key, v_label, c_cnt, c_vils)
        docs.append(doc)
        json_path = export_rts_overlay_json(doc, OUT_DIR / json_name)
        print(f"Wrote RTS Overlay JSON: {json_path} ({len(doc.rts_steps)} steps)")
        print(f"  Rot telemetry ({v_label}): {doc.telemetry_summary['rotted_food']} (Total: {doc.telemetry_summary['total_rotted_food']}F)")

    for v_key, v_label, c_cnt, c_vils, json_name in extra_json_variants:
        doc_20 = run_dravidians_maa_variant(v_key, v_label, c_cnt, c_vils)
        json_path = export_rts_overlay_json(doc_20, OUT_DIR / json_name)
        print(f"Wrote RTS Overlay JSON: {json_path} ({len(doc_20.rts_steps)} steps)")

    html_path = export_build_order_html(
        docs,
        title="Dravidians Man-at-Arms into Archers — Build Order Guide (Deer & Chicken Variants)",
        output_path=OUT_DIR / "dravidian_maa_into_archers.html",
    )
    print(f"Wrote HTML report: {html_path}")


if __name__ == "__main__":
    main()

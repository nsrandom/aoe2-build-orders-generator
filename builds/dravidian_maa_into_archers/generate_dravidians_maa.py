#!/usr/bin/env python3
"""
Generator & 1-Second Discrete-Event Simulator for:
Dravidians 20-Pop (19-Vil) 3 MAA -> Archers (7 Chickens Milled on Arabia)
into 3 Castle Age Paths:
  1. 1tc_xbow_lc_ram       : 1 TC -> 2-Range Xbows + 1-Stable Light Cav + 2-4 Armored Elephants (Rams) -> Later TCs
  2. 1tc_xbow_ls_spear_ram : 1 TC -> 2-Range Xbows + 2-Barracks Longswords & Spears/Pikes (~50/50) + 2-4 Armored Elephants -> Later TCs
  3. 3tc_boom_ele_archer   : 3 TC Boom First -> Switch to 2-Range Elephant Archers + 8-10 Light Cav + 2-4 Armored Elephants

Generates:
1. Standalone multi-tab HTML guide (`dravidian_maa_into_archers.html`)
2. RTS Overlay compatible JSON files (`dravidians_maa_*.json`)
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
from sim_dravidians_maa import DravidiansChickenSimulator

OUT_DIR = THIS_DIR


def run_dravidians_path(path_key: str, variant_label: str) -> Tuple[BuildOrderDocument, Dict[str, object]]:
    """
    Runs a 1-second resolution simulation from 00:00 through 35:00 (Castle Age push + expansion)
    with updated boar garrison idling (7 vils x 5s), animal limits, and imperfect execution buffers
    (92% Feudal, 90% Castle). Outputs combined same-resource rows for the first ~20 vils and
    simplified high-level macro blocks for Feudal Age and beyond.
    """
    sim = DravidiansChickenSimulator(path_key=path_key, chicken_count=7)
    planner = BackwardPlanner(sim.db, sim.rules)

    rows: List[DetailedBuildRow] = []
    resource_timeline: List[Dict[str, object]] = []
    milestones: Dict[str, object] = {
        "path_key": path_key,
        "variant": variant_label,
    }

    def current_army_dict() -> Dict[str, int]:
        inf_key = (
            "longsword"
            if "long swordsman" in sim.upgrades
            else ("maa" if "man-at-arms" in sim.upgrades else "militia")
        )
        spear_key = "pikeman" if "pikeman" in sim.upgrades else "spearman"
        arch_key = "crossbow" if "crossbowman" in sim.upgrades else "archer"
        out: Dict[str, int] = {"scout": sim.military_units["scout"]}
        if sim.military_units["militia"] > 0:
            out[inf_key] = sim.military_units["militia"]
        if sim.military_units["spearman"] > 0:
            out[spear_key] = sim.military_units["spearman"]
        if sim.military_units["archer"] > 0:
            out[arch_key] = sim.military_units["archer"]
        if sim.military_units["elephant_archer"] > 0:
            out["elephant_archer"] = sim.military_units["elephant_archer"]
        if sim.military_units["light_cav"] > 0:
            out["light_cav"] = sim.military_units["light_cav"]
        if sim.military_units["armored_elephant"] > 0:
            out["armored_elephant"] = sim.military_units["armored_elephant"]
        return out

    def total_pop() -> int:
        return len(sim.vils) + sum(sim.military_units.values())

    def record_timeline_point() -> None:
        army_d = current_army_dict()
        resource_timeline.append(
            {
                "t": sim.time_s,
                "ts": sim.fmt_time(),
                "food": round(sim.bank.food),
                "wood": round(sim.bank.wood),
                "gold": round(sim.bank.gold),
                "stone": round(sim.bank.stone),
                "vils": len(sim.vils),
                "mil": sum(army_d.values()),
                "army": format_army_counts(army_d),
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
                army_counts=current_army_dict(),
            )
        )
        record_timeline_point()

    # t = 0:00 start
    sim.bank = sim.bank - ResourceBundle(food=50)
    sim.tc_busy_until[0] = 25
    sim.tc_action[0] = "vil_4"

    # Tracking state
    boar1_shot = False
    boar2_lured = False
    boar2_shot = False
    loom_done = False
    feudal_clicked = False
    feudal_click_t = 0
    barracks_ready: List[Optional[int]] = [None, None, None, None]
    rax_busy: List[int] = [0, 0, 0, 0]
    militia_trained = 0
    militia_logged = False
    mc_started = False
    range_ready: List[Optional[int]] = [None, None, None, None, None]
    range_busy: List[int] = [0, 0, 0, 0, 0]
    bs_started = False
    bs_ready_t: Optional[int] = None
    houses_built = 5
    house_busy_until = 0
    wb_started = False
    castle_clicked = False
    castle_click_t = 0
    castle_arrived_t: Optional[int] = None
    lc2_rebuilt = False
    lc3_rebuilt = False

    # Castle & Imperial Age state
    next_vil_id = 20
    stable_ready: List[Optional[int]] = [None, None, None]
    stable_busy: List[int] = [0, 0, 0]
    univ_started = False
    univ_ready_t: Optional[int] = None
    sw_ready: List[Optional[int]] = [None, None]
    sw_busy: List[int] = [0, 0]
    market_ready_t: Optional[int] = None
    tc2_started = False
    tc2_ready_t: Optional[int] = None
    tc3_started = False
    tc3_ready_t: Optional[int] = None

    ele_switch_started = False
    imp_prep_started = False
    imp_prep_t: Optional[int] = None
    imp_clicked = False
    imp_click_t: Optional[int] = None
    imp_arrived_t: Optional[int] = None
    feudal_loop1_logged = False
    castle_loop1_logged = False
    castle_loop2_logged = False
    castle_loop3_logged = False
    imp_loop_logged = False
    push_ready_t: Optional[int] = None
    idle_range_castle_s = 0
    idle_stable_castle_s = 0
    idle_tc_feudal_s = 0
    max_non_save_float: Dict[str, float] = {"food": 0.0, "wood": 0.0, "gold": 0.0}

    max_sim_t = 2400  # 40:00 (must hit Imperial Age < 40:00)
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
            else "Imperial Transition"
            if (sim.age == 3 and imp_clicked)
            else "Imperial Age"
            if sim.age == 4
            else "Castle Age"
        )

        # Boar #1 arrival at 03:25 (t=205): 7 TC vils garrison for 5s to shoot boar down
        if not boar1_shot and t == 205:
            boar1_shot = True
            garr = 0
            for v in sim.vils:
                if v["role"] in ("sheep", "boar") and garr < sim.rules.boar_garrison_vils:
                    v["busy_until"] = max(int(v["busy_until"]), t + int(sim.rules.boar_garrison_seconds))
                    garr += 1
            # Put 6+ vils onto boar if only small food left on active sheep (<= 40F)
            if sim.active_carcass_food["sheep"] <= 40.0:
                kept_one = False
                for v in sim.vils:
                    if v["role"] == "sheep":
                        if not kept_one and sim.active_carcass_food["sheep"] > 5.0:
                            kept_one = True
                        else:
                            v["role"] = "boar"

        # Once active sheep finishes while boar is open/available, remaining shepherd joins boar
        if boar1_shot and sim.active_carcass_food["sheep"] <= 1e-6 and any(v["role"] == "sheep" for v in sim.vils):
            if sim.active_carcass_food["boar"] > 1e-6 or sim.remaining_animals["boar"] > 0:
                boar_cnt = sim.count_role("boar")
                for v in sim.vils:
                    if v["role"] == "sheep":
                        if boar_cnt < 10:
                            v["role"] = "boar"
                            boar_cnt += 1
                        else:
                            v["role"] = "straggler"

        # Boar #2 lure at 04:35 (t=275) -> arrives at 05:05 (t=305)
        if not boar2_lured and t == 275:
            boar2_lured = True
            for v in sim.vils:
                if v["role"] == "boar":
                    v["busy_until"] = t + 30
                    break
        if not boar2_shot and t == 305:
            boar2_shot = True
            garr = 0
            for v in sim.vils:
                if v["role"] in ("sheep", "boar") and garr < sim.rules.boar_garrison_vils:
                    v["busy_until"] = max(int(v["busy_until"]), t + int(sim.rules.boar_garrison_seconds))
                    garr += 1

        # Check TC completions
        for ti in range(sim.tc_count):
            if t == sim.tc_busy_until[ti] and sim.tc_action[ti] != "idle":
                act = sim.tc_action[ti]
                sim.tc_action[ti] = "idle"

                if act.startswith("vil_"):
                    vid = int(act.split("_")[1])
                    if vid in (4, 5, 6):
                        sim.vils.append({"id": vid, "role": "sheep", "busy_until": t})
                        if vid == 6:
                            add_row(
                                "3–6 (4–7)",
                                "00:00 – 01:15",
                                "Dark Age",
                                "Vils #1–#6 (6 vils) -> Build 2 Houses (-50W), then all 6 on Sheep under TC.",
                                "Start 200F, 200W, 100G, 200S. Max 7 on Sheep rule.",
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
                                "Vils #7–#9 (3 vils) -> Wood (1st vil walks 15s + builds Lumber Camp [-100W, 35s], then all 3 on Wood).",
                                "LC completes at 02:30 (100% wood efficiency).",
                            )
                    elif vid == 10:
                        sim.vils.append({"id": vid, "role": "boar", "busy_until": t + 30})
                        add_row(
                            "10 (11)",
                            "02:55",
                            "Dark Age",
                            "Vil #10 -> Lure Boar #1 (15s out + 15s back).",
                            "Boar #1 arrives 03:25 -> garrison 7 TC vils 5s to shoot boar; put 6+ vils on Boar (1 vil finishes ~24F on Sheep #4 then joins Boar).",
                        )
                    elif vid == 11:
                        sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 15})
                        add_row(
                            "11 (12)",
                            "03:20",
                            "Dark Age",
                            "Vil #11 -> Wood at Lumber Camp (15s walk; 4 on Wood).",
                            "",
                        )
                    elif vid == 12:
                        sim.bank = sim.bank - ResourceBundle(wood=125)
                        sim.vils.append({"id": vid, "role": "chicken_mill", "busy_until": t + 80})
                    elif vid in (13, 14, 15):
                        sim.vils.append({"id": vid, "role": "chicken_mill", "busy_until": t + 15})
                        if vid == 15:
                            add_row(
                                "12–15 (13–16)",
                                "03:45 – 05:00",
                                "Dark Age",
                                "Vils #12–#15 (4 vils) -> 7 Chickens (1st vil builds House #3 [-25W] + Mill [-100W], then all 4 on Chickens).",
                                "Milling 7 Chickens (525F) = Dark Age building #2. At 04:35, 1 hunter lures Boar #2 (arrives 05:05; 7 vils garrison 5s to kill).",
                            )
                    elif vid in (16, 17, 18):
                        role_u = "boar" if sim.count_role("boar") < 10 else "sheep"
                        sim.vils.append({"id": vid, "role": role_u, "busy_until": t})
                        if vid == 18:
                            add_row(
                                "16–18 (17–19)",
                                "05:25 – 06:15",
                                "Dark Age",
                                "Vils #16–#18 (3 vils) -> Boar under TC (0s walk; up to 9–10 on Boar during pre-Feudal transition, never opening an extra Sheep early).",
                                "",
                            )
                    elif vid == 19 and sim.age == 1:
                        sim.bank = sim.bank - ResourceBundle(wood=25)
                        sim.vils.append({"id": vid, "role": "gold_ld", "busy_until": t + 45})
                        add_row(
                            "19 (20)",
                            "06:40",
                            "Dark Age",
                            "Vil #19 -> Build House #4 (-25W) -> Long-Distance Gold (15s walk), then queue Loom (-50G, 25s).",
                            "Funds 3 Militia (60G) + Loom (50G) + early Feudal MAA (20G).",
                        )
                    elif sim.age == 2:
                        g_c = sim.count_role("gold", "gold_ld")
                        w_c = sim.count_role("wood")
                        f_c = sim.count_role("farm")
                        if g_c < 4:
                            sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                        elif w_c < 8:
                            sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 15})
                        elif (f_c >= 14 or len(sim.vils) >= 29) and g_c < 7:
                            sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                        else:
                            sim.vils.append({"id": vid, "role": "straggler", "busy_until": t + 3})
                    else:
                        # Castle & Imperial Age villager routing per path
                        g_c = sim.count_role("gold", "gold_ld")
                        w_c = sim.count_role("wood")
                        f_c = sim.count_role("farm")
                        cur_res_w = (275 if (path_key == "3tc_boom_ele_archer" and not tc3_started) else 0) + (200 if (sw_ready[0] is None or not univ_started) else 0)
                        if path_key == "1tc_xbow_lc_ram":
                            t_g, t_w, t_f = 13, 14, 30
                        elif path_key == "1tc_xbow_ls_spear_ram":
                            t_g, t_w, t_f = 13, 15, 32
                        else:  # 3tc_boom_ele_archer
                            t_g, t_w, t_f = 15, (13 if not univ_started else 10), 38

                        if path_key == "3tc_boom_ele_archer" and not ele_switch_started and w_c < 13:
                            sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 15})
                        elif w_c < (13 if not univ_started else t_w):
                            sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 15})
                        elif f_c < 26 and sim.bank.wood >= (60 + cur_res_w):
                            sim.bank = sim.bank - ResourceBundle(wood=60)
                            sim.register_new_farm()
                            sim.vils.append({"id": vid, "role": "farm", "busy_until": t + 20})
                        elif g_c < t_g and f_c >= 17:
                            sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                        elif f_c < t_f and sim.bank.wood >= (60 + cur_res_w):
                            sim.bank = sim.bank - ResourceBundle(wood=60)
                            sim.register_new_farm()
                            sim.vils.append({"id": vid, "role": "farm", "busy_until": t + 20})
                        elif f_c < t_f and sim.straggler_wood > 1e-6 and sim.count_role("straggler") < 2:
                            sim.vils.append({"id": vid, "role": "straggler", "busy_until": t + 3})
                        elif g_c < (t_g + 4):
                            sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                        else:
                            sim.vils.append({"id": vid, "role": "wood", "busy_until": t + 15})

                    if sim.age == 1:
                        if vid < 19:
                            sim.bank = sim.bank - ResourceBundle(food=50)
                            sim.tc_busy_until[0] = t + 25
                            sim.tc_action[0] = f"vil_{vid+1}"
                        else:
                            sim.bank = sim.bank - ResourceBundle(gold=50)
                            sim.tc_busy_until[0] = t + 25
                            sim.tc_action[0] = "loom"

                elif act == "loom":
                    loom_done = True

                elif act == "feudal":
                    sim.age = 2
                    sim.bank = sim.bank + ResourceBundle(wood=200)
                    milestones["feudal_reached_str"] = sim.fmt_time()
                    # Immediate Feudal actions
                    sim.bank = sim.bank - ResourceBundle(food=50)
                    sim.tc_busy_until[0] = t + 25
                    sim.tc_action[0] = f"vil_{next_vil_id}"
                    next_vil_id += 1
                    sim.bank = sim.bank - ResourceBundle(food=50, gold=20)
                    sim.upgrades.add("man-at-arms")
                    sim.bank = sim.bank - ResourceBundle(food=100, wood=50)
                    sim.upgrades.add("double-bit axe")
                    sim.bank = sim.bank - ResourceBundle(wood=175)
                    range_ready[0] = t + 60
                    for v in sim.vils:
                        if v["role"] == "wood" and int(v["busy_until"]) <= t:
                            v["busy_until"] = t + 60
                            break
                    add_row(
                        f"{len(sim.vils)} ({total_pop()})",
                        sim.fmt_time(),
                        "Feudal Age",
                        "REACHED FEUDAL AGE (+200W Dravidians bonus!): Queue Vil, research MAA (-50F, -20G) & Double-Bit Axe (-100F, -50W), build Archery Range #1 (-175W).",
                        f"3 Militia upgrade to 3 MAA. Imperfect execution buffer active (92% Feudal macro efficiency).",
                    )

                elif act == "wheelbarrow":
                    sim.upgrades.add("wheelbarrow")
                    milestones["wheelbarrow_done_str"] = sim.fmt_time()

                elif act == "hand cart":
                    sim.upgrades.add("hand cart")
                    milestones["hand_cart_done_str"] = sim.fmt_time()

                elif act == "castle":
                    sim.age = 3
                    castle_arrived_t = t
                    sim.bank = sim.bank + ResourceBundle(wood=200)
                    milestones["castle_reached_s"] = t
                    milestones["castle_reached_str"] = sim.fmt_time()
                    milestones["castle_arrival_vils"] = len(sim.vils)
                    milestones["castle_arrival_archers"] = sim.military_units["archer"]
                    milestones["castle_arrival_bank"] = sim.bank.to_dict()
                    # Log end of Castle Transition right before Castle Age starts
                    add_row(
                        f"{len(sim.vils)} ({total_pop()})",
                        f"{sim.fmt_time(castle_click_t)} – {sim.fmt_time()}",
                        "Castle Transition",
                        "CLICK CASTLE AGE (-800F, -200G, 160s): Build Archery Range #2 (-175W) & Padded Archer Armor (-100F); produce Archers continuously from 2 Ranges (save 200G in final 45s).",
                        f"Macro transition complete -> arrives Castle Age with {sim.military_units['archer']} Archers + 3 MAA.",
                    )

                elif act == "imperial":
                    sim.age = 4
                    imp_arrived_t = t
                    sim.bank = sim.bank + ResourceBundle(wood=200)
                    milestones["imp_reached_s"] = t
                    milestones["imp_reached_str"] = sim.fmt_time()
                    milestones["imp_reached_vils"] = len(sim.vils)
                    milestones["imp_reached_army"] = current_army_dict()
                    add_row(
                        f"{len(sim.vils)} ({total_pop()})",
                        f"{sim.fmt_time(imp_click_t or t)} – {sim.fmt_time()}",
                        "Imperial Transition",
                        "CLICK IMPERIAL AGE (-1000F, -800G, 190s): Resume all production buildings, finish Ballistics/Thumb Ring/Hand Cart/Armor & extra TCs while maintaining <500–1000 resource float.",
                        f"Imperial click to arrival: {format_army_counts(current_army_dict())}.",
                    )

        # Complete TC #2 / TC #3
        if tc2_ready_t is not None and t == tc2_ready_t:
            tc2_ready_t = None
            sim.tc_count = 2
            milestones["tc2_ready_str"] = sim.fmt_time()
        if tc3_ready_t is not None and t == tc3_ready_t:
            tc3_ready_t = None
            sim.tc_count = 3
            milestones["tc3_ready_str"] = sim.fmt_time()

        # Click Feudal Age as soon as Loom completes
        if loom_done and not feudal_clicked and sim.tc_action[0] == "idle" and sim.bank.food >= 500:
            loom_done_t = (19 - 3) * 25 + 25
            idle_wait_s = max(0, t - loom_done_t)
            milestones["feudal_click_str"] = sim.fmt_time()
            milestones["feudal_click_idle_s"] = idle_wait_s
            sim.bank = sim.bank - ResourceBundle(food=500)
            sim.tc_busy_until[0] = t + 130
            sim.tc_action[0] = "feudal"
            feudal_clicked = True
            feudal_click_t = t
            # Transition: 1st vil builds Barracks (-175W) -> House #5 (-25W) -> Wood; 2 more vils -> Wood
            sim.bank = sim.bank - ResourceBundle(wood=200)
            barracks_ready[0] = t + 60
            moved = 0
            for v in sim.vils:
                if v["role"] in ("boar", "sheep") and int(v["busy_until"]) <= t:
                    if moved == 0:
                        v["role"] = "wood"
                        v["busy_until"] = t + 95
                        moved += 1
                    elif moved <= 3:
                        v["role"] = "wood"
                        v["busy_until"] = t + 15
                        moved += 1
            add_row(
                f"{len(sim.vils)} ({total_pop()})",
                sim.fmt_time(),
                "Feudal Transition",
                f"CLICK FEUDAL AGE (-500F, 130s, {idle_wait_s}s idle): Move 3 food vils to Wood (1st builds Barracks [-175W] -> House #5 [-25W], all 3 to Wood = 7 on Wood).",
                "Sequential building rule (0s walk between Barracks & House #5). Up to 10 vils allowed on Boar in transition.",
            )

        # Build Mining Camp on Gold (~45s after clicking Feudal)
        if feudal_clicked and not mc_started and sim.bank.wood >= 100 and t >= feudal_click_t + 45:
            mc_started = True
            sim.bank = sim.bank - ResourceBundle(wood=100)
            for v in sim.vils:
                if v["role"] == "gold_ld":
                    v["role"] = "gold"
                    v["busy_until"] = t + 35
            for v in sim.vils:
                if v["role"] in ("boar", "sheep", "chicken_mill") and int(v["busy_until"]) <= t:
                    v["role"] = "gold"
                    v["busy_until"] = t + 50
                    break
            add_row(
                f"{len(sim.vils)} ({total_pop()})",
                sim.fmt_time(),
                "Feudal Transition",
                "Build Mining Camp on Gold (-100W, 35s) & send 2nd vil to Gold (2 on Gold).",
                "Ensures 20G for MAA + smooth Gold flow for 1-Range Archers.",
            )

        # Train 3 Militia during Feudal Transition
        if barracks_ready[0] is not None and t >= barracks_ready[0] and militia_trained < 3 and t >= rax_busy[0]:
            if sim.bank.food >= 50 and sim.bank.gold >= 20:
                sim.bank = sim.bank - ResourceBundle(food=50, gold=20)
                militia_trained += 1
                rax_busy[0] = t + 21
                sim.military_units["militia"] += 1
        if militia_trained == 3 and not militia_logged:
            militia_logged = True
            add_row(
                f"{len(sim.vils)} ({total_pop()})",
                f"{sim.fmt_time((barracks_ready[0] or t))} – {sim.fmt_time()}",
                "Feudal Transition",
                "Train 3 Militia at Barracks (-150F, -60G total; 21s each) & march forward.",
                "All 3 Militia finish before Feudal Age arrives at 09:15.",
            )

        # Feudal Age TC management
        if sim.age == 2 and sim.tc_action[0] == "idle" and not castle_clicked:
            if sim.bank.food >= 800 and sim.bank.gold >= 200 and bs_ready_t is not None and t >= bs_ready_t:
                castle_clicked = True
                castle_click_t = t
                milestones["castle_click_s"] = t
                milestones["castle_click_str"] = sim.fmt_time()
                milestones["castle_click_vils"] = len(sim.vils)
                milestones["castle_click_archers"] = sim.military_units["archer"]
                sim.bank = sim.bank - ResourceBundle(food=800, gold=200)
                sim.tc_busy_until[0] = t + 160
                sim.tc_action[0] = "castle"
                add_row(
                    f"{len(sim.vils)} ({total_pop()})",
                    f"{sim.fmt_time(feudal_loop1_start_t)} – {sim.fmt_time()}",
                    "Feudal Age",
                    "Macro Loop 2 — Scale Eco to Castle Age: Continuous Vils -> Stragglers & seed Farms every 60W (up to 17 Farms), add 3 to Gold (7 on Gold) + Gold Mining (-100F, -75W), refresh Lumber Camp #2 (-100W at ~65% eff.), produce 1-Range Archers & Houses, then Wheelbarrow (-175F, -50W) -> click Castle Age (800F, 200G).",
                    f"Clicked Castle Age at {sim.fmt_time()} with {len(sim.vils)} vils & {sim.military_units['archer']} Archers.",
                )
            elif not wb_started and len(sim.vils) >= 32 and sim.count_role("farm") >= 14 and sim.bank.food >= 175 and sim.bank.wood >= 50:
                wb_started = True
                sim.bank = sim.bank - ResourceBundle(food=175, wood=50)
                sim.tc_busy_until[0] = t + 75
                sim.tc_action[0] = "wheelbarrow"
            elif not (wb_started and sim.bank.food >= 680 and sim.bank.gold >= 165) and sim.bank.food >= 50:
                sim.bank = sim.bank - ResourceBundle(food=50)
                sim.tc_busy_until[0] = t + 25
                sim.tc_action[0] = f"vil_{next_vil_id}"
                next_vil_id += 1
            else:
                idle_tc_feudal_s += 1

        # Feudal Age eco & military buildings/upgrades
        tc_f_res = 50 if (sim.tc_busy_until[0] - t) <= 10 else 0
        if sim.age == 2 and "horse collar" not in sim.upgrades and sim.bank.food >= (75 + tc_f_res) and sim.bank.wood >= 75:
            sim.bank = sim.bank - ResourceBundle(food=75, wood=75)
            sim.upgrades.add("horse collar")

        if sim.age == 2 and not bs_started and sim.bank.wood >= 150 and t >= (range_ready[0] or 9999):
            bs_started = True
            sim.bank = sim.bank - ResourceBundle(wood=150)
            bs_ready_t = t + 50

        if bs_ready_t is not None and t >= bs_ready_t and "fletching" not in sim.upgrades and sim.bank.food >= (100 + tc_f_res) and sim.bank.gold >= 50:
            sim.bank = sim.bank - ResourceBundle(food=100, gold=50)
            sim.upgrades.add("fletching")
            milestones["fletching_str"] = sim.fmt_time()

        if sim.age == 2 and "fletching" in sim.upgrades and "gold mining" not in sim.upgrades and sim.count_role("gold", "gold_ld") >= 6 and sim.bank.food >= (100 + tc_f_res) and sim.bank.wood >= 75:
            sim.bank = sim.bank - ResourceBundle(food=100, wood=75)
            sim.upgrades.add("gold mining")

        # Log Feudal Macro Loop 1 once we reach ~29 vils & ~10 Farms
        if sim.age == 2 and not feudal_loop1_logged and len(sim.vils) >= 29 and "fletching" in sim.upgrades:
            feudal_loop1_logged = True
            feudal_loop1_start_t = t
            add_row(
                f"20–{len(sim.vils)} ({total_pop()})",
                f"09:40 – {sim.fmt_time()}",
                "Feudal Age",
                "Macro Loop 1 — Setup Archers & Blacksmith: Continuous Vils -> Gold to 4, then Wood to 8; research Horse Collar (-75F, -75W), build Blacksmith (-150W) -> Fletching (-100F, -50G); produce Archers continuously from 1 Range; finishing food vils go to Stragglers & seed Farms every 60W (up to ~10 Farms).",
                "Simple priority rule: never idle TC or Range #1; spare Wood goes into Farms.",
            )

        if castle_clicked and range_ready[1] is None and sim.bank.wood >= 175:
            sim.bank = sim.bank - ResourceBundle(wood=175)
            range_ready[1] = t + 60
        if castle_clicked and "padded archer armor" not in sim.upgrades and sim.bank.food >= 150:
            sim.bank = sim.bank - ResourceBundle(food=100)
            sim.upgrades.add("padded archer armor")

        # Refresh Lumber Camp #2 / #3 when wood efficiency drops to 65%
        if sim.age >= 2 and not lc2_rebuilt and sim.farms_seeded >= 3 and sim.wood_efficiency() <= 0.65 and sim.bank.wood >= 100:
            lc2_rebuilt = True
            sim.bank = sim.bank - ResourceBundle(wood=100)
            sim.lc_completed_s = t + 35
            sim.lc_count = 2
            milestones["lc2_rebuilt_str"] = sim.fmt_time()
        if sim.age >= 3 and not lc3_rebuilt and sim.wood_efficiency() <= 0.65 and sim.bank.wood >= 100:
            lc3_rebuilt = True
            sim.bank = sim.bank - ResourceBundle(wood=100)
            sim.lc_completed_s = t + 35
            sim.lc_count = 3

        # Castle & Imperial Age logic
        if sim.age >= 3:
            total_army = sum(sim.military_units.values())
            saving_for_imp = imp_prep_started and not imp_clicked

            # Core Castle Age arrival upgrades
            if "crossbowman" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=175, gold=100)):
                sim.bank = sim.bank - ResourceBundle(food=175, gold=100)
                sim.upgrades.add("crossbowman")
            if "bodkin arrow" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=200, gold=100)):
                sim.bank = sim.bank - ResourceBundle(food=200, gold=100)
                sim.upgrades.add("bodkin arrow")
            if "bow saw" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=150, wood=100)):
                sim.bank = sim.bank - ResourceBundle(food=150, wood=100)
                sim.upgrades.add("bow saw")

            if (
                "crossbowman" in sim.upgrades
                and "bodkin arrow" in sim.upgrades
                and "bow saw" in sim.upgrades
                and "castle_spike_logged" not in milestones
            ):
                milestones["castle_spike_logged"] = True
                milestones["xbow_bodkin_bowsaw_str"] = sim.fmt_time()
                if path_key == "3tc_boom_ele_archer":
                    spike_txt = "REACHED CASTLE AGE (+200W): Research Crossbowman (-175F, -100G), Bodkin Arrow (-200F, -100G), Bow Saw (-150F, -100W); pause Range production briefly and drop TC #2 & TC #3 (-275W, -100S each) immediately."
                else:
                    spike_txt = "REACHED CASTLE AGE (+200W): Research Crossbowman (-175F, -100G), Bodkin Arrow (-200F, -100G), Bow Saw (-150F, -100W); keep 1 TC & 2-Range Xbows continuous."
                add_row(
                    f"{len(sim.vils)} ({total_pop()})",
                    sim.fmt_time(),
                    "Castle Age",
                    spike_txt,
                    "90% Castle macro buffer active. Dravidians +200W bonus funds Bow Saw + buildings immediately.",
                )

            # TC queues in Castle & Imperial Age (TC #1 prioritizes Imperial Click once 50+ army & 2 Castle buildings ready)
            vil_cap = 84 if path_key == "3tc_boom_ele_archer" else 76
            imp_prereq_ready = (
                sw_ready[0] is not None
                and t >= sw_ready[0]
                and univ_ready_t is not None
                and t >= univ_ready_t
            )
            hold_tc_for_imp = saving_for_imp and len(sim.vils) >= 62 and sim.bank.food < 1000
            for ti in range(sim.tc_count):
                if sim.tc_action[ti] == "idle":
                    if (
                        ti == 0
                        and sim.age == 3
                        and not imp_clicked
                        and imp_prep_started
                        and imp_prereq_ready
                        and sim.bank.food >= 1000
                        and sim.bank.gold >= 800
                    ):
                        imp_clicked = True
                        imp_click_t = t
                        milestones["imp_click_s"] = t
                        milestones["imp_click_str"] = sim.fmt_time()
                        milestones["imp_click_vils"] = len(sim.vils)
                        milestones["imp_click_army"] = current_army_dict()
                        sim.bank = sim.bank - ResourceBundle(food=1000, gold=800)
                        sim.tc_busy_until[ti] = t + 190
                        sim.tc_action[ti] = "imperial"
                        saving_for_imp = False
                    elif (
                        ti == 0
                        and not hold_tc_for_imp
                        and "hc_started" not in sim.upgrades
                        and len(sim.vils) >= 48
                        and (path_key == "3tc_boom_ele_archer" or not saving_for_imp)
                        and sim.bank.food >= 300
                        and sim.bank.wood >= 200
                    ):
                        sim.upgrades.add("hc_started")
                        sim.bank = sim.bank - ResourceBundle(food=300, wood=200)
                        sim.tc_busy_until[ti] = t + 55
                        sim.tc_action[ti] = "hand cart"
                    elif not hold_tc_for_imp and sim.bank.food >= 50 and len(sim.vils) < vil_cap:
                        sim.bank = sim.bank - ResourceBundle(food=50)
                        sim.tc_busy_until[ti] = t + 25
                        sim.tc_action[ti] = f"vil_{next_vil_id}"
                        next_vil_id += 1
                    elif ti == 0 and len(sim.vils) < vil_cap and not hold_tc_for_imp:
                        sim.tc1_idle_castle_s += 1

            # Path-specific buildings & upgrades once core 3 Castle techs are clicked
            ranged_cnt = sim.military_units["archer"] + sim.military_units["elephant_archer"]
            ballistics_prio = (
                sim.age >= 3
                and "crossbowman" in sim.upgrades
                and ranged_cnt >= 20
                and "ballistics" not in sim.upgrades
                and not imp_prep_started
                and (path_key != "3tc_boom_ele_archer" or (tc3_started and ele_switch_started))
            )
            if "crossbowman" in sim.upgrades and "bodkin arrow" in sim.upgrades and "bow saw" in sim.upgrades:
                sw_started = sw_ready[0] is not None
                stable_started = stable_ready[0] is not None
                hp_ok = (path_key != "3tc_boom_ele_archer") or tc3_started
                if hp_ok and not saving_for_imp and not (ballistics_prio and univ_started) and "heavy plow" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=125, wood=125)):
                    sim.bank = sim.bank - ResourceBundle(food=125, wood=125)
                    sim.upgrades.add("heavy plow")

                # Shared rule: at 20+ ranged units, prioritize University + Ballistics ahead of extra production/secondary techs
                if (ballistics_prio or sw_started) and not univ_started and sim.bank.wood >= 200:
                    univ_started = True
                    sim.bank = sim.bank - ResourceBundle(wood=200)
                    univ_ready_t = t + 60
                if univ_ready_t and t >= univ_ready_t and not saving_for_imp and "ballistics" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(wood=300, gold=175)):
                    sim.bank = sim.bank - ResourceBundle(wood=300, gold=175)
                    sim.upgrades.add("ballistics")
                    milestones["ballistics_str"] = sim.fmt_time()

                def count_built(slots: List[Optional[int]]) -> int:
                    return sum(1 for x in slots if x is not None)

                def add_prod_building(slots: List[Optional[int]], cost_w: int = 175, build_s: int = 60) -> bool:
                    for idx_b in range(len(slots)):
                        if slots[idx_b] is None and sim.bank.wood >= cost_w:
                            sim.bank = sim.bank - ResourceBundle(wood=cost_w)
                            slots[idx_b] = t + build_s
                            return True
                    return False

                if path_key == "1tc_xbow_lc_ram":
                    if not stable_started and sim.bank.wood >= 175:
                        add_prod_building(stable_ready, 175, 60)
                    if not saving_for_imp and not (ballistics_prio and univ_started):
                        if stable_ready[0] and t >= stable_ready[0] and "light cavalry" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=150, gold=50)):
                            sim.bank = sim.bank - ResourceBundle(food=150, gold=50)
                            sim.upgrades.add("light cavalry")
                        if "leather archer armor" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=150, gold=150)):
                            sim.bank = sim.bank - ResourceBundle(food=150, gold=150)
                            sim.upgrades.add("leather archer armor")
                        if "scale barding armor" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=150)):
                            sim.bank = sim.bank - ResourceBundle(food=150)
                            sim.upgrades.add("scale barding armor")
                        if "forging" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=150)):
                            sim.bank = sim.bank - ResourceBundle(food=150)
                            sim.upgrades.add("forging")
                    # Prioritize Siege Workshop + Ballistics, then scale extra Ranges/Stables
                    if not sw_started and sim.military_units["archer"] >= 20 and not (ballistics_prio and not univ_started) and sim.bank.wood >= 200:
                        add_prod_building(sw_ready, 200, 50)
                        milestones["sw_ready_str"] = sim.fmt_time(t + 50)
                        if not castle_loop1_logged:
                            castle_loop1_logged = True
                            add_row(
                                f"{len(sim.vils)} ({total_pop()})",
                                f"{sim.fmt_time(castle_arrived_t)} – {sim.fmt_time()}",
                                "Castle Age",
                                "Macro Loop 1 — 1-TC Fast Army Ramp: Build Stable (-175W) + Heavy Plow; Vils -> Farms to 26–30, Gold to 14–15, Wood to 13–14; at 20+ Xbows prioritize University (-200W) -> Ballistics (-300W, -175G) + Siege Workshop (-200W), then scale Ranges (#3–#4) & Stable (#2) to hit 50+ army fast.",
                                "Prioritizes Ballistics at 20+ Xbows and spends surplus Wood on extra Ranges.",
                            )
                    if sw_started and univ_started and not saving_for_imp and not ballistics_prio:
                        if count_built(range_ready) < (5 if imp_clicked else 4) and sim.bank.wood >= 275:
                            add_prod_building(range_ready, 175, 60)
                        elif count_built(stable_ready) < 2 and sim.bank.wood >= 275:
                            add_prod_building(stable_ready, 175, 60)
                    if not ballistics_prio and (imp_prep_started or (sw_started and univ_started and sim.bank.wood >= 450)) and not tc2_started and sim.bank.wood >= 275 and sim.bank.stone >= 100:
                        tc2_started = True
                        sim.bank = sim.bank - ResourceBundle(wood=275, stone=100)
                        tc2_ready_t = t + 100
                        milestones["tc2_str"] = sim.fmt_time()
                    if tc2_started and not tc3_started and sim.bank.wood >= 275 and sim.bank.stone >= 100:
                        tc3_started = True
                        sim.bank = sim.bank - ResourceBundle(wood=275, stone=100)
                        tc3_ready_t = t + 100
                        milestones["tc3_str"] = sim.fmt_time()
                        if not castle_loop3_logged:
                            castle_loop3_logged = True
                            add_row(
                                f"{len(sim.vils)} ({total_pop()})",
                                sim.fmt_time(),
                                current_phase,
                                "Late TCs Expansion: Add TC #2 & TC #3 (-275W, -100S each using starting 200S) -> scale Farms (30+) & Gold (15+) into Imperial.",
                                "Dravidians starting 200 Stone funds both extra TCs with zero Stone mining.",
                            )

                elif path_key == "1tc_xbow_ls_spear_ram":
                    if barracks_ready[1] is None and sim.bank.wood >= 175:
                        add_prod_building(barracks_ready, 175, 60)
                    if not saving_for_imp and not (ballistics_prio and univ_started):
                        if "long swordsman" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=75, gold=32.5)):
                            sim.bank = sim.bank - ResourceBundle(food=75, gold=32.5)
                            sim.upgrades.add("long swordsman")
                        if "pikeman" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=80, gold=45)):
                            sim.bank = sim.bank - ResourceBundle(food=80, gold=45)
                            sim.upgrades.add("pikeman")
                        if "squires" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=50)):
                            sim.bank = sim.bank - ResourceBundle(food=50)
                            sim.upgrades.add("squires")
                        if "scale mail armor" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=100)):
                            sim.bank = sim.bank - ResourceBundle(food=100)
                            sim.upgrades.add("scale mail armor")
                        if "forging" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=150)):
                            sim.bank = sim.bank - ResourceBundle(food=150)
                            sim.upgrades.add("forging")
                        if "leather archer armor" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=150, gold=150)):
                            sim.bank = sim.bank - ResourceBundle(food=150, gold=150)
                            sim.upgrades.add("leather archer armor")
                    inf_tot = sim.military_units["militia"] + sim.military_units["spearman"]
                    if not sw_started and inf_tot >= 8 and not (ballistics_prio and not univ_started) and sim.bank.wood >= 200:
                        add_prod_building(sw_ready, 200, 50)
                        milestones["sw_ready_str"] = sim.fmt_time(t + 50)
                        if not castle_loop1_logged:
                            castle_loop1_logged = True
                            add_row(
                                f"{len(sim.vils)} ({total_pop()})",
                                f"{sim.fmt_time(castle_arrived_t)} – {sim.fmt_time()}",
                                "Castle Age",
                                "Macro Loop 1 — 1-TC 2-Rax Infantry + Xbows Ramp: Build Barracks #2 (-175W) + Heavy Plow; at 20+ Xbows prioritize University (-200W) -> Ballistics (-300W, -175G) + Siege Workshop (-200W); get -50% Long Swordsman, Pikeman, Squires, Scale Mail, Forging & Leather Armor; add Range #3/Rax #3 on spare Wood until 50+ army.",
                                "Prioritizes Ballistics at 20+ Xbows; -50% Barracks tech discount + extra Ranges/Rax prevent float.",
                            )
                    if sw_started and univ_started and not saving_for_imp and not ballistics_prio:
                        if count_built(range_ready) < (5 if imp_clicked else 4) and sim.bank.wood >= 275:
                            add_prod_building(range_ready, 175, 60)
                        elif count_built(barracks_ready) < (4 if imp_clicked else 3) and sim.bank.wood >= 275:
                            add_prod_building(barracks_ready, 175, 60)
                    if not ballistics_prio and (imp_prep_started or (sw_started and univ_started and sim.bank.wood >= 450)) and not tc2_started and sim.bank.wood >= 275 and sim.bank.stone >= 100:
                        tc2_started = True
                        sim.bank = sim.bank - ResourceBundle(wood=275, stone=100)
                        tc2_ready_t = t + 100
                        milestones["tc2_str"] = sim.fmt_time()
                    if tc2_started and not tc3_started and sim.bank.wood >= 275 and sim.bank.stone >= 100:
                        tc3_started = True
                        sim.bank = sim.bank - ResourceBundle(wood=275, stone=100)
                        tc3_ready_t = t + 100
                        milestones["tc3_str"] = sim.fmt_time()
                        if not castle_loop3_logged:
                            castle_loop3_logged = True
                            add_row(
                                f"{len(sim.vils)} ({total_pop()})",
                                sim.fmt_time(),
                                current_phase,
                                "Late TCs Expansion: Add TC #2 & TC #3 (-275W, -100S each) -> scale Farms (32+) & Gold (15+) into Imperial.",
                                "Dravidians starting 200 Stone funds both extra TCs.",
                            )

                elif path_key == "3tc_boom_ele_archer":
                    if not tc2_started and sim.bank.wood >= 275 and sim.bank.stone >= 100:
                        tc2_started = True
                        sim.bank = sim.bank - ResourceBundle(wood=275, stone=100)
                        tc2_ready_t = t + 100
                        milestones["tc2_str"] = sim.fmt_time()
                    if tc2_started and not tc3_started and sim.bank.wood >= 275 and sim.bank.stone >= 100:
                        tc3_started = True
                        sim.bank = sim.bank - ResourceBundle(wood=275, stone=100)
                        tc3_ready_t = t + 100
                        milestones["tc3_str"] = sim.fmt_time()
                    if not ele_switch_started and tc3_started and len(sim.vils) >= 48:
                        ele_switch_started = True
                        milestones["ele_switch_str"] = sim.fmt_time()
                        if not castle_loop1_logged:
                            castle_loop1_logged = True
                            add_row(
                                f"{len(sim.vils)} ({total_pop()})",
                                f"{sim.fmt_time(castle_arrived_t)} – {sim.fmt_time()}",
                                "Castle Age",
                                "Macro Loop 1 — 3-TC Eco Boom: Continuous Vils across 3 TCs -> Farms to 28+ (Heavy Plow), Gold to 16–20, Wood to 14; research Hand Cart (-300F, -200W) at ~48 vils.",
                                "Defend with 18 Xbows + 3 MAA while 3 TCs rapidly scale to ~49 vils.",
                            )
                    if ele_switch_started:
                        if not stable_started and sim.bank.wood >= 175:
                            add_prod_building(stable_ready, 175, 60)
                        if not saving_for_imp and not (ballistics_prio and univ_started):
                            if stable_ready[0] and t >= stable_ready[0] and "light cavalry" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=150, gold=50)):
                                sim.bank = sim.bank - ResourceBundle(food=150, gold=50)
                                sim.upgrades.add("light cavalry")
                            if "leather archer armor" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=150, gold=150)):
                                sim.bank = sim.bank - ResourceBundle(food=150, gold=150)
                                sim.upgrades.add("leather archer armor")
                            if "scale barding armor" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=150)):
                                sim.bank = sim.bank - ResourceBundle(food=150)
                                sim.upgrades.add("scale barding armor")
                            if "husbandry" not in sim.upgrades and stable_ready[0] and sim.bank.can_afford(ResourceBundle(food=150)):
                                sim.bank = sim.bank - ResourceBundle(food=150)
                                sim.upgrades.add("husbandry")
                        if not sw_started and sim.military_units["elephant_archer"] >= 4 and not (ballistics_prio and not univ_started) and sim.bank.wood >= 200:
                            add_prod_building(sw_ready, 200, 50)
                            milestones["sw_ready_str"] = sim.fmt_time(t + 50)
                            if not castle_loop2_logged:
                                castle_loop2_logged = True
                                add_row(
                                    f"{len(sim.vils)} ({total_pop()})",
                                    f"{milestones['ele_switch_str']} – {sim.fmt_time()}",
                                    "Castle Age",
                                    "Macro Loop 2 — Multi-Range Elephant Archers + Light Cav Switch: Zero-stall Elephant Archers, add Stable (-175W) + University (-200W) -> Ballistics (-300W, -175G) at 20+ ranged, Siege Workshop (-200W), scale Ranges (#3–#4) & Stable (#2) on spare Wood & Thumb Ring until 50+ army.",
                                    "After 3-TC boom, Ballistics triggers first at 20+ ranged, then extra Ranges.",
                                )
                        if sw_started and univ_started and not saving_for_imp and not ballistics_prio and len(sim.vils) >= 58:
                            if count_built(range_ready) < (5 if imp_clicked else 4) and sim.bank.wood >= 275 and sim.bank.food >= 200:
                                add_prod_building(range_ready, 175, 60)
                            elif len(sim.vils) >= 64 and count_built(stable_ready) < 2 and sim.bank.wood >= 275 and sim.bank.food >= 200:
                                add_prod_building(stable_ready, 175, 60)
                        if sw_started and not saving_for_imp and not ballistics_prio and "thumb ring" not in sim.upgrades and sim.military_units["elephant_archer"] >= 6 and sim.bank.can_afford(ResourceBundle(food=300, wood=250)):
                            sim.bank = sim.bank - ResourceBundle(food=300, wood=250)
                            sim.upgrades.add("thumb ring")
                            milestones["thumb_ring_str"] = sim.fmt_time()

                # Trigger shift to Imperial Age priority once 50+ army & Siege Workshop exist
                if (
                    sim.age == 3
                    and not imp_prep_started
                    and total_army >= 50
                    and sw_ready[0] is not None
                    and sim.military_units["armored_elephant"] >= 2
                ):
                    imp_prep_started = True
                    imp_prep_t = t
                    milestones["army50_str"] = sim.fmt_time()
                    milestones["army50_vils"] = len(sim.vils)
                    milestones["army50_army"] = current_army_dict()
                    add_row(
                        f"{len(sim.vils)} ({total_pop()})",
                        sim.fmt_time(),
                        "Castle Age",
                        "50+ Army Hit -> Shift Priority to Imperial Age: Pause extra military queues as needed to bank 1000F + 800G; ensure Siege Workshop & University are up, then click Imperial Age (<40:00 goal).",
                        f"Army at shift: {format_army_counts(current_army_dict())}. Idling extra military buildings briefly to hit fast Imp.",
                    )

                # During Imperial Transition & Imperial Age: add SW #2 if floating Wood, plus late Castle / Imperial upgrades
                if imp_clicked or sim.age == 4:
                    if count_built(sw_ready) < 2 and sim.bank.wood >= 450:
                        add_prod_building(sw_ready, 200, 50)
                    if "chain barding armor" not in sim.upgrades and path_key in ("1tc_xbow_lc_ram", "3tc_boom_ele_archer") and sim.bank.can_afford(ResourceBundle(food=250, gold=150)):
                        sim.bank = sim.bank - ResourceBundle(food=250, gold=150)
                        sim.upgrades.add("chain barding armor")
                    if "iron casting" not in sim.upgrades and path_key in ("1tc_xbow_lc_ram", "1tc_xbow_ls_spear_ram") and sim.bank.can_afford(ResourceBundle(food=220, gold=120)):
                        sim.bank = sim.bank - ResourceBundle(food=220, gold=120)
                        sim.upgrades.add("iron casting")
                    if "chain mail armor" not in sim.upgrades and path_key == "1tc_xbow_ls_spear_ram" and sim.bank.can_afford(ResourceBundle(food=200, gold=100)):
                        sim.bank = sim.bank - ResourceBundle(food=200, gold=100)
                        sim.upgrades.add("chain mail armor")

                if sim.age == 4:
                    if not imp_loop_logged:
                        imp_loop_logged = True
                        add_row(
                            f"{len(sim.vils)} ({total_pop()})",
                            sim.fmt_time(),
                            "Imperial Age",
                            "REACHED IMPERIAL AGE (+200W Dravidians bonus!): Research Imperial unit/Blacksmith power spikes (Arbalester/Elite Ele Archer, Bracer, Chemistry, Siege Elephant, Champion/Halberdier on Path 2) and keep spending resources (<500–1000 float) on 4–5 Ranges/Stables/Rax + Armored/Siege Elephants.",
                            f"Imperial reached well before 40:00 at {sim.fmt_time()} with {len(sim.vils)} vils.",
                        )
                    if path_key in ("1tc_xbow_lc_ram", "1tc_xbow_ls_spear_ram") and "arbalester" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=450, gold=350)):
                        sim.bank = sim.bank - ResourceBundle(food=450, gold=350)
                        sim.upgrades.add("arbalester")
                        milestones["imp_main_unit_upg_str"] = sim.fmt_time()
                    if path_key == "3tc_boom_ele_archer" and "elite elephant archer" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=900, gold=500)):
                        sim.bank = sim.bank - ResourceBundle(food=900, gold=500)
                        sim.upgrades.add("elite elephant archer")
                        milestones["imp_main_unit_upg_str"] = sim.fmt_time()
                    if "bracer" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=300, gold=200)):
                        sim.bank = sim.bank - ResourceBundle(food=300, gold=200)
                        sim.upgrades.add("bracer")
                        milestones["bracer_str"] = sim.fmt_time()
                    if "chemistry" not in sim.upgrades and univ_ready_t and t >= univ_ready_t and sim.bank.can_afford(ResourceBundle(food=300, gold=200)):
                        sim.bank = sim.bank - ResourceBundle(food=300, gold=200)
                        sim.upgrades.add("chemistry")
                        milestones["chemistry_str"] = sim.fmt_time()
                    if "ring archer armor" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=250, gold=250)):
                        sim.bank = sim.bank - ResourceBundle(food=250, gold=250)
                        sim.upgrades.add("ring archer armor")
                    if path_key == "1tc_xbow_ls_spear_ram":
                        if "two-handed swordsman" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=100, gold=50)):
                            sim.bank = sim.bank - ResourceBundle(food=100, gold=50)
                            sim.upgrades.add("two-handed swordsman")
                        if "two-handed swordsman" in sim.upgrades and "champion" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=325, gold=175)):
                            sim.bank = sim.bank - ResourceBundle(food=325, gold=175)
                            sim.upgrades.add("champion")
                        if "halberdier" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=150, gold=300)):
                            sim.bank = sim.bank - ResourceBundle(food=150, gold=300)
                            sim.upgrades.add("halberdier")
                        if "plate mail armor" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=300, gold=150)):
                            sim.bank = sim.bank - ResourceBundle(food=300, gold=150)
                            sim.upgrades.add("plate mail armor")
                        if "blast furnace" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=275, gold=225)):
                            sim.bank = sim.bank - ResourceBundle(food=275, gold=225)
                            sim.upgrades.add("blast furnace")
                    if "siege elephant" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=850)):
                        sim.bank = sim.bank - ResourceBundle(food=850)
                        sim.upgrades.add("siege elephant")
                        milestones["siege_ele_str"] = sim.fmt_time()
                    if "two-man saw" not in sim.upgrades and sim.bank.can_afford(ResourceBundle(food=300, wood=200)):
                        sim.bank = sim.bank - ResourceBundle(food=300, wood=200)
                        sim.upgrades.add("two-man saw")

        # Build Houses ahead of pop cap
        cur_pop = total_pop()
        pop_cap = 5 + houses_built * 5
        if sim.age >= 2 and cur_pop + 4 >= pop_cap and t >= house_busy_until and sim.bank.wood >= 25:
            houses_built += 1
            house_busy_until = t + 35
            sim.bank = sim.bank - ResourceBundle(wood=25)
            for v in sim.vils:
                if v["role"] in ("wood", "straggler") and int(v["busy_until"]) <= t:
                    v["busy_until"] = t + 35
                    break

        # Range production (1 in Feudal, 2 in Castle Transition, up to 5 Ranges in Castle/Imperial)
        hold_mil_for_imp = (imp_prep_started and not imp_clicked)
        ranged_now = sim.military_units["archer"] + sim.military_units["elephant_archer"]
        ballistics_res_now = (
            sim.age >= 3
            and "crossbowman" in sim.upgrades
            and ranged_now >= 20
            and "ballistics" not in sim.upgrades
            and not imp_prep_started
            and (path_key != "3tc_boom_ele_archer" or (tc3_started and ele_switch_started))
        )
        bal_hold = bool(ballistics_res_now and univ_started and univ_ready_t and t >= univ_ready_t - 20)
        bal_w = 300 if bal_hold else 0
        bal_g = 175 if bal_hold else 0
        max_arch = 110 if (imp_clicked or sim.age == 4) else 44
        max_ele = 95 if (imp_clicked or sim.age == 4) else 22
        pop_ok = total_pop() < 197
        for ri in range(len(range_ready)):
            if range_ready[ri] is not None and t >= range_ready[ri]:
                if sim.age == 2 and t >= range_busy[ri]:
                    fletching_res = 50 if (bs_ready_t is not None and t >= bs_ready_t and "fletching" not in sim.upgrades and sim.military_units["archer"] >= 2) else 0
                    castle_res = 175 if (castle_clicked and (sim.tc_busy_until[0] - t) <= 45) else 0
                    if sim.bank.wood >= 25 and sim.bank.gold >= 45 + fletching_res + castle_res:
                        sim.bank = sim.bank - ResourceBundle(wood=25, gold=45)
                        sim.military_units["archer"] += 1
                        range_busy[ri] = t + 35
                elif sim.age >= 3 and "crossbowman" in sim.upgrades and not hold_mil_for_imp and pop_ok:
                    if path_key == "3tc_boom_ele_archer":
                        if ele_switch_started and t >= range_busy[ri] and sim.military_units["elephant_archer"] < max_ele:
                            if sim.bank.food >= 60 and sim.bank.gold >= (80 + bal_g):
                                sim.bank = sim.bank - ResourceBundle(food=60, gold=80)
                                sim.military_units["elephant_archer"] += 1
                                range_busy[ri] = t + 32
                            elif sim.age == 3 and ri < 2 and not bal_hold:
                                idle_range_castle_s += 1
                    else:
                        if t >= range_busy[ri] and sim.military_units["archer"] < max_arch:
                            if sim.bank.wood >= (25 + bal_w) and sim.bank.gold >= (45 + bal_g):
                                sim.bank = sim.bank - ResourceBundle(wood=25, gold=45)
                                sim.military_units["archer"] += 1
                                range_busy[ri] = t + 35
                            elif sim.age == 3 and ri < 2 and not bal_hold:
                                idle_range_castle_s += 1

        # Stable Light Cav production (up to 10 pre-Imp, up to 28 in Imp/transition)
        max_lc = 28 if (imp_clicked or sim.age == 4) else 10
        if not hold_mil_for_imp and pop_ok:
            for si in range(len(stable_ready)):
                if stable_ready[si] is not None and t >= stable_ready[si] and t >= stable_busy[si] and sim.military_units["light_cav"] < max_lc:
                    if sim.bank.food >= 80:
                        sim.bank = sim.bank - ResourceBundle(food=80)
                        sim.military_units["light_cav"] += 1
                        stable_busy[si] = t + 30
                    elif sim.age == 3 and si == 0:
                        idle_stable_castle_s += 1

        # Multi-Barracks Longswords & Spears/Pikes (~50/50) for Path 2
        if path_key == "1tc_xbow_ls_spear_ram" and sim.age >= 3 and "long swordsman" in sim.upgrades and not hold_mil_for_imp and pop_ok:
            max_ls = 35 if (imp_clicked or sim.age == 4) else 15
            max_pk = 32 if (imp_clicked or sim.age == 4) else 13
            for bi in range(len(barracks_ready)):
                if barracks_ready[bi] is not None and t >= barracks_ready[bi] and t >= rax_busy[bi]:
                    # Even indices train Longswords, odd indices train Pikes (~50/50 split)
                    if bi % 2 == 0 and sim.military_units["militia"] < max_ls:
                        if sim.bank.food >= 50 and sim.bank.gold >= 20:
                            sim.bank = sim.bank - ResourceBundle(food=50, gold=20)
                            sim.military_units["militia"] += 1
                            rax_busy[bi] = t + 21
                    elif bi % 2 == 1 and sim.military_units["spearman"] < max_pk:
                        if sim.bank.food >= 35 and sim.bank.wood >= 25:
                            sim.bank = sim.bank - ResourceBundle(food=35, wood=25)
                            sim.military_units["spearman"] += 1
                            rax_busy[bi] = t + 22

        # Siege Workshop Armored/Siege Elephants (2-4 in Castle, up to 6 in Imp)
        max_rams = 6 if (imp_clicked or sim.age == 4) else 3
        for wi in range(len(sw_ready)):
            if sw_ready[wi] is not None and t >= sw_ready[wi] and t >= sw_busy[wi] and sim.military_units["armored_elephant"] < max_rams:
                if (not hold_mil_for_imp or sim.military_units["armored_elephant"] < 2) and sim.bank.food >= 120 and sim.bank.gold >= 95:
                    sim.bank = sim.bank - ResourceBundle(food=120, gold=95)
                    sim.military_units["armored_elephant"] += 1
                    sw_busy[wi] = t + 36
                    if sim.military_units["armored_elephant"] == 3 and push_ready_t is None:
                        push_ready_t = t
                        milestones["push_ready_str"] = sim.fmt_time()
                        milestones["push_ready_vils"] = len(sim.vils)
                        milestones["push_ready_army"] = current_army_dict()
                        add_row(
                            f"{len(sim.vils)} ({total_pop()})",
                            sim.fmt_time(),
                            current_phase,
                            "Siege Push Ready — Build Siege Workshop (-200W) & 3 Armored Elephants (Dravidians' Rams: 120F, 95G each): Push with upgraded army!",
                            f"Push force: {format_army_counts(current_army_dict())}.",
                        )

        # Farm seeding (hit 25-28 Farms first, drop SW/Univ/Range #3, then scale to 36-38 Farms)
        if sim.age == 2:
            target_farms = 17
        elif not univ_started:
            target_farms = 26 if path_key == "3tc_boom_ele_archer" else 24
        else:
            target_farms = 38 if path_key == "3tc_boom_ele_archer" else 34
        reserve_w = 0
        if sim.age == 2:
            if not bs_started and "horse collar" in sim.upgrades:
                reserve_w += 150
            if castle_clicked and range_ready[1] is None:
                reserve_w += 175
        else:
            if path_key == "3tc_boom_ele_archer" and not tc3_started:
                reserve_w += 275
            if sw_ready[0] is None and (
                (path_key == "1tc_xbow_lc_ram" and sim.military_units["archer"] >= 19)
                or (path_key == "1tc_xbow_ls_spear_ram" and sim.military_units["militia"] + sim.military_units["spearman"] >= 6)
                or (path_key == "3tc_boom_ele_archer" and sim.military_units["elephant_archer"] >= 3)
            ):
                reserve_w += 200
            if (ballistics_res_now or sw_ready[0] is not None) and not univ_started:
                reserve_w += 200
            if (ballistics_res_now and univ_started) or (univ_started and univ_ready_t and t >= univ_ready_t and not saving_for_imp and "ballistics" not in sim.upgrades):
                reserve_w += 300
            if imp_clicked and not tc3_started and sim.bank.stone >= 100 and path_key in ("1tc_xbow_lc_ram", "1tc_xbow_ls_spear_ram"):
                reserve_w += 275

        early_farm = sim.age == 2 and "horse collar" in sim.upgrades and sim.farms_seeded < 1 and t <= (range_ready[0] or 9999) - 25 and sim.bank.wood >= 60
        later_farm = sim.age >= 2 and bs_started and sim.count_role("farm") < target_farms and sim.bank.wood >= (60 + reserve_w)
        if early_farm or later_farm:
            target_vil = None
            if sim.age >= 3 and not univ_started:
                keep_wood_min = 12
            elif sim.age >= 3 and path_key == "3tc_boom_ele_archer":
                keep_wood_min = 8
            elif sim.age >= 3:
                keep_wood_min = 10
            else:
                keep_wood_min = 7
            for pref_roles in (("straggler",), ("wood",)):
                if pref_roles == ("wood",) and sim.count_role("wood") <= keep_wood_min:
                    continue
                for v in sim.vils:
                    if v["role"] in pref_roles and int(v["busy_until"]) <= t:
                        target_vil = v
                        break
                if target_vil is not None:
                    break
            if target_vil is not None:
                sim.bank = sim.bank - ResourceBundle(wood=60)
                sim.register_new_farm()
                target_vil["role"] = "farm"
                target_vil["busy_until"] = t + 20

        # Anti-Float Rebalancer & Late-Castle/Imp Market balancing (every 10s in Castle+)
        if sim.age >= 3 and t % 10 == 0:
            # 1) Build Market once if Wood floats while saving for Imp Gold or severely imbalanced
            if market_ready_t is None and ((saving_for_imp and sim.bank.gold < 800) or sim.bank.wood >= 550) and sim.bank.wood >= (175 + reserve_w):
                sim.bank = sim.bank - ResourceBundle(wood=175)
                market_ready_t = t + 50
            # 2) Rebalance up to 2 excess vils away from overflowing resource (NEVER drain existing Farms onto Wood!)
            def reallocate_vils(src_role: str, dst_role: str, keep_min: int, max_move: int = 2) -> None:
                cur_cnt = sim.count_role(src_role)
                moved_n = 0
                for v in sim.vils:
                    if moved_n >= max_move or cur_cnt <= keep_min:
                        break
                    if v["role"] == src_role and int(v["busy_until"]) <= t:
                        if dst_role == "farm":
                            if sim.bank.wood >= (60 + reserve_w) and sim.count_role("farm") < 44:
                                sim.bank = sim.bank - ResourceBundle(wood=60)
                                sim.register_new_farm()
                                v["role"] = "farm"
                                v["busy_until"] = t + 20
                            else:
                                continue
                        else:
                            v["role"] = dst_role
                            v["busy_until"] = t + 15
                        cur_cnt -= 1
                        moved_n += 1

            is_ele_path = path_key == "3tc_boom_ele_archer"
            if not univ_started or ballistics_res_now:
                w_cap = 14
                w_min = 12
            elif is_ele_path:
                w_cap = 6
                w_min = 3
            else:
                w_cap = 15
                w_min = 10
            w_bank, f_bank, g_bank = sim.bank.wood, sim.bank.food, sim.bank.gold
            w_cur = sim.count_role("wood")

            # Always trim excess Lumberjacks into Farms or Gold so Wood neither starves Farms nor floats
            if w_cur > w_cap or w_bank > (380 + reserve_w):
                dst = "gold" if g_bank < (850 if saving_for_imp else (420 if is_ele_path else 500)) else "farm"
                reallocate_vils("wood", dst, keep_min=w_min, max_move=3)
            g_thresh = 420 if is_ele_path else 480
            if not saving_for_imp and g_bank > g_thresh:
                if not is_ele_path and w_bank < 260 and w_cur < (w_cap + 2):
                    reallocate_vils("gold", "wood", keep_min=8, max_move=2)
                elif sim.count_role("farm") < 44 and w_bank >= (60 + reserve_w):
                    reallocate_vils("gold", "farm", keep_min=7, max_move=3)
                elif f_bank < 500 or w_cur < w_cap:
                    reallocate_vils("gold", "wood", keep_min=7, max_move=2)
            elif saving_for_imp and g_bank > 880 and f_bank < 1000:
                reallocate_vils("gold", "farm", keep_min=8, max_move=2)
            if not saving_for_imp and f_bank > 600 and (g_bank < 480 or (not is_ele_path and w_bank < 240)):
                dst = "wood" if (not is_ele_path and w_bank < 240) else "gold"
                reallocate_vils("farm", dst, keep_min=24, max_move=2)
            elif saving_for_imp and f_bank > 1080 and g_bank < 800:
                reallocate_vils("farm", "gold", keep_min=24, max_move=2)

            # 3) Occasional Market trade per rules.md (30G/100 in Castle, 15G/100 in Imp) to prevent excess float
            if market_ready_t is not None and t >= market_ready_t:
                rate = 15.0 if sim.age == 4 else 30.0
                if saving_for_imp and sim.bank.wood >= 550 + reserve_w and sim.bank.gold < 800:
                    sim.bank = sim.bank - ResourceBundle(wood=100) + ResourceBundle(gold=rate)
                    sim.market_trades.append({"t": t, "sold": "100W", "bought": f"{int(rate)}G"})
                elif saving_for_imp and sim.bank.food >= 1150 and sim.bank.gold < 800:
                    sim.bank = sim.bank - ResourceBundle(food=100) + ResourceBundle(gold=rate)
                    sim.market_trades.append({"t": t, "sold": "100F", "bought": f"{int(rate)}G"})
                elif not saving_for_imp and sim.bank.wood >= 650 + reserve_w:
                    sim.bank = sim.bank - ResourceBundle(wood=100) + ResourceBundle(gold=rate)
                    sim.market_trades.append({"t": t, "sold": "100W", "bought": f"{int(rate)}G"})
                elif not saving_for_imp and sim.bank.food >= 800 and ("siege elephant" in sim.upgrades or sim.age == 3):
                    sim.bank = sim.bank - ResourceBundle(food=100) + ResourceBundle(gold=rate)
                    sim.market_trades.append({"t": t, "sold": "100F", "bought": f"{int(rate)}G"})

        # Track non-saved peak float across Castle/Imperial (excludes intentional Age-Up banking)
        is_banking_age = (
            (sim.age == 1 and loom_done and not feudal_clicked)
            or (sim.age == 2 and bs_ready_t is not None and len(sim.vils) >= 32 and not castle_clicked)
            or (sim.age == 3 and imp_prep_started and not imp_clicked)
        )
        if sim.age >= 3 and not is_banking_age:
            max_non_save_float["food"] = max(max_non_save_float["food"], sim.bank.food)
            max_non_save_float["wood"] = max(max_non_save_float["wood"], sim.bank.wood)
            max_non_save_float["gold"] = max(max_non_save_float["gold"], sim.bank.gold)

        urgent_building_res_w = float(reserve_w) if (sim.age >= 3 and (sw_ready[0] is None or not univ_started or ballistics_res_now or (path_key == "3tc_boom_ele_archer" and not tc3_started))) else 0.0
        sim.tick_gather(
            boar_open=(boar1_shot and sim.active_carcass_food["boar"] > 1e-6),
            reseed_reserve_w=urgent_building_res_w,
        )
        if t % 10 == 0:
            record_timeline_point()

    milestones["idle_range_castle_s"] = idle_range_castle_s
    milestones["idle_stable_castle_s"] = idle_stable_castle_s
    milestones["idle_tc_castle_s"] = sim.tc1_idle_castle_s
    milestones["market_trades_count"] = len(sim.market_trades)
    milestones["max_non_save_float"] = {k: round(v, 1) for k, v in max_non_save_float.items()}
    milestones["final_vils"] = len(sim.vils)
    milestones["final_army"] = current_army_dict()
    milestones["final_bank"] = sim.bank.to_dict()

    # Compute steady-state villager target with 10% Castle Age human execution buffer
    if path_key == "1tc_xbow_lc_ram":
        ss_items = [
            ContinuousProductionItem("villager", 1),
            ContinuousProductionItem("archer", 2),
            ContinuousProductionItem("scout cavalry", 1),
        ]
        ss_title = "Steady-State (1 TC + 2-Range Xbows + 1-Stable Light Cav, w/ 10% Castle Buffer)"
    elif path_key == "1tc_xbow_ls_spear_ram":
        ss_items = [
            ContinuousProductionItem("villager", 1),
            ContinuousProductionItem("archer", 2),
            ContinuousProductionItem("militia", 1),
            ContinuousProductionItem("spearman", 1),
        ]
        ss_title = "Steady-State (1 TC + 2-Range Xbows + 2-Rax Longswords/Pikes, w/ 10% Castle Buffer)"
    else:
        ss_items = [
            ContinuousProductionItem("villager", 3),
            ContinuousProductionItem("elephant archer", 2),
            ContinuousProductionItem("scout cavalry", 1),
        ]
        ss_title = "Steady-State (3 TCs + 2-Range Ele Archers + 1-Stable Light Cav, w/ 10% Castle Buffer)"

    steady_state = planner.compute_steady_state_vils(
        items=ss_items,
        civ="Dravidians",
        age=3,
        upgrades=["double-bit axe", "bow saw", "horse collar", "wheelbarrow", "gold mining"],
        food_source="farmer",
        wood_minutes_since_lc=2.0,
    )
    # Apply 10% Castle Age buffer to recommended vils so human execution is safely covered
    import math
    ex_raw = steady_state["exact_vils"]
    ex_buf = {k: round(float(v) / 0.90, 2) for k, v in ex_raw.items() if k != "total"}
    ex_buf["total"] = round(sum(ex_buf.values()), 2)
    rec_buf = {k: math.ceil(v - 1e-6) for k, v in ex_buf.items() if k != "total"}
    rec_buf["total"] = sum(rec_buf.values())
    steady_state["exact_vils"] = ex_buf
    steady_state["recommended_vils"] = rec_buf
    steady_state["title"] = ss_title

    # Build clean, simplified RTS Overlay steps synced to exact simulated milestones
    I = RTS_ICONS
    c_vils = int(milestones["castle_click_vils"])
    c_arch = int(milestones["castle_arrival_archers"])
    imp_c_vils = int(milestones.get("imp_click_vils", 60))
    imp_c_str = str(milestones.get("imp_click_str", "30:00"))
    imp_r_str = str(milestones.get("imp_reached_str", "33:10"))
    a50_str = str(milestones.get("army50_str", "27:00"))
    end_alloc = sim.current_macro_alloc()
    fin_vils = int(milestones["final_vils"])
    # Ensure RTS sum matches villager_count strictly
    end_w = int(end_alloc["wood"])
    end_f = int(end_alloc["food"])
    end_g = int(end_alloc["gold"])
    end_s = max(0, fin_vils - (end_w + end_f + end_g))
    if end_w + end_f + end_g + end_s != fin_vils:
        end_f = fin_vils - (end_w + end_g + end_s)

    if path_key == "1tc_xbow_lc_ram":
        castle_rts = [
            RTSOverlayStep(
                villager_count=c_vils,
                age=3,
                wood=11,
                food=17,
                gold=7,
                stone=0,
                notes=[
                    f"Click {I['castle_age']} -> {I['build']} 2nd {I['archery_range']} & Padded Archer Armor; keep 2-Range Archers continuous.",
                    f"Reach {I['castle_age']} (+200 {I['wood']}!): immediately research {I['crossbowman']}, {I['bodkin_arrow']}, and {I['bow_saw']}.",
                ],
            ),
            RTSOverlayStep(
                villager_count=48,
                age=3,
                wood=13,
                food=22,
                gold=13,
                stone=0,
                notes=[
                    f"Fast 50+ Army Ramp ({a50_str}): {I['build']} {I['stable']} + {I['heavy_plow']}; add {I['siege_workshop']} (3 Armored Elephants) + University; scale Ranges (#3-#4) & Stable #2 on spare {I['wood']}.",
                    f"Hit 50+ army -> shift priority to {I['imperial_age']} (pause extra queues briefly to bank 1000F + 800G); click Imp around {imp_c_str} & drop {I['town_center']} #2/#3!",
                ],
            ),
            RTSOverlayStep(
                villager_count=fin_vils,
                age=4,
                wood=end_w,
                food=end_f,
                gold=end_g,
                stone=end_s,
                notes=[
                    f"Imperial Transition -> Reach {I['imperial_age']} ({imp_r_str}, +200W): Resume all production, finish {I['ballistics']}, {I['hand_cart']} & extra TCs.",
                    f"Imperial Spike: Research Arbalester, Bracer, Chemistry, Siege Elephant & Ring Archer Armor; spend down below 500-1000 float!",
                ],
            ),
        ]
    elif path_key == "1tc_xbow_ls_spear_ram":
        castle_rts = [
            RTSOverlayStep(
                villager_count=c_vils,
                age=3,
                wood=11,
                food=17,
                gold=7,
                stone=0,
                notes=[
                    f"Click {I['castle_age']} -> {I['build']} 2nd {I['archery_range']} & Padded Archer Armor; keep 2-Range Archers continuous.",
                    f"Reach {I['castle_age']} (+200 {I['wood']}!): immediately research {I['crossbowman']}, {I['bodkin_arrow']}, and {I['bow_saw']}.",
                ],
            ),
            RTSOverlayStep(
                villager_count=50,
                age=3,
                wood=14,
                food=23,
                gold=13,
                stone=0,
                notes=[
                    f"Fast 50+ Army Ramp ({a50_str}): {I['build']} 2nd {I['barracks']} + {I['heavy_plow']}; get -50% {I['long_swordsman']}, {I['pikeman']}, Squires & Scale Mail.",
                    f"Add {I['siege_workshop']} (3 Armored Elephants) + University + Range #3/Rax #3 on spare {I['wood']}; at 50+ army shift to {I['imperial_age']} ({imp_c_str}) + late TCs!",
                ],
            ),
            RTSOverlayStep(
                villager_count=fin_vils,
                age=4,
                wood=end_w,
                food=end_f,
                gold=end_g,
                stone=end_s,
                notes=[
                    f"Reach {I['imperial_age']} ({imp_r_str}, +200W): Resume 4 Ranges + 3-4 Rax; research Arbalester, Bracer, Chemistry, Champion, Halberdier & Siege Elephant.",
                    f"Anti-Float Rule: Rebalance excess Lumberjacks/Miners & push 4-5 production buildings to keep float <500-1000.",
                ],
            ),
        ]
    else:  # 3tc_boom_ele_archer
        castle_rts = [
            RTSOverlayStep(
                villager_count=c_vils,
                age=3,
                wood=11,
                food=17,
                gold=7,
                stone=0,
                notes=[
                    f"Click {I['castle_age']} -> {I['build']} 2nd {I['archery_range']} & Padded Archer Armor; keep 2-Range Archers continuous.",
                    f"Reach {I['castle_age']} (+200 {I['wood']}!): research {I['crossbowman']}, {I['bodkin_arrow']}, {I['bow_saw']}; pause Range & drop {I['town_center']} #2 & #3!",
                ],
            ),
            RTSOverlayStep(
                villager_count=64,
                age=3,
                wood=11,
                food=36,
                gold=17,
                stone=0,
                notes=[
                    f"3-TC Boom to ~49 {I['villager']}s ({milestones.get('ele_switch_str', '23:43')}) while defending with {c_arch} {I['crossbowman']}s; then unleash {I['elephant_archer']}s + {I['stable']} -> {I['light_cavalry']} + {I['siege_workshop']}!",
                    f"Scale to 3-4 Ranges & 2 Stables when >58 {I['villager']}s -> hit 50+ army ({a50_str}) -> shift priority to click {I['imperial_age']} ({imp_c_str})!",
                ],
            ),
            RTSOverlayStep(
                villager_count=fin_vils,
                age=4,
                wood=end_w,
                food=end_f,
                gold=end_g,
                stone=end_s,
                notes=[
                    f"Reach {I['imperial_age']} ({imp_r_str}, +200W): Research Elite Elephant Archer, Bracer, Chemistry, Thumb Ring, {I['ballistics']} & Siege Elephant.",
                    f"Trim excess Lumberjacks (Ele Archers cost 0W!) into Farms/Gold to keep float <500-1000 while flooding 60+ Ele Archers!",
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
                f"Vils #1-#6: Build 2 Houses, then all 6 on {I['sheep']} under TC (max 7 on Sheep).",
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
                f"Vils #7-#9 (3 vils) -> {I['wood']} (1st vil builds {I['lumber_camp']} first, then all 3 on Wood).",
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
                f"Vil #10 lures 1st {I['boar']} (garrison 7 TC vils 5s at 03:25 to shoot boar -> 6+ on Boar); Vil #11 to {I['wood']} (4 on Wood).",
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
                f"Vils #12-#15 (4 vils) -> 7 Chickens (1st vil builds House #3 + {I['mill']} on Chickens, all 4 gather).",
                f"At 04:35, 1 hunter lures 2nd {I['boar']} (garrison 7 TC vils 5s at 05:05 to shoot).",
            ],
        ),
        RTSOverlayStep(
            villager_count=19,
            age=1,
            wood=4,
            food=14,
            gold=1,
            stone=0,
            notes=[
                f"Vils #16-#18 -> {I['boar']}/{I['sheep']} under TC; Vil #19 builds House #4 -> LD {I['gold']}.",
                f"Research {I['loom']} -> Click {I['feudal_age']} (20 Pop / 19v, 0s TC idle).",
            ],
        ),
        RTSOverlayStep(
            villager_count=19,
            age=2,
            wood=7,
            food=10,
            gold=2,
            stone=0,
            notes=[
                f"Feudal Transition: 3 food vils -> {I['wood']} (1st builds {I['barracks']} -> House #5); {I['build']} {I['mining_camp']} on {I['gold']} (2 on Gold); train 3 Militia.",
            ],
        ),
        RTSOverlayStep(
            villager_count=c_vils,
            age=2,
            wood=11,
            food=17,
            gold=7,
            stone=0,
            notes=[
                f"Feudal (+200W): MAA + {I['double_bit_axe']} + {I['horse_collar']} + 1st {I['archery_range']}.",
                f"Macro Loop: Continuous Vils -> {I['gold']} to 4, {I['wood']} to 8, then stragglers & {I['farm']}s every 60W (to 17 Farms) + 3 more to {I['gold']} (7 Gold) + {I['gold_mining']}; {I['blacksmith']} -> {I['fletching']} + 1-Range {I['archer']}s; {I['wheelbarrow']} -> Click {I['castle_age']}.",
            ],
        ),
        *castle_rts,
    ]

    desc = (
        f"Dravidians 20-Pop (19v) 3 MAA -> Archers (7 Chickens Milled on Arabia) into {variant_label}. "
        f"Includes 5s Boar-shooting TC garrison idling, updated animal caps (<=7 Sheep, 7-8 Boar / 10 transition), "
        f"combined same-resource steps for Dark Age, and high-level macro loops with 92% Feudal / 90% Castle execution buffers."
    )

    doc = BuildOrderDocument(
        name="Dravidians 20-Pop MAA -> Archers (7 Chickens Milled)",
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
    return doc, milestones


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = [
        ("1tc_xbow_lc_ram", "Path 1: 1 TC -> 2-Range Xbows + Light Cav + 3 Armored Elephants (Rams) -> Later TCs", "dravidians_maa_xbow_lc_ram.json"),
        ("1tc_xbow_ls_spear_ram", "Path 2: 1 TC -> 2-Range Xbows + 2-Rax Longswords/Pikes + 3 Armored Elephants -> Later TCs", "dravidians_maa_xbow_ls_spear_ram.json"),
        ("3tc_boom_ele_archer", "Path 3: 3 TC Boom First -> 2-Range Elephant Archers + Light Cav + Rams", "dravidians_maa_ele_archer_3tc_boom.json"),
    ]

    docs: List[BuildOrderDocument] = []
    for p_key, p_label, json_name in paths:
        doc, ms = run_dravidians_path(p_key, p_label)
        docs.append(doc)
        json_path = export_rts_overlay_json(doc, OUT_DIR / json_name)
        print(f"=== {ms['variant']} ===")
        for k, v in ms.items():
            if k != "variant":
                print(f"  {k}: {v}")
        print(f"  Steady-State (w/ 10% buffer): {doc.steady_state_summary['recommended_vils']} (exact: {doc.steady_state_summary['exact_vils']})")
        print(f"  Rot telemetry: {doc.telemetry_summary['rotted_food']} (Total: {doc.telemetry_summary['total_rotted_food']}F)")
        print(f"  Wrote JSON: {json_path} ({len(doc.rts_steps)} steps)\n")

    html_path = export_build_order_html(
        docs,
        title="Dravidians 20-Pop MAA into Archers (7 Chickens Milled) — 3 Castle Age Paths",
        output_path=OUT_DIR / "dravidian_maa_into_archers.html",
    )
    print(f"Wrote HTML report: {html_path}")


if __name__ == "__main__":
    main()

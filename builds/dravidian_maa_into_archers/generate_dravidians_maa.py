#!/usr/bin/env python3
"""
Generator & 1-Second Discrete-Event Simulator for:
Dravidians 20-Pop (19-Vil) 3 MAA -> Archers (Arabia: 6 Chickens on a Mill / 8-Chicken Check)
into 3 Castle Age Paths:
  1. 1tc_xbow_lc_ram       : 1 TC -> 2-Range Xbows + 1-Stable Light Cav + 3 Armored Elephants -> Later TCs
  2. 1tc_xbow_ls_spear_ram : 1 TC -> 2-Range Xbows + 2-Rax Longswords & Spears/Pikes (~50/50) + 3 Armored Elephants -> Later TCs
  3. 3tc_boom_ele_archer   : 3 TC Boom First -> Switch to 2-Range Elephant Archers + Light Cav + 3 Armored Elephants

Enforces all rules in `rules.md` and `output.md`:
- Default Arabia Chicken map (rules 1.3, 3.9): 6 Chickens on a Mill (with 8-chicken check under rule 8.3)
- Mill prerequisite for Horse Collar & Farms (rule 3.10)
- Effective gather rates w/ drop-off round trips (rule 3.2) & 60% wood floor / mover-only LC refresh (rule 3.4)
- Real tech research times (rule 11.4), real builder times (rule 4.1), house buffers (rule 4.4), dynamic Market (rule 7.2)
- TC idle <= 5s (rules 5.1, 5.3), Imperial < 40:00 (rule 6.5), late-command robustness checks (rule 8.3)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))
sys.path.insert(0, str(THIS_DIR.parents[1] / "scripts"))

from aoe2_data import ResourceBundle, calc_construction_time
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
from sim_dravidians_maa import DravidiansSimulator
from simulator import run_late_command_checks

OUT_DIR = THIS_DIR


def _pull_builders(
    sim: DravidiansSimulator,
    roles: Tuple[str, ...],
    count: int,
    busy_until: int,
    camp_idx: Optional[int] = None,
) -> int:
    pulled = 0
    for r in roles:
        for v in sim.vils:
            if v["role"] == r and int(v["busy_until"]) <= sim.time_s and pulled < count:
                v["busy_until"] = busy_until
                if camp_idx is not None:
                    v["camp_idx"] = camp_idx
                pulled += 1
    return pulled


def run_dravidians_path(
    path_key: str,
    variant_label: str,
    delay_fn: Optional[Callable[[int], int]] = None,
    chicken_override: Optional[int] = None,
    record_outputs: bool = True,
) -> Tuple[BuildOrderDocument, Dict[str, object]]:
    """
    Runs a 1-second simulation from 00:00 through 40:00 for a given Castle Age path
    on a 6-chicken Arabia map (with a Mill on Chickens; checked against 8 chickens).
    """
    chk_cnt = chicken_override if chicken_override is not None else 6

    sim = DravidiansSimulator(path_key=path_key, deer_count=0, chicken_count=chk_cnt)
    rules = sim.rules
    planner = BackwardPlanner(sim.db, rules)

    def d_t(planned_t: int) -> int:
        return planned_t if delay_fn is None else delay_fn(planned_t)

    rows: List[DetailedBuildRow] = []
    resource_timeline: List[Dict[str, object]] = []
    milestones: Dict[str, object] = {
        "path_key": path_key,
        "map_variant": "chickens_mill",
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

    def record_timeline_point() -> None:
        if not record_outputs:
            return
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
        if not record_outputs:
            return
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

    feudal_cost, feudal_time, feudal_lump = sim.db.get_age_advance_spec(2, "Dravidians")
    castle_cost, castle_time, castle_lump = sim.db.get_age_advance_spec(3, "Dravidians")
    imp_cost, imp_time, imp_lump = sim.db.get_age_advance_spec(4, "Dravidians")

    # t = 0:00 start (rule 1.5)
    sim.spend(ResourceBundle(food=50), "vil_4")
    sim.tc_busy_until[0] = 25
    sim.tc_action[0] = "vil_4"
    record_timeline_point()

    # Tracking state
    boar1_arrive_t: Optional[int] = None
    boar1_shot = False
    boar2_lured = False
    boar2_arrive_t: Optional[int] = None
    boar2_shot = False
    loom_done = False
    feudal_clicked = False
    feudal_click_t = 0
    feudal_cmd_t: Optional[int] = None
    barracks_ready: List[Optional[int]] = [None] * 4
    rax_busy: List[int] = [0] * 4
    militia_trained = 0
    militia_logged = False
    mc_started = False
    range_ready: List[Optional[int]] = [None] * 5
    range_busy: List[int] = [0] * 5
    bs_started = False
    bs_ready_t: Optional[int] = None
    house_busy_until = 0
    wb_started = False
    hc_started = False
    castle_clicked = False
    castle_click_t = 0
    castle_cmd_t: Optional[int] = None
    castle_click_alloc: Dict[str, int] = {}
    castle_arrived_t: Optional[int] = None
    last_lc_refresh_t = -999

    next_vil_id = 20
    stable_ready: List[Optional[int]] = [None] * 3
    stable_busy: List[int] = [0] * 3
    univ_started = False
    univ_ready_t: Optional[int] = None
    sw_ready: List[Optional[int]] = [None] * 2
    sw_busy: List[int] = [0] * 2
    market_ready_t: Optional[int] = None
    last_market_trade_t = -999
    tc2_started = False
    tc2_ready_t: Optional[int] = None
    tc3_started = False
    tc3_ready_t: Optional[int] = None

    started_upgs: set[str] = set()
    ele_switch_started = False
    imp_prep_started = False
    imp_hold_start_t: Optional[int] = None
    castle_hold_start_t: Optional[int] = None
    imp_clicked = False
    imp_click_t: Optional[int] = None
    imp_arrived_t: Optional[int] = None
    feudal_loop1_logged = False
    feudal_loop1_start_t = 0
    castle_loop1_logged = False
    castle_loop2_logged = False
    castle_loop3_logged = False
    imp_loop_logged = False
    push_ready_t: Optional[int] = None
    idle_range_castle_s = 0
    idle_stable_castle_s = 0
    housed_seconds = 0
    tc_pre_click_idle_s = 0
    tc_unplanned_idle_s = 0
    max_non_save_float: Dict[str, float] = {"food": 0.0, "wood": 0.0, "gold": 0.0}

    def queue_upg(name: str, res_food: float = 0.0, res_wood: float = 0.0, res_gold: float = 0.0) -> bool:
        if name in started_upgs or name in sim.upgrades:
            return False
        c, rt = sim.db.get_upgrade_spec(name, "Dravidians")
        if (
            sim.bank.food >= c.food + res_food
            and sim.bank.wood >= c.wood + res_wood
            and sim.bank.gold >= c.gold + res_gold
            and sim.bank.stone >= c.stone
        ):
            started_upgs.add(name)
            sim.spend(c, f"upgrade:{name}")
            sim.queue_upgrade(name, sim.time_s + int(round(rt)))
            return True
        return False

    max_sim_t = 2400  # 40:00 (Imperial Age must be reached < 40:00; rule 6.5)
    for t in range(1, max_sim_t + 1):
        sim.time_s = t
        sim.in_age_transition = (feudal_clicked and sim.age == 1) or (castle_clicked and sim.age == 2) or (imp_clicked and sim.age == 3)
        current_phase = (
            "Dark Age" if (sim.age == 1 and not feudal_clicked)
            else "Feudal Transition" if (sim.age == 1 and feudal_clicked)
            else "Feudal Age" if (sim.age == 2 and not castle_clicked)
            else "Castle Transition" if (sim.age == 2 and castle_clicked)
            else "Imperial Transition" if (sim.age == 3 and imp_clicked)
            else "Imperial Age" if sim.age == 4
            else "Castle Age"
        )

        # Track TC #1 idle time (rules 5.1, 5.3)
        vil_cap = 84 if path_key == "3tc_boom_ele_archer" else 76
        if not imp_clicked and sim.tc_action[0] == "idle":
            if (
                (sim.age == 1 and loom_done and not feudal_clicked)
                or (sim.age == 2 and (castle_hold_start_t is not None or castle_cmd_t is not None) and not castle_clicked)
                or (sim.age >= 3 and (imp_hold_start_t is not None or len(sim.vils) >= vil_cap))
            ):
                tc_pre_click_idle_s += 1
            else:
                tc_unplanned_idle_s += 1

        # Boar #1 arrival -> garrison 7 TC vils 5s (rule 3.7)
        if boar1_arrive_t is not None and not boar1_shot and t >= boar1_arrive_t:
            boar1_shot = True
            _pull_builders(sim, ("sheep", "boar"), rules.boar_garrison_vils, t + int(rules.boar_garrison_seconds))
            if sim.active_carcass_food["sheep"] <= 40.0:
                kept_one = False
                for v in sim.vils:
                    if v["role"] == "sheep":
                        if not kept_one and sim.active_carcass_food["sheep"] > 5.0:
                            kept_one = True
                        else:
                            v["role"] = "boar"
                            v["busy_until"] = max(int(v["busy_until"]), t + int(rules.tc_food_switch_walk_time))

        # Boar #2 lured dynamically so it arrives right as Boar #1 runs out (rule 3.7)
        if boar1_shot and not boar2_lured and sim.remaining_animals["boar"] >= 1:
            n_boar = max(1, sim.count_role("boar"))
            boar_rate = n_boar * sim.db.get_gather_rate("boar", civ=sim.civ, rules=rules) + 0.40
            if sim.remaining_animals["boar"] == 1 and sim.active_carcass_food["boar"] <= boar_rate * 32.0:
                boar2_lured = True
                lure_t = d_t(t)
                for v in sim.vils:
                    if v["role"] == "boar":
                        boar2_arrive_t = lure_t + int(2 * rules.boar_lure_walk_time_one_way)
                        v["busy_until"] = max(int(v["busy_until"]), boar2_arrive_t)
                        break

        if boar2_arrive_t is not None and not boar2_shot and t >= boar2_arrive_t:
            boar2_shot = True
            _pull_builders(sim, ("boar", "sheep"), rules.boar_garrison_vils, t + int(rules.boar_garrison_seconds))

        # Complete TC #2 / TC #3
        if tc2_ready_t is not None and t == tc2_ready_t:
            tc2_ready_t = None
            sim.tc_count += 1
            sim.tc_busy_until.append(t)
            sim.tc_action.append("idle")
            milestones["tc2_ready_str"] = sim.fmt_time()
        if tc3_ready_t is not None and t == tc3_ready_t:
            tc3_ready_t = None
            sim.tc_count += 1
            sim.tc_busy_until.append(t)
            sim.tc_action.append("idle")
            milestones["tc3_ready_str"] = sim.fmt_time()

        # Check TC completions
        for ti in range(sim.tc_count):
            if t == sim.tc_busy_until[ti] and sim.tc_action[ti] != "idle":
                act = sim.tc_action[ti]
                sim.tc_action[ti] = "idle"

                if act.startswith("vil_"):
                    vid = len(sim.vils) + 1
                    if sim.age == 1:
                        if vid in (4, 5, 6):
                            sim.vils.append({"id": vid, "role": "sheep", "busy_until": t})
                            if vid == 6:
                                add_row(
                                    "3–6 (4–7)",
                                    f"00:00 – {sim.fmt_time()}",
                                    "Dark Age",
                                    "Vils #1–#6 (6 vils) -> Build 2 Houses (-50W), then all 6 on Sheep under TC.",
                                    "Start 200F, 200W, 100G, 200S; +2 Sheep at 1:30 & 2:30 (rule 1.3).",
                                )
                        elif vid == 7:
                            sim.spend(ResourceBundle(wood=100), "LC1")
                            comp_t = t + int(rules.camp_or_berry_walk_time_one_way) + 35
                            lc1_idx = sim.add_lumber_camp(comp_t)
                            sim.vils.append({"id": vid, "role": "wood", "camp_idx": lc1_idx, "busy_until": comp_t})
                        elif vid in (8, 9):
                            sim.vils.append({"id": vid, "role": "wood", "camp_idx": 0, "busy_until": t + int(rules.camp_or_berry_walk_time_one_way)})
                            if vid == 9:
                                add_row(
                                    "7–9 (8–10)",
                                    f"01:40 – {sim.fmt_time()}",
                                    "Dark Age",
                                    "Vils #7–#9 (3 vils) -> Wood (1st vil walks 15s + builds Lumber Camp #1 [-100W, 35s], then all 3 on Wood).",
                                    "LC #1 completes at 02:30; wood decay -1% per 20s down to 60% floor (rule 3.4).",
                                )
                        elif vid == 10:
                            lure_start = d_t(t)
                            boar1_arrive_t = lure_start + int(2 * rules.boar_lure_walk_time_one_way)
                            sim.vils.append({"id": vid, "role": "boar", "busy_until": boar1_arrive_t})
                            add_row(
                                "10 (11)",
                                sim.fmt_time(),
                                "Dark Age",
                                "Vil #10 -> Lure Boar #1 (15s out + 15s back).",
                                f"Boar #1 arrives {sim.fmt_time(boar1_arrive_t)} -> garrison 7 TC vils 5s (rule 3.7).",
                            )
                        elif vid == 11:
                            sim.vils.append({"id": vid, "role": "wood", "camp_idx": 0, "busy_until": t + int(rules.camp_or_berry_walk_time_one_way)})
                            add_row("11 (12)", sim.fmt_time(), "Dark Age", "Vil #11 -> Wood at LC #1 (15s walk; 4 on Wood).", "")
                        elif vid == 12:
                            sim.spend(ResourceBundle(wood=100), "ChickenMill")
                            mill_comp = t + int(rules.camp_or_berry_walk_time_one_way) + 35
                            sim.add_building("mill", mill_comp)
                            sim.vils.append({"id": vid, "role": "chicken_mill", "busy_until": mill_comp})
                        elif vid == 13:
                            sim.spend(ResourceBundle(wood=25), "House3")
                            comp_t = t + int(rules.house_walk_time_one_way) + 25
                            sim.add_pending_pop_building(comp_t, 5, "house")
                            sim.vils.append({"id": vid, "role": "chicken_mill", "busy_until": comp_t + int(rules.camp_or_berry_walk_time_one_way)})
                        elif vid in (14, 15):
                            sim.vils.append({"id": vid, "role": "chicken_mill", "busy_until": t + int(rules.camp_or_berry_walk_time_one_way)})
                            if vid == 15:
                                add_row(
                                    "12–15 (13–16)",
                                    f"03:45 – {sim.fmt_time()}",
                                    "Dark Age",
                                    "Vils #12–#15 (4 vils) -> 6 Chickens on Mill (Vil #12 walks 15s + builds Mill [-100W, 35s]; Vil #13 builds House #3 [-25W] -> joins Chickens; unlocks Farms & Horse Collar).",
                                    "Milling Chickens first (23.9/min vs 17.3/min Berries; rule 3.9); LC #1 + Mill satisfies Feudal Age building req (rule 4.6); 2nd Boar lured before 1st finishes.",
                                )
                        elif vid == 16:
                            sim.vils.append({"id": vid, "role": "boar", "busy_until": t})
                        elif vid == 17:
                            sim.spend(ResourceBundle(wood=25), "House4")
                            h4_comp = t + int(rules.house_walk_time_one_way) + 25
                            sim.add_pending_pop_building(h4_comp, 5, "house")
                            sim.vils.append({"id": vid, "role": "boar", "busy_until": h4_comp + int(rules.house_walk_time_one_way)})
                        elif vid == 18:
                            sim.vils.append({"id": vid, "role": "boar", "busy_until": t})
                            add_row(
                                "16–18 (17–19)",
                                f"05:25 – {sim.fmt_time()}",
                                "Dark Age",
                                "Vils #16–#18 (3 vils) -> Boar under TC (Vil #17 builds House #4 [-25W] -> joins Boar).",
                                "LC #1 + Chicken Mill already satisfies 2 Dark Age buildings (rule 4.6), saving Barracks wood for Feudal click.",
                            )
                        elif vid == 19:
                            sim.vils.append({"id": vid, "role": "gold_ld", "busy_until": t + int(rules.camp_or_berry_walk_time_one_way)})
                            add_row(
                                "19 (20)",
                                sim.fmt_time(),
                                "Dark Age",
                                "Vil #19 -> Long-Distance Gold (15s walk), then queue Loom (-50G, 25s) -> Click Feudal Age (20 Pop / 19v).",
                                "Funds 3 Militia (60G) + Loom (50G) + MAA (20G).",
                            )

                        if vid < 19 and sim.bank.food >= 50:
                            sim.spend(ResourceBundle(food=50), f"vil_{vid+1}")
                            sim.tc_busy_until[0] = t + 25
                            sim.tc_action[0] = f"vil_{vid+1}"
                        elif vid == 19 and sim.bank.gold >= 50:
                            sim.spend(ResourceBundle(gold=50), "Loom")
                            sim.tc_busy_until[0] = t + 25
                            sim.tc_action[0] = "loom"

                    elif sim.age == 2:
                        g_c = sim.count_role("gold", "gold_ld")
                        w_c = sim.count_role("wood")
                        f_c = sim.count_role("farm")
                        cur_camp = max(0, len(sim.lumber_camps) - 1)
                        if g_c < 4:
                            sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                        elif w_c < 8:
                            sim.vils.append({"id": vid, "role": "wood", "camp_idx": cur_camp, "busy_until": t + 15})
                        elif (f_c >= 14 or len(sim.vils) >= 29) and g_c < 7:
                            sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                        else:
                            sim.vils.append({"id": vid, "role": "straggler", "busy_until": t + int(rules.straggler_walk_time)})

                    else:
                        g_c = sim.count_role("gold", "gold_ld")
                        w_c = sim.count_role("wood")
                        f_c = sim.count_role("farm")
                        cur_camp = max(0, len(sim.lumber_camps) - 1)
                        cur_res_w = (275 if (path_key == "3tc_boom_ele_archer" and not tc3_started) else 0) + (200 if (sw_ready[0] is None or not univ_started) else 0)
                        if path_key == "1tc_xbow_lc_ram":
                            t_g, t_w, t_f = 12, 13, 34
                        elif path_key == "1tc_xbow_ls_spear_ram":
                            t_g, t_w, t_f = 12, 14, 36
                        else:
                            t_g, t_w, t_f = 15, (12 if not univ_started else 10), 42

                        if path_key == "3tc_boom_ele_archer" and not ele_switch_started and f_c < 26 and sim.bank.wood >= (60 + cur_res_w):
                            sim.spend(ResourceBundle(wood=60), "CastleFarm")
                            sim.register_new_farm(t + int(rules.farm_walk_time) + 15)
                            sim.vils.append({"id": vid, "role": "farm", "busy_until": t + int(rules.farm_walk_time) + 15})
                        elif path_key == "3tc_boom_ele_archer" and not ele_switch_started and w_c < 12:
                            sim.vils.append({"id": vid, "role": "wood", "camp_idx": cur_camp, "busy_until": t + 15})
                        elif w_c < (12 if not univ_started else t_w):
                            sim.vils.append({"id": vid, "role": "wood", "camp_idx": cur_camp, "busy_until": t + 15})
                        elif f_c < 28 and sim.bank.wood >= (60 + cur_res_w):
                            sim.spend(ResourceBundle(wood=60), "CastleFarm")
                            sim.register_new_farm(t + int(rules.farm_walk_time) + 15)
                            sim.vils.append({"id": vid, "role": "farm", "busy_until": t + int(rules.farm_walk_time) + 15})
                        elif g_c < t_g and f_c >= 17 and sim.bank.gold < 1200:
                            sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                        elif f_c < t_f and sim.bank.wood >= (60 + cur_res_w):
                            sim.spend(ResourceBundle(wood=60), "CastleFarm")
                            sim.register_new_farm(t + int(rules.farm_walk_time) + 15)
                            sim.vils.append({"id": vid, "role": "farm", "busy_until": t + int(rules.farm_walk_time) + 15})
                        elif f_c < t_f and sim.straggler_wood > 1e-6 and sim.count_role("straggler") < 2:
                            sim.vils.append({"id": vid, "role": "straggler", "busy_until": t + int(rules.straggler_walk_time)})
                        elif g_c < t_g and sim.bank.gold < 1200:
                            sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                        else:
                            sim.vils.append({"id": vid, "role": "wood", "camp_idx": cur_camp, "busy_until": t + 15})

                elif act == "loom":
                    loom_done = True

                elif act == "feudal":
                    sim.age = 2
                    sim.bank = sim.bank + feudal_lump
                    milestones["feudal_reached_str"] = sim.fmt_time()
                    if sim.bank.food >= 50:
                        sim.spend(ResourceBundle(food=50), "feudal_vil1")
                        sim.tc_busy_until[0] = t + 25
                        sim.tc_action[0] = f"vil_{next_vil_id}"
                        next_vil_id += 1
                    queue_upg("man-at-arms")
                    queue_upg("double-bit axe", res_food=50)
                    if sim.bank.wood >= 175:
                        sim.spend(ResourceBundle(wood=175), "ArcheryRange1")
                        sim.buildings.append("archery range")
                        range_ready[0] = t + 10 + 50
                        _pull_builders(sim, ("wood", "straggler"), 1, (range_ready[0] or t) + 10)
                    add_row(
                        f"{len(sim.vils)} ({sim.total_pop()})",
                        sim.fmt_time(),
                        "Feudal Age",
                        "REACHED FEUDAL AGE (+200W Dravidians bonus!): Queue Vil, research MAA (-50F, -20G, 40s) & Double-Bit Axe (-100F, -50W, 25s), build Archery Range #1 (-175W).",
                        "3 Militia upgrade to 3 MAA. 92% Feudal macro efficiency active (rule 8.2).",
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
                    sim.bank = sim.bank + castle_lump
                    milestones["castle_reached_s"] = t
                    milestones["castle_reached_str"] = sim.fmt_time()
                    milestones["castle_arrival_vils"] = len(sim.vils)
                    milestones["castle_arrival_archers"] = sim.military_units["archer"]
                    milestones["castle_arrival_bank"] = sim.bank.to_dict()
                    add_row(
                        f"{len(sim.vils)} ({sim.total_pop()})",
                        f"{sim.fmt_time(castle_click_t)} – {sim.fmt_time()}",
                        "Castle Transition",
                        "CASTLE TRANSITION (160s): Build Archery Range #2 (-175W) & Padded Archer Armor (-100F, 40s); produce Archers continuously from 2 Ranges.",
                        f"Arrives Castle Age with {sim.military_units['archer']} Archers + 3 MAA.",
                    )

                elif act == "imperial":
                    sim.age = 4
                    imp_arrived_t = t
                    sim.bank = sim.bank + imp_lump
                    milestones["imp_reached_s"] = t
                    milestones["imp_reached_str"] = sim.fmt_time()
                    milestones["imp_reached_vils"] = len(sim.vils)
                    milestones["imp_reached_army"] = current_army_dict()
                    add_row(
                        f"{len(sim.vils)} ({sim.total_pop()})",
                        f"{sim.fmt_time(imp_click_t or t)} – {sim.fmt_time()}",
                        "Imperial Transition",
                        "IMPERIAL TRANSITION (190s): Resume production buildings, finish Ballistics/Thumb Ring/Hand Cart & extra TCs (<500–1000 float).",
                        f"Arrives Imperial Age at {sim.fmt_time()} (<40:00 per rule 6.5).",
                    )

        # Click Feudal Age as soon as Loom completes
        if loom_done and not feudal_clicked and sim.tc_action[0] == "idle":
            if feudal_cmd_t is None and sim.bank.can_afford(feudal_cost):
                feudal_cmd_t = d_t(t)
            if feudal_cmd_t is not None and t >= feudal_cmd_t and sim.bank.can_afford(feudal_cost):
                feudal_clicked = True
                sim.feudal_clicked = True
                feudal_click_t = t
                milestones["feudal_click_s"] = t
                milestones["feudal_click_str"] = sim.fmt_time()
                milestones["feudal_click_idle_s"] = tc_pre_click_idle_s
                sim.spend(feudal_cost, "FeudalClick")
                sim.tc_busy_until[0] = t + int(feudal_time)
                sim.tc_action[0] = "feudal"
                # Move 3 food vils to Wood (1st builds Barracks [-175W] -> chains House #5 [-25W, 0s walk]; rules 2.3, 4.6)
                moved = 0
                for v in sim.vils:
                    if v["role"] in ("boar", "sheep", "chicken_mill") and int(v["busy_until"]) <= t and moved < 3:
                        if moved == 0:
                            sim.spend(ResourceBundle(wood=200), "Barracks+House5")
                            rax_ready = t + int(rules.building_walk_time_one_way) + 50
                            barracks_ready[0] = rax_ready
                            sim.add_building("barracks", rax_ready)
                            h5_comp = rax_ready + 25  # 0s walk chained sequentially (rule 2.3)
                            sim.add_pending_pop_building(h5_comp, 5, "house")
                            v["role"] = "wood"
                            v["camp_idx"] = 0
                            v["busy_until"] = h5_comp + int(rules.camp_or_berry_walk_time_one_way)
                        else:
                            v["role"] = "wood"
                            v["camp_idx"] = 0
                            v["busy_until"] = t + int(rules.camp_or_berry_walk_time_one_way)
                        moved += 1
                add_row(
                    f"{len(sim.vils)} ({sim.total_pop()})",
                    sim.fmt_time(),
                    "Feudal Transition",
                    f"CLICK FEUDAL AGE (-500F, 130s, {tc_pre_click_idle_s}s idle): Move 3 food vils to Wood (1st builds Barracks [-175W, 50s] -> chains House #5 [-25W, 0s walk] -> LC #1 = 7 on Wood).",
                    "20 Pop / 19v Feudal click (rule 4.6); Barracks completes ~60s into transition for 3 Militia.",
                )

        # Build Mining Camp on Gold (~35s after clicking Feudal)
        if feudal_clicked and not mc_started and sim.bank.wood >= 100 and t >= d_t(feudal_click_t + 35):
            mc_started = True
            sim.spend(ResourceBundle(wood=100), "GoldMC")
            sim.buildings.append("mining camp")
            for v in sim.vils:
                if v["role"] == "gold_ld":
                    v["role"] = "gold"
                    v["busy_until"] = t + 35
            for v in sim.vils:
                if v["role"] in ("boar", "sheep", "chicken_mill") and int(v["busy_until"]) <= t:
                    v["role"] = "gold"
                    v["busy_until"] = t + int(rules.camp_or_berry_walk_time_one_way) + 35
                    break
            add_row(
                f"{len(sim.vils)} ({sim.total_pop()})",
                sim.fmt_time(),
                "Feudal Transition",
                "Build Mining Camp on Gold (-100W, 35s) & send 2nd vil to Gold (2 on Gold).",
                "Funds 3 Militia + MAA upgrade + smooth 1-Range Archer gold.",
            )

        # Train 3 Militia during Feudal Transition
        if barracks_ready[0] is not None and t >= barracks_ready[0] and militia_trained < 3 and t >= rax_busy[0] and sim.free_pop() >= 1:
            if sim.bank.food >= 50 and sim.bank.gold >= 20:
                sim.spend(ResourceBundle(food=50, gold=20), "Militia")
                militia_trained += 1
                rax_busy[0] = t + 21
                sim.military_units["militia"] += 1
        if militia_trained == 3 and not militia_logged:
            militia_logged = True
            add_row(
                f"{len(sim.vils)} ({sim.total_pop()})",
                f"{sim.fmt_time((barracks_ready[0] or t))} – {sim.fmt_time()}",
                "Feudal Transition",
                "Train 3 Militia at Barracks (-150F, -60G total; 21s each) & march forward.",
                "All 3 Militia ready for instant MAA upgrade on Feudal arrival.",
            )

        # Rule 4.4 Houses (Feudal+): maintain 2-3 + producing_mil + extra_tcs room at completion; houses before units
        producing_mil = (
            sum(1 for x in range_ready if x is not None and t >= x)
            + sum(1 for x in stable_ready if x is not None and t >= x)
            + sum(1 for x in sw_ready if x is not None and t >= x)
            + (sum(1 for x in barracks_ready if x is not None and t >= x) if path_key == "1tc_xbow_ls_spear_ram" else 0)
        )
        extra_tcs = max(0, sim.tc_count - 1)
        need_house_room = sim.house_threshold(producing_mil, extra_tcs) + (4 if (producing_mil + extra_tcs) >= 3 else 2)
        pending_houses = sum(1 for _, p in sim.pending_pop_buildings if p == 5)
        projected_free = sim.pop_cap() + pending_houses * 5 - sim.total_pop()
        house_waiting_wood = sim.age >= 2 and projected_free <= need_house_room and pending_houses < 4 and (sim.pop_cap() + pending_houses * 5) < 200
        if house_waiting_wood and sim.bank.wood >= 25:
            sim.spend(ResourceBundle(wood=25), "House")
            comp_t = t + int(rules.house_walk_time_one_way) + 25
            sim.add_pending_pop_building(comp_t, 5, "house")
            _pull_builders(sim, ("wood", "straggler", "farm"), 1, comp_t + int(rules.house_walk_time_one_way))
        house_wood_res = 25 if house_waiting_wood else 0

        # Feudal Age TC management
        if sim.age == 2 and sim.tc_action[0] == "idle" and not castle_clicked:
            want_hold_castle = wb_started and bs_ready_t is not None and t >= bs_ready_t and sim.bank.food >= 790 and sim.bank.gold >= 195
            if want_hold_castle:
                if castle_hold_start_t is None:
                    castle_hold_start_t = t
                hold_castle = (t - castle_hold_start_t) < int(rules.max_end_of_age_tc_idle_seconds)
            else:
                hold_castle = False
            if bs_ready_t is not None and t >= bs_ready_t and sim.bank.can_afford(castle_cost):
                if castle_cmd_t is None:
                    castle_cmd_t = d_t(t)
                if t >= castle_cmd_t:
                    castle_clicked = True
                    castle_click_t = t
                    castle_click_alloc = sim.current_macro_alloc()
                    milestones["castle_click_s"] = t
                    milestones["castle_click_str"] = sim.fmt_time()
                    milestones["castle_click_vils"] = len(sim.vils)
                    milestones["castle_click_archers"] = sim.military_units["archer"]
                    sim.spend(castle_cost, "CastleClick")
                    sim.tc_busy_until[0] = t + int(castle_time)
                    sim.tc_action[0] = "castle"
                    add_row(
                        f"{len(sim.vils)} ({sim.total_pop()})",
                        f"{sim.fmt_time(feudal_loop1_start_t or feudal_click_t)} – {sim.fmt_time()}",
                        "Feudal Age",
                        "Macro Loop 2 — Scale Eco to Castle Age: Continuous Vils -> Stragglers & Farms (up to 17), Gold to 7 + Gold Mining (-100F, -75W), 1-Range Archers & Houses, Wheelbarrow (-175F, -50W) -> Click Castle Age (800F, 200G).",
                        f"Clicked Castle Age at {sim.fmt_time()} with {len(sim.vils)} vils & {sim.military_units['archer']} Archers.",
                    )
            elif not wb_started and len(sim.vils) >= 34 and sim.bank.food >= 175 and sim.bank.wood >= (50 + house_wood_res):
                wb_started = True
                sim.spend(ResourceBundle(food=175, wood=50), "Wheelbarrow")
                sim.tc_busy_until[0] = t + 75
                sim.tc_action[0] = "wheelbarrow"
            elif not hold_castle and sim.free_pop() >= 1 and sim.bank.food >= 50:
                castle_hold_start_t = None
                sim.spend(ResourceBundle(food=50), "feudal_vil")
                sim.tc_busy_until[0] = t + 25
                sim.tc_action[0] = f"vil_{next_vil_id}"
                next_vil_id += 1
            elif sim.free_pop() <= 0:
                housed_seconds += 1

        # Feudal / Castle food reserve for TC continuous villager production
        tc_f_res = 80 if sim.age <= 2 else ((130 * sim.tc_count + 70) if sim.tc_count >= 2 else 200)
        if sim.age == 2:
            queue_upg("horse collar", res_food=tc_f_res, res_wood=house_wood_res)
        if sim.age == 2 and not bs_started and range_ready[0] is not None and t >= range_ready[0] and sim.bank.wood >= (150 + house_wood_res):
            bs_started = True
            sim.spend(ResourceBundle(wood=150), "Blacksmith")
            sim.buildings.append("blacksmith")
            bs_ready_t = t + 10 + 40
            _pull_builders(sim, ("wood", "straggler"), 1, bs_ready_t + 10)
        if bs_ready_t is not None and t >= bs_ready_t and "fletching" not in started_upgs:
            if queue_upg("fletching", res_food=tc_f_res):
                milestones["fletching_str"] = sim.fmt_time(t + 30)
        if sim.age == 2 and "fletching" in started_upgs and sim.count_role("gold", "gold_ld") >= 6:
            queue_upg("gold mining", res_food=tc_f_res, res_wood=house_wood_res)

        if sim.age == 2 and not feudal_loop1_logged and len(sim.vils) >= 29 and "fletching" in started_upgs:
            feudal_loop1_logged = True
            feudal_loop1_start_t = t
            add_row(
                f"20–{len(sim.vils)} ({sim.total_pop()})",
                f"{sim.fmt_time(feudal_click_t + 130)} – {sim.fmt_time()}",
                "Feudal Age",
                "Macro Loop 1 — Setup Archers & Blacksmith: Continuous Vils -> Gold to 4, Wood to 8; Horse Collar (-75F, -75W), Blacksmith (-150W) -> Fletching (-100F, -50G); 1-Range Archers; finishing food vils -> Stragglers & Farms every 60W.",
                "Never idle TC or Range #1; spare Wood goes to Farms.",
            )

        if castle_clicked and range_ready[1] is None and sim.bank.wood >= (175 + house_wood_res):
            sim.spend(ResourceBundle(wood=175), "ArcheryRange2")
            sim.buildings.append("archery range")
            range_ready[1] = t + 10 + 50
            _pull_builders(sim, ("wood", "straggler"), 1, (range_ready[1] or t) + 10)
        if castle_clicked:
            queue_upg("padded archer armor", res_food=tc_f_res)

        # Reserve calculation for Farm / LC priority
        ranged_now = sim.military_units["archer"] + sim.military_units["elephant_archer"]
        ballistics_res_now = (
            sim.age >= 3
            and "crossbowman" in sim.upgrades
            and ranged_now >= 20
            and "ballistics" not in started_upgs
            and not imp_prep_started
            and (path_key != "3tc_boom_ele_archer" or (tc3_started and ele_switch_started))
        )
        reserve_w = house_wood_res
        if sim.age == 2:
            if not bs_started and "horse collar" in started_upgs:
                reserve_w += 150
            if castle_clicked and range_ready[1] is None:
                reserve_w += 175
            if not wb_started and len(sim.vils) >= 32:
                reserve_w += 75
        else:
            if path_key == "3tc_boom_ele_archer" and not tc3_started:
                reserve_w += 275
            if sw_ready[0] is None and (
                (path_key == "1tc_xbow_lc_ram" and sim.military_units["archer"] >= 19)
                or (path_key == "1tc_xbow_ls_spear_ram" and (sim.military_units["militia"] + sim.military_units["spearman"] >= 4 or sim.military_units["archer"] >= 18))
                or (path_key == "3tc_boom_ele_archer" and sim.military_units["elephant_archer"] >= 3)
            ):
                reserve_w += 200
            if (ballistics_res_now or sw_ready[0] is not None) and not univ_started:
                reserve_w += 200
            if (ballistics_res_now and univ_started) or (univ_started and univ_ready_t and t >= univ_ready_t and not (imp_prep_started and not imp_clicked) and "ballistics" not in started_upgs):
                reserve_w += 300
            if imp_clicked and not tc3_started and sim.bank.stone >= 100 and path_key in ("1tc_xbow_lc_ram", "1tc_xbow_ls_spear_ram"):
                reserve_w += 275

        # Lowest-priority Lumber Camp refresh & density check (rule 3.4: 60-65% or >8/camp, movers pay 15s)
        active_wood_vils = sim.count_role("wood")
        camps_needed_density = max(1, (active_wood_vils + rules.max_lumberjacks_per_lc - 1) // rules.max_lumberjacks_per_lc)
        if (
            sim.age >= 2
            and sim.farms_seeded >= 3
            and (sim.min_active_camp_efficiency() <= rules.wood_refresh_lc_threshold or len(sim.lumber_camps) < camps_needed_density)
            and (t - last_lc_refresh_t) >= 90
            and sim.bank.wood >= (100 + reserve_w + 100)
        ):
            last_lc_refresh_t = t
            sim.spend(ResourceBundle(wood=100), "LumberCampRefresh")
            comp_t = t + int(rules.camp_or_berry_walk_time_one_way) + 35
            new_idx = sim.add_lumber_camp(comp_t)
            _pull_builders(sim, ("wood", "straggler"), 1, comp_t, camp_idx=new_idx)
            sim.reassign_woodcutters_to_new_camp(new_idx, min(rules.max_lumberjacks_per_lc - 1, max(3, active_wood_vils // 2)))
            milestones.setdefault("lc2_rebuilt_str", sim.fmt_time())

        # Castle & Imperial Age logic
        if sim.age >= 3:
            total_army = sum(sim.military_units.values())
            saving_for_imp = imp_prep_started and not imp_clicked

            queue_upg("crossbowman", res_food=tc_f_res)
            queue_upg("bodkin arrow", res_food=tc_f_res)
            queue_upg("bow saw", res_food=tc_f_res, res_wood=house_wood_res)

            if (
                "crossbowman" in started_upgs
                and "bodkin arrow" in started_upgs
                and "bow saw" in started_upgs
                and "castle_spike_logged" not in milestones
            ):
                milestones["castle_spike_logged"] = True
                milestones["xbow_bodkin_bowsaw_str"] = sim.fmt_time()
                spike_txt = (
                    "REACHED CASTLE AGE (+200W): Research Crossbowman (-175F, -100G, 35s), Bodkin Arrow (-200F, -100G, 35s), Bow Saw (-150F, -100W, 50s); pause Range briefly & drop TC #2 & TC #3 (-275W, -100S each)."
                    if path_key == "3tc_boom_ele_archer"
                    else "REACHED CASTLE AGE (+200W): Research Crossbowman (-175F, -100G, 35s), Bodkin Arrow (-200F, -100G, 35s), Bow Saw (-150F, -100W, 50s); keep 1 TC & 2-Range Xbows continuous."
                )
                add_row(
                    f"{len(sim.vils)} ({sim.total_pop()})",
                    sim.fmt_time(),
                    "Castle Age",
                    spike_txt,
                    "90% Castle macro efficiency buffer active (rule 8.2).",
                )

            imp_prereq_ready = sw_ready[0] is not None and t >= sw_ready[0] and univ_ready_t is not None and t >= univ_ready_t
            # Rule 5.3: only hold TC <= 5s when Imperial will be affordable within 5s
            want_hold_imp = saving_for_imp and len(sim.vils) >= 62 and sim.bank.gold >= 785 and sim.bank.food >= 975
            if want_hold_imp:
                if imp_hold_start_t is None:
                    imp_hold_start_t = t
                hold_tc_for_imp = (t - imp_hold_start_t) < int(rules.max_end_of_age_tc_idle_seconds)
            else:
                hold_tc_for_imp = False

            for ti in range(sim.tc_count):
                if sim.tc_action[ti] == "idle":
                    if ti == 0 and sim.age == 3 and not imp_clicked and imp_prep_started and imp_prereq_ready and sim.bank.can_afford(imp_cost):
                        imp_clicked = True
                        imp_click_t = t
                        milestones["imp_click_s"] = t
                        milestones["imp_click_str"] = sim.fmt_time()
                        milestones["imp_click_vils"] = len(sim.vils)
                        milestones["imp_click_army"] = current_army_dict()
                        sim.spend(imp_cost, "ImperialClick")
                        sim.tc_busy_until[ti] = t + int(imp_time)
                        sim.tc_action[ti] = "imperial"
                        saving_for_imp = False
                    elif ti == 0 and not hold_tc_for_imp and not hc_started and len(sim.vils) >= 48 and (path_key == "3tc_boom_ele_archer" or not saving_for_imp) and sim.bank.food >= (300 + 180 * sim.tc_count) and sim.bank.wood >= (200 + house_wood_res):
                        hc_started = True
                        sim.spend(ResourceBundle(food=300, wood=200), "HandCart")
                        sim.tc_busy_until[ti] = t + 55
                        sim.tc_action[ti] = "hand cart"
                    elif not hold_tc_for_imp and len(sim.vils) < vil_cap:
                        if sim.free_pop() <= 0:
                            housed_seconds += 1
                        elif sim.bank.food >= 50:
                            imp_hold_start_t = None
                            sim.spend(ResourceBundle(food=50), "vil_train")
                            sim.tc_busy_until[ti] = t + 25
                            sim.tc_action[ti] = f"vil_{next_vil_id}"
                            next_vil_id += 1

            # Castle Age buildings & upgrades
            if "crossbowman" in started_upgs and "bodkin arrow" in started_upgs and "bow saw" in started_upgs:
                sw_started = sw_ready[0] is not None
                stable_started = stable_ready[0] is not None
                hp_ok = (path_key != "3tc_boom_ele_archer") or tc3_started
                if hp_ok and not saving_for_imp and not (ballistics_prio := ballistics_res_now and univ_started):
                    queue_upg("heavy plow", res_food=tc_f_res, res_wood=house_wood_res)

                if (ballistics_res_now or sw_started) and not univ_started and sim.bank.wood >= (200 + house_wood_res):
                    univ_started = True
                    sim.spend(ResourceBundle(wood=200), "University")
                    univ_ready_t = t + 10 + 60
                    _pull_builders(sim, ("wood", "straggler"), 1, univ_ready_t + 10)
                if univ_ready_t and t >= univ_ready_t and not saving_for_imp:
                    if queue_upg("ballistics", res_wood=house_wood_res):
                        milestones["ballistics_str"] = sim.fmt_time(t + 60)

                def count_built(slots: List[Optional[int]]) -> int:
                    return sum(1 for x in slots if x is not None)

                def add_prod_building(slots: List[Optional[int]], cost_w: int, build_base_s: float) -> bool:
                    for idx_b in range(len(slots)):
                        if slots[idx_b] is None and sim.bank.wood >= (cost_w + house_wood_res):
                            sim.spend(ResourceBundle(wood=cost_w), f"ProdBldg_{cost_w}")
                            ready_t = t + 10 + int(round(build_base_s))
                            slots[idx_b] = ready_t
                            _pull_builders(sim, ("wood", "straggler"), 1, ready_t + 10)
                            return True
                    return False

                def add_tc(is_second: bool) -> Optional[int]:
                    sim.spend(ResourceBundle(wood=275, stone=100), "TC_extra")
                    tc_b = int(round(calc_construction_time(150.0, 3)))  # 90s w/ 3 builders
                    ready_t = t + 10 + tc_b
                    sim.add_pending_pop_building(ready_t, 5, "town center")
                    _pull_builders(sim, ("wood", "straggler", "gold"), 3, ready_t + 10)
                    return ready_t

                if path_key == "1tc_xbow_lc_ram":
                    if not stable_started and sim.bank.wood >= (175 + house_wood_res):
                        add_prod_building(stable_ready, 175, 50)
                    if not saving_for_imp and not (ballistics_res_now and univ_started):
                        if stable_ready[0] and t >= stable_ready[0]:
                            queue_upg("light cavalry", res_food=tc_f_res)
                        queue_upg("leather archer armor", res_food=tc_f_res)
                        queue_upg("scale barding armor", res_food=tc_f_res)
                        queue_upg("forging", res_food=tc_f_res)
                    if not sw_started and sim.military_units["archer"] >= 20 and not (ballistics_res_now and not univ_started) and sim.bank.wood >= (200 + house_wood_res):
                        add_prod_building(sw_ready, 200, 40)
                        milestones["sw_ready_str"] = sim.fmt_time(sw_ready[0] or t)
                        if not castle_loop1_logged:
                            castle_loop1_logged = True
                            add_row(
                                f"{len(sim.vils)} ({sim.total_pop()})",
                                f"{sim.fmt_time(castle_arrived_t)} – {sim.fmt_time()}",
                                "Castle Age",
                                "Macro Loop 1 — 1-TC Fast Army Ramp: Build Stable (-175W) + Heavy Plow; at 20+ Xbows prioritize University (-200W) -> Ballistics (-300W, -175G) + Siege Workshop (-200W), then scale Ranges (#3–#4) & Stable (#2) to hit 50+ army.",
                                "Prioritizes Ballistics at 20+ Xbows (rule 6.4).",
                            )
                    if sw_started and univ_started and not saving_for_imp and not ballistics_res_now:
                        if count_built(range_ready) < (5 if imp_clicked else 4) and sim.bank.wood >= (275 + house_wood_res):
                            add_prod_building(range_ready, 175, 50)
                        elif count_built(stable_ready) < 2 and sim.bank.wood >= (275 + house_wood_res):
                            add_prod_building(stable_ready, 175, 50)
                    if not ballistics_res_now and (imp_prep_started or (sw_started and univ_started and sim.bank.wood >= 450)) and not tc2_started and sim.bank.wood >= (275 + house_wood_res) and sim.bank.stone >= 100:
                        tc2_started = True
                        tc2_ready_t = add_tc(True)
                        milestones["tc2_str"] = sim.fmt_time()
                    if tc2_started and not tc3_started and sim.bank.wood >= (275 + house_wood_res) and sim.bank.stone >= 100:
                        tc3_started = True
                        tc3_ready_t = add_tc(False)
                        milestones["tc3_str"] = sim.fmt_time()
                        if not castle_loop3_logged:
                            castle_loop3_logged = True
                            add_row(
                                f"{len(sim.vils)} ({sim.total_pop()})",
                                sim.fmt_time(),
                                current_phase,
                                "Late TCs Expansion: Add TC #2 & TC #3 (-275W, -100S each, 90s w/ 3 builders) -> scale Farms (30+) & Gold (15+) into Imperial.",
                                "Dravidians starting 200 Stone funds both extra TCs with zero Stone mining.",
                            )

                elif path_key == "1tc_xbow_ls_spear_ram":
                    if barracks_ready[1] is None and sim.bank.wood >= (175 + house_wood_res):
                        add_prod_building(barracks_ready, 175, 50)
                    if not saving_for_imp and not (ballistics_res_now and univ_started):
                        queue_upg("long swordsman", res_food=tc_f_res)
                        queue_upg("pikeman", res_food=tc_f_res)
                        queue_upg("squires", res_food=tc_f_res)
                        queue_upg("scale mail armor", res_food=tc_f_res)
                        queue_upg("forging", res_food=tc_f_res)
                        queue_upg("leather archer armor", res_food=tc_f_res)
                    inf_tot = sim.military_units["militia"] + sim.military_units["spearman"]
                    if not sw_started and (inf_tot >= 4 or sim.military_units["archer"] >= 18) and not (ballistics_res_now and not univ_started) and sim.bank.wood >= (200 + house_wood_res):
                        add_prod_building(sw_ready, 200, 40)
                        milestones["sw_ready_str"] = sim.fmt_time(sw_ready[0] or t)
                        if not castle_loop1_logged:
                            castle_loop1_logged = True
                            add_row(
                                f"{len(sim.vils)} ({sim.total_pop()})",
                                f"{sim.fmt_time(castle_arrived_t)} – {sim.fmt_time()}",
                                "Castle Age",
                                "Macro Loop 1 — 1-TC 2-Rax Infantry + Xbows Ramp: Build Barracks #2 (-175W) + Heavy Plow; at 20+ Xbows prioritize University -> Ballistics + Siege Workshop; get -50% Long Swordsman, Pikeman, Squires, Scale Mail, Forging & Leather Armor.",
                                "Prioritizes Ballistics at 20+ Xbows (rule 6.4); -50% Barracks techs.",
                            )
                    if sw_started and univ_started and not saving_for_imp and not ballistics_res_now:
                        if count_built(range_ready) < (4 if imp_clicked else 3) and sim.bank.wood >= (275 + house_wood_res + reserve_w):
                            add_prod_building(range_ready, 175, 50)
                        elif count_built(barracks_ready) < (4 if imp_clicked else 3) and sim.bank.wood >= (275 + house_wood_res + reserve_w):
                            add_prod_building(barracks_ready, 175, 50)
                    if not ballistics_res_now and (imp_prep_started or (sw_started and univ_started and sim.bank.wood >= 450)) and not tc2_started and sim.bank.wood >= (275 + house_wood_res) and sim.bank.stone >= 100:
                        tc2_started = True
                        tc2_ready_t = add_tc(True)
                        milestones["tc2_str"] = sim.fmt_time()
                    if tc2_started and not tc3_started and sim.bank.wood >= (275 + house_wood_res) and sim.bank.stone >= 100:
                        tc3_started = True
                        tc3_ready_t = add_tc(False)
                        milestones["tc3_str"] = sim.fmt_time()
                        if not castle_loop3_logged:
                            castle_loop3_logged = True
                            add_row(
                                f"{len(sim.vils)} ({sim.total_pop()})",
                                sim.fmt_time(),
                                current_phase,
                                "Late TCs Expansion: Add TC #2 & TC #3 (-275W, -100S each) -> scale Farms (32+) & Gold (15+) into Imperial.",
                                "Dravidians starting 200 Stone funds both extra TCs.",
                            )

                elif path_key == "3tc_boom_ele_archer":
                    if not tc2_started and sim.bank.wood >= (275 + house_wood_res) and sim.bank.stone >= 100:
                        tc2_started = True
                        tc2_ready_t = add_tc(True)
                        milestones["tc2_str"] = sim.fmt_time()
                    if tc2_started and not tc3_started and sim.bank.wood >= (275 + house_wood_res) and sim.bank.stone >= 100:
                        tc3_started = True
                        tc3_ready_t = add_tc(False)
                        milestones["tc3_str"] = sim.fmt_time()
                    if not ele_switch_started and tc3_started and len(sim.vils) >= 54 and sim.count_role("farm") >= 27:
                        ele_switch_started = True
                        milestones["ele_switch_str"] = sim.fmt_time()
                        if not castle_loop1_logged:
                            castle_loop1_logged = True
                            add_row(
                                f"{len(sim.vils)} ({sim.total_pop()})",
                                f"{sim.fmt_time(castle_arrived_t)} – {sim.fmt_time()}",
                                "Castle Age",
                                "Macro Loop 1 — 3-TC Eco Boom: Continuous Vils across 3 TCs -> Farms to 28+ (Heavy Plow), Gold to 16–20, Wood to 14; research Hand Cart (-300F, -200W) at ~48 vils.",
                                "Defend with Xbows + MAA while 3 TCs rapidly scale.",
                            )
                    if ele_switch_started:
                        if not stable_started and sim.bank.wood >= (175 + house_wood_res):
                            add_prod_building(stable_ready, 175, 50)
                        if not saving_for_imp and not (ballistics_res_now and univ_started):
                            if stable_ready[0] and t >= stable_ready[0]:
                                queue_upg("light cavalry", res_food=tc_f_res)
                            queue_upg("leather archer armor", res_food=tc_f_res)
                            queue_upg("scale barding armor", res_food=tc_f_res)
                            if stable_ready[0] and t >= stable_ready[0]:
                                queue_upg("husbandry", res_food=tc_f_res)
                        if not sw_started and sim.military_units["elephant_archer"] >= 4 and not (ballistics_res_now and not univ_started) and sim.bank.wood >= (200 + house_wood_res):
                            add_prod_building(sw_ready, 200, 40)
                            milestones["sw_ready_str"] = sim.fmt_time(sw_ready[0] or t)
                            if not castle_loop2_logged:
                                castle_loop2_logged = True
                                add_row(
                                    f"{len(sim.vils)} ({sim.total_pop()})",
                                    f"{milestones['ele_switch_str']} – {sim.fmt_time()}",
                                    "Castle Age",
                                    "Macro Loop 2 — Multi-Range Elephant Archers + Light Cav Switch: Elephant Archers, add Stable (-175W) + University (-200W) -> Ballistics (-300W, -175G) at 20+ ranged, Siege Workshop (-200W), scale Ranges & Thumb Ring until 50+ army.",
                                    "Ballistics triggers at 20+ ranged per rule 6.4.",
                                )
                        if sw_started and univ_started and not saving_for_imp and not ballistics_res_now and len(sim.vils) >= 58:
                            if count_built(range_ready) < (5 if imp_clicked else 4) and sim.bank.wood >= (275 + house_wood_res) and sim.bank.food >= 200:
                                add_prod_building(range_ready, 175, 50)
                            elif len(sim.vils) >= 64 and count_built(stable_ready) < 2 and sim.bank.wood >= (275 + house_wood_res) and sim.bank.food >= 200:
                                add_prod_building(stable_ready, 175, 50)
                        if sw_started and not saving_for_imp and not ballistics_res_now and sim.military_units["elephant_archer"] >= 6:
                            if queue_upg("thumb ring", res_food=tc_f_res, res_wood=house_wood_res):
                                milestones["thumb_ring_str"] = sim.fmt_time(t + 45)

                if sim.age == 3 and not imp_prep_started and sw_ready[0] is not None and univ_ready_t is not None and (total_army >= 38 or t >= 1920):
                    imp_prep_started = True
                    milestones["army50_str"] = sim.fmt_time()
                    milestones["army50_vils"] = len(sim.vils)
                    milestones["army50_army"] = current_army_dict()
                    add_row(
                        f"{len(sim.vils)} ({sim.total_pop()})",
                        sim.fmt_time(),
                        "Castle Age",
                        "50+ Army Hit -> Shift Priority to Imperial Age: Pause extra military queues as needed to bank 1000F + 800G; ensure Siege Workshop & University are up, then click Imperial Age (<40:00 goal; rule 6.5).",
                        f"Army at shift: {format_army_counts(current_army_dict())}.",
                    )

                if imp_clicked or sim.age == 4:
                    if count_built(sw_ready) < 2 and sim.bank.wood >= (450 + house_wood_res):
                        add_prod_building(sw_ready, 200, 40)
                    if path_key in ("1tc_xbow_lc_ram", "3tc_boom_ele_archer"):
                        queue_upg("chain barding armor", res_food=tc_f_res)
                    if path_key in ("1tc_xbow_lc_ram", "1tc_xbow_ls_spear_ram"):
                        queue_upg("iron casting", res_food=tc_f_res)
                    if path_key == "1tc_xbow_ls_spear_ram":
                        queue_upg("chain mail armor", res_food=tc_f_res)

                if sim.age == 4:
                    if not imp_loop_logged:
                        imp_loop_logged = True
                        add_row(
                            f"{len(sim.vils)} ({sim.total_pop()})",
                            sim.fmt_time(),
                            "Imperial Age",
                            "REACHED IMPERIAL AGE (+200W Dravidians bonus!): Research Imperial unit/Blacksmith spikes and keep spending resources (<500–1000 float) on production + Armored/Siege Elephants.",
                            f"Imperial reached well before 40:00 at {sim.fmt_time()} with {len(sim.vils)} vils.",
                        )
                    if path_key in ("1tc_xbow_lc_ram", "1tc_xbow_ls_spear_ram") and queue_upg("arbalester"):
                        milestones["imp_main_unit_upg_str"] = sim.fmt_time(t + 50)
                    if path_key == "3tc_boom_ele_archer" and queue_upg("elite elephant archer"):
                        milestones["imp_main_unit_upg_str"] = sim.fmt_time(t + 70)
                    if queue_upg("bracer"):
                        milestones["bracer_str"] = sim.fmt_time(t + 40)
                    if univ_ready_t and t >= univ_ready_t and queue_upg("chemistry"):
                        milestones["chemistry_str"] = sim.fmt_time(t + 100)
                    queue_upg("ring archer armor")
                    if path_key == "1tc_xbow_ls_spear_ram":
                        queue_upg("two-handed swordsman")
                        if "two-handed swordsman" in sim.upgrades:
                            queue_upg("champion")
                        queue_upg("halberdier")
                        queue_upg("plate mail armor")
                        queue_upg("blast furnace")
                    if queue_upg("siege elephant"):
                        milestones["siege_ele_str"] = sim.fmt_time(t + 65)
                    queue_upg("two-man saw", res_wood=house_wood_res)

        # Military production
        hold_mil_for_imp = imp_prep_started and not imp_clicked
        bal_hold = bool(ballistics_res_now and univ_started and univ_ready_t and t >= univ_ready_t - 20)
        bal_w = 300 if bal_hold else 0
        bal_g = 175 if bal_hold else 0
        max_arch = 110 if (imp_clicked or sim.age == 4) else 44
        max_ele = 95 if (imp_clicked or sim.age == 4) else 22

        for ri in range(len(range_ready)):
            if range_ready[ri] is not None and t >= range_ready[ri]:
                if sim.age == 2 and t >= range_busy[ri] and sim.free_pop() >= 1 and sim.military_units["archer"] < 8:
                    fletching_res = 50 if (bs_ready_t is not None and t >= bs_ready_t and "fletching" not in started_upgs and sim.military_units["archer"] >= 2) else 0
                    castle_res = 175 if (castle_clicked and (sim.tc_busy_until[0] - t) <= 45) else 0
                    wb_w_res = 50 if (not wb_started and len(sim.vils) >= 32) else 0
                    if sim.bank.wood >= (25 + house_wood_res + wb_w_res) and sim.bank.gold >= 45 + fletching_res + castle_res:
                        sim.spend(ResourceBundle(wood=25, gold=45), "Archer")
                        sim.military_units["archer"] += 1
                        range_busy[ri] = t + 35
                elif sim.age >= 3 and "crossbowman" in sim.upgrades and not hold_mil_for_imp and sim.free_pop() >= 1 and sim.total_pop() < 197:
                    if path_key == "3tc_boom_ele_archer":
                        if ele_switch_started and t >= range_busy[ri] and sim.military_units["elephant_archer"] < max_ele:
                            if sim.bank.food >= (60 + tc_f_res) and sim.bank.gold >= (80 + bal_g):
                                sim.spend(ResourceBundle(food=60, gold=80), "EleArcher")
                                sim.military_units["elephant_archer"] += 1
                                range_busy[ri] = t + 32
                            elif sim.age == 3 and ri < 2 and not bal_hold:
                                idle_range_castle_s += 1
                    else:
                        if t >= range_busy[ri] and sim.military_units["archer"] < max_arch:
                            if sim.bank.wood >= (25 + house_wood_res + bal_w) and sim.bank.gold >= (45 + bal_g):
                                sim.spend(ResourceBundle(wood=25, gold=45), "Xbow")
                                sim.military_units["archer"] += 1
                                range_busy[ri] = t + 35
                            elif sim.age == 3 and ri < 2 and not bal_hold:
                                idle_range_castle_s += 1

        max_lc = 28 if (imp_clicked or sim.age == 4) else 10
        if not hold_mil_for_imp and sim.free_pop() >= 1 and sim.total_pop() < 197:
            for si in range(len(stable_ready)):
                if stable_ready[si] is not None and t >= stable_ready[si] and t >= stable_busy[si] and sim.military_units["light_cav"] < max_lc:
                    if sim.bank.food >= (80 + tc_f_res):
                        sim.spend(ResourceBundle(food=80), "LightCav")
                        sim.military_units["light_cav"] += 1
                        stable_busy[si] = t + 30
                    elif sim.age == 3 and si == 0:
                        idle_stable_castle_s += 1

        if path_key == "1tc_xbow_ls_spear_ram" and sim.age >= 3 and "long swordsman" in sim.upgrades and not hold_mil_for_imp and sim.free_pop() >= 1 and sim.total_pop() < 197:
            max_ls = 35 if (imp_clicked or sim.age == 4) else 15
            max_pk = 32 if (imp_clicked or sim.age == 4) else 13
            for bi in range(len(barracks_ready)):
                if barracks_ready[bi] is not None and t >= barracks_ready[bi] and t >= rax_busy[bi]:
                    if bi % 2 == 0 and sim.military_units["militia"] < max_ls and sim.bank.food >= (50 + tc_f_res) and sim.bank.gold >= 20:
                        sim.spend(ResourceBundle(food=50, gold=20), "Longsword")
                        sim.military_units["militia"] += 1
                        rax_busy[bi] = t + 21
                    elif bi % 2 == 1 and sim.military_units["spearman"] < max_pk and sim.bank.food >= (35 + tc_f_res) and sim.bank.wood >= (25 + house_wood_res):
                        sim.spend(ResourceBundle(food=35, wood=25), "Pikeman")
                        sim.military_units["spearman"] += 1
                        rax_busy[bi] = t + 22

        max_rams = 6 if (imp_clicked or sim.age == 4) else 3
        for wi in range(len(sw_ready)):
            if sw_ready[wi] is not None and t >= sw_ready[wi] and t >= sw_busy[wi] and sim.military_units["armored_elephant"] < max_rams and sim.free_pop() >= 1:
                if (not hold_mil_for_imp or sim.military_units["armored_elephant"] < 2) and sim.bank.food >= (120 + tc_f_res) and sim.bank.gold >= 95:
                    sim.spend(ResourceBundle(food=120, gold=95), "ArmoredEle")
                    sim.military_units["armored_elephant"] += 1
                    sw_busy[wi] = t + 36
                    if sim.military_units["armored_elephant"] == 3 and push_ready_t is None:
                        push_ready_t = t
                        milestones["push_ready_str"] = sim.fmt_time()
                        milestones["push_ready_vils"] = len(sim.vils)
                        milestones["push_ready_army"] = current_army_dict()
                        add_row(
                            f"{len(sim.vils)} ({sim.total_pop()})",
                            sim.fmt_time(),
                            current_phase,
                            "Siege Push Ready — Build Siege Workshop (-200W) & 3 Armored Elephants (120F, 95G each): Push with upgraded army!",
                            f"Push force: {format_army_counts(current_army_dict())}.",
                        )

        # Farm seeding (let expired farms reseed before adding new farms)
        n_farm_vils = sim.count_role("farm")
        has_expired_farm = any(f["remaining"] <= 1e-6 for f in sim.farms[:n_farm_vils])
        target_farms = 18 if sim.age == 2 else ((28 if path_key == "3tc_boom_ele_archer" else 26) if not univ_started else (40 if path_key == "3tc_boom_ele_archer" else 36))
        early_farm = sim.age == 2 and "horse collar" in started_upgs and sim.farms_seeded < 1 and t <= (range_ready[0] or 9999) - 25 and sim.bank.wood >= (60 + house_wood_res)
        later_farm = sim.age >= 2 and bs_started and not has_expired_farm and n_farm_vils < target_farms and sim.bank.wood >= (60 + reserve_w)
        if early_farm or later_farm:
            keep_wood_min = 12 if (sim.age >= 3 and not univ_started) else (6 if (sim.age >= 3 and path_key == "3tc_boom_ele_archer") else (10 if sim.age >= 3 else 5))
            for pref_roles in (("straggler",), ("wood",)):
                if pref_roles == ("wood",) and sim.count_role("wood") <= keep_wood_min:
                    continue
                placed = False
                for v in sim.vils:
                    if v["role"] in pref_roles and int(v["busy_until"]) <= t:
                        walk_t = int(rules.farm_walk_time) if v["role"] == "straggler" else int(rules.camp_or_berry_walk_time_one_way)
                        sim.spend(ResourceBundle(wood=60), "MacroFarm")
                        sim.register_new_farm(t + walk_t + 15)
                        v["role"] = "farm"
                        v["busy_until"] = t + walk_t + 15
                        placed = True
                        break
                if placed:
                    break

        # Anti-float rebalancer & dynamic Market (rules 7.2, 8.4)
        if sim.age >= 3 and t % 10 == 0:
            if market_ready_t is None and ((imp_prep_started and not imp_clicked and sim.bank.gold < 800) or sim.bank.wood >= 450) and sim.bank.wood >= (175 + reserve_w):
                sim.spend(ResourceBundle(wood=175), "Market")
                market_ready_t = t + 10 + 60
                _pull_builders(sim, ("wood", "straggler"), 1, market_ready_t + 10)

            cur_camp = max(0, len(sim.lumber_camps) - 1)
            def reallocate_vils(src_role: str, dst_role: str, keep_min: int, max_move: int = 2) -> None:
                cur_cnt = sim.count_role(src_role)
                moved_n = 0
                for v in sim.vils:
                    if moved_n >= max_move or cur_cnt <= keep_min:
                        break
                    if v["role"] == src_role and int(v["busy_until"]) <= t:
                        if dst_role == "farm":
                            cur_farms_n = sim.count_role("farm")
                            exp_farm_now = any(f["remaining"] <= 1e-6 for f in sim.farms[:cur_farms_n])
                            if not exp_farm_now and sim.bank.wood >= (60 + reserve_w) and cur_farms_n < 44:
                                sim.spend(ResourceBundle(wood=60), "RebalFarm")
                                sim.register_new_farm(t + 30)
                                v["role"] = "farm"
                                v["busy_until"] = t + 30
                            else:
                                continue
                        else:
                            v["role"] = dst_role
                            if dst_role == "wood":
                                v["camp_idx"] = cur_camp
                            v["busy_until"] = t + int(rules.site_to_site_walk_time_one_way)
                        cur_cnt -= 1
                        moved_n += 1

            is_ele_path = path_key == "3tc_boom_ele_archer"
            saving_imp_now = imp_prep_started and not imp_clicked
            w_cap = 14 if (not univ_started or ballistics_res_now) else (6 if is_ele_path else 15)
            w_min = 12 if (not univ_started or ballistics_res_now) else (3 if is_ele_path else 10)
            w_bank, f_bank, g_bank = sim.bank.wood, sim.bank.food, sim.bank.gold
            w_cur = sim.count_role("wood")

            if w_cur > w_cap or w_bank > (400 + reserve_w):
                dst = "gold" if g_bank < (820 if saving_imp_now else (450 if is_ele_path else 520)) else "farm"
                reallocate_vils("wood", dst, keep_min=w_min, max_move=3)
            g_thresh = 420 if is_ele_path else 480
            if not saving_imp_now and g_bank > g_thresh:
                if not is_ele_path and w_bank < 280 and w_cur < (w_cap + 2):
                    reallocate_vils("gold", "wood", keep_min=7, max_move=3)
                elif sim.count_role("farm") < 44 and w_bank >= (60 + reserve_w):
                    reallocate_vils("gold", "farm", keep_min=7, max_move=3)
                elif f_bank < 500 or w_cur < w_cap:
                    reallocate_vils("gold", "wood", keep_min=7, max_move=2)
            elif saving_imp_now and g_bank > 820 and f_bank < 1000:
                reallocate_vils("gold", "farm" if w_bank >= (100 + reserve_w) else "wood", keep_min=4, max_move=4)
            if not saving_imp_now and f_bank > 600 and (g_bank < 480 or (not is_ele_path and w_bank < 260)):
                reallocate_vils("farm", "wood" if (not is_ele_path and w_bank < 260) else "gold", keep_min=24, max_move=2)
            elif saving_imp_now and f_bank > 1080 and g_bank < 800:
                reallocate_vils("farm", "gold", keep_min=24, max_move=3)

            # Dynamic Market trade (rule 7.2)
            if market_ready_t is not None and t >= market_ready_t and (t - last_market_trade_t) >= 20:
                if saving_imp_now and sim.bank.wood >= 400 + reserve_w and sim.bank.gold < 800:
                    last_market_trade_t = t
                    sim.sell_at_market("wood", 100)
                elif saving_imp_now and sim.bank.food >= 1080 and sim.bank.gold < 800:
                    last_market_trade_t = t
                    sim.sell_at_market("food", 100)
                elif not saving_imp_now and sim.bank.wood >= 750 + reserve_w:
                    last_market_trade_t = t
                    sim.sell_at_market("wood", 100)
                elif not saving_imp_now and sim.bank.food >= 850 and ("siege elephant" in sim.upgrades or sim.age == 3):
                    last_market_trade_t = t
                    sim.sell_at_market("food", 100)

        is_banking_age = (sim.age == 1 and loom_done and not feudal_clicked) or (sim.age == 2 and bs_ready_t is not None and len(sim.vils) >= 32 and not castle_clicked) or (sim.age == 3 and imp_prep_started and not imp_clicked)
        if sim.age >= 3 and not is_banking_age:
            max_non_save_float["food"] = max(max_non_save_float["food"], sim.bank.food)
            max_non_save_float["wood"] = max(max_non_save_float["wood"], sim.bank.wood)
            max_non_save_float["gold"] = max(max_non_save_float["gold"], sim.bank.gold)

        # Always allow existing expired farms to reseed (reserving only house wood)
        urgent_res_w = float(house_wood_res)
        sim.tick_gather(
            boar_open=(boar1_shot and sim.active_carcass_food["boar"] > 1e-6),
            reseed_reserve_w=urgent_res_w,
            fallback_order=("boar", "chicken_mill"),
        )
        if t % 10 == 0:
            record_timeline_point()

    milestones["idle_range_castle_s"] = idle_range_castle_s
    milestones["idle_stable_castle_s"] = idle_stable_castle_s
    milestones["housed_seconds"] = housed_seconds
    milestones["tc_pre_click_idle_s"] = tc_pre_click_idle_s
    milestones["extra_tc_idle_s"] = tc_unplanned_idle_s
    milestones["negative_bank_count"] = len(sim.negative_bank_events)
    milestones["market_trades_count"] = len(sim.market_trades)
    milestones["max_non_save_float"] = {k: round(v, 1) for k, v in max_non_save_float.items()}
    milestones["final_vils"] = len(sim.vils)
    milestones["final_army"] = current_army_dict()
    milestones["final_bank"] = sim.bank.to_dict()

    if not record_outputs:
        return BuildOrderDocument("", "Dravidians", variant_label, "", [], []), milestones

    assert imp_arrived_t is not None and imp_arrived_t < 2400, f"Imperial missed <40:00: {imp_arrived_t}"
    assert housed_seconds == 0, f"Housed for {housed_seconds}s"
    assert tc_unplanned_idle_s <= int(rules.max_end_of_age_tc_idle_seconds), f"Unplanned TC idle: {tc_unplanned_idle_s}s"
    assert not sim.negative_bank_events, f"Negative bank events: {sim.negative_bank_events[:3]}"

    if path_key == "1tc_xbow_lc_ram":
        ss_items = [ContinuousProductionItem("villager", 1), ContinuousProductionItem("archer", 2), ContinuousProductionItem("scout cavalry", 1)]
        ss_title = "Steady-State (1 TC + 2-Range Xbows + 1-Stable Light Cav, w/ 10% Castle Buffer)"
    elif path_key == "1tc_xbow_ls_spear_ram":
        ss_items = [ContinuousProductionItem("villager", 1), ContinuousProductionItem("archer", 2), ContinuousProductionItem("militia", 1), ContinuousProductionItem("spearman", 1)]
        ss_title = "Steady-State (1 TC + 2-Range Xbows + 2-Rax Longswords/Pikes, w/ 10% Castle Buffer)"
    else:
        ss_items = [ContinuousProductionItem("villager", 3), ContinuousProductionItem("elephant archer", 2), ContinuousProductionItem("scout cavalry", 1)]
        ss_title = "Steady-State (3 TCs + 2-Range Ele Archers + 1-Stable Light Cav, w/ 10% Castle Buffer)"

    steady_state = planner.compute_steady_state_vils(
        items=ss_items,
        civ="Dravidians",
        age=3,
        upgrades=["double-bit axe", "bow saw", "horse collar", "wheelbarrow", "gold mining"],
        food_source="farmer",
        wood_minutes_since_lc=2.0,
    )
    steady_state["title"] = ss_title

    I = RTS_ICONS
    c_vils = int(milestones["castle_click_vils"])
    c_arch = int(milestones["castle_arrival_archers"])
    c_alloc = castle_click_alloc or {"wood": 11, "food": 17, "gold": 7, "stone": 0}
    imp_c_vils = int(milestones.get("imp_click_vils", 60))
    imp_c_str = str(milestones.get("imp_click_str", "30:00"))
    imp_r_str = str(milestones.get("imp_reached_str", "33:10"))
    a50_str = str(milestones.get("army50_str", "27:00"))
    end_alloc = sim.current_macro_alloc()
    fin_vils = int(milestones["final_vils"])

    if path_key == "1tc_xbow_lc_ram":
        castle_rts = [
            RTSOverlayStep(villager_count=c_vils, age=3, wood=c_alloc["wood"], food=c_alloc["food"], gold=c_alloc["gold"], stone=c_alloc["stone"],
                           notes=[f"Click {I['castle_age']} -> {I['build']} 2nd {I['archery_range']} & Padded Archer Armor; keep 2-Range Archers continuous.", f"Reach {I['castle_age']} (+200 {I['wood']}!): {I['crossbowman']}, {I['bodkin_arrow']}, {I['bow_saw']}."]),
            RTSOverlayStep(villager_count=48, age=3, wood=13, food=22, gold=13, stone=0,
                           notes=[f"Fast 50+ Army Ramp ({a50_str}): {I['build']} {I['stable']} + {I['heavy_plow']}; add {I['siege_workshop']} (3 Armored Elephants) + University; scale Ranges & Stable #2.", f"Hit 50+ army -> click {I['imperial_age']} (~{imp_c_str}) & drop {I['town_center']} #2/#3!"]),
            RTSOverlayStep(villager_count=fin_vils, age=4, wood=end_alloc["wood"], food=end_alloc["food"], gold=end_alloc["gold"], stone=end_alloc["stone"],
                           notes=[f"Reach {I['imperial_age']} ({imp_r_str}, +200W): Arbalester, Bracer, Chemistry, Siege Elephant & Ring Archer Armor; spend below 500-1000 float!"]),
        ]
    elif path_key == "1tc_xbow_ls_spear_ram":
        castle_rts = [
            RTSOverlayStep(villager_count=c_vils, age=3, wood=c_alloc["wood"], food=c_alloc["food"], gold=c_alloc["gold"], stone=c_alloc["stone"],
                           notes=[f"Click {I['castle_age']} -> {I['build']} 2nd {I['archery_range']} & Padded Archer Armor; keep 2-Range Archers continuous.", f"Reach {I['castle_age']} (+200 {I['wood']}!): {I['crossbowman']}, {I['bodkin_arrow']}, {I['bow_saw']}."]),
            RTSOverlayStep(villager_count=50, age=3, wood=14, food=23, gold=13, stone=0,
                           notes=[f"Fast 50+ Army Ramp ({a50_str}): {I['build']} 2nd {I['barracks']} + {I['heavy_plow']}; -50% {I['long_swordsman']}, {I['pikeman']}, Squires & Scale Mail.", f"Add {I['siege_workshop']} + University + Range #3/Rax #3; shift to {I['imperial_age']} ({imp_c_str}) + late TCs!"]),
            RTSOverlayStep(villager_count=fin_vils, age=4, wood=end_alloc["wood"], food=end_alloc["food"], gold=end_alloc["gold"], stone=end_alloc["stone"],
                           notes=[f"Reach {I['imperial_age']} ({imp_r_str}, +200W): Arbalester, Bracer, Chemistry, Champion, Halberdier & Siege Elephant."]),
        ]
    else:
        castle_rts = [
            RTSOverlayStep(villager_count=c_vils, age=3, wood=c_alloc["wood"], food=c_alloc["food"], gold=c_alloc["gold"], stone=c_alloc["stone"],
                           notes=[f"Click {I['castle_age']} -> {I['build']} 2nd {I['archery_range']} & Padded Archer Armor.", f"Reach {I['castle_age']} (+200 {I['wood']}!): {I['crossbowman']}, {I['bodkin_arrow']}, {I['bow_saw']}; drop {I['town_center']} #2 & #3!"]),
            RTSOverlayStep(villager_count=64, age=3, wood=11, food=36, gold=17, stone=0,
                           notes=[f"3-TC Boom to ~49 {I['villager']}s ({milestones.get('ele_switch_str', '23:43')}) defending with {c_arch} {I['crossbowman']}s; then {I['elephant_archer']}s + {I['light_cavalry']} + {I['siege_workshop']}!", f"Hit 50+ army ({a50_str}) -> click {I['imperial_age']} ({imp_c_str})!"]),
            RTSOverlayStep(villager_count=fin_vils, age=4, wood=end_alloc["wood"], food=end_alloc["food"], gold=end_alloc["gold"], stone=end_alloc["stone"],
                           notes=[f"Reach {I['imperial_age']} ({imp_r_str}, +200W): Elite Elephant Archer, Bracer, Chemistry, Thumb Ring, {I['ballistics']} & Siege Elephant."]),
        ]

    rts_steps = [
        RTSOverlayStep(villager_count=6, age=1, wood=0, food=6, gold=0, stone=0, notes=[f"Vils #1-#6: Build 2 Houses at 0:00, then all 6 on {I['sheep']} under TC (max 7)."]),
        RTSOverlayStep(villager_count=9, age=1, wood=3, food=6, gold=0, stone=0, notes=[f"Vils #7-#9 (3 vils) -> {I['wood']} (1st builds {I['lumber_camp']} #1)."]),
        RTSOverlayStep(villager_count=11, age=1, wood=4, food=7, gold=0, stone=0, notes=[f"Vil #10 lures 1st {I['boar']} (garrison 7 TC vils 5s on arrival); Vil #11 to {I['wood']} (4 on Wood)."]),
        RTSOverlayStep(villager_count=15, age=1, wood=4, food=11, gold=0, stone=0, notes=[f"Vils #12-#15 (4 vils) -> 6 Chickens on {I['mill']} (Vil #12 builds {I['mill']}, Vil #13 builds House #3; unlocks {I['horse_collar']} & {I['farm']}s).", f"Lure 2nd {I['boar']} dynamically before 1st finishes."]),
        RTSOverlayStep(villager_count=19, age=1, wood=4, food=14, gold=1, stone=0, notes=[f"Vils #16-#18 -> {I['boar']}/{I['sheep']} (Vil #17 builds House #4); Vil #19 -> LD {I['gold']}.", f"Research {I['loom']} -> Click {I['feudal_age']} (20 Pop / 19v; LC + Mill already built)."]),
        RTSOverlayStep(villager_count=19, age=2, wood=7, food=10, gold=2, stone=0, notes=[f"Feudal Transition: 3 food vils -> {I['wood']} (1st builds {I['barracks']} -> chains House #5); {I['build']} {I['mining_camp']} on {I['gold']}; train 3 Militia."]),
        RTSOverlayStep(villager_count=c_vils, age=2, wood=c_alloc["wood"], food=c_alloc["food"], gold=c_alloc["gold"], stone=c_alloc["stone"],
                       notes=[f"Feudal (+200W): MAA + {I['double_bit_axe']} + {I['horse_collar']} + 1st {I['archery_range']}.", f"Macro: {I['gold']} to 4, {I['wood']} to 8, {I['farm']}s to 18, 7 {I['gold']} + {I['gold_mining']}; {I['blacksmith']} -> {I['fletching']}; {I['wheelbarrow']} -> Click {I['castle_age']}."]),
        *castle_rts,
    ]

    map_tag = "6 Chickens Milled (Checked w/ 8)"
    desc = (
        f"Dravidians 20-Pop (19v) 3 MAA -> Archers ({map_tag}) — {variant_label}. "
        f"Synced to rules.md (Chicken Mill unlocks Horse Collar & Farms, drop-off round trips, 60% wood floor, dynamic Market, real tech/builder times, late-command check)."
    )

    doc = BuildOrderDocument(
        name=f"Dravidians 20-Pop MAA -> Archers ({map_tag})",
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
    configs = [
        ("1tc_xbow_lc_ram", "Path 1 (6 Chickens Milled): 1 TC -> 2-Range Xbows + Light Cav + 3 Armored Elephants", "dravidians_maa_xbow_lc_ram.json"),
        ("1tc_xbow_ls_spear_ram", "Path 2 (6 Chickens Milled): 1 TC -> 2-Range Xbows + 2-Rax Longswords/Pikes + 3 Armored Elephants", "dravidians_maa_xbow_ls_spear_ram.json"),
        ("3tc_boom_ele_archer", "Path 3 (6 Chickens Milled): 3 TC Boom First -> 2-Range Elephant Archers + Light Cav + Rams", "dravidians_maa_ele_archer_3tc_boom.json"),
    ]

    docs: List[BuildOrderDocument] = []
    for p_key, p_label, json_name in configs:
        doc, ms = run_dravidians_path(p_key, p_label)
        rob = run_late_command_checks(
            p_key,
            lambda dfn, chk, _pk=p_key, _pl=p_label: run_dravidians_path(_pk, _pl, delay_fn=dfn, chicken_override=chk, record_outputs=False)[1],
            baseline_clicks={"feudal_click_s": int(ms["feudal_click_s"]), "castle_click_s": int(ms["castle_click_s"])},
            chicken_check_counts=(8,),
        )
        ms["robustness_passed"] = rob["passed"]
        ms["robustness_details"] = rob["details"]
        assert rob["passed"], f"Robustness failed for {p_key}: {rob['failures']}"
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
        title="Dravidians 20-Pop MAA into Archers (6 Chickens Milled, Checked w/ 8) — 3 Castle Age Paths",
        output_path=OUT_DIR / "dravidian_maa_into_archers.html",
    )
    print(f"Wrote HTML report: {html_path}")


if __name__ == "__main__":
    main()

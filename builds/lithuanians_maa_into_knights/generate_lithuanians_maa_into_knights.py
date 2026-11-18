#!/usr/bin/env python3
"""
1-Second Discrete-Event Generator & Verified Exporter for:
Lithuanians 20-Pop (19-Vil) 3 MAA -> Fast Castle Priority (1 TC) -> 2-Stable Knights + 3 Monks
(Arabia: 6 Chickens on a Mill, Checked with 8 Chickens).

Generates:
1) Path 1 (1tc_fast_push): Early Feudal Berry Mill (-100W) -> skips Feudal Wheelbarrow -> 16:45 (37v)
   Castle click -> 19:25 Castle arrival -> immediate 2-Stable Knights & 20% faster 3-Monk Relic grab ->
   strictly 1-TC Castle Age (Siege Workshop + 3rd Stable + University) -> 34:50 Imperial click (38:00 arr)
   -> late Imperial TC #2/#3 (+100F each).
2) Path 2 (1tc_wb_into_3tc): Skips Berry Mill -> Horse Collar Farms + Feudal Wheelbarrow -> 17:35 (36v)
   Castle click -> 20:15 Castle arrival w/ 18 Farms -> 0s idle 2-Stable Knights + 3 Monks -> stays 1 TC
   through ~8 Knights & 3 Monks (~22:33), then scales to 3 TCs (+100F Lithuanian TC bonus each) + Hand Cart
   -> 35:40 Imperial click (38:50 arr) -> 4-Stable Cavalier/Paladin + 105 vils!
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from aoe2_data import AoE2Database, ResourceBundle, RuleConfig, calc_construction_time
from backward_planner import BackwardPlanner, ContinuousProductionItem
from exporters import (
    BuildOrderDocument,
    DetailedBuildRow,
    RTS_ICONS,
    RTSOverlayStep,
    export_build_order_html,
    export_rts_overlay_json,
    format_army_counts,
    format_vils_pop_range,
)
from sim_lithuanians_maa_into_knights import LithuaniansKnightSimulator
from simulator import run_late_command_checks

OUT_DIR = Path(__file__).resolve().parent


def _pull_builders(
    sim: LithuaniansKnightSimulator,
    roles: Tuple[str, ...],
    count: int,
    busy_until: int,
) -> int:
    pulled = 0
    for r in roles:
        for v in sim.vils:
            if v["role"] == r and int(v["busy_until"]) <= sim.time_s and pulled < count:
                v["busy_until"] = busy_until
                pulled += 1
    return pulled


def run_lithuanians_path(
    path_key: str,
    variant_label: str = "",
    delay_fn: Optional[Callable[[int], int]] = None,
    chicken_override: Optional[int] = None,
    record_outputs: bool = True,
) -> Tuple[BuildOrderDocument, Dict[str, object]]:
    """Simulates a Lithuanians 3 MAA -> 1-TC 2-Stable Knights + Monks path at 1s resolution."""
    db = AoE2Database()
    rules = RuleConfig()
    chk = rules.arabia_chicken_design_count if chicken_override is None else chicken_override
    sim = LithuaniansKnightSimulator(
        path_key=path_key,
        deer_count=0,
        chicken_count=chk,
        db=db,
        rules=rules,
    )
    planner = BackwardPlanner(db, rules)

    if not variant_label:
        variant_label = (
            "Path 1 (6 Chickens Milled): Fast Castle Priority (1 TC Push -> Fast Imp)"
            if path_key == "1tc_fast_push"
            else "Path 2 (6 Chickens Milled): Wheelbarrow Eco 1-TC -> Mid-Castle 3-TC Scale"
        )

    def d_t(planned_t: int) -> int:
        return planned_t if delay_fn is None else delay_fn(planned_t)

    is_fast = path_key == "1tc_fast_push"
    vil_cap = 92 if is_fast else 104

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
        kn_key = (
            "paladin"
            if "paladin" in sim.upgrades
            else ("cavalier" if "cavalier" in sim.upgrades else "knight")
        )
        out: Dict[str, int] = {"scout": sim.military_units["scout"]}
        if sim.military_units["militia"] > 0:
            out[inf_key] = sim.military_units["militia"]
        if sim.military_units["knight"] > 0:
            out[kn_key] = sim.military_units["knight"]
        if sim.military_units["monk"] > 0:
            out["monk"] = sim.military_units["monk"]
        if sim.military_units["mangonel"] > 0:
            out["mangonel"] = sim.military_units["mangonel"]
        if sim.military_units["battering_ram"] > 0:
            out["battering_ram"] = sim.military_units["battering_ram"]
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

    last_logged_vils = 3
    vil_spawn_pop: Dict[int, int] = {3: sim.total_pop()}

    def add_row(time_str: str, phase: str, action: str, notes: str = "") -> None:
        nonlocal last_logged_vils
        if not record_outputs:
            return
        curr_vils = len(sim.vils)
        curr_pop = sim.total_pop()
        vil_spawn_pop[curr_vils] = curr_pop
        pop_start = (
            vil_spawn_pop.get(last_logged_vils, 4)
            if len(rows) == 0
            else vil_spawn_pop.get(last_logged_vils + 1, curr_pop)
        )
        resolved_pop = format_vils_pop_range(
            last_logged_vils,
            curr_vils,
            pop_start,
            curr_pop,
            include_start_vil=(len(rows) == 0),
        )
        last_logged_vils = curr_vils
        alloc = sim.current_macro_alloc()
        fb = sim.current_food_breakdown()
        rows.append(
            DetailedBuildRow(
                pop=resolved_pop,
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

    fcost, _, _ = sim.db.get_age_advance_spec(2, "Lithuanians")
    ccost, _, _ = sim.db.get_age_advance_spec(3, "Lithuanians")
    icost, _, _ = sim.db.get_age_advance_spec(4, "Lithuanians")

    # t = 0:00 start (Rule 1.5 opening)
    sim.spend(ResourceBundle(food=50), "vil_4")
    sim.tc_busy_until[0] = 25
    sim.tc_action[0] = "vil_4"
    record_timeline_point()

    # Simulation state
    b1_arr: Optional[int] = None
    b1_shot = False
    b2_lured = False
    b2_arr: Optional[int] = None
    b2_shot = False
    loom = False
    fclick = False
    fclick_t = 0
    fcmd_t: Optional[int] = None
    f_arr: Optional[int] = None
    rax_r: Optional[int] = None
    rax_b = 0
    mil = 0
    militia_logged = False
    mc = False
    bm_s = False
    bm_r: Optional[int] = None
    s1: Optional[int] = None
    s2: Optional[int] = None
    s3: Optional[int] = None
    s4: Optional[int] = None
    bs_s = False
    bs_r: Optional[int] = None
    feudal_loop_logged = False
    feudal_loop_t = 0
    chold: Optional[int] = None
    cclick = False
    cclick_t = 0
    ccmd_t: Optional[int] = None
    c_vils = 0
    c_arr: Optional[int] = None
    c_alloc: Optional[Dict[str, int]] = None
    arr_bank: Optional[Dict[str, float]] = None
    arr_alloc: Optional[Dict[str, int]] = None
    mon_s = False
    mon_r: Optional[int] = None
    mon_b = 0.0
    monks = 0
    monks_logged = False
    knights = 0
    st_b = [0, 0, 0, 0]
    k_times: List[int] = []
    m_times: List[int] = []
    relic_targets: List[int] = []
    relic_times: List[int] = []
    sw_s = False
    sw_r: Optional[int] = None
    sw_b = 0
    univ_s = False
    univ_r: Optional[int] = None
    mkt_s = False
    mkt_r: Optional[int] = None
    upgs: set[str] = set()
    next_v = 20
    wb_s = False
    bsaw_s = False
    hc_s = False
    gm_s = False
    bl_s = False
    sb_s = False
    cb_s = False
    pb_s = False
    forg_s = False
    ic_s = False
    husb_s = False
    hp_s = False
    hc_cart_s = False
    cav_s = False
    pal_s = False
    two_man_s = False
    tc2_s = False
    tc2_r: Optional[int] = None
    tc3_s = False
    tc3_r: Optional[int] = None
    castle_boom_started = False
    mid_castle_logged = False
    mid_castle_t = 0
    imp_prep = False
    imp_hold: Optional[int] = None
    iclick = False
    iclick_t = 0
    icmd_t: Optional[int] = None
    i_arr: Optional[int] = None
    tc_pre = 0
    tc_unp = 0
    idle_st = 0
    housed = 0
    last_lc_ref = -999
    last_mkt = -999
    max_float: Dict[str, float] = {"food": 0.0, "wood": 0.0, "gold": 0.0}

    def qu(name: str, rf: float = 0.0, rw: float = 0.0, rg: float = 0.0) -> bool:
        if name in upgs or name in sim.upgrades:
            return False
        cost, rt = sim.db.get_upgrade_spec(name, "Lithuanians")
        if (
            sim.bank.food >= cost.food + rf
            and sim.bank.wood >= cost.wood + rw
            and sim.bank.gold >= cost.gold + rg
            and sim.bank.stone >= cost.stone
        ):
            upgs.add(name)
            sim.spend(cost, f"upg:{name}")
            sim.queue_upgrade(name, sim.time_s + int(round(rt)))
            return True
        return False

    max_sim_t = 2400
    for t in range(1, max_sim_t + 1):
        sim.time_s = t
        sim.in_age_transition = (fclick and sim.age == 1) or (cclick and sim.age == 2) or (iclick and sim.age == 3)
        current_phase = (
            "Dark Age"
            if (sim.age == 1 and not fclick)
            else "Feudal Transition"
            if (sim.age == 1 and fclick)
            else "Feudal Age"
            if (sim.age == 2 and not cclick)
            else "Castle Transition"
            if (sim.age == 2 and cclick)
            else "Imperial Transition"
            if (sim.age == 3 and iclick)
            else "Imperial Age"
            if sim.age == 4
            else "Castle Age"
        )

        if not iclick and sim.tc_action[0] == "idle":
            if (
                (sim.age == 1 and loom and not fclick)
                or (sim.age == 2 and (chold is not None or ccmd_t is not None) and not cclick)
                or (sim.age >= 3 and (imp_hold is not None or icmd_t is not None or len(sim.vils) >= vil_cap))
            ):
                tc_pre += 1
            else:
                tc_unp += 1

        # Boar #1 shot + garrison 7 vils for 5s (Rule 3.7)
        if b1_arr and not b1_shot and t >= b1_arr:
            b1_shot = True
            _pull_builders(sim, ("sheep", "boar"), int(rules.boar_garrison_vils), t + int(rules.boar_garrison_seconds))
            if sim.active_carcass_food["sheep"] <= 40.0:
                kept = False
                for v in sim.vils:
                    if v["role"] == "sheep":
                        if not kept and sim.active_carcass_food["sheep"] > 5.0:
                            kept = True
                        else:
                            v["role"] = "boar"
                            v["busy_until"] = max(int(v["busy_until"]), t + int(rules.tc_food_switch_walk_time))

        # Dynamic Boar #2 lure (Rule 3.7)
        if b1_shot and not b2_lured and sim.remaining_animals["boar"] >= 1:
            nb = max(1, sim.count_role("boar"))
            br = nb * sim.db.get_gather_rate("boar", civ="Lithuanians", rules=rules) + 0.40
            if sim.remaining_animals["boar"] == 1 and sim.active_carcass_food["boar"] <= br * 32.0:
                b2_lured = True
                lt = d_t(t)
                for v in sim.vils:
                    if v["role"] == "boar":
                        b2_arr = lt + int(2 * rules.boar_lure_walk_time_one_way)
                        v["busy_until"] = max(int(v["busy_until"]), b2_arr)
                        break

        if b2_arr and not b2_shot and t >= b2_arr:
            b2_shot = True
            _pull_builders(sim, ("boar", "sheep"), int(rules.boar_garrison_vils), t + int(rules.boar_garrison_seconds))

        # Relic garrisoning (Rule 7.3)
        for rt in list(relic_targets):
            if t >= rt:
                relic_targets.remove(rt)
                sim.relics_garrisoned += 1
                relic_times.append(t)

        # Complete TC #2 / TC #3 (+100F Lithuanians TC bonus per Update 81058!)
        if tc2_r and t == tc2_r:
            tc2_r = None
            sim.complete_extra_tc(t)
            milestones["tc2_ready_str"] = sim.fmt_time()
        if tc3_r and t == tc3_r:
            tc3_r = None
            sim.complete_extra_tc(t)
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
                            vil_spawn_pop[vid] = sim.total_pop()
                            if vid == 6:
                                add_row(
                                    f"00:00 – {sim.fmt_time()}",
                                    "Dark Age",
                                    "Build 2 Houses (-50W)\nAssign Vils #1–#6 -> Sheep under TC",
                                    "Lithuanians start 300F (+100F TC bonus!), 200W, 100G, 200S; +2 Sheep at 1:30 & 2:30 (Rule 1.3).",
                                )
                        elif vid == 7:
                            sim.spend(ResourceBundle(wood=100), "LC1")
                            ct = t + int(rules.camp_or_berry_walk_time_one_way) + 35
                            lc = sim.add_lumber_camp(ct)
                            sim.vils.append({"id": vid, "role": "wood", "camp_idx": lc, "busy_until": ct})
                            vil_spawn_pop[vid] = sim.total_pop()
                        elif vid in (8, 9):
                            sim.vils.append({"id": vid, "role": "wood", "camp_idx": 0, "busy_until": t + int(rules.camp_or_berry_walk_time_one_way)})
                            vil_spawn_pop[vid] = sim.total_pop()
                            if vid == 9:
                                add_row(
                                    f"01:40 – {sim.fmt_time()}",
                                    "Dark Age",
                                    "Vil #7 -> Build Lumber Camp #1 (-100W, 35s)\nAssign Vils #7–#9 -> Wood at LC #1",
                                    "15s walk to woodline; LC #1 completes at 02:30; wood decay -1%/20s down to 60% floor (Rule 3.4).",
                                )
                        elif vid == 10:
                            lt = d_t(t)
                            b1_arr = lt + int(2 * rules.boar_lure_walk_time_one_way)
                            sim.vils.append({"id": vid, "role": "boar", "busy_until": b1_arr})
                            vil_spawn_pop[vid] = sim.total_pop()
                            add_row(
                                sim.fmt_time(),
                                "Dark Age",
                                "Assign Vil #10 -> Lure Boar #1 -> Boar under TC",
                                f"15s out + 15s back; Boar #1 arrives {sim.fmt_time(b1_arr)} -> garrison 7 TC vils 5s (Rule 3.7).",
                            )
                        elif vid == 11:
                            sim.vils.append({"id": vid, "role": "wood", "camp_idx": 0, "busy_until": t + int(rules.camp_or_berry_walk_time_one_way)})
                            vil_spawn_pop[vid] = sim.total_pop()
                            add_row(sim.fmt_time(), "Dark Age", "Assign Vil #11 -> Wood at LC #1", "4 on Wood.")
                        elif vid == 12:
                            sim.spend(ResourceBundle(wood=100), "ChickenMill")
                            ct = t + int(rules.camp_or_berry_walk_time_one_way) + 35
                            sim.add_building("mill", ct)
                            sim.vils.append({"id": vid, "role": "chicken_mill", "busy_until": ct})
                            vil_spawn_pop[vid] = sim.total_pop()
                        elif vid == 13:
                            sim.spend(ResourceBundle(wood=25), "House3")
                            ct = t + int(rules.house_walk_time_one_way) + 25
                            sim.add_pending_pop_building(ct, 5, "house")
                            sim.vils.append({"id": vid, "role": "chicken_mill", "busy_until": ct + int(rules.camp_or_berry_walk_time_one_way)})
                            vil_spawn_pop[vid] = sim.total_pop()
                        elif vid in (14, 15):
                            sim.vils.append({"id": vid, "role": "chicken_mill", "busy_until": t + int(rules.camp_or_berry_walk_time_one_way)})
                            vil_spawn_pop[vid] = sim.total_pop()
                            if vid == 15:
                                add_row(
                                    f"03:45 – {sim.fmt_time()}",
                                    "Dark Age",
                                    "Vil #12 -> Build Mill (-100W, 35s) on 6 Chickens\nVil #13 -> Build House #3 (-25W)\nAssign Vils #12–#15 -> Chickens at Mill",
                                    "Milling 6 Chickens first (23.9/min vs 17.3/min Berries; Rule 3.9) + LC #1 satisfies 2 Dark Age buildings (Rule 4.6); 2nd Boar lured dynamically.",
                                )
                        elif vid == 16:
                            sim.vils.append({"id": vid, "role": "boar", "busy_until": t})
                            vil_spawn_pop[vid] = sim.total_pop()
                        elif vid == 17:
                            sim.spend(ResourceBundle(wood=25), "House4")
                            ct = t + int(rules.house_walk_time_one_way) + 25
                            sim.add_pending_pop_building(ct, 5, "house")
                            sim.vils.append({"id": vid, "role": "boar", "busy_until": ct + int(rules.house_walk_time_one_way)})
                            vil_spawn_pop[vid] = sim.total_pop()
                        elif vid == 18:
                            sim.vils.append({"id": vid, "role": "boar", "busy_until": t})
                            vil_spawn_pop[vid] = sim.total_pop()
                            add_row(
                                f"05:25 – {sim.fmt_time()}",
                                "Dark Age",
                                "Vil #17 -> Build House #4 (-25W)\nAssign Vils #16–#18 -> Boar under TC",
                                "Save Barracks wood for Feudal click; keep TC food sustained.",
                            )
                        else:
                            sim.vils.append({"id": vid, "role": "gold_ld", "busy_until": t + int(rules.camp_or_berry_walk_time_one_way)})
                            vil_spawn_pop[vid] = sim.total_pop()
                            add_row(
                                sim.fmt_time(),
                                "Dark Age",
                                "Assign Vil #19 -> Long-Distance Gold\nResearch Loom (-50G, 25s)\nClick Feudal Age (-500F, 130s)",
                                "20 Pop (19v); starting 100G + Vil #19 funds Loom (-50G), 3 Militia (-60G), and MAA (-40G).",
                            )
                        if vid < 19 and sim.bank.food >= 50:
                            sim.spend(ResourceBundle(food=50), f"v{vid+1}")
                            sim.tc_busy_until[0] = t + 25
                            sim.tc_action[0] = f"vil_{vid+1}"
                        elif vid == 19 and sim.bank.gold >= 50:
                            sim.spend(ResourceBundle(gold=50), "loom")
                            sim.tc_busy_until[0] = t + 25
                            sim.tc_action[0] = "loom"
                    elif sim.age == 2:
                        if is_fast and bm_r and sim.count_role("berries") < 4 and sim.berries_food > 50:
                            sim.vils.append({"id": vid, "role": "berries", "busy_until": t + 15})
                        elif sim.count_role("wood") < 7:
                            sim.vils.append({"id": vid, "role": "wood", "camp_idx": 0, "busy_until": t + 15})
                        elif sim.count_role("gold", "gold_ld") < 2:
                            sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                        else:
                            sim.vils.append({"id": vid, "role": "straggler" if sim.straggler_wood > 10 else "wood", "camp_idx": 0, "busy_until": t + int(rules.straggler_walk_time)})
                        vil_spawn_pop[vid] = sim.total_pop()
                    else:
                        g_c = sim.count_role("gold")
                        w_c = sim.count_role("wood")
                        f_c = sim.count_role("farm")
                        cur_camp = max(0, len(sim.lumber_camps) - 1)
                        save_imp_now = imp_prep and not iclick
                        bldgs_done = bool(univ_s and sw_s and (mkt_s or is_fast))
                        f_tgt = (27 if not bldgs_done else (29 if not iclick else 36)) if is_fast else (25 if not bldgs_done else (34 if not iclick else 46))
                        g_tgt = (12 if f_c < 23 else 14) if (not imp_prep and is_fast) else (18 if (not is_fast and tc3_s and not imp_prep) else (15 if not imp_prep else (20 if save_imp_now else (22 if is_fast else 24))))
                        if is_fast:
                            w_tgt = 17 if (f_c >= 19 and not mon_s) else (15 if (f_c >= 20 and not bldgs_done) else (12 if not bldgs_done else (12 if not iclick else 15)))
                        else:
                            w_tgt = 24 if (castle_boom_started and not bldgs_done) else (15 if not iclick else 17)
                        rw_b = (175 if s2 is None else 0) + (175 if (not mon_s and (not is_fast or (bsaw_s and f_c >= 18))) else 0) + (275 if (not is_fast and castle_boom_started and not tc3_s and sim.bank.stone >= 100) else 0)
                        hold_new_farms_for_tc = (not is_fast and castle_boom_started and not tc3_s and sim.bank.stone >= 100)
                        hold_new_farms_for_imp_bldgs = (not bldgs_done and f_c >= (27 if is_fast else 25))
                        if f_c < (26 if is_fast else 23) and not save_imp_now and not hold_new_farms_for_tc and sim.bank.wood >= 60 + rw_b and (w_c >= 8 or f_c < 20):
                            sim.spend(ResourceBundle(wood=60), "CF")
                            sim.register_new_farm(t + 17)
                            sim.vils.append({"id": vid, "role": "farm", "busy_until": t + 17})
                        elif is_fast and f_c < 25 and g_c >= 12:
                            sim.vils.append({"id": vid, "role": "wood", "camp_idx": cur_camp, "busy_until": t + 15})
                        elif g_c < (12 if (is_fast and f_c < 23) else (14 if is_fast else 13)):
                            sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                        elif w_c < w_tgt:
                            sim.vils.append({"id": vid, "role": "wood", "camp_idx": cur_camp, "busy_until": t + 15})
                        elif g_c < g_tgt and sim.bank.gold < (780 if save_imp_now else 550):
                            sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                        elif f_c < f_tgt and not hold_new_farms_for_tc and not hold_new_farms_for_imp_bldgs and sim.bank.wood >= 60 + rw_b and sim.bank.food < 1100:
                            sim.spend(ResourceBundle(wood=60), "CF2")
                            sim.register_new_farm(t + 17)
                            sim.vils.append({"id": vid, "role": "farm", "busy_until": t + 17})
                        else:
                            sim.vils.append({"id": vid, "role": "wood" if (not bldgs_done or sim.bank.gold >= 600) else "gold", "camp_idx": cur_camp, "busy_until": t + 15})
                        vil_spawn_pop[vid] = sim.total_pop()
                elif act == "loom":
                    loom = True
                elif act == "feudal":
                    sim.age = 2
                    f_arr = t
                    milestones["feudal_arrival_str"] = sim.fmt_time()
                    sim.spend(ResourceBundle(food=50), "fv")
                    sim.tc_busy_until[0] = t + 25
                    sim.tc_action[0] = f"vil_{next_v}"
                    next_v += 1
                    if qu("man-at-arms"):
                        milestones["maa_queued_str"] = sim.fmt_time()
                    if "man-at-arms" in upgs:
                        qu("double-bit axe", rf=50)
                    add_row(
                        sim.fmt_time(),
                        "Feudal Age",
                        "Reach Feudal Age\nResearch Man-at-Arms (-100F, -40G), Double-Bit Axe (-100F, -50W), Horse Collar (-75F, -75W)\nAttack with 3 MAA + Scout",
                        "Feudal eco efficiency 92% (Rule 8.2); Stable #1 + Blacksmith satisfy Castle Age building req.",
                    )
                elif act == "wheelbarrow":
                    sim.upgrades.add("wheelbarrow")
                elif act == "hand cart":
                    sim.upgrades.add("hand cart")
                elif act == "castle":
                    sim.age = 3
                    c_arr = t
                    arr_bank = sim.bank.to_dict()
                    arr_alloc = sim.current_macro_alloc()
                    milestones["castle_arrival_s"] = t
                    milestones["castle_arrival_str"] = sim.fmt_time()
                    milestones["castle_arrival_bank"] = arr_bank
                    milestones["castle_arrival_alloc"] = arr_alloc
                    sim.spend(ResourceBundle(food=50), "cv")
                    sim.tc_busy_until[0] = t + 25
                    sim.tc_action[0] = f"vil_{next_v}"
                    next_v += 1
                    trans_upgs = "Build Stable #2 (-175W, ready before arrival)"
                    if not is_fast:
                        trans_upgs += "\nResearch Scale Barding (-150F) & Bloodlines (-150F, -100G)"
                    add_row(
                        f"{sim.fmt_time(cclick_t)} – {sim.fmt_time()}",
                        "Castle Transition",
                        f"{trans_upgs}\nMove Gold to ~{arr_alloc['gold']}, Farms to {sim.count_role('farm')}\nReach Castle Age!",
                        f"Bank on arrival: {int(arr_bank['food'])}F, {int(arr_bank['wood'])}W, {int(arr_bank['gold'])}G; ready for immediate 2-Stable Knights!",
                    )
                elif act == "imperial":
                    sim.age = 4
                    i_arr = t
                    milestones["imp_reached_s"] = t
                    milestones["imp_reached_str"] = sim.fmt_time()
                    extra_imp = (
                        "Drop TC #2 & TC #3 (+100F each)"
                        if is_fast
                        else "Finish Chemistry & add 4th Stable (-175W)"
                    )
                    add_row(
                        f"{sim.fmt_time(iclick_t)} – {sim.fmt_time()}",
                        "Imperial Transition",
                        f"Reach Imperial Age!\nQueue Cavalier (-300F, -300G) -> Paladin (-1300F, -750G) & Plate Barding (-350F, -200G)\nResearch Two-Man Saw; {extra_imp}",
                        f"Castle macro efficiency 90% (Rule 8.2); {len(sim.vils)} vils pushing Imperial power spike.",
                    )

        # Dark -> Feudal click
        if loom and not fclick and sim.tc_action[0] == "idle":
            if fcmd_t is None and sim.bank.can_afford(fcost):
                fcmd_t = d_t(t)
            if fcmd_t is not None and t >= fcmd_t and sim.bank.can_afford(fcost):
                fclick = True
                sim.feudal_clicked = True
                fclick_t = t
                milestones["feudal_click_s"] = t
                milestones["feudal_click_str"] = sim.fmt_time()
                sim.spend(fcost, "FeudalClick")
                sim.tc_busy_until[0] = t + 130
                sim.tc_action[0] = "feudal"
                m = 0
                for v in sim.vils:
                    if v["role"] in ("boar", "sheep", "chicken_mill") and int(v["busy_until"]) <= t and m < 3:
                        if m == 0:
                            sim.spend(ResourceBundle(wood=200), "Barracks+House5")
                            rax_r = t + 60
                            sim.add_building("barracks", rax_r)
                            sim.add_pending_pop_building(rax_r + 25, 5, "house")
                            v["role"] = "wood"
                            v["camp_idx"] = 0
                            v["busy_until"] = rax_r + 40
                        else:
                            v["role"] = "wood"
                            v["camp_idx"] = 0
                            v["busy_until"] = t + 15
                        m += 1

        if fclick and not mc and sim.bank.wood >= 100 and t >= d_t(fclick_t + 35):
            mc = True
            sim.spend(ResourceBundle(wood=100), "MiningCamp")
            sim.buildings.append("mining camp")
            for v in sim.vils:
                if v["role"] == "gold_ld":
                    v["role"] = "gold"
                    v["busy_until"] = t + 35
            for v in sim.vils:
                if v["role"] in ("boar", "sheep", "chicken_mill") and int(v["busy_until"]) <= t:
                    v["role"] = "gold"
                    v["busy_until"] = t + 50
                    break

        if is_fast and fclick and mc and not bm_s and sim.bank.wood >= 100 and t >= d_t(fclick_t + 70):
            bm_s = True
            sim.spend(ResourceBundle(wood=100), "BerryMill")
            bm_r = t + 50
            mb = 0
            for v in sim.vils:
                if v["role"] in ("sheep", "boar", "chicken_mill", "straggler") and int(v["busy_until"]) <= t and mb < 4:
                    v["role"] = "berries"
                    v["busy_until"] = bm_r if mb == 0 else t + 15
                    mb += 1

        if rax_r and t >= rax_r and mil < 3 and t >= rax_b:
            sim.spend(ResourceBundle(food=50, gold=20), "Militia")
            mil += 1
            rax_b = t + 21
            sim.military_units["militia"] += 1
            if mil == 3 and not militia_logged:
                militia_logged = True
                berry_note = "\nBuild 1st Berry Mill (-100W) -> 4 Food vils to Berries" if is_fast else ""
                add_row(
                    f"{sim.fmt_time(fclick_t)} – {sim.fmt_time()}",
                    "Feudal Transition",
                    f"Move 3 TC food vils -> Wood (1st builds Barracks -175W -> chains House #5 -25W)\nLD Gold vil builds Mining Camp (-100W) + 1 Food vil -> Gold (2 Gold){berry_note}\nTrain 3 Militia (-150F, -60G)",
                    f"Barracks completes {sim.fmt_time(rax_r)}; 3 Militia rally forward cleanly into Feudal arrival.",
                )

        # Dynamic housing (Rule 4.4)
        prod_m = (
            (1 if s1 and t >= s1 else 0)
            + (1 if s2 and t >= s2 else 0)
            + (1 if s3 and t >= s3 else 0)
            + (1 if s4 and t >= s4 else 0)
            + (1 if mon_r and t >= mon_r else 0)
            + (1 if sw_r and t >= sw_r else 0)
        )
        extra_tcs = max(0, sim.tc_count - 1)
        need_r = sim.house_threshold(prod_m, extra_tcs) + (6 if (prod_m + extra_tcs) >= 3 else 2)
        pend_h = sum(1 for _, p in sim.pending_pop_buildings if p == 5)
        h_wait = fclick and (sim.pop_cap() + pend_h * 5 - sim.total_pop()) <= need_r and pend_h < 6 and (sim.pop_cap() + pend_h * 5) < 200
        if h_wait and sim.bank.wood >= 25:
            sim.spend(ResourceBundle(wood=25), "House")
            hc = t + 30
            sim.add_pending_pop_building(hc, 5, "house")
            _pull_builders(sim, ("wood", "straggler", "farm"), 1, hc + 5)
        h_res = 25 if h_wait else 0

        # Feudal Age macro & buildings
        if sim.age == 2 and not cclick:
            if qu("man-at-arms"):
                milestones["maa_queued_str"] = sim.fmt_time()
            if "man-at-arms" in upgs:
                qu("double-bit axe", rf=50)
            if "double-bit axe" in upgs:
                qu("horse collar", rf=60, rw=h_res)
            if s1 is None and (not is_fast or bm_s) and sim.bank.wood >= 175 + h_res:
                sim.spend(ResourceBundle(wood=175), "Stable1")
                s1 = t + 60
                sim.add_building("stable", s1)
                _pull_builders(sim, ("wood", "straggler"), 1, s1 + 10)
            bs_farm_req = 2 if is_fast else 5
            if s1 is not None and not bs_s and (sim.count_role("farm") >= bs_farm_req or sim.bank.food >= 550) and sim.bank.wood >= 150 + h_res:
                bs_s = True
                sim.spend(ResourceBundle(wood=150), "Blacksmith")
                bs_r = t + 50
                sim.add_building("blacksmith", bs_r)
                _pull_builders(sim, ("wood", "straggler"), 1, bs_r + 10)
                if not feudal_loop_logged:
                    feudal_loop_logged = True
                    feudal_loop_t = t
                    add_row(
                        f"{sim.fmt_time(f_arr or 555)} – {sim.fmt_time()}",
                        "Feudal Age",
                        f"Build Stable #1 (-175W) & Blacksmith (-150W)\nSeed Farms w/ Horse Collar (continuous Wood -> Farms)",
                        "Two Feudal buildings (Stable + Blacksmith) unlock Castle Age without wasting wood on a Range/Market.",
                    )

            rw_b = (175 if s1 is None else 0) + (150 if (not bs_s and (sim.count_role("farm") >= bs_farm_req or sim.bank.food >= 550)) else 0)
            stop_f = sim.bank.food >= 680 and sim.count_role("farm") >= 10
            feudal_f_cap = 15 if is_fast else 16
            if not stop_f and sim.count_role("farm") < feudal_f_cap and sim.bank.wood >= 60 + h_res + rw_b:
                for pref in (("straggler",), ("wood",)):
                    if pref == ("wood",) and sim.count_role("wood") <= 6:
                        continue
                    pl = False
                    for v in sim.vils:
                        if v["role"] in pref and int(v["busy_until"]) <= t:
                            wt = 2 if v["role"] == "straggler" else 15
                            sim.spend(ResourceBundle(wood=60), "FeudalFarm")
                            sim.register_new_farm(t + wt + 15)
                            v["role"] = "farm"
                            v["busy_until"] = t + wt + 15
                            pl = True
                            break
                    if pl:
                        break

            if sim.tc_action[0] == "idle":
                bldgs_ok = s1 and t >= s1 and bs_r and t >= bs_r
                wb_ok = is_fast or wb_s
                min_cv = 37 if is_fast else 33
                want_h = bldgs_ok and wb_ok and len(sim.vils) >= min_cv and sim.bank.food >= 780 and sim.bank.gold >= 195
                if want_h:
                    if chold is None:
                        chold = t
                    hc_flag = (t - chold) < 5
                else:
                    hc_flag = False
                if bldgs_ok and wb_ok and len(sim.vils) >= min_cv and sim.bank.can_afford(ccost):
                    if ccmd_t is None:
                        ccmd_t = d_t(t)
                    if t >= ccmd_t:
                        cclick = True
                        cclick_t = t
                        c_vils = len(sim.vils)
                        c_alloc = sim.current_macro_alloc()
                        milestones["castle_click_s"] = t
                        milestones["castle_click_str"] = sim.fmt_time()
                        milestones["castle_click_vils"] = c_vils
                        sim.spend(ccost, "CastleClick")
                        sim.tc_busy_until[0] = t + 160
                        sim.tc_action[0] = "castle"
                        wb_note = (
                            "Skip Feudal Wheelbarrow for earliest 19:25 Castle spike"
                            if is_fast
                            else "Research Wheelbarrow (-175F, -50W) at 31 vils for Castle economy"
                        )
                        add_row(
                            f"{sim.fmt_time(feudal_loop_t or f_arr or 555)} – {sim.fmt_time()}",
                            "Feudal Age",
                            f"{wb_note}\nRamp Farms to {sim.count_role('farm')}; Click Castle Age (-800F, -200G, 160s)",
                            f"Click Castle Age at {c_vils} vils ({sim.fmt_time()}).",
                        )
                        tgt_g_trans = 10 if is_fast else 12
                        need_g = max(0, tgt_g_trans - sim.count_role("gold"))
                        mg = 0
                        for v in sim.vils:
                            if v["role"] in ("straggler", "wood", "berries", "sheep") and int(v["busy_until"]) <= t and mg < need_g:
                                if v["role"] == "wood" and sim.count_role("wood") <= (11 if is_fast else 9):
                                    continue
                                v["role"] = "gold"
                                v["busy_until"] = t + 15
                                mg += 1
                elif not is_fast and not wb_s and len(sim.vils) >= 31 and sim.bank.food >= 175 and sim.bank.wood >= 50 + h_res:
                    wb_s = True
                    sim.spend(ResourceBundle(food=175, wood=50), "Wheelbarrow")
                    sim.tc_busy_until[0] = t + 75
                    sim.tc_action[0] = "wheelbarrow"
                elif not hc_flag and sim.free_pop() >= 1 and sim.bank.food >= 50:
                    chold = None
                    sim.spend(ResourceBundle(food=50), "vil_f")
                    sim.tc_busy_until[0] = t + 25
                    sim.tc_action[0] = f"vil_{next_v}"
                    next_v += 1

        # Castle Age transition
        if cclick and sim.age == 2:
            if not hc_s:
                hc_s = qu("horse collar", rw=h_res)
            if s2 is None and sim.bank.wood >= 175 + h_res:
                sim.spend(ResourceBundle(wood=175), "Stable2")
                s2 = t + 60
                sim.add_building("stable", s2)
                milestones["s2_ready_str"] = sim.fmt_time(s2)
                _pull_builders(sim, ("wood", "straggler"), 1, s2 + 10)
            if not gm_s:
                gm_s = qu("gold mining", rf=150, rw=h_res)
            if not is_fast:
                if bs_r and t >= bs_r and not sb_s and sim.count_role("farm") >= 16:
                    sb_s = qu("scale barding armor", rf=250)
                if s1 and t >= s1 and not bl_s and sim.count_role("farm") >= 17:
                    bl_s = qu("bloodlines", rf=250, rg=200)
            trans_farm_cap = 18
            rw_m = 175 if s2 is None else (175 if sim.count_role("farm") >= 17 else 0)
            if sim.count_role("farm") < trans_farm_cap and sim.bank.wood >= 60 + h_res + rw_m:
                for pref in (("berries",), ("straggler",), ("wood",)):
                    if pref == ("berries",) and (sim.berries_food > 120 or not is_fast):
                        continue
                    if pref == ("wood",) and sim.count_role("wood") <= (12 if is_fast else 8):
                        continue
                    pl = False
                    for v in sim.vils:
                        if v["role"] in pref and int(v["busy_until"]) <= t:
                            wt = 2 if v["role"] == "straggler" else 15
                            sim.spend(ResourceBundle(wood=60), "TransFarm")
                            sim.register_new_farm(t + wt + 15)
                            v["role"] = "farm"
                            v["busy_until"] = t + wt + 15
                            pl = True
                            break
                    if pl:
                        break

        # Castle & Imperial Age
        if sim.age >= 3:
            if s2 is None and sim.bank.wood >= 175 + h_res:
                sim.spend(ResourceBundle(wood=175), "Stable2")
                s2 = t + 60
                sim.add_building("stable", s2)
                milestones["s2_ready_str"] = sim.fmt_time(s2)
                _pull_builders(sim, ("wood", "straggler"), 1, s2 + 10)
            if not bsaw_s and (knights >= 2 or sim.bank.food >= 280):
                bsaw_s = qu("bow saw", rf=150, rw=h_res + (175 if (not is_fast and not mon_s) else 0))
            if s2 and not mon_s and knights >= (4 if is_fast else 2) and (not is_fast or sim.count_role("farm") >= 18) and sim.bank.wood >= 175 + h_res:
                mon_s = True
                sim.spend(ResourceBundle(wood=175), "Monastery")
                mon_r = t + 50
                sim.add_building("monastery", mon_r)
                milestones["monastery_ready_str"] = sim.fmt_time(mon_r)
                _pull_builders(sim, ("wood", "straggler"), 1, mon_r + 10)

            save_imp = imp_prep and not iclick
            next_bldg_w = 0
            if not bsaw_s:
                next_bldg_w += 100
            elif not mon_s and (not is_fast or (knights >= 4 and sim.count_role("farm") >= 18)):
                next_bldg_w += 175
            elif not is_fast and castle_boom_started and (not tc2_s or not tc3_s) and sim.bank.stone >= 100:
                next_bldg_w += 275
            elif is_fast and knights >= 8 and sim.count_role("farm") >= 25 and not sw_s:
                next_bldg_w += 200
            elif is_fast and sw_s and not univ_s:
                next_bldg_w += 200
            elif is_fast and univ_s and knights >= 14 and s3 is None:
                next_bldg_w += 175
            elif not is_fast and tc3_s and not univ_s:
                next_bldg_w += 200
            elif not is_fast and univ_s and not sw_s:
                next_bldg_w += 200
            elif univ_s and not mkt_s:
                next_bldg_w += 175
            rw_c = h_res + next_bldg_w

            bldgs_done_w = bool(univ_s and sw_s and (mkt_s or is_fast))
            f_cap = (27 if not bldgs_done_w else (29 if not imp_prep else 36)) if is_fast else (25 if not bldgs_done_w else (34 if not iclick else 42))
            hold_f_tc = (not is_fast and castle_boom_started and not tc3_s and sim.bank.stone >= 100) or (not bldgs_done_w and sim.count_role("farm") >= (27 if is_fast else 25))
            if sim.count_role("farm") < f_cap and not save_imp and not hold_f_tc and sim.bank.wood >= 60 + rw_c and sim.bank.food < 1100:
                for pref in (("straggler",), ("wood",)):
                    if pref == ("wood",) and sim.count_role("wood") <= (10 if not bldgs_done_w else (8 if is_fast else 11)):
                        continue
                    pl = False
                    for v in sim.vils:
                        if v["role"] in pref and int(v["busy_until"]) <= t:
                            wt = 2 if v["role"] == "straggler" else 15
                            sim.spend(ResourceBundle(wood=60), "CastleFarm")
                            sim.register_new_farm(t + wt + 15)
                            v["role"] = "farm"
                            v["busy_until"] = t + wt + 15
                            pl = True
                            break
                    if pl:
                        break

            # Path 2 scales to 3 TCs after ~8 Knights & 3 Monks on 1 TC (+100F Lithuanian TC bonus per TC!)
            if not is_fast and not castle_boom_started and knights >= 8 and monks >= 3:
                castle_boom_started = True
                milestones["tc_boom_start_str"] = sim.fmt_time()
            if not is_fast and castle_boom_started:
                if not tc2_s and sim.bank.wood >= 275 + h_res and sim.bank.stone >= 100:
                    tc2_s = True
                    sim.spend(ResourceBundle(wood=275, stone=100), "TC2")
                    tc2_r = t + 10 + int(round(calc_construction_time(150.0, 3)))
                    sim.add_pending_pop_building(tc2_r, 5, "town center")
                    _pull_builders(sim, ("wood", "farm"), 3, tc2_r + 10)
                if tc2_s and not tc3_s and sim.bank.wood >= 275 + h_res and sim.bank.stone >= 100:
                    tc3_s = True
                    sim.spend(ResourceBundle(wood=275, stone=100), "TC3")
                    tc3_r = t + 10 + int(round(calc_construction_time(150.0, 3)))
                    sim.add_pending_pop_building(tc3_r, 5, "town center")
                    _pull_builders(sim, ("wood", "farm"), 3, tc3_r + 10)

            need_tc_w = 275 if (not is_fast and castle_boom_started and not tc3_s and sim.bank.stone >= 100) else 0
            if (is_fast and mon_s and knights >= 8 and sim.count_role("farm") >= 25 and not sw_s) or (not is_fast and tc3_s and univ_s and not sw_s):
                if sim.bank.wood >= 200 + h_res + need_tc_w:
                    sw_s = True
                    sim.spend(ResourceBundle(wood=200), "SiegeWorkshop")
                    sw_r = t + 50
                    sim.add_building("siege workshop", sw_r)
                    milestones["sw_ready_str"] = sim.fmt_time(sw_r)
                    _pull_builders(sim, ("wood", "straggler"), 1, sw_r + 10)
            if ((is_fast and univ_s and knights >= 14) or (not is_fast and iclick)) and s3 is None and sim.bank.wood >= 175 + h_res + need_tc_w:
                s3 = t + 60
                sim.spend(ResourceBundle(wood=175), "Stable3")
                sim.add_building("stable", s3)
                _pull_builders(sim, ("wood", "straggler"), 1, s3 + 10)
            if ((is_fast and sw_s) or (not is_fast and tc3_s)) and not univ_s and sim.bank.wood >= 200 + h_res + need_tc_w:
                univ_s = True
                sim.spend(ResourceBundle(wood=200), "University")
                univ_r = t + 60
                sim.add_building("university", univ_r)
                milestones["univ_ready_str"] = sim.fmt_time(univ_r)
                _pull_builders(sim, ("wood", "straggler"), 1, univ_r + 10)
            if univ_s and sw_s and not mkt_s and sim.bank.wood >= 175 + h_res + need_tc_w:
                mkt_s = True
                sim.spend(ResourceBundle(wood=175), "Market")
                mkt_r = t + 70
                sim.add_building("market", mkt_r)
                _pull_builders(sim, ("wood", "straggler"), 1, mkt_r + 10)
            if ((is_fast and (iclick or sim.age == 4)) or (not is_fast and s3 and sim.age == 4)) and s4 is None and sim.bank.wood >= 175 + h_res:
                s4 = t + 60
                sim.spend(ResourceBundle(wood=175), "Stable4")
                sim.add_building("stable", s4)
                _pull_builders(sim, ("wood", "straggler"), 1, s4 + 10)

            if sim.age == 3 and not imp_prep and knights >= (14 if is_fast else 10) and monks >= 3 and univ_r and t >= univ_r and sw_r and t >= sw_r and (is_fast or (tc3_s and tc3_r is None and len(sim.vils) >= 54)):
                imp_prep = True

            if not mid_castle_logged and monks_logged and univ_s and sw_s and (is_fast or (tc3_s and tc3_r is None)):
                mid_castle_logged = True
                mid_castle_t = t
                if is_fast:
                    add_row(
                        f"{sim.fmt_time(m_times[-1])} – {sim.fmt_time()}",
                        "Castle Age",
                        "Stay strictly 1 TC; research Wheelbarrow (-175F, -50W), Chain Barding, Iron Casting, Husbandry\nAdd Siege Workshop (-200W, Mangonels), University (-200W) & 3rd Stable (-175W)",
                        "Keep 2–3 Stables pushing (+3 Relic atk Knights!) before banking for fast Imperial.",
                    )
                else:
                    add_row(
                        f"{sim.fmt_time(m_times[-1])} – {sim.fmt_time()}",
                        "Castle Age",
                        f"Add TC #2 & TC #3 (~{milestones.get('tc_boom_start_str', '22:33')}, -275W/-100S, +100F bonus each!)\nResearch Hand Cart (-300F, -200W), Heavy Plow, Chain Barding, Iron Casting, Husbandry\nBuild University (-200W) & Siege Workshop (-200W); scale Farms -> 27+",
                        f"Relic-empowered Knights defend while 3 TCs boom to ~{len(sim.vils)}+ vils.",
                    )

            if is_fast and iclick:
                if not tc2_s and sim.bank.wood >= 275 + h_res and sim.bank.stone >= 100:
                    tc2_s = True
                    sim.spend(ResourceBundle(wood=275, stone=100), "TC2")
                    tc2_r = t + 10 + int(round(calc_construction_time(150.0, 3)))
                    sim.add_pending_pop_building(tc2_r, 5, "town center")
                    _pull_builders(sim, ("wood", "farm"), 3, tc2_r + 10)
                if tc2_s and not tc3_s and sim.bank.wood >= 275 + h_res and sim.bank.stone >= 100:
                    tc3_s = True
                    sim.spend(ResourceBundle(wood=275, stone=100), "TC3")
                    tc3_r = t + 10 + int(round(calc_construction_time(150.0, 3)))
                    sim.add_pending_pop_building(tc3_r, 5, "town center")
                    _pull_builders(sim, ("wood", "farm"), 3, tc3_r + 10)

            for ti in range(sim.tc_count):
                if sim.tc_action[ti] == "idle":
                    want_imp_h = ti == 0 and sim.age == 3 and not iclick and imp_prep and sim.bank.food >= 975 and sim.bank.gold >= 785
                    if want_imp_h:
                        if imp_hold is None:
                            imp_hold = t
                        hi_flag = (t - imp_hold) < 5
                    else:
                        hi_flag = False
                    if ti == 0 and sim.age == 3 and not iclick and imp_prep and univ_r and t >= univ_r and sw_r and t >= sw_r and sim.bank.can_afford(icost):
                        if icmd_t is None:
                            icmd_t = d_t(t)
                        if t >= icmd_t:
                            iclick = True
                            iclick_t = t
                            milestones["imp_click_s"] = t
                            milestones["imp_click_str"] = sim.fmt_time()
                            milestones["imp_click_vils"] = len(sim.vils)
                            sim.spend(icost, "ImpClick")
                            sim.tc_busy_until[0] = t + 190
                            sim.tc_action[0] = "imperial"
                            span_start = mid_castle_t if mid_castle_logged else (m_times[-1] if m_times else c_arr or t)
                            add_row(
                                f"{sim.fmt_time(span_start)} – {sim.fmt_time()}",
                                "Castle Age",
                                f"Click Imperial Age (-1000F, -800G, 190s) at {len(sim.vils)} vils\nBuild Market (-175W) &{' drop TC #2/#3 ->' if is_fast else ' add 3rd Stable (-175W) ->'} Knights / Upgrades",
                                f"Market balance & 3-Relic gold income lock Imperial arrival at {sim.fmt_time(t + 190)}.",
                            )
                    elif ti == 0 and is_fast and not wb_s and not save_imp and knights >= 6 and sim.count_role("farm") >= 21 and sim.bank.food >= 320 and sim.bank.wood >= 50 + rw_c:
                        wb_s = True
                        sim.spend(ResourceBundle(food=175, wood=50), "Wheelbarrow")
                        sim.tc_busy_until[0] = t + 75
                        sim.tc_action[0] = "wheelbarrow"
                    elif ti == 0 and wb_s and "wheelbarrow" in sim.upgrades and not hc_cart_s and not save_imp and len(sim.vils) >= 48 and sim.bank.food >= 420 and sim.bank.wood >= 200 + rw_c:
                        hc_cart_s = True
                        sim.spend(ResourceBundle(food=300, wood=200), "HandCart")
                        sim.tc_busy_until[0] = t + 55
                        sim.tc_action[0] = "hand cart"
                    elif not hi_flag and len(sim.vils) < vil_cap:
                        if sim.free_pop() <= 0:
                            housed += 1
                        elif sim.bank.food >= 50:
                            if ti == 0:
                                imp_hold = None
                            sim.spend(ResourceBundle(food=50), "vil_c")
                            sim.tc_busy_until[ti] = t + 25
                            sim.tc_action[ti] = f"vil_{next_v}"
                            next_v += 1

            monk_g_res = 100 if (mon_r and monks < 3) else 0
            tc_soon = sum(1 for ti in range(sim.tc_count) if sim.tc_action[ti] == "idle" or (sim.tc_busy_until[ti] - t) <= 14)
            tc_f_res = 50 * tc_soon
            if not save_imp and sim.total_pop() < 196:
                for si, sr in enumerate((s1, s2, s3, s4)):
                    if sr and t >= sr and t >= st_b[si] and sim.free_pop() >= 1:
                        if sim.bank.food >= 60 + tc_f_res and sim.bank.gold >= 75 + monk_g_res:
                            sim.spend(ResourceBundle(food=60, gold=75), "Knight")
                            knights += 1
                            sim.military_units["knight"] += 1
                            st_b[si] = t + (23 if "conscription" in sim.upgrades else 30)
                            k_times.append(t)
                        elif si < 2 and c_arr and t >= c_arr + 5 and not iclick and monks >= 3 and sim.age == 3 and (is_fast or not castle_boom_started):
                            idle_st += 1

            if mon_r and t >= mon_r and monks < 3 and t >= mon_b and sim.free_pop() >= 1 and sim.bank.gold >= 100:
                sim.spend(ResourceBundle(gold=100), "Monk")
                monks += 1
                sim.military_units["monk"] += 1
                mon_b = t + 42.5  # Lithuanians 20% faster Monastery: 51s / 1.2 = 42.5s!
                m_times.append(t)
                relic_targets.append(t + 43 + 70 + (monks - 1) * 15)
                if monks == 3 and not monks_logged:
                    monks_logged = True
                    add_row(
                        f"{sim.fmt_time(c_arr or t)} – {sim.fmt_time()}",
                        "Castle Age",
                        f"Queue 2-Stable Knights (-60F, -75G ea) & Bow Saw (-150F, -100W)\nBuild Monastery (-175W) -> train 3 Monks (-100G ea, 20% faster 42.5s) to collect Relics\nResearch Bloodlines, Forging, Scale Barding; Farms to ~22–23",
                        f"First 4 Knights out {sim.fmt_time(k_times[0])}/{sim.fmt_time(k_times[2])}; 3 Monks out {sim.fmt_time(m_times[0])}/{sim.fmt_time(m_times[1])}/{sim.fmt_time(m_times[2])} securing +3 Knight attack Relics.",
                    )

            if sw_r and t >= sw_r and t >= sw_b and not save_imp and sim.military_units["mangonel"] < (2 if is_fast else 1) and sim.free_pop() >= 1 and sim.bank.wood >= 160 + rw_c and sim.bank.gold >= 135 + 150 + monk_g_res:
                sim.spend(ResourceBundle(wood=160, gold=135), "Mangonel")
                sim.military_units["mangonel"] += 1
                sw_b = t + 46
            if sw_r and t >= sw_r and t >= sw_b and not save_imp and sim.age == 4 and sim.military_units["battering_ram"] < 3 and sim.free_pop() >= 1 and sim.bank.wood >= 160 + h_res and sim.bank.gold >= 75:
                sim.spend(ResourceBundle(wood=160, gold=75), "BatteringRam")
                sim.military_units["battering_ram"] += 1
                sw_b = t + 36

            if not save_imp:
                st_ready_f = 60 * sum(1 for si, sr in enumerate((s1, s2, s3)) if sr and t >= sr and st_b[si] - t <= 20)
                st_ready_g = 75 * sum(1 for si, sr in enumerate((s1, s2, s3)) if sr and t >= sr and st_b[si] - t <= 20)
                k_f_res = max(140, st_ready_f) + tc_f_res
                k_g_res = max(200, st_ready_g) + monk_g_res
                if bs_r and knights >= 4:
                    if not sb_s:
                        sb_s = qu("scale barding armor", rf=k_f_res)
                    else:
                        cb_s = qu("chain barding armor", rf=k_f_res, rg=k_g_res) or cb_s
                    forg_s = qu("forging", rf=k_f_res) or forg_s
                    if forg_s and "forging" in sim.upgrades:
                        ic_s = qu("iron casting", rf=k_f_res, rg=k_g_res) or ic_s
                if s1 and knights >= 4 and not bl_s:
                    bl_s = qu("bloodlines", rf=k_f_res, rg=k_g_res)
                if s1 and knights >= 8 and not husb_s:
                    husb_s = qu("husbandry", rf=k_f_res)
                if knights >= 10:
                    hp_s = qu("heavy plow", rf=k_f_res, rw=rw_c) or hp_s

            if sim.age == 4:
                cav_s = qu("cavalier") or cav_s
                if cav_s and "cavalier" in sim.upgrades:
                    pal_s = qu("paladin") or pal_s
                pb_s = qu("plate barding armor") or pb_s
                two_man_s = qu("two-man saw", rw=h_res) or two_man_s
                qu("sanctity")
                qu("fervor")
                if univ_r and t >= univ_r:
                    qu("chemistry", rf=150, rg=150)

            if t % 15 == 0 and c_arr and t >= c_arr + 60:
                if mon_s and sim.min_active_camp_efficiency() <= rules.wood_refresh_lc_threshold and t - last_lc_ref >= 180 and sim.bank.wood >= 150 + rw_c:
                    last_lc_ref = t
                    sim.spend(ResourceBundle(wood=100), "LCRefresh")
                    nc = sim.add_lumber_camp(t + 50)
                    sim.reassign_woodcutters_to_new_camp(nc, min(8, sim.count_role("wood")))
                if save_imp and mkt_r and t >= mkt_r and t - last_mkt >= 20:
                    if sim.bank.food >= 1080 and sim.bank.gold < 800:
                        last_mkt = t
                        sim.sell_at_market("food", 100)
                    elif sim.bank.wood >= 500 + h_res and sim.bank.gold < 800:
                        last_mkt = t
                        sim.sell_at_market("wood", 100)
                    elif sim.bank.gold >= 960 and sim.bank.food < 980:
                        last_mkt = t
                        sim.buy_at_market("food", 100)
                if not save_imp and sim.bank.wood > 450 + rw_c and mkt_r and t >= mkt_r and t - last_mkt >= 25:
                    last_mkt = t
                    sim.sell_at_market("wood", 100)
                if sim.age >= 3 and not is_fast and not save_imp and sim.bank.food > 450 and not bldgs_done_w and sim.count_role("farm") >= 24 and sim.count_role("wood") < 23:
                    m = 0
                    for v in sim.vils:
                        if v["role"] == "farm" and int(v["busy_until"]) <= t and m < 3:
                            v["role"] = "wood"
                            v["camp_idx"] = max(0, len(sim.lumber_camps) - 1)
                            v["busy_until"] = t + 15
                            m += 1
                if sim.age >= 3 and not is_fast and save_imp and sim.bank.food > 850 and sim.bank.gold < 760 and sim.count_role("wood") > 12:
                    m = 0
                    for v in sim.vils:
                        if v["role"] == "wood" and int(v["busy_until"]) <= t and m < 4:
                            v["role"] = "gold"
                            v["busy_until"] = t + 15
                            m += 1
                if sim.age == 3 and not save_imp and not imp_prep and is_fast and knights >= 10 and sim.count_role("farm") >= 22 and sim.count_role("gold") < 14:
                    m = 0
                    for v in sim.vils:
                        if v["role"] in ("wood", "farm") and int(v["busy_until"]) <= t and m < 2:
                            if v["role"] == "wood" and sim.count_role("wood") <= 9:
                                continue
                            v["role"] = "gold"
                            v["busy_until"] = t + 15
                            m += 1
                if not save_imp and not hold_f_tc and sim.count_role("farm") < f_cap and sim.bank.wood >= 60 + rw_c and sim.count_role("wood") > (8 if is_fast else 14):
                    m = 0
                    for v in sim.vils:
                        if v["role"] == "wood" and int(v["busy_until"]) <= t and m < 2 and sim.bank.wood >= 60 + rw_c:
                            sim.spend(ResourceBundle(wood=60), "RebWF")
                            sim.register_new_farm(t + 30)
                            v["role"] = "farm"
                            v["busy_until"] = t + 30
                            m += 1
                if sim.bank.gold > (850 if save_imp else 480) and sim.count_role("gold") > (10 if save_imp else 13):
                    m = 0
                    for v in sim.vils:
                        if v["role"] == "gold" and int(v["busy_until"]) <= t and m < 2:
                            if not hold_f_tc and sim.bank.wood >= 60 + rw_c and sim.count_role("farm") < 44:
                                sim.spend(ResourceBundle(wood=60), "RebF")
                                sim.register_new_farm(t + 30)
                                v["role"] = "farm"
                                v["busy_until"] = t + 30
                            else:
                                v["role"] = "wood"
                                v["camp_idx"] = max(0, len(sim.lumber_camps) - 1)
                                v["busy_until"] = t + 15
                            m += 1
                elif sim.bank.gold < (800 if save_imp else 350) and sim.count_role("farm") > 22 and sim.bank.food > 400:
                    m = 0
                    for v in sim.vils:
                        if v["role"] == "farm" and int(v["busy_until"]) <= t and m < 2:
                            v["role"] = "gold"
                            v["busy_until"] = t + 15
                            m += 1
                if not save_imp and sim.bank.food > 850 and sim.bank.wood < 400 and sim.count_role("farm") > 26:
                    m = 0
                    for v in sim.vils:
                        if v["role"] == "farm" and int(v["busy_until"]) <= t and m < 2:
                            v["role"] = "gold" if sim.bank.gold < 700 else "wood"
                            v["camp_idx"] = max(0, len(sim.lumber_camps) - 1)
                            v["busy_until"] = t + 15
                            m += 1
                if save_imp and sim.bank.food < 1000 and sim.bank.wood >= 240 + h_res and sim.count_role("wood") > 8 and sim.count_role("farm") < 44:
                    m = 0
                    for v in sim.vils:
                        if v["role"] == "wood" and int(v["busy_until"]) <= t and m < 2:
                            sim.spend(ResourceBundle(wood=60), "ImpF")
                            sim.register_new_farm(t + 30)
                            v["role"] = "farm"
                            v["busy_until"] = t + 30
                            m += 1

        if sim.age >= 3 and not (imp_prep and not iclick) and not (sim.age == 4 and not pal_s):
            max_float["food"] = max(max_float["food"], sim.bank.food)
            max_float["wood"] = max(max_float["wood"], sim.bank.wood)
            max_float["gold"] = max(max_float["gold"], sim.bank.gold)

        reseed_w_guard = float(175 + h_res) if (sim.age == 3 and bsaw_s and not mon_s and sim.count_role("farm") >= 18 and sim.bank.wood >= 70) else float(h_res)
        sim.tick_gather(
            boar_open=(b1_shot and sim.active_carcass_food["boar"] > 1e-6),
            reseed_reserve_w=reseed_w_guard,
            fallback_order=("boar", "chicken_mill"),
        )
        if t % 10 == 0:
            record_timeline_point()

    if record_outputs and len(sim.vils) > last_logged_vils:
        add_row(
            f"{sim.fmt_time(i_arr or 2300)} – 40:00",
            "Imperial Age",
            f"Scale to {len(sim.vils)} vils / {sim.total_pop()} pop across {sim.tc_count} TCs & 4 Stables\nPush with Relic-empowered Cavaliers/Paladins (+{sim.relics_garrisoned} atk!) & Battering Rams",
            f"Total trained: {knights} Knights, {monks} Monks ({sim.relics_garrisoned} Relics), {sim.military_units['mangonel']} Mangonels, {sim.military_units['battering_ram']} Rams.",
        )

    milestones["k1_k4"] = [sim.fmt_time(x) for x in k_times[:4]]
    milestones["monks_trained"] = [sim.fmt_time(x) for x in m_times]
    milestones["relics_garrisoned"] = [sim.fmt_time(x) for x in relic_times]
    milestones["knights_total"] = knights
    milestones["idle_stable_castle_s"] = idle_st
    milestones["housed_seconds"] = housed
    milestones["tc_pre_click_idle_s"] = tc_pre
    milestones["extra_tc_idle_s"] = tc_unp
    milestones["negative_bank_count"] = len(sim.negative_bank_events)
    milestones["max_non_save_float"] = {k: round(v, 1) for k, v in max_float.items()}
    milestones["final_vils"] = len(sim.vils)
    milestones["final_pop"] = sim.total_pop()
    milestones["final_army"] = current_army_dict()
    milestones["final_bank"] = {k: round(v, 1) for k, v in sim.bank.to_dict().items()}

    if not record_outputs:
        return BuildOrderDocument("", "Lithuanians", variant_label, "", [], []), milestones

    assert i_arr is not None and i_arr < 2400, f"Imperial missed <40:00: {i_arr}"
    assert housed == 0, f"Housed for {housed}s"
    assert tc_unp <= int(rules.max_end_of_age_tc_idle_seconds), f"Unplanned TC idle: {tc_unp}s"
    assert tc_pre <= int(rules.max_end_of_age_tc_idle_seconds), f"Pre-click TC idle: {tc_pre}s"
    assert not sim.negative_bank_events, f"Negative bank events: {sim.negative_bank_events[:3]}"
    assert "man-at-arms" in sim.upgrades, "Man-at-Arms upgrade missing!"
    assert "double-bit axe" in sim.upgrades, "Double-Bit Axe missing!"
    assert sim.relics_garrisoned == 3, f"Expected 3 Relics garrisoned, got {sim.relics_garrisoned}"

    if is_fast:
        ss_upgs = ["double-bit axe", "horse collar", "gold mining"]
        ss_title = "Early Castle Steady-State (1 TC + 2-Stable Knights w/ Double-Bit Axe & Horse Collar, 10% Buffer)"
    else:
        ss_upgs = ["double-bit axe", "bow saw", "horse collar", "wheelbarrow", "gold mining"]
        ss_title = "Early Castle Steady-State (1 TC + 2-Stable Knights w/ Wheelbarrow & Bow Saw, 10% Buffer)"

    steady_state = planner.compute_steady_state_vils(
        items=[ContinuousProductionItem("villager", 1), ContinuousProductionItem("knight", 2)],
        civ="Lithuanians",
        age=3,
        upgrades=ss_upgs,
        food_source="farmer",
        wood_minutes_since_lc=2.0,
    )
    steady_state["title"] = ss_title

    I = RTS_ICONS
    ca_str = str(milestones["castle_arrival_str"])
    ic_str = str(milestones["imp_click_str"])
    ir_str = str(milestones["imp_reached_str"])
    c_alloc_map = c_alloc or {"wood": 16, "food": 19, "gold": 2, "stone": 0}
    arr_alloc_map = arr_alloc or {"wood": 12, "food": 15, "gold": 10, "stone": 0}
    end_alloc = sim.current_macro_alloc()
    berry_step_note = (
        f"; Build 1st {I['berries']} {I['mill']} (4 vils)"
        if is_fast
        else ""
    )

    if is_fast:
        castle_rts = [
            RTSOverlayStep(
                villager_count=c_vils,
                age=3,
                wood=arr_alloc_map["wood"],
                food=arr_alloc_map["food"],
                gold=arr_alloc_map["gold"],
                stone=arr_alloc_map["stone"],
                notes=[
                    f"Click {I['castle_age']} -> {I['build']} 2nd {I['stable']} ({milestones['s2_ready_str']}), {I['gold_mining']} & push {I['gold']} to {arr_alloc_map['gold']} -> 14; reach {ca_str}.",
                    f"Instant 2-Stable {I['knight']}s ({milestones['k1_k4'][0]} / {milestones['k1_k4'][2]}) + {I['bow_saw']} -> {I['monastery']} ({milestones['monastery_ready_str']}) + 3 {I['monk']}s (42.5s ea) for Relics (+3 atk).",
                ],
            ),
            RTSOverlayStep(
                villager_count=54,
                age=3,
                wood=16,
                food=24,
                gold=14,
                stone=0,
                notes=[
                    f"1-TC Pressure: {I['bloodlines']}, {I['forging']}, {I['scale_barding']} -> {I['wheelbarrow']}, {I['chain_barding']}, {I['iron_casting']}, {I['husbandry']}.",
                    f"Add {I['siege_workshop']} ({I['mangonel']}s), {I['university']}, 3rd {I['stable']}, {I['market']} -> Click {I['imperial_age']} ({ic_str}) -> drop TC #2 & #3 (+100 {I['food']} ea)!",
                ],
            ),
            RTSOverlayStep(
                villager_count=len(sim.vils),
                age=4,
                wood=end_alloc["wood"],
                food=end_alloc["food"],
                gold=end_alloc["gold"],
                stone=end_alloc["stone"],
                notes=[
                    f"Reach {I['imperial_age']} ({ir_str}): {I['cavalier']} -> {I['paladin']}, {I['plate_barding']}, {I['two_man_saw']}, {I['battering_ram']}s w/ Relic-boosted Cavalry!",
                ],
            ),
        ]
        feudal_rts_note = (
            f"Feudal: {I['man_at_arms']}, {I['double_bit_axe']}, {I['horse_collar']}. "
            f"{I['build']} {I['stable']} #1 + {I['blacksmith']}; Farms to ~15 (2 on {I['gold']}); skip WB -> Click {I['castle_age']} ({milestones['castle_click_str']}, {c_vils}v)."
        )
    else:
        castle_rts = [
            RTSOverlayStep(
                villager_count=c_vils,
                age=3,
                wood=arr_alloc_map["wood"],
                food=arr_alloc_map["food"],
                gold=arr_alloc_map["gold"],
                stone=arr_alloc_map["stone"],
                notes=[
                    f"Click {I['castle_age']} -> {I['build']} 2nd {I['stable']} ({milestones['s2_ready_str']}), {I['gold_mining']}, {I['scale_barding']} & {I['bloodlines']}; arrive {ca_str} w/ {arr_alloc_map['food']} {I['farm']}s!",
                    f"0s-idle 2-Stable {I['knight']}s ({milestones['k1_k4'][0]} / {milestones['k1_k4'][2]}) + {I['bow_saw']} -> {I['monastery']} ({milestones['monastery_ready_str']}) + 3 {I['monk']}s (42.5s ea) for Relics.",
                ],
            ),
            RTSOverlayStep(
                villager_count=62,
                age=3,
                wood=18,
                food=27,
                gold=17,
                stone=0,
                notes=[
                    f"Stay 1 TC until ~8 {I['knight']}s & 3 {I['monk']}s (~{milestones['tc_boom_start_str']}), then drop {I['town_center']} #2 & #3 (+100 {I['food']} bonus each!).",
                    f"Add {I['hand_cart']}, {I['heavy_plow']}, {I['chain_barding']}, {I['iron_casting']}, {I['husbandry']}, {I['university']}, {I['siege_workshop']} -> Click {I['imperial_age']} ({ic_str}).",
                ],
            ),
            RTSOverlayStep(
                villager_count=len(sim.vils),
                age=4,
                wood=end_alloc["wood"],
                food=end_alloc["food"],
                gold=end_alloc["gold"],
                stone=end_alloc["stone"],
                notes=[
                    f"Reach {I['imperial_age']} ({ir_str}): {I['cavalier']} -> {I['paladin']}, {I['plate_barding']}, {I['chemistry']}, {I['two_man_saw']}, 4 {I['stable']}s & {I['battering_ram']}s (105v late-game scale!).",
                ],
            ),
        ]
        feudal_rts_note = (
            f"Feudal: {I['man_at_arms']}, {I['double_bit_axe']}, {I['horse_collar']}. "
            f"{I['build']} {I['stable']} #1 + {I['blacksmith']}; Farms -> ~16, {I['wheelbarrow']} at 31v -> Click {I['castle_age']} ({milestones['castle_click_str']}, {c_vils}v)."
        )

    rts_steps = [
        RTSOverlayStep(villager_count=6, age=1, wood=0, food=6, gold=0, stone=0, notes=[f"300 {I['food']} start (+100F TC bonus!). Build 2 {I['house']}s -> all 6 on {I['sheep']} under TC."]),
        RTSOverlayStep(villager_count=9, age=1, wood=3, food=6, gold=0, stone=0, notes=[f"Vils #7–#9 -> {I['wood']} (Vil #7 builds {I['lumber_camp']} #1)."]),
        RTSOverlayStep(villager_count=11, age=1, wood=4, food=7, gold=0, stone=0, notes=[f"Vil #10 lures 1st {I['boar']}; Vil #11 -> {I['wood']} (4 Wood)."]),
        RTSOverlayStep(villager_count=15, age=1, wood=4, food=11, gold=0, stone=0, notes=[f"Vils #12–#15 -> 6 Chickens w/ {I['mill']} (Vil #13 builds {I['house']} #3); lure 2nd {I['boar']}."]),
        RTSOverlayStep(villager_count=19, age=1, wood=4, food=14, gold=1, stone=0, notes=[f"Vils #16–#18 -> {I['boar']}/{I['sheep']} (Vil #17 builds {I['house']} #4); Vil #19 -> LD {I['gold']}; {I['loom']} -> Click {I['feudal_age']} (20 Pop)."]),
        RTSOverlayStep(villager_count=19, age=2, wood=7, food=10, gold=2, stone=0, notes=[f"Feudal Trans: 3 Food -> {I['wood']} ({I['barracks']} + {I['house']} #5); {I['mining_camp']} + 1 -> {I['gold']}{berry_step_note}; 3 Militia."]),
        RTSOverlayStep(villager_count=c_vils, age=2, wood=c_alloc_map["wood"], food=c_alloc_map["food"], gold=c_alloc_map["gold"], stone=c_alloc_map["stone"], notes=[feudal_rts_note]),
        *castle_rts,
    ]

    map_tag = "6 Chickens Milled, Checked w/ 8"
    desc = (
        f"Lithuanians 20-Pop (19v) 3 MAA -> 1-TC Castle Age Priority -> 2-Stable Knights + 3 Relic Monks ({map_tag}) — {variant_label}. "
        f"Models Lithuanians +100F/TC bonus (Update 81058), +20% faster Monasteries (42.5s Monks), Relic +1/+3/+4 Knight attack & 0.5 G/s, "
        f"Arabia 6-Chicken Mill, drop-off round trips, LC decay (-1%/20s floor 60%), dynamic Market, and full Rule 8.3 robustness."
    )

    doc = BuildOrderDocument(
        name=f"Lithuanians 3 MAA into Knights + Monks ({map_tag})",
        civilization="Lithuanians",
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
        (
            "1tc_fast_push",
            "Path 1 (6 Chickens Milled): Fast Castle Priority (1 TC Push -> 2-Stable Knights & 3 Monks -> Fast Imp)",
            "lithuanians_maa_knights_1tc_fast_push.json",
        ),
        (
            "1tc_wb_into_3tc",
            "Path 2 (6 Chickens Milled): Wheelbarrow Eco 1-TC Opening -> 2-Stable Knights & 3 Monks -> Mid-Castle 3-TC Scale",
            "lithuanians_maa_knights_1tc_wb_into_3tc.json",
        ),
    ]

    docs: List[BuildOrderDocument] = []
    for p_key, p_label, json_name in configs:
        doc, ms = run_lithuanians_path(p_key, p_label)
        rob = run_late_command_checks(
            p_key,
            lambda dfn, chk, _pk=p_key, _pl=p_label: run_lithuanians_path(
                _pk, _pl, delay_fn=dfn, chicken_override=chk, record_outputs=False
            )[1],
            baseline_clicks={
                "feudal_click_s": int(ms["feudal_click_s"]),
                "castle_click_s": int(ms["castle_click_s"]),
            },
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
        print(
            f"  Steady-State (w/ 10% buffer): {doc.steady_state_summary['recommended_vils']} "
            f"(exact: {doc.steady_state_summary['exact_vils']})"
        )
        print(
            f"  Rot telemetry: {doc.telemetry_summary['rotted_food']} "
            f"(Total: {doc.telemetry_summary['total_rotted_food']}F)"
        )
        print(f"  Wrote JSON: {json_path} ({len(doc.rts_steps)} steps)\n")

    html_path = export_build_order_html(
        docs,
        title="Lithuanians 20-Pop 3 MAA into Knights + Relic Monks (6 Chickens Milled, Checked w/ 8) — 2 Strategic Paths",
        output_path=OUT_DIR / "lithuanians_maa_into_knights.html",
    )
    print(f"Wrote HTML report: {html_path}")


if __name__ == "__main__":
    main()

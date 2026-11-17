#!/usr/bin/env python3
"""
Generator & 1-Second Discrete-Event Simulator for:
Bohemians Arena Fast Castle (24+2 1-TC Fast Hand Cannoneers):
  - 6 Chickens Milled + Berry Mill in Dark Age (Checked w/ 8 Chickens)
  - 1 vil long-distance mines 10 Gold before Market completes + sell 100 Stone (+91G -> 201G, saving 200W!)
  - Stay 1 TC & 1 Range until Chemistry completes & Hand Cannoneers start producing ASAP
  - Scale quickly to 3 Ranges, Siege Workshop (2+ Mangonels), Pikemen, and TC #2 & TC #3
  - Shift surplus Gold miners to Stone / Wood / Farms (+ Market buy fallback on bottlenecks) to avoid gold float
  - Build a Forward Castle -> Imperial Age & Trebuchets push (<40:00)

Enforces all rules in `rules.md` and `output.md`.
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
    format_vils_pop_range,
)
from sim_bohemians_arena_fc_hand_cannons import BohemiansArenaSimulator
from simulator import run_late_command_checks

OUT_DIR = THIS_DIR


def _pull_builders(
    sim: BohemiansArenaSimulator,
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


def run_bohemians_1tc_fast_hc(
    delay_fn: Optional[Callable[[int], int]] = None,
    chicken_override: Optional[int] = None,
    record_outputs: bool = True,
    castle_rams: int = 0,
) -> Tuple[BuildOrderDocument, Dict[str, object]]:
    """Runs a 1-second simulation for the 24+2 1-TC Fast Hand Cannoneer build."""
    dark_vils = 24
    sim = BohemiansArenaSimulator(dark_vils=dark_vils, chicken_count=chicken_override)
    rules = sim.rules
    planner = BackwardPlanner(sim.db, rules)

    def d_t(planned_t: int) -> int:
        return planned_t if delay_fn is None else delay_fn(planned_t)

    variant_label = (
        "24+2 1-TC Fast Hand Cannons -> 3-TC Boom, Houfnices, Light Cav, Halbs & ~800S Castles"
    )

    rows: List[DetailedBuildRow] = []
    resource_timeline: List[Dict[str, object]] = []
    milestones: Dict[str, object] = {
        "strategy": "24p2_1tc_fast_hc",
        "variant": variant_label,
        "dark_vils": dark_vils,
        "castle_click_vils": dark_vils + 2,
    }

    def current_army_dict() -> Dict[str, int]:
        pike_key = (
            "halberdier"
            if "halberdier" in sim.upgrades
            else ("pikeman" if "pikeman" in sim.upgrades else "spearman")
        )
        bbc_key = "houfnice" if "houfnice" in sim.upgrades else "bombard_cannon"
        out: Dict[str, int] = {"scout": sim.military_units["scout"]}
        if sim.military_units["hand_cannoneer"] > 0:
            out["hand_cannoneer"] = sim.military_units["hand_cannoneer"]
        if sim.military_units["light_cav"] > 0:
            out["light_cav"] = sim.military_units["light_cav"]
        if sim.military_units["mangonel"] > 0:
            out["mangonel"] = sim.military_units["mangonel"]
        if sim.military_units["battering_ram"] > 0:
            out["battering_ram"] = sim.military_units["battering_ram"]
        if sim.military_units["pikeman"] > 0:
            out[pike_key] = sim.military_units["pikeman"]
        if sim.military_units["monk"] > 0:
            out["monk"] = sim.military_units["monk"]
        if sim.military_units["trebuchet"] > 0:
            out["trebuchet"] = sim.military_units["trebuchet"]
        if sim.military_units["bombard_cannon"] > 0:
            out[bbc_key] = sim.military_units["bombard_cannon"]
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

    def add_row(pop_str: str, time_str: str, phase: str, action: str, notes: str = "") -> None:
        nonlocal last_logged_vils
        if not record_outputs:
            return
        curr_vils = len(sim.vils)
        curr_pop = sim.total_pop()
        vil_spawn_pop[curr_vils] = curr_pop
        pop_start = vil_spawn_pop.get(last_logged_vils, 4) if len(rows) == 0 else vil_spawn_pop.get(last_logged_vils + 1, curr_pop)
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

    feudal_cost, feudal_time, _ = sim.db.get_age_advance_spec(2, "Bohemians")
    castle_cost, castle_time, _ = sim.db.get_age_advance_spec(3, "Bohemians")
    imp_cost, imp_time, _ = sim.db.get_age_advance_spec(4, "Bohemians")
    bs_cost, bs_build_time = sim.db.get_unit_or_building_spec("blacksmith", "Bohemians", 2)
    univ_cost, univ_build_time = sim.db.get_unit_or_building_spec("university", "Bohemians", 3)

    # t = 0:00 start (rule 1.5)
    sim.spend(ResourceBundle(food=50), "vil_4")
    sim.tc_busy_until[0] = 25
    sim.tc_action[0] = "vil_4"
    record_timeline_point()

    # Dark / Feudal state
    boar1_arrive_t: Optional[int] = None
    boar1_shot = False
    boar2_lured = False
    boar2_arrive_t: Optional[int] = None
    boar2_shot = False
    sheep_post_logged = False

    ld_gold_done = False
    ld_gold_vil_id: Optional[int] = None
    feudal_clicked = False
    feudal_click_t = 0
    feudal_cmd_t: Optional[int] = None
    feudal_vils_queued = 0
    market_started = False
    market_ready_t: Optional[int] = None
    bs_started = False
    bs_ready_t: Optional[int] = None
    stone_sold = False
    gold_mc_started = False
    castle_clicked = False
    castle_click_t = 0
    castle_cmd_t: Optional[int] = None
    castle_reached_t: Optional[int] = None

    dba_started = False
    hc_started = False
    bow_saw_started = False
    lc2_built = False

    tc2_started = False
    tc2_ready_t: Optional[int] = None
    tc3_started = False
    tc3_ready_t: Optional[int] = None

    wheelbarrow_started = False
    hand_cart_started = False
    loom_started = False

    univ_started = False
    univ_ready_t: Optional[int] = None
    chemistry_started = False
    chemistry_ready_t: Optional[int] = None
    chemistry_logged = False
    first_hc_t: Optional[int] = None

    barracks_started = False
    barracks_ready_t: Optional[int] = None
    barracks_ready_times: List[int] = []
    rax_busy_until: List[int] = [0, 0, 0]
    pikeman_upg_started = False
    squires_started = False
    halberdier_upg_started = False

    ranges_started = 0
    range_ready_times: List[int] = []
    range_busy_until: List[int] = [0, 0, 0, 0, 0]

    stables_started = 0
    stable_ready_times: List[int] = []
    stable_busy_until: List[int] = [0, 0, 0]
    light_cav_upg_started = False
    light_cav_converted = False
    husbandry_started = False

    sw_started = False
    sw_ready_t: Optional[int] = None
    sw_ready_times: List[int] = []
    sw_busy_until: List[int] = [0, 0]
    houfnice_started = False
    houfnice_ready_t: Optional[int] = None
    houfnice_logged = False

    monastery_started = False
    monastery_ready_t: Optional[int] = None
    monastery_busy_until = 0
    monks_trained = 0
    relic1_time: Optional[int] = None

    bs_busy_until = 0
    padded_armor_started = False
    leather_armor_started = False
    ring_armor_started = False
    forging_started = False
    iron_casting_started = False
    blast_furnace_started = False
    scale_mail_started = False
    chain_mail_started = False
    plate_mail_started = False
    scale_barding_started = False
    chain_barding_started = False

    heavy_plow_started = False
    two_man_saw_started = False
    fervor_started = False
    sanctity_started = False

    stone_ramp_started = False
    fwd_vils_dispatched = False
    fwd_vils_arrive_t: Optional[int] = None
    fwd_vils: List[Dict[str, object]] = []
    fwd_castle_started = False
    fwd_castle_ready_t: Optional[int] = None
    castle_busy_until = 0

    wagenburg_started = False
    siege_engineers_started = False
    conscription_started = False
    imp_prep_started = False
    imp_hold_start_t: Optional[int] = None
    imp_clicked = False
    imp_click_t = 0
    imp_reached_t: Optional[int] = None

    extra_castles_started = 0
    extra_castle_ready_t: Optional[int] = None

    last_market_trade_t = -999
    last_lc_refresh_t = -999
    v37_loop_logged = False
    v46_pre_stone_logged = False
    mil_loop_logged = False
    tc_expand_logged = False
    fwd_loop_logged = False

    housed_seconds = 0
    tc_pre_click_idle_s = 0
    tc_unplanned_idle_s = 0
    max_castle_float = {"food": 0.0, "wood": 0.0, "gold": 0.0}

    def queue_upg(
        name: str,
        extra_check: bool = True,
        res_food: float = 0.0,
        res_wood: float = 0.0,
        res_gold: float = 0.0,
    ) -> bool:
        if not extra_check:
            return False
        c, rt = sim.db.get_upgrade_spec(name, "Bohemians")
        if (
            sim.bank.food >= c.food + res_food
            and sim.bank.wood >= c.wood + res_wood
            and sim.bank.gold >= c.gold + res_gold
            and sim.bank.stone >= c.stone
        ):
            sim.spend(c, f"upgrade:{name}")
            sim.queue_upgrade(name, sim.time_s + int(round(rt)))
            return True
        return False

    max_sim_t = 3200
    for t in range(1, max_sim_t + 1):
        sim.time_s = t
        sim.in_age_transition = (
            (feudal_clicked and sim.age == 1)
            or (castle_clicked and sim.age == 2)
            or (imp_clicked and sim.age == 3)
        )

        # Track TC #1 idle time prior to Imperial Click (rules 5.1, 5.3)
        if not imp_clicked and sim.tc_action[0] == "idle":
            if (
                (sim.age == 1 and len(sim.vils) == dark_vils and not feudal_clicked)
                or (sim.age == 2 and feudal_vils_queued == 2 and not castle_clicked)
                or (sim.age >= 3 and imp_hold_start_t is not None)
            ):
                tc_pre_click_idle_s += 1
            else:
                tc_unplanned_idle_s += 1
            sim.tc1_idle_before_imp_s = tc_pre_click_idle_s + tc_unplanned_idle_s

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
                        v["busy_until"] = max(
                            int(v["busy_until"]), lure_t + int(2 * rules.boar_lure_walk_time_one_way)
                        )
                        boar2_arrive_t = lure_t + int(2 * rules.boar_lure_walk_time_one_way)
                        break

        if boar2_arrive_t is not None and not boar2_shot and t >= boar2_arrive_t:
            boar2_shot = True
            _pull_builders(sim, ("boar", "sheep"), rules.boar_garrison_vils, t + int(rules.boar_garrison_seconds))

        # Relic #1 garrisoned by Monk #1 (rule 7.3 -> +0.5G/s = +30G/min)
        if relic1_time is not None and t >= relic1_time and sim.relics_garrisoned < 1:
            sim.relics_garrisoned = 1
            milestones["relic1_str"] = sim.fmt_time(t)

        # Long-distance 10 Gold completion -> return villager to Stragglers/Wood once >= 110.2G
        if not ld_gold_done and ld_gold_vil_id is not None and sim.bank.gold >= 110.2:
            ld_gold_done = True
            milestones["ld_gold_done_str"] = sim.fmt_time(t)
            for v in sim.vils:
                if v["id"] == ld_gold_vil_id:
                    v["role"] = "straggler"
                    v["busy_until"] = t + int(rules.straggler_walk_time)
                    break

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
                                    f"00:00 – {sim.fmt_time()}",
                                    "Dark Age",
                                    "Build 2 Houses (-50W)\nAssign Vils #1–#6 -> Sheep under TC",
                                    "Start 200F, 200W, 100G, 200S; +2 Sheep at 1:30 & 2:30 (rule 1.3).",
                                )
                        elif vid == 7:
                            sim.spend(ResourceBundle(wood=100), "LC1")
                            comp_t = t + int(rules.camp_or_berry_walk_time_one_way) + 35
                            lc1_idx = sim.add_lumber_camp(comp_t)
                            sim.vils.append({"id": vid, "role": "wood", "camp_idx": lc1_idx, "busy_until": comp_t})
                        elif vid in (8, 9):
                            sim.vils.append(
                                {
                                    "id": vid,
                                    "role": "wood",
                                    "camp_idx": 0,
                                    "busy_until": t + int(rules.camp_or_berry_walk_time_one_way),
                                }
                            )
                            if vid == 9:
                                add_row(
                                    "7–9 (8–10)",
                                    f"01:40 – {sim.fmt_time()}",
                                    "Dark Age",
                                    "Vil #7 -> Build Lumber Camp #1 (-100W, 35s)\nAssign Vils #7–#9 -> Wood at LC #1",
                                    "15s walk to woodline; LC #1 completes at 02:30; wood decay -1% per 20s down to 60% floor (rule 3.4).",
                                )
                        elif vid == 10:
                            lure_start = d_t(t)
                            boar1_arrive_t = lure_start + int(2 * rules.boar_lure_walk_time_one_way)
                            sim.vils.append({"id": vid, "role": "boar", "busy_until": boar1_arrive_t})
                            add_row(
                                "10 (11)",
                                sim.fmt_time(),
                                "Dark Age",
                                "Assign Vil #10 -> Lure Boar #1 -> Boar under TC",
                                f"15s out + 15s back; Boar #1 arrives {sim.fmt_time(boar1_arrive_t)} -> garrison 7 TC vils 5s (rule 3.7).",
                            )
                        elif vid == 11:
                            sim.vils.append(
                                {
                                    "id": vid,
                                    "role": "wood",
                                    "camp_idx": 0,
                                    "busy_until": t + int(rules.camp_or_berry_walk_time_one_way),
                                }
                            )
                            add_row("11 (12)", sim.fmt_time(), "Dark Age", "Assign Vil #11 -> Wood at LC #1", "15s walk; 4 on Wood.")
                        elif vid == 12:
                            sim.spend(ResourceBundle(wood=100), "ChickenMill")
                            cmill_comp = t + int(rules.camp_or_berry_walk_time_one_way) + 35
                            sim.add_building("mill", cmill_comp)
                            sim.vils.append({"id": vid, "role": "chicken_mill", "busy_until": cmill_comp})
                        elif vid == 13:
                            sim.spend(ResourceBundle(wood=25), "House3")
                            comp_t = t + int(rules.house_walk_time_one_way) + 25
                            sim.add_pending_pop_building(comp_t, 5, "house")
                            sim.vils.append(
                                {
                                    "id": vid,
                                    "role": "chicken_mill",
                                    "busy_until": comp_t + int(rules.camp_or_berry_walk_time_one_way),
                                }
                            )
                        elif vid in (14, 15):
                            sim.vils.append(
                                {
                                    "id": vid,
                                    "role": "chicken_mill",
                                    "busy_until": t + int(rules.camp_or_berry_walk_time_one_way),
                                }
                            )
                            if vid == 15:
                                add_row(
                                    "12–15 (13–16)",
                                    f"03:45 – {sim.fmt_time()}",
                                    "Dark Age",
                                    "Vil #12 -> Build Mill #1 (-100W, 35s) on Chickens\nVil #13 -> Build House #3 (-25W)\nAssign Vils #12–#15 -> 6 Chickens at Mill #1",
                                    "Mill #1 on Chickens (23.9/min) unlocks Horse Collar & Farms (rules 3.9, 3.10); 2nd Boar lured before 1st finishes.",
                                )
                        elif vid == 16:
                            sim.spend(ResourceBundle(wood=100), "BerryMill")
                            bmill_comp = t + int(rules.camp_or_berry_walk_time_one_way) + 35
                            sim.add_building("mill", bmill_comp)
                            sim.vils.append({"id": vid, "role": "berries", "busy_until": bmill_comp})
                        elif vid == 17:
                            sim.vils.append({"id": vid, "role": "berries", "busy_until": t + 15})
                        elif vid == 18:
                            sim.spend(ResourceBundle(wood=25), "House4")
                            comp_t = t + 30
                            sim.add_pending_pop_building(comp_t, 5, "house")
                            sim.vils.append({"id": vid, "role": "berries", "busy_until": comp_t + 15})
                        elif vid == 19:
                            sim.vils.append({"id": vid, "role": "berries", "busy_until": t + 15})
                            add_row(
                                "16–19 (17–20)",
                                f"05:25 – {sim.fmt_time()}",
                                "Dark Age",
                                "Vil #16 -> Build Mill #2 (-100W, 35s) on Berries\nVil #18 -> Build House #4 (-25W)\nAssign Vils #16–#19 -> Berries at Mill #2",
                                "Both Mills affordable in Dark Age for FC (rule 3.9); 4/4 on Berries.",
                            )
                        elif vid in (20, 21):
                            sim.vils.append({"id": vid, "role": "wood", "camp_idx": 0, "busy_until": t + 15})
                            if vid == 21:
                                add_row(
                                    "20–21 (21–22)",
                                    f"07:05 – {sim.fmt_time()}",
                                    "Dark Age",
                                    "Assign Vils #20–#21 -> Wood at LC #1",
                                    "15s walk (6 on Wood); skip Dark Age Gold MC (-100W saved); long-distance 10G + sell 100S keeps +200W in Feudal.",
                                )
                        elif vid == 22:
                            sim.spend(ResourceBundle(wood=25), "House5")
                            comp_t = t + 30
                            sim.add_pending_pop_building(comp_t, 5, "house")
                            sim.vils.append({"id": vid, "role": "wood", "camp_idx": 0, "busy_until": comp_t + 15})
                        elif vid == 23:
                            if sim.active_carcass_food["sheep"] > 10.0 or sim.remaining_animals["sheep"] > 0:
                                sim.vils.append(
                                    {
                                        "id": vid,
                                        "role": "sheep",
                                        "busy_until": t + int(rules.tc_food_switch_walk_time),
                                    }
                                )
                            else:
                                sim.vils.append({"id": vid, "role": "wood", "camp_idx": 0, "busy_until": t + 15})
                        elif vid == 24:
                            # Vil #24 long-distance mines 10 Gold before Market completes (rule 3.3)
                            ld_gold_vil_id = vid
                            sim.vils.append(
                                {
                                    "id": vid,
                                    "role": "gold_ld",
                                    "busy_until": t + int(rules.camp_or_berry_walk_time_one_way),
                                }
                            )
                            add_row(
                                "22–24 (23–25)",
                                f"07:55 – {sim.fmt_time()}",
                                "Dark Age",
                                "Vil #22 -> Build House #5 (-25W) -> Wood at LC #1\nAssign Vil #23 -> Sheep / Food under TC\nAssign Vil #24 -> Long-distance 10 Gold -> Stragglers/Farms",
                                "7 on Wood; Vil #24 finishes 10G at ~09:58 (rule 3.3) -> 110G so selling 100S at Market (+91G) hits 201G without wasting 200W.",
                            )

                        if vid < dark_vils and sim.bank.food >= 50:
                            sim.spend(ResourceBundle(food=50), f"vil_{vid+1}")
                            sim.tc_busy_until[0] = t + 25
                            sim.tc_action[0] = f"vil_{vid+1}"

                    elif sim.age == 2:
                        sim.vils.append(
                            {
                                "id": vid,
                                "role": "wood",
                                "camp_idx": max(0, len(sim.lumber_camps) - 1),
                                "busy_until": t + 15,
                            }
                        )
                        if vid == dark_vils + 2:
                            add_row(
                                f"{dark_vils+1}–{dark_vils+2} ({dark_vils+2}–{dark_vils+3})",
                                f"{sim.fmt_time(t-25)} – {sim.fmt_time()}",
                                "Feudal Age",
                                f"Assign Vils #{dark_vils+1}–#{dark_vils+2} -> Wood\nSell 100 Stone at Market (+91G)",
                                "Hits 201G total while keeping +200W and 100S left for TC #2 later.",
                            )

                    else:
                        # Castle & Imperial villager routing (prioritize Wood & Farms early so Ranges/SW/TCs drop fast!)
                        g_cnt = sim.count_role("gold")
                        w_cnt = sim.count_role("wood", "straggler")
                        f_cnt = sim.count_role("farm")
                        s_cnt = sim.count_role("stone")
                        cur_camp = max(0, len(sim.lumber_camps) - 1)

                        saving_for_bldg = (
                            (not univ_started and sim.bank.wood < int(univ_cost.wood))
                            or (not barracks_started and sim.bank.wood < 175)
                            or (barracks_started and ranges_started < 1 and sim.bank.wood < 175)
                            or (chemistry_started and not monastery_started and sim.bank.wood < 175)
                            or (first_hc_t is not None and monastery_started and ranges_started < 3 and sim.bank.wood < 175)
                            or (first_hc_t is not None and ranges_started >= 2 and not sw_started and sim.bank.wood < 200)
                            or (ranges_started >= 3 and sw_started and not tc3_started and sim.bank.wood < 275)
                        )
                        farm_t1 = 15 if first_hc_t is None else (34 if not imp_clicked else 52)
                        wood_t1 = 14 if first_hc_t is None else (20 if not imp_clicked else 36)
                        # Keep Gold miners tight so we don't float Gold!
                        if first_hc_t is None:
                            gold_t1 = 4 if sim.bank.gold < 320 else 3
                        elif not imp_clicked:
                            gold_t1 = 6 if sim.bank.gold > 500 else (10 if not imp_prep_started else 14)
                        else:
                            gold_t1 = 29

                        need_castle_stone = 660 if not tc2_started else (760 if not tc3_started else 660)
                        stone_t = 7 if (stone_ramp_started and not fwd_castle_started and sim.bank.stone < need_castle_stone) else 0

                        if f_cnt < 12 and sim.bank.wood >= 60 and not saving_for_bldg:
                            sim.spend(ResourceBundle(wood=60), "farm_new")
                            sim.register_new_farm(t + int(rules.farm_walk_time) + 15)
                            sim.vils.append(
                                {
                                    "id": vid,
                                    "role": "farm",
                                    "busy_until": t + int(rules.farm_walk_time) + 15,
                                }
                            )
                        elif stone_t > 0 and s_cnt < stone_t:
                            sim.vils.append({"id": vid, "role": "stone", "busy_until": t + 15})
                        elif w_cnt < wood_t1:
                            sim.vils.append({"id": vid, "role": "wood", "camp_idx": cur_camp, "busy_until": t + 15})
                        elif f_cnt < farm_t1 and sim.bank.wood >= 60 and not saving_for_bldg and sim.bank.food < 1150:
                            sim.spend(ResourceBundle(wood=60), "farm_new")
                            sim.register_new_farm(t + int(rules.farm_walk_time) + 15)
                            sim.vils.append(
                                {
                                    "id": vid,
                                    "role": "farm",
                                    "busy_until": t + int(rules.farm_walk_time) + 15,
                                }
                            )
                        elif g_cnt < gold_t1 and sim.bank.gold < (950 if imp_prep_started else 600):
                            sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                        else:
                            sim.vils.append(
                                {
                                    "id": vid,
                                    "role": "wood" if (sim.bank.gold >= 600 or g_cnt >= gold_t1) else "gold",
                                    "camp_idx": cur_camp,
                                    "busy_until": t + 15,
                                }
                            )
                    vil_spawn_pop[len(sim.vils)] = sim.total_pop()

                elif act == "feudal":
                    sim.age = 2
                    sim.upgrades.update({"gold mining", "stone mining"})
                    milestones["feudal_reached_s"] = t
                    milestones["feudal_reached_str"] = sim.fmt_time()

                    if sim.bank.food >= 50:
                        sim.spend(ResourceBundle(food=50), "feudal_vil1")
                        sim.tc_busy_until[0] = t + 25
                        sim.tc_action[0] = f"vil_{len(sim.vils)+1}"
                        feudal_vils_queued = 1

                    # Market (175W, 3 builders -> 36s) & Bohemian Blacksmith (50W, 1 builder -> 40s)
                    if sim.bank.wood >= (175 + int(bs_cost.wood)):
                        market_started = True
                        bs_started = True
                        sim.spend(ResourceBundle(wood=175 + bs_cost.wood), "Market+Blacksmith")
                        mkt_build = int(round(calc_construction_time(60.0, 3)))
                        market_ready_t = t + 10 + mkt_build
                        bs_ready_t = t + 10 + int(bs_build_time)
                        _pull_builders(sim, ("straggler", "wood", "berries"), 3, market_ready_t + 10)
                        _pull_builders(sim, ("straggler", "wood", "berries"), 1, bs_ready_t + 10)
                        add_row(
                            f"{len(sim.vils)} ({sim.total_pop()})",
                            sim.fmt_time(),
                            "Feudal Age",
                            f"Queue +2 Feudal Vils -> Wood\n3 Straggler/Wood vils build Market (-175W, {mkt_build}s) -> return to Wood\n1 Straggler/Wood vil builds Blacksmith (-{bs_cost.wood:.0f}W, 40s) -> return to Wood",
                            "Free Gold/Stone Mining (+15%); Bohemians save 100W on Blacksmith + Mining Camp techs; 110G ready -> sell 100S for +91G (saving 200W).",
                        )

                elif act == "castle":
                    sim.age = 3
                    sim.upgrades.update({"gold shaft mining", "stone shaft mining"})
                    castle_reached_t = t
                    milestones["castle_reached_s"] = t
                    milestones["castle_reached_str"] = sim.fmt_time()
                    milestones["castle_arrival_bank"] = sim.bank.to_dict()
                    milestones["castle_arrival_alloc"] = sim.current_macro_alloc()

                    add_row(
                        f"{len(sim.vils)} ({sim.total_pop()})",
                        f"{sim.fmt_time(castle_click_t)} – {sim.fmt_time()}",
                        "Castle Transition",
                        "Research Double-Bit Axe (-100F, -50W)\nResearch Horse Collar (-75F, -75W)\nMove 4 Straggler/Wood vils -> Gold (1st builds Gold Mining Camp [-100W])\n1 Wood/Straggler vil builds Barracks (-175W) -> Wood",
                        "Castle Transition (160s); Barracks & Gold MC complete early using saved 200W so University + Range #1 drop immediately at 14:26.",
                    )

                    if sim.bank.food >= 50:
                        sim.spend(ResourceBundle(food=50), "castle_vil1")
                        sim.tc_busy_until[0] = t + 25
                        sim.tc_action[0] = f"vil_{len(sim.vils)+1}"

                    castle_acts = ["Queue Villager -> Wood / Farms"]
                    if sim.bank.food >= 200 and sim.bank.wood >= 100 and queue_upg("bow saw", res_food=50):
                        bow_saw_started = True
                        castle_acts.append("Research Bow Saw (-150F, -100W)")

                    if not univ_started and sim.bank.wood >= int(univ_cost.wood):
                        univ_started = True
                        sim.spend(univ_cost, "University")
                        univ_ready_t = t + 10 + int(univ_build_time)
                        sim.add_building("university", univ_ready_t)
                        _pull_builders(sim, ("straggler", "wood"), 1, univ_ready_t + 10)
                        milestones["univ_ready_str"] = sim.fmt_time(univ_ready_t)
                        castle_acts.append(f"1 Wood/Straggler vil builds University (-{univ_cost.wood:.0f}W, 60s) -> Wood")

                    if barracks_ready_t is not None and t >= barracks_ready_t and ranges_started == 0 and sim.bank.wood >= 175:
                        ranges_started = 1
                        sim.spend(ResourceBundle(wood=175), "Range1")
                        r_ready = t + 10 + 50
                        range_ready_times.append(r_ready)
                        sim.add_building("archery range", r_ready)
                        _pull_builders(sim, ("straggler", "wood"), 1, r_ready + 10)
                        milestones["range1_ready_str"] = sim.fmt_time(r_ready)
                        castle_acts.append("1 Wood/Straggler vil builds Archery Range #1 (-175W, 50s) -> Wood")

                    add_row(
                        f"{len(sim.vils)} ({sim.total_pop()})",
                        sim.fmt_time(),
                        "Castle Age",
                        "\n".join(castle_acts),
                        "Free Gold/Stone Shaft Mining (+15%); Bohemians save 100W on University; stay 1 TC & 1 Range until Hand Cannons start; 90% Castle+ buffer active (rule 8.2).",
                    )

                elif act == "loom":
                    sim.upgrades.add("loom")
                    milestones["loom_done_str"] = sim.fmt_time(t)

                elif act == "wheelbarrow":
                    sim.upgrades.add("wheelbarrow")
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
                    milestones["imp_arrival_army"] = current_army_dict()

                    add_row(
                        f"{len(sim.vils)} ({sim.total_pop()})",
                        f"{sim.fmt_time(imp_click_t)} – {sim.fmt_time()}",
                        "Imperial Transition",
                        "Continue 3-TC Vils (toward 120–130 vils) -> Farms / Wood / Gold\nResearch Hand Cart (-300F, -200W), Heavy Plow (-125F, -125W), Fervor (-140G) & Sanctity (-175G)\nAdd Barracks #2–#3 (-175W each), Stables #1–#2 (-175W each), Range #4 (-175W) & Siege Workshop #2 (-200W)\nResearch Light Cavalry (-150F, -50G), Husbandry (-150F), Squires (-100F) & Blacksmith melee/cavalry upgrades\nBuild Castle #2 (-650S) at ~800 Stone (and another Castle every time Stone reaches ~800S)",
                        f"Imperial Transition (190s): Arrives Imperial Age at {sim.fmt_time()} (target <40:00 per rule 6.5).",
                    )

                    if sim.bank.food >= 150 and sim.bank.gold >= 150:
                        conscription_started = True
                        sim.spend(ResourceBundle(food=150, gold=150), "Conscription")
                        sim.queue_upgrade("conscription", t + 60)
                        castle_busy_until = max(castle_busy_until, t + 60)

                    add_row(
                        f"{len(sim.vils)} ({sim.total_pop()})",
                        sim.fmt_time(),
                        "Imperial Age",
                        "Research Conscription (-150F, -150G), Two-Man Saw (-300F, -200W) & Siege Engineers (-500F, -600W)\nResearch Ring Archer Armor (-250F, -250G), Halberdier (-300F, -600G) & Wagenburg Tactics (-300F, -300G)\nTrain Bombard Cannons (-225W, -225G) from 2 Siege Workshops + Trebuchets (-200W, -200G) from Castles",
                        f"Reached Imperial Age; bank on arrival: {sim.bank.food:.0f}F / {sim.bank.wood:.0f}W / {sim.bank.gold:.0f}G / {sim.bank.stone:.0f}S.",
                    )

        # Click Feudal Age (rule 5.1 <= 5s buffer)
        if sim.age == 1 and not feudal_clicked and sim.tc_action[0] == "idle" and len(sim.vils) == dark_vils:
            if feudal_cmd_t is None and sim.bank.can_afford(feudal_cost):
                feudal_cmd_t = d_t(t)
            if feudal_cmd_t is not None and t >= feudal_cmd_t and sim.bank.can_afford(feudal_cost):
                feudal_clicked = True
                feudal_click_t = t
                sim.feudal_clicked = True
                milestones["feudal_click_s"] = t
                milestones["feudal_click_str"] = sim.fmt_time(t)
                sim.spend(feudal_cost, "FeudalClick")
                sim.tc_busy_until[0] = t + int(feudal_time)
                sim.tc_action[0] = "feudal"
                add_row(
                    f"{len(sim.vils)} ({sim.total_pop()})",
                    sim.fmt_time(),
                    "Feudal Transition",
                    "Click Feudal Age (-500F, 130s)",
                    f"Pre-click TC idle: {tc_pre_click_idle_s}s; reaches Feudal Age at {sim.fmt_time(t + int(feudal_time))}.",
                )

        # Feudal Transition: Sheep #8 finishes -> Stragglers + Farms (8 Farms!)
        if (
            not sheep_post_logged
            and feudal_clicked
            and sim.age == 1
            and sim.undiscovered_sheep == 0
            and sim.remaining_animals["sheep"] == 0
            and sim.active_carcass_food["sheep"] <= 1e-6
        ):
            sheep_post_logged = True
            moved_sh = 0
            for v in sim.vils:
                if v["role"] in ("straggler", "sheep") and int(v["busy_until"]) <= t:
                    if v["role"] == "sheep":
                        moved_sh += 1
                    v["role"] = "straggler"
                    v["busy_until"] = t + int(rules.straggler_walk_time)
            add_row(
                f"{len(sim.vils)} ({sim.total_pop()})",
                sim.fmt_time(),
                "Feudal Transition",
                f"Move {moved_sh} TC Sheep vils -> Stragglers\nMove up to 8 Straggler vils -> Seed Farms (-60W each)",
                "Sheep #8 finishes under TC; reserve 225W for Market + Blacksmith (no 200W sale needed since selling 100S).",
            )

        if sheep_post_logged and not castle_clicked and sim.farms_seeded < 8 and sim.has_building("mill"):
            res_mb = (0 if market_started else 175) + (0 if bs_started else int(bs_cost.wood))
            if sim.bank.wood >= (60 + res_mb):
                for v in sim.vils:
                    if v["role"] in ("straggler", "sheep", "wood") and int(v["busy_until"]) <= t:
                        walk_t = (
                            int(rules.camp_or_berry_walk_time_one_way)
                            if v["role"] == "wood"
                            else int(rules.farm_walk_time)
                        )
                        sim.spend(ResourceBundle(wood=60), "TransitionFarm")
                        v["role"] = "farm"
                        v["busy_until"] = t + walk_t + 15
                        sim.register_new_farm(t + walk_t + 15)
                        break

        # Feudal Age: Queue 2nd Feudal villager
        if sim.age == 2 and not castle_clicked and sim.tc_action[0] == "idle" and feudal_vils_queued == 1:
            if sim.bank.food >= 50:
                sim.spend(ResourceBundle(food=50), "feudal_vil2")
                sim.tc_busy_until[0] = t + 25
                sim.tc_action[0] = f"vil_{len(sim.vils)+1}"
                feudal_vils_queued = 2

        # Feudal Age Market trade: Sell 100 Stone for +91 Gold (110G + 91G = 201G, rule 7.2)
        if (
            market_ready_t is not None
            and t >= market_ready_t
            and not stone_sold
            and sim.bank.stone >= 100
            and sim.bank.gold >= 110
            and sim.bank.gold < 200
        ):
            stone_sold = True
            sim.sell_at_market("stone", 100)

        # Click Castle Age
        if (
            sim.age == 2
            and not castle_clicked
            and feudal_vils_queued == 2
            and sim.tc_action[0] == "idle"
            and bs_ready_t is not None
            and t >= bs_ready_t
            and sim.bank.can_afford(castle_cost)
        ):
            if castle_cmd_t is None:
                castle_cmd_t = d_t(t)
            if t >= castle_cmd_t:
                castle_clicked = True
                castle_click_t = t
                milestones["castle_click_s"] = t
                milestones["castle_click_str"] = sim.fmt_time(t)
                sim.spend(castle_cost, "CastleClick")
                sim.tc_busy_until[0] = t + int(castle_time)
                sim.tc_action[0] = "castle"
                add_row(
                    f"{len(sim.vils)} ({sim.total_pop()})",
                    sim.fmt_time(),
                    "Feudal Age",
                    "Click Castle Age (-800F, -200G, 160s)",
                    f"27 pop click; reaches Castle Age at {sim.fmt_time(t + int(castle_time))} with {sim.bank.stone:.0f}S left in bank.",
                )

        # Castle Transition: DBA + HC + Gold MC (4 on Gold) + Barracks + Farms up to 10 while keeping 275W for Univ + Range #1!
        if castle_clicked and sim.age == 2 and t >= castle_click_t + 1:
            if not dba_started and queue_upg("double-bit axe"):
                dba_started = True
            if dba_started and not hc_started and queue_upg("horse collar"):
                hc_started = True
            if hc_started and not gold_mc_started and sim.bank.wood >= 100:
                gold_mc_started = True
                sim.spend(ResourceBundle(wood=100), "GoldMC")
                sim.buildings.append("mining camp")
                moved_g = 0
                for v in sim.vils:
                    if v["role"] in ("wood", "straggler") and int(v["busy_until"]) <= t and moved_g < 4:
                        v["role"] = "gold"
                        v["busy_until"] = (t + 50) if moved_g == 0 else (t + 15)
                        moved_g += 1
            if gold_mc_started and not barracks_started and sim.bank.wood >= (175 + int(univ_cost.wood)):
                barracks_started = True
                sim.spend(ResourceBundle(wood=175), "Barracks")
                barracks_ready_t = t + 10 + 50
                sim.add_building("barracks", barracks_ready_t)
                _pull_builders(sim, ("wood", "straggler"), 1, barracks_ready_t + 10)
            if barracks_started and sim.farms_seeded < 10 and sim.bank.wood >= (60 + int(univ_cost.wood) + 175):
                for v in sim.vils:
                    if v["role"] in ("straggler", "wood") and int(v["busy_until"]) <= t:
                        walk_t = (
                            int(rules.farm_walk_time)
                            if v["role"] == "straggler"
                            else int(rules.camp_or_berry_walk_time_one_way)
                        )
                        sim.spend(ResourceBundle(wood=60), "CastleTransFarm")
                        v["role"] = "farm"
                        v["busy_until"] = t + walk_t + 15
                        sim.register_new_farm(t + walk_t + 15)
                        break

        # Rule 4.4 House management (active from Castle click onwards)
        house_wood_res = 0
        if castle_clicked:
            producing_mil = (
                len(range_ready_times)
                + (1 if sw_ready_t and t >= sw_ready_t else 0)
                + (1 if barracks_ready_t and t >= barracks_ready_t else 0)
            )
            extra_tcs = max(0, sim.tc_count - 1)
            need_house_room = sim.house_threshold(producing_mil, extra_tcs) + (4 if (producing_mil + extra_tcs) >= 4 else 2)
            pending_houses = sum(1 for _, p in sim.pending_pop_buildings if p == 5)
            pending_house_pop = pending_houses * 5
            projected_free = sim.pop_cap() + pending_house_pop - sim.total_pop()
            house_waiting_wood = (
                projected_free <= need_house_room
                and pending_houses < 4
                and (sim.pop_cap() + pending_house_pop) < 200
            )
            if house_waiting_wood and sim.bank.wood >= 25:
                if sim.age >= 3 or projected_free <= 5:
                    sim.spend(ResourceBundle(wood=25), "House")
                    comp_t = t + int(rules.house_walk_time_one_way) + 25
                    sim.add_pending_pop_building(comp_t, 5, "house")
                    _pull_builders(sim, ("wood", "straggler", "farm"), 1, comp_t + int(rules.house_walk_time_one_way))
                    house_waiting_wood = False
            house_wood_res = 25 if house_waiting_wood else 0

        # === CASTLE AGE & IMPERIAL AGE ===
        if sim.age >= 3:
            if sim.age == 3 and not imp_clicked:
                max_castle_float["food"] = max(max_castle_float["food"], sim.bank.food)
                max_castle_float["wood"] = max(max_castle_float["wood"], sim.bank.wood)
                max_castle_float["gold"] = max(max_castle_float["gold"], sim.bank.gold)

            if not bow_saw_started and queue_upg("bow saw", res_food=50 * sim.tc_count):
                bow_saw_started = True

            # Activate TCs on completion
            if tc2_ready_t is not None and t == tc2_ready_t:
                sim.tc_count += 1
                sim.tc_busy_until.append(t)
                sim.tc_action.append("idle")
                milestones["tc2_ready_str"] = sim.fmt_time(t)
            if tc3_ready_t is not None and t == tc3_ready_t:
                sim.tc_count += 1
                sim.tc_busy_until.append(t)
                sim.tc_action.append("idle")
                milestones["tc3_ready_str"] = sim.fmt_time(t)

            f_cnt_now = sim.count_role("farm")
            w_cnt_now = sim.count_role("wood", "straggler")
            saving_for_imp = imp_prep_started and not imp_clicked

            # TC Queue management FIRST (rules 4.3, 5.1-5.3: villager production takes priority over military/upgrades!)
            for tc_idx in range(sim.tc_count):
                if sim.tc_action[tc_idx] == "idle":
                    can_click_imp = (
                        imp_prep_started
                        and not imp_clicked
                        and tc_idx == 0
                        and sim.bank.can_afford(imp_cost)
                    )
                    if can_click_imp:
                        if not fwd_loop_logged:
                            fwd_loop_logged = True
                            fwd_src_lbl = str(milestones.get("fwd_vils_src_str", "Wood/Farm"))
                            fwd_disp_t = str(milestones.get("fwd_vils_dispatched_str", sim.fmt_time()))
                            imp_prep_start_t = str(milestones.get("imp_prep_str", fwd_disp_t))
                            add_row(
                                "",
                                f"{imp_prep_start_t} – {sim.fmt_time()}",
                                "Castle Age",
                                f"Send 8 Loom {fwd_src_lbl} vils forward at {fwd_disp_t} (60s walk)\n8 vils build Forward Castle (-650S, 60s) -> return to Wood\nKeep 7 vils on Stone (for extra Castles & repairs)\nAssign 3-TC Vils -> Farms / Wood / Gold to bank 1000F / 800G",
                                f"Forward Castle ready {milestones.get('fwd_castle_ready_str', '')}; satisfies Imperial Age building req w/ University/SW (rule 4.6).",
                            )
                        imp_clicked = True
                        imp_click_t = t
                        milestones["imp_click_s"] = t
                        milestones["imp_click_str"] = sim.fmt_time(t)
                        milestones["imp_click_vils"] = len(sim.vils)
                        milestones["imp_click_alloc"] = sim.current_macro_alloc()
                        milestones["imp_click_army"] = current_army_dict()
                        sim.spend(imp_cost, "ImperialClick")
                        sim.tc_busy_until[0] = t + int(imp_time)
                        sim.tc_action[0] = "imperial"
                        add_row(
                            f"{len(sim.vils)} ({sim.total_pop()})",
                            sim.fmt_time(),
                            "Castle Age",
                            "Click Imperial Age (-1000F, -800G, 190s)",
                            f"Army: {format_army_counts(current_army_dict()).replace('Army: ', '')}; reaches Imperial Age at {sim.fmt_time(t + int(imp_time))} (<40:00 per rule 6.5).",
                        )
                    elif tc_idx == 0 and not wheelbarrow_started and f_cnt_now >= 14 and first_hc_t is not None and not saving_for_imp and sim.bank.food >= 225 and sim.bank.wood >= (50 + house_wood_res):
                        wheelbarrow_started = True
                        sim.spend(ResourceBundle(food=175, wood=50), "Wheelbarrow")
                        sim.tc_busy_until[0] = t + 75
                        sim.tc_action[0] = "wheelbarrow"
                    elif not loom_started and tc_idx == 0 and first_hc_t is not None and sim.bank.gold >= 100:
                        loom_started = True
                        sim.spend(ResourceBundle(gold=50), "Loom")
                        sim.tc_busy_until[tc_idx] = t + 25
                        sim.tc_action[tc_idx] = "loom"
                    elif tc_idx == 0 and wheelbarrow_started and "wheelbarrow" in sim.upgrades and not hand_cart_started and tc3_started and not saving_for_imp and f_cnt_now >= 26 and sim.bank.food >= 520 and sim.bank.wood >= (200 + house_wood_res):
                        hand_cart_started = True
                        sim.spend(ResourceBundle(food=300, wood=200), "HandCart")
                        sim.tc_busy_until[0] = t + 55
                        sim.tc_action[0] = "hand_cart"
                    else:
                        max_vils_cap = 124
                        in_flight_vils = sum(1 for a in sim.tc_action if a.startswith("vil_"))
                        want_hold_imp = (
                            tc_idx == 0
                            and not imp_clicked
                            and imp_prep_started
                            and sim.bank.gold >= imp_cost.gold - 25
                            and sim.bank.food >= imp_cost.food - 35
                        )
                        if want_hold_imp:
                            if imp_hold_start_t is None:
                                imp_hold_start_t = t
                            hold_for_imp = (t - imp_hold_start_t) < int(rules.max_end_of_age_tc_idle_seconds)
                        else:
                            hold_for_imp = False
                        if not hold_for_imp and (len(sim.vils) + in_flight_vils) < max_vils_cap:
                            if sim.free_pop() <= 0:
                                housed_seconds += 1
                            elif sim.bank.food >= 50:
                                imp_hold_start_t = None
                                sim.spend(ResourceBundle(food=50), "vil_train")
                                sim.tc_busy_until[tc_idx] = t + 25
                                sim.tc_action[tc_idx] = f"vil_{len(sim.vils) + in_flight_vils + 1}"

            # University (100W) + Chemistry (300F, 200G, 100s) + Barracks + Range #1 -> immediate 1-Range HC!
            if not univ_started and sim.bank.wood >= (int(univ_cost.wood) + house_wood_res):
                univ_started = True
                sim.spend(univ_cost, "University")
                univ_ready_t = t + 10 + int(univ_build_time)
                sim.add_building("university", univ_ready_t)
                _pull_builders(sim, ("wood", "farm"), 1, univ_ready_t + 10)
                milestones["univ_ready_str"] = sim.fmt_time(univ_ready_t)

            if univ_ready_t is not None and t >= univ_ready_t and not chemistry_started:
                if queue_upg("chemistry", res_food=55):
                    chemistry_started = True
                    chemistry_ready_t = t + 100
                    milestones["chemistry_started_str"] = sim.fmt_time(t)
                    milestones["chemistry_done_str"] = sim.fmt_time(chemistry_ready_t)

            if not barracks_started and sim.bank.wood >= (175 + house_wood_res):
                barracks_started = True
                sim.spend(ResourceBundle(wood=175), "Barracks")
                barracks_ready_t = t + 10 + 50
                barracks_ready_times.append(barracks_ready_t)
                sim.add_building("barracks", barracks_ready_t)
                _pull_builders(sim, ("wood", "farm"), 1, barracks_ready_t + 10)

            # Monastery (175W) builds right after Chemistry starts & Range #1 is placed (ahead of Range #2!) -> train 2 Monks (100G each) for Relic control + conversions!
            if chemistry_started and ranges_started >= 1 and not monastery_started and sim.bank.wood >= (175 + house_wood_res):
                monastery_started = True
                sim.spend(ResourceBundle(wood=175), "Monastery")
                monastery_ready_t = t + 10 + 40
                sim.add_building("monastery", monastery_ready_t)
                _pull_builders(sim, ("wood", "farm"), 1, monastery_ready_t + 10)
                milestones["monastery_ready_str"] = sim.fmt_time(monastery_ready_t)

            if (
                monastery_ready_t is not None
                and t >= monastery_ready_t
                and first_hc_t is not None
                and monks_trained < 2
                and t >= monastery_busy_until
                and sim.free_pop() >= 1
                and sim.total_pop() < 195
                and sim.bank.gold >= 100
            ):
                monks_trained += 1
                sim.spend(ResourceBundle(gold=100), f"Monk{monks_trained}")
                sim.military_units["monk"] += 1
                monastery_busy_until = t + 51
                if monks_trained == 1:
                    relic1_time = t + 51 + 50
                if monks_trained == 2:
                    milestones["monks2_done_str"] = sim.fmt_time(t + 51)

            # Monastery eco techs (Fervor +15% vil speed, Sanctity +15 vil HP) once Imperial clicked
            if imp_clicked and monastery_ready_t is not None and t >= monastery_ready_t and monks_trained >= 2 and t >= monastery_busy_until:
                if not fervor_started and queue_upg("fervor"):
                    fervor_started = True
                    monastery_busy_until = t + 50
                elif fervor_started and not sanctity_started and queue_upg("sanctity"):
                    sanctity_started = True
                    monastery_busy_until = t + 60

            # Range #1 builds ASAP; Ranges #2 & #3 delay until Monastery is placed & 1-Range HC production has started;
            # Ranges #4-#5, Barracks #2-#3, Stables #1-#3, and Siege Workshop #2 scale after clicking Imperial!
            if barracks_ready_t is not None and t >= barracks_ready_t:
                max_ranges = 5 if imp_clicked else 3
                want_range = (ranges_started == 0) or (ranges_started < max_ranges and first_hc_t is not None and monastery_started)
                if want_range and sim.bank.wood >= (175 + house_wood_res + (175 if (ranges_started >= 1 and not monastery_started) else 0)):
                    if ranges_started < 3 or (stables_started >= 2 and len(sw_ready_times) >= 2 and len(barracks_ready_times) >= 2):
                        ranges_started += 1
                        sim.spend(ResourceBundle(wood=175), f"Range{ranges_started}")
                        r_ready = t + 10 + 50
                        range_ready_times.append(r_ready)
                        sim.add_building("archery range", r_ready)
                        _pull_builders(sim, ("wood", "farm"), 1, r_ready + 10)
                        if ranges_started == 1:
                            milestones["range1_ready_str"] = sim.fmt_time(r_ready)
                        if ranges_started == 2:
                            milestones["range2_ready_str"] = sim.fmt_time(r_ready)
                        if ranges_started == 3:
                            milestones["ranges3_ready_str"] = sim.fmt_time(r_ready)

            # Siege Workshop #1 in Castle; Siege Workshop #2 after Imperial click
            if first_hc_t is not None and ranges_started >= 2 and not sw_started and sim.bank.wood >= (200 + house_wood_res):
                sw_started = True
                sim.spend(ResourceBundle(wood=200), "SiegeWorkshop1")
                sw_ready_t = t + 10 + 40
                sw_ready_times.append(sw_ready_t)
                sim.add_building("siege workshop", sw_ready_t)
                _pull_builders(sim, ("wood", "farm"), 1, sw_ready_t + 10)
                milestones["sw_ready_str"] = sim.fmt_time(sw_ready_t)

            if imp_clicked and len(sw_ready_times) < 2 and sim.bank.wood >= (200 + house_wood_res):
                sim.spend(ResourceBundle(wood=200), "SiegeWorkshop2")
                sw2_ready = t + 10 + 40
                sw_ready_times.append(sw2_ready)
                sim.add_building("siege workshop", sw2_ready)
                _pull_builders(sim, ("wood", "farm"), 1, sw2_ready + 10)

            # Stables #1-#3 & Barracks #2-#3 after Imperial click
            if imp_clicked:
                max_stables = 3 if sim.age == 4 else 2
                if stables_started < max_stables and sim.bank.wood >= (175 + house_wood_res):
                    stables_started += 1
                    sim.spend(ResourceBundle(wood=175), f"Stable{stables_started}")
                    st_ready = t + 10 + 50
                    stable_ready_times.append(st_ready)
                    sim.add_building("stable", st_ready)
                    _pull_builders(sim, ("wood", "farm"), 1, st_ready + 10)

                max_barracks = 3
                if len(barracks_ready_times) < max_barracks and stables_started >= 1 and sim.bank.wood >= (175 + house_wood_res):
                    sim.spend(ResourceBundle(wood=175), f"Barracks{len(barracks_ready_times)+1}")
                    b_ready = t + 10 + 50
                    barracks_ready_times.append(b_ready)
                    sim.add_building("barracks", b_ready)
                    _pull_builders(sim, ("wood", "farm"), 1, b_ready + 10)

            # Pre-Stone milestone row at Vil #46 (explains allocations right before moving Wood vils to Stone!)
            if (
                sim.age == 3
                and v37_loop_logged
                and not v46_pre_stone_logged
                and not stone_ramp_started
                and len(sim.vils) == 46
                and sw_started
            ):
                v46_pre_stone_logged = True
                milestones["v46_str"] = sim.fmt_time(t)
                milestones["v46_alloc"] = sim.current_macro_alloc()
                add_row(
                    f"{len(sim.vils)} ({sim.total_pop()})",
                    f"{milestones.get('v37_str', sim.fmt_time())} – {sim.fmt_time(t)}",
                    "Castle Age",
                    "Queue Vils #38–#46 -> Wood (shift 3 Wood vils -> Gold to 10 Gold)\nWood vils build Archery Ranges #2 & #3 (-175W each), LC #2 (-100W) & Siege Workshop (-200W) -> Wood\nResearch Pikeman (-160F, -90G) & train Pikemen at Barracks",
                    f"Pre-Stone allocation at Vil #46 ({sim.count_role('farm')} Farms, {sim.count_role('wood', 'straggler')} Wood, {sim.count_role('gold')} Gold, 0 Stone) before moving Wood vils to Stone.",
                )

            # Build Stone Mining Camp (-100W) & move 7 Wood vils to Stone once Ranges #2-#3 & SW are placed (keep 7 on Stone permanently!)
            if ranges_started >= 3 and sw_started and not stone_ramp_started and sim.bank.wood >= (100 + house_wood_res):
                stone_ramp_started = True
                sim.spend(ResourceBundle(wood=100), "StoneMC")
                smc_comp = t + int(rules.camp_or_berry_walk_time_one_way) + 35
                sim.add_building("mining camp", smc_comp)
                moved_s = 0
                moved_from_counts = {"wood": 0, "farm": 0}
                for pref_r in ("wood", "farm"):
                    for v in sim.vils:
                        if v["role"] == pref_r and int(v["busy_until"]) <= t and moved_s < 7:
                            v["role"] = "stone"
                            v["busy_until"] = smc_comp if moved_s == 0 else (t + int(rules.camp_or_berry_walk_time_one_way))
                            moved_s += 1
                            moved_from_counts[pref_r] += 1
                milestones["stone_started_str"] = sim.fmt_time(t)
                milestones["stone_started_vils"] = len(sim.vils)
                milestones["stone_started_alloc"] = sim.current_macro_alloc()
                src_desc = "Wood" if moved_from_counts["farm"] == 0 else f"{moved_from_counts['wood']} Wood / {moved_from_counts['farm']} Farm"
                add_row(
                    f"{len(sim.vils)} ({sim.total_pop()})",
                    sim.fmt_time(t),
                    "Castle Age",
                    f"Vil #47 -> Wood\n1 Wood vil builds Mining Camp (-100W) on Stone\nMove 7 {src_desc} vils (including builder) -> Stone",
                    "Ready +50s; leftover 100S pays for TC #2, and all 7 Stone miners stay on Stone (~165S/min w/ Free Stone + Shaft Mining) for TC #3 (100S), Forward Castle (650S), extra Castles & repairs.",
                )

            # TC #2 (uses our remaining 100S!) & TC #3 unlock after 1-Range HC starts + Ranges #2-#3 & SW are started!
            tc_unlock = first_hc_t is not None and ranges_started >= 3 and sw_started and f_cnt_now >= 15
            if tc_unlock and not tc2_started and sim.bank.wood >= (275 + house_wood_res) and sim.bank.stone >= 100:
                tc2_started = True
                sim.spend(ResourceBundle(wood=275, stone=100), "TC2")
                tc2_ready_t = t + 10 + int(round(calc_construction_time(150.0, 3)))
                sim.add_pending_pop_building(tc2_ready_t, 5, "town center")
                _pull_builders(sim, ("wood", "farm"), 3, tc2_ready_t + 10)
                milestones["tc2_started_str"] = sim.fmt_time(t)
            if tc_unlock and tc2_started and not tc3_started and sim.bank.wood >= (275 + house_wood_res) and sim.bank.stone >= 100:
                tc3_started = True
                sim.spend(ResourceBundle(wood=275, stone=100), "TC3")
                tc3_ready_t = t + 10 + int(round(calc_construction_time(150.0, 3)))
                sim.add_pending_pop_building(tc3_ready_t, 5, "town center")
                _pull_builders(sim, ("wood", "farm"), 3, tc3_ready_t + 10)
                milestones["tc3_started_str"] = sim.fmt_time(t)

            if ranges_started >= 2 and not lc2_built and bow_saw_started and w_cnt_now >= 9 and sim.bank.wood >= (100 + house_wood_res + (175 if ranges_started < 3 else 0)):
                lc2_built = True
                sim.spend(ResourceBundle(wood=100), "LC2")
                lc2_comp = t + 15 + 35
                c2_idx = sim.add_lumber_camp(lc2_comp)
                moved_w = 0
                for v in sim.vils:
                    if v["role"] in ("straggler", "wood") and int(v["busy_until"]) <= t and moved_w < 7:
                        v["role"] = "wood"
                        v["camp_idx"] = c2_idx
                        v["busy_until"] = lc2_comp if moved_w == 0 else (t + 15)
                        moved_w += 1

            # Continuous Castle/Imp Farm seeder (prioritize Univ/Rax/Range1/Monastery, then Ranges 2-3 & SW, then Stone/TCs + Farms)
            if f_cnt_now < 14:
                bldg_w_res = (
                    (int(univ_cost.wood) if not univ_started else 0)
                    + (175 if not barracks_started else 0)
                    + (175 if (barracks_ready_t is not None and ranges_started < 1) else 0)
                    + (175 if (chemistry_started and not monastery_started) else 0)
                )
            elif not monastery_started:
                bldg_w_res = 175
            elif ranges_started < 3:
                bldg_w_res = 175
            elif not sw_started:
                bldg_w_res = 200
            elif not stone_ramp_started:
                bldg_w_res = 100
            elif not tc2_started or not tc3_started:
                bldg_w_res = 275 if (f_cnt_now >= 15 and w_cnt_now < 20) else 0
            elif sim.age == 4 and not siege_engineers_started:
                bldg_w_res = 600
            elif imp_clicked and (stables_started < 2 or len(barracks_ready_times) < 3 or len(sw_ready_times) < 2 or ranges_started < 5):
                bldg_w_res = 200
            else:
                bldg_w_res = 0
            farm_cap_now = 15 if first_hc_t is None else (36 if not imp_clicked else 50)
            min_w_keep = 8 if first_hc_t is None else (12 if not imp_clicked else 20)
            can_seed_farms = bow_saw_started and f_cnt_now < farm_cap_now and w_cnt_now > min_w_keep
            if can_seed_farms and sim.bank.food < 1100 and sim.bank.wood >= (60 + house_wood_res + bldg_w_res):
                for v in sim.vils:
                    if v["role"] in ("straggler", "wood") and int(v["busy_until"]) <= t:
                        walk_t = (
                            int(rules.farm_walk_time)
                            if v["role"] == "straggler"
                            else int(rules.camp_or_berry_walk_time_one_way)
                        )
                        sim.spend(ResourceBundle(wood=60), "CastleFarm")
                        v["role"] = "farm"
                        v["busy_until"] = t + walk_t + 15
                        sim.register_new_farm(t + walk_t + 15)
                        break

            # Keep the 7 Stone vils on Stone permanently so player can build extra Castles and/or repair them.

            if chemistry_ready_t is not None and t >= chemistry_ready_t and not chemistry_logged:
                chemistry_logged = True
                add_row(
                    f"{len(sim.vils)} ({sim.total_pop()})",
                    f"{sim.fmt_time(castle_reached_t or t)} – {sim.fmt_time()}",
                    "Castle Age",
                    "University completes -> Research Chemistry (-300F, -200G, 100s)\n1 Wood vil builds Archery Range #1 (-175W) -> Wood\n1 Wood vil builds Monastery (-175W) -> Wood\nQueue Vils #27–#32 -> Wood & seed Farm #9 (-60W, from Wood)",
                    f"Bohemians save 100W on University; Chemistry finishes at {sim.fmt_time()} for immediate 1-Range Hand Cannoneers.",
                )

            # Upgrades at Mill, Lumber Camp, Blacksmith, Barracks, and Stables
            saving_for_houfnice = (
                sim.age == 4
                and not houfnice_started
                and sim.military_units["bombard_cannon"] >= 5
                and len(sim.vils) >= 100
            )
            if imp_clicked and not heavy_plow_started and queue_upg("heavy plow", res_food=60 * sim.tc_count):
                heavy_plow_started = True
            if sim.age == 4 and not two_man_saw_started and queue_upg("two-man saw", res_food=60 * sim.tc_count, res_wood=house_wood_res):
                two_man_saw_started = True

            if t >= bs_busy_until:
                if not padded_armor_started and chemistry_started and queue_upg("padded archer armor", res_food=60 * sim.tc_count + 40):
                    padded_armor_started = True
                    bs_busy_until = t + 40
                elif padded_armor_started and "padded archer armor" in sim.upgrades and not leather_armor_started and queue_upg("leather archer armor", res_food=60 * sim.tc_count + 40, res_gold=100):
                    leather_armor_started = True
                    bs_busy_until = t + 55
                elif sim.age == 4 and leather_armor_started and "leather archer armor" in sim.upgrades and not ring_armor_started and queue_upg("ring archer armor", res_food=60 * sim.tc_count + 40, res_gold=150):
                    ring_armor_started = True
                    bs_busy_until = t + 70
                elif imp_clicked and not forging_started and queue_upg("forging", res_food=60 * sim.tc_count):
                    forging_started = True
                    bs_busy_until = t + 50
                elif imp_clicked and forging_started and "forging" in sim.upgrades and not scale_mail_started and queue_upg("scale mail armor", res_food=60 * sim.tc_count):
                    scale_mail_started = True
                    bs_busy_until = t + 40
                elif imp_clicked and scale_mail_started and "scale mail armor" in sim.upgrades and not scale_barding_started and queue_upg("scale barding armor", res_food=60 * sim.tc_count):
                    scale_barding_started = True
                    bs_busy_until = t + 45
                elif imp_clicked and scale_barding_started and "scale barding armor" in sim.upgrades and not chain_mail_started and queue_upg("chain mail armor", res_food=60 * sim.tc_count):
                    chain_mail_started = True
                    bs_busy_until = t + 55
                elif imp_clicked and chain_mail_started and "chain mail armor" in sim.upgrades and not iron_casting_started and not saving_for_houfnice and queue_upg("iron casting", res_food=60 * sim.tc_count):
                    iron_casting_started = True
                    bs_busy_until = t + 75
                elif sim.age == 4 and "chain mail armor" in sim.upgrades and not plate_mail_started and not saving_for_houfnice and queue_upg("plate mail armor", res_food=60 * sim.tc_count):
                    plate_mail_started = True
                    bs_busy_until = t + 70
                elif sim.age == 4 and "scale barding armor" in sim.upgrades and not chain_barding_started and not saving_for_houfnice and queue_upg("chain barding armor", res_food=60 * sim.tc_count):
                    chain_barding_started = True
                    bs_busy_until = t + 60
                elif sim.age == 4 and "iron casting" in sim.upgrades and not blast_furnace_started and not saving_for_houfnice and queue_upg("blast furnace", res_food=60 * sim.tc_count):
                    blast_furnace_started = True
                    bs_busy_until = t + 100

            if barracks_ready_t is not None and t >= barracks_ready_t and t >= rax_busy_until[0]:
                if not pikeman_upg_started and first_hc_t is not None and sim.bank.food >= (160 + 60 * sim.tc_count) and sim.bank.gold >= 90:
                    pikeman_upg_started = True
                    sim.spend(ResourceBundle(food=160, gold=90), "PikemanUpg")
                    sim.queue_upgrade("pikeman", t + 45)
                    rax_busy_until[0] = t + 45
                elif imp_clicked and "pikeman" in sim.upgrades and not squires_started and queue_upg("squires", res_food=60 * sim.tc_count):
                    squires_started = True
                    rax_busy_until[0] = t + 25
                elif sim.age == 4 and "pikeman" in sim.upgrades and not halberdier_upg_started and sim.bank.food >= 420 and sim.bank.gold >= 600:
                    halberdier_upg_started = True
                    sim.spend(ResourceBundle(food=300, gold=600), "HalberdierUpg")
                    sim.queue_upgrade("halberdier", t + 50)
                    rax_busy_until[0] = t + 50

            if stable_ready_times and t >= stable_ready_times[0] and t >= stable_busy_until[0]:
                if not light_cav_upg_started and queue_upg("light cavalry", res_food=60 * sim.tc_count):
                    light_cav_upg_started = True
                    stable_busy_until[0] = t + 45
                elif light_cav_upg_started and "light cavalry" in sim.upgrades and not husbandry_started and queue_upg("husbandry", res_food=60 * sim.tc_count):
                    husbandry_started = True
                    stable_busy_until[0] = t + 40

            if not light_cav_converted and "light cavalry" in sim.upgrades:
                light_cav_converted = True
                if sim.military_units["scout"] > 0:
                    sim.military_units["scout"] -= 1
                    sim.military_units["light_cav"] += 1

            saving_for_imp = imp_prep_started and not imp_clicked
            tc_food_res = 75 * sim.tc_count
            monk_g_res = 100 if (monastery_ready_t is not None and t >= monastery_ready_t and first_hc_t is not None and monks_trained < 2 and t >= monastery_busy_until - 10) else 0
            houf_f_res = 1100 if saving_for_houfnice else 0
            houf_g_res = 800 if saving_for_houfnice else 0

            # Hand Cannoneers from active Ranges (cap 32 in Castle, 36 in Imp; leave pop room for 124 vils + 6 Bombards/Houfnices + Light Cav + Halbs)
            hc_train_s = 25 if "conscription" in sim.upgrades else 34
            hc_cap = 32 if not imp_clicked else 36
            bbc_target = 6
            bbc_pop_res = max(0, bbc_target - sim.military_units["bombard_cannon"]) if (imp_clicked or sim.age == 4) else 0
            if "chemistry" in sim.upgrades:
                for idx, r_ready in enumerate(range_ready_times):
                    if (
                        t >= r_ready
                        and t >= range_busy_until[idx]
                        and not (saving_for_imp and (sim.bank.food < imp_cost.food + 45 or sim.bank.gold < imp_cost.gold + 50))
                        and sim.free_pop() >= 1
                        and sim.total_pop() < (200 - bbc_pop_res)
                        and sim.military_units["hand_cannoneer"] < hc_cap
                        and sim.bank.food >= (45 + tc_food_res + (houf_f_res if sim.military_units["hand_cannoneer"] >= 32 else 0))
                        and sim.bank.gold >= (50 + monk_g_res + (houf_g_res if sim.military_units["hand_cannoneer"] >= 32 else 0))
                    ):
                        sim.spend(ResourceBundle(food=45, gold=50), "HandCannoneer")
                        range_busy_until[idx] = t + hc_train_s
                        sim.military_units["hand_cannoneer"] += 1
                        if first_hc_t is None:
                            first_hc_t = t
                            milestones["first_hc_str"] = sim.fmt_time(t)

            # Mangonels (Castle), Bombard Cannons & Houfnice upgrade (Imperial) from 2 Siege Workshops
            mang_target = 2
            for sw_idx, sw_r in enumerate(sw_ready_times):
                if t >= sw_r and t >= sw_busy_until[sw_idx] and "chemistry" in sim.upgrades and not saving_for_imp:
                    if (
                        sim.age == 4
                        and sw_idx == 0
                        and not houfnice_started
                        and sim.military_units["bombard_cannon"] >= 5
                        and len(sim.vils) >= 100
                        and queue_upg("houfnice")
                    ):
                        houfnice_started = True
                        houfnice_ready_t = t + 140
                        sw_busy_until[sw_idx] = houfnice_ready_t
                        milestones["houfnice_started_str"] = sim.fmt_time(t)
                        milestones["houfnice_done_str"] = sim.fmt_time(houfnice_ready_t)
                    elif (
                        sim.age == 4
                        and sim.military_units["bombard_cannon"] < bbc_target
                        and sim.free_pop() >= 1
                        and sim.total_pop() < 200
                        and sim.bank.wood >= (225 + house_wood_res)
                        and sim.bank.gold >= (225 + (houf_g_res if sim.military_units["bombard_cannon"] >= 5 else 0))
                    ):
                        sim.spend(ResourceBundle(wood=225, gold=225), "BombardCannon")
                        sw_busy_until[sw_idx] = t + (42 if "conscription" in sim.upgrades else 56)
                        sim.military_units["bombard_cannon"] += 1
                    elif (
                        sim.age == 3
                        and sim.military_units["mangonel"] < mang_target
                        and sim.free_pop() >= 1
                        and sim.total_pop() < 195
                        and sim.bank.wood >= (160 + house_wood_res)
                        and sim.bank.gold >= (135 + monk_g_res)
                    ):
                        sim.spend(ResourceBundle(wood=160, gold=135), "Mangonel")
                        sw_busy_until[sw_idx] = t + 46
                        sim.military_units["mangonel"] += 1

            # Light Cavalry from Stables (once Light Cavalry upgrade completes)
            lcav_target = 12
            lcav_train_s = 23 if "conscription" in sim.upgrades else 30
            if "light cavalry" in sim.upgrades:
                for st_idx, st_r in enumerate(stable_ready_times):
                    if (
                        t >= st_r
                        and t >= stable_busy_until[st_idx]
                        and sim.military_units["light_cav"] < lcav_target
                        and sim.free_pop() >= 1
                        and sim.total_pop() < (200 - bbc_pop_res)
                        and sim.bank.food >= (80 + tc_food_res + houf_f_res)
                    ):
                        sim.spend(ResourceBundle(food=80), "LightCav")
                        stable_busy_until[st_idx] = t + lcav_train_s
                        sim.military_units["light_cav"] += 1

            # Pikemen / Halberdiers from Barracks (#1-#3)
            pike_target = 8 if not imp_clicked else 16
            for b_idx, b_r in enumerate(barracks_ready_times):
                if (
                    t >= b_r
                    and t >= rax_busy_until[b_idx]
                    and "pikeman" in sim.upgrades
                    and sim.military_units["pikeman"] < pike_target
                    and not (saving_for_imp and sim.bank.food < imp_cost.food + 35)
                    and sim.free_pop() >= 1
                    and sim.total_pop() < (200 - bbc_pop_res)
                    and sim.bank.food >= (35 + tc_food_res + (houf_f_res if sim.military_units["pikeman"] >= 10 else 0))
                    and sim.bank.wood >= (25 + house_wood_res)
                ):
                    sim.spend(ResourceBundle(food=35, wood=25), "Pikeman")
                    rax_busy_until[b_idx] = t + (17 if "conscription" in sim.upgrades else 22)
                    sim.military_units["pikeman"] += 1

            if not mil_loop_logged and stone_ramp_started and ranges_started >= 3 and sw_started and sim.military_units["mangonel"] >= 2:
                mil_loop_logged = True
                add_row(
                    f"{len(sim.vils)} ({sim.total_pop()})",
                    f"{milestones.get('stone_started_str', sim.fmt_time())} – {sim.fmt_time()}",
                    "Castle Age",
                    "Continue 3-Range Hand Cannoneers + 2+ Mangonels (-160W, -135G each) + Pikemen\nQueue Vils #48–#50 -> Wood & seed Farm #15 (-60W, from Wood)\nKeep all 7 vils on Stone",
                    f"3-Range + Siege production online ({format_army_counts(current_army_dict()).replace('Army: ', '')}); 7 Stone miners banking 750S for TC #3 + Forward Castle.",
                )

            if not tc_expand_logged and tc3_ready_t is not None and t >= tc3_ready_t:
                tc_expand_logged = True
                milestones["boom3tc_ready_str"] = sim.fmt_time(t)
                milestones["boom3tc_vils"] = len(sim.vils)
                milestones["boom3tc_alloc"] = sim.current_macro_alloc()
                add_row(
                    f"{len(sim.vils)} ({sim.total_pop()})",
                    f"{milestones.get('tc2_started_str', sim.fmt_time())} – {sim.fmt_time()}",
                    "Castle Age",
                    "3 Wood/Farm vils build TC #2 (-275W, -100S) -> return to Wood/Farms\n3 Wood/Farm vils build TC #3 (-275W, -100S) -> return to Wood/Farms\nQueue 3-TC Vils -> Farms / Wood / Gold (keep 7 on Stone)",
                    f"TC #2 uses remaining 100S from Dark Age; 3-TC eco + 3-Range production active ({format_army_counts(current_army_dict()).replace('Army: ', '')}).",
                )

            # Forward Castle expedition (8 Loom vils from Wood/Farms, 60s walk per rule 2.10; never pull Stone miners)
            if (
                "chemistry" in sim.upgrades
                and "loom" in sim.upgrades
                and tc3_started
                and sim.military_units["hand_cannoneer"] >= 14
                and sim.military_units["mangonel"] >= 2
                and sim.bank.stone >= 650
                and not fwd_vils_dispatched
            ):
                fwd_vils_dispatched = True
                fwd_vils_arrive_t = t + int(rules.forward_walk_time_default)
                milestones["fwd_vils_dispatched_str"] = sim.fmt_time(t)
                fwd_src = {"wood": 0, "farm": 0}
                for pref_r in ("wood", "farm"):
                    for v in sim.vils:
                        if v["role"] == pref_r and int(v["busy_until"]) <= t and len(fwd_vils) < 8:
                            v["role"] = "forward"
                            v["busy_until"] = fwd_vils_arrive_t + 120
                            fwd_vils.append(v)
                            fwd_src[pref_r] += 1
                milestones["fwd_vils_src_str"] = (
                    "Wood"
                    if fwd_src["farm"] == 0
                    else f"{fwd_src['wood']} Wood / {fwd_src['farm']} Farm"
                )

            if fwd_vils_arrive_t is not None and t >= fwd_vils_arrive_t and not fwd_castle_started and sim.bank.stone >= 650:
                fwd_castle_started = True
                sim.spend(ResourceBundle(stone=650), "ForwardCastle")
                c_b = int(round(calc_construction_time(200.0, max(1, len(fwd_vils)))))
                fwd_castle_ready_t = t + c_b
                sim.add_pending_pop_building(fwd_castle_ready_t, 20, "castle")
                milestones["fwd_castle_started_str"] = sim.fmt_time(t)
                milestones["fwd_castle_ready_str"] = sim.fmt_time(fwd_castle_ready_t)
                for v in fwd_vils:
                    v["busy_until"] = fwd_castle_ready_t

            if fwd_castle_ready_t is not None and t >= fwd_castle_ready_t:
                cur_camp = max(0, len(sim.lumber_camps) - 1)
                for v in fwd_vils:
                    if v["role"] == "forward" and int(v["busy_until"]) <= t:
                        v["role"] = "wood"
                        v["camp_idx"] = cur_camp
                        v["busy_until"] = t + int(rules.forward_walk_time_default)

            # Imp prep once Forward Castle expedition has launched + 3 TCs up + solid army!
            if (
                sim.age == 3
                and not imp_prep_started
                and tc3_ready_t is not None
                and t >= tc3_ready_t
                and fwd_vils_dispatched
                and len(sim.vils) >= 65
                and sim.military_units["hand_cannoneer"] >= 18
            ):
                imp_prep_started = True
                milestones["imp_prep_str"] = sim.fmt_time(t)

            # Extra Castles every time Stone reaches ~800S after clicking Imperial + Forward Castle started
            if (
                (imp_clicked or sim.age == 4)
                and fwd_castle_started
                and (extra_castle_ready_t is None or t >= extra_castle_ready_t)
                and sim.bank.stone >= 800
            ):
                extra_castles_started += 1
                sim.spend(ResourceBundle(stone=650), f"Castle{extra_castles_started + 1}")
                c_ex = int(round(calc_construction_time(200.0, 6)))
                extra_castle_ready_t = t + 10 + c_ex
                sim.add_pending_pop_building(extra_castle_ready_t, 20, "castle")
                _pull_builders(sim, ("wood", "farm"), 6, extra_castle_ready_t + 10)
                milestones[f"castle{extra_castles_started + 1}_str"] = sim.fmt_time(extra_castle_ready_t)

            # Trebuchets & Castle/University Imperial Techs
            if sim.age == 4 and fwd_castle_ready_t is not None and t >= fwd_castle_ready_t:
                if t >= castle_busy_until:
                    treb_target = 2
                    treb_train_s = 38 if "conscription" in sim.upgrades else 50
                    if (
                        sim.military_units["trebuchet"] < treb_target
                        and sim.free_pop() >= 1
                        and sim.total_pop() < 200
                        and sim.bank.wood >= (200 + house_wood_res)
                        and sim.bank.gold >= (200 + houf_g_res)
                    ):
                        sim.spend(ResourceBundle(wood=200, gold=200), "Trebuchet")
                        castle_busy_until = t + treb_train_s
                        sim.military_units["trebuchet"] += 1
                    elif not wagenburg_started and sim.military_units["trebuchet"] >= 2 and not saving_for_houfnice and sim.bank.food >= 300 and sim.bank.gold >= 300:
                        wagenburg_started = True
                        sim.spend(ResourceBundle(food=300, gold=300), "WagenburgTactics")
                        sim.queue_upgrade("wagenburg tactics", t + 45)
                        castle_busy_until = t + 45

                if univ_ready_t is not None and t >= univ_ready_t and not siege_engineers_started and sim.military_units["trebuchet"] >= 2:
                    if queue_upg("siege engineers", res_food=100, res_wood=100):
                        siege_engineers_started = True

            # Refresh Lumber Camp when worst active camp hits <= 65% (rule 3.4)
            if (
                t - last_lc_refresh_t >= 240
                and sim.min_active_camp_efficiency() <= rules.wood_refresh_lc_threshold
                and not saving_for_imp
                and sim.bank.wood >= (350 + house_wood_res)
                and sim.count_role("wood") >= 6
            ):
                last_lc_refresh_t = t
                sim.spend(ResourceBundle(wood=100), "LumberCampRefresh")
                new_idx = sim.add_lumber_camp(t + 15 + 35)
                sim.reassign_woodcutters_to_new_camp(new_idx, min(8, sim.count_role("wood")))

            # Anti-float rebalancer + Gold -> Stone / Wood / Farms shifting + Market fallback!
            if t % 10 == 0 and t >= (castle_reached_t or 0) + 90:
                g_cnt_r = sim.count_role("gold")
                w_cnt_r = sim.count_role("wood", "straggler")
                f_cnt_r = sim.count_role("farm")
                s_cnt_r = sim.count_role("stone")
                cur_camp = max(0, len(sim.lumber_camps) - 1)

                # 1) Gold float guard: keep >= 10 Gold vils once 3 Ranges are active so Mangonels/HCs/Bombards don't starve!
                gold_float_thresh = 880 if (saving_for_imp or saving_for_houfnice) else (480 if sim.age == 3 else 750)
                min_gold_vils = 10 if ranges_started >= 3 else 4
                if sim.bank.gold > gold_float_thresh and g_cnt_r > min_gold_vils:
                    stone_target_chk = 660 if tc3_started else 760
                    if stone_ramp_started and not fwd_castle_started and sim.bank.stone < stone_target_chk and s_cnt_r < 7:
                        moved = 0
                        for v in sim.vils:
                            if v["role"] == "gold" and int(v["busy_until"]) <= t and moved < 3:
                                v["role"] = "stone"
                                v["busy_until"] = t + 15
                                moved += 1
                    elif (sim.bank.wood < 450 or ranges_started < 3) and w_cnt_r < (34 if imp_clicked else 22):
                        moved = 0
                        for v in sim.vils:
                            if v["role"] == "gold" and int(v["busy_until"]) <= t and moved < 3:
                                v["role"] = "wood"
                                v["camp_idx"] = cur_camp
                                v["busy_until"] = t + 15
                                moved += 1
                    elif sim.bank.food < 1050 and f_cnt_r < (50 if imp_clicked else 46) and sim.bank.wood >= (180 + house_wood_res):
                        moved = 0
                        for v in sim.vils:
                            if v["role"] == "gold" and int(v["busy_until"]) <= t and moved < 3:
                                sim.spend(ResourceBundle(wood=60), "ShiftGoldToFarm")
                                v["role"] = "farm"
                                v["busy_until"] = t + 30
                                sim.register_new_farm(t + 30)
                                moved += 1
                                if moved >= 3 or sim.bank.wood < (120 + house_wood_res):
                                    break
                # 2) Pull vils back from surplus Wood/Farms to Gold when Gold drops low (or below 10 Gold vils with 3 Ranges)
                elif (sim.bank.gold < (850 if (saving_for_imp or saving_for_houfnice) else (650 if sim.age == 4 else 380)) or (ranges_started >= 3 and g_cnt_r < 10 and sim.bank.gold < 600)) and (sim.bank.wood > 350 or sim.bank.food > 800 or w_cnt_r > 18 or f_cnt_r > 24) and g_cnt_r < 28:
                    src_role = "farm" if (sim.bank.food > 1050 and f_cnt_r > 22) else ("wood" if w_cnt_r > 16 else None)
                    if src_role:
                        moved = 0
                        for v in sim.vils:
                            if v["role"] == src_role and int(v["busy_until"]) <= t and moved < 3:
                                v["role"] = "gold"
                                v["busy_until"] = t + 15
                                moved += 1
                # 3) Excess Food -> Wood if Wood low
                elif (not saving_for_imp and not saving_for_houfnice and sim.bank.food > 950 and sim.bank.wood < 450 and f_cnt_r > 18) or (sim.age == 4 and not siege_engineers_started and sim.bank.wood < 650 and sim.bank.food > 800 and f_cnt_r > 24):
                    moved = 0
                    for v in sim.vils:
                        if v["role"] == "farm" and int(v["busy_until"]) <= t and moved < 4:
                            v["role"] = "wood"
                            v["camp_idx"] = cur_camp
                            v["busy_until"] = t + 15
                            moved += 1
                # 4) Excess Wood -> Farms once Ranges/SW/TCs are placed (don't steal 275W from TC #2/#3 or 600W Siege Eng!)
                if tc3_started and (sim.age < 4 or siege_engineers_started) and sim.bank.wood > (300 + house_wood_res) and sim.bank.food < (1200 if saving_for_houfnice else 950) and w_cnt_r > 16 and f_cnt_r < (50 if imp_clicked else 42):
                    moved = 0
                    for v in sim.vils:
                        if v["role"] == "wood" and int(v["busy_until"]) <= t and moved < 4:
                            sim.spend(ResourceBundle(wood=60), "ShiftWoodToFarm")
                            v["role"] = "farm"
                            v["busy_until"] = t + 30
                            sim.register_new_farm(t + 30)
                            moved += 1
                            if moved >= 4 or sim.bank.wood < (240 + house_wood_res):
                                break

                # 5) Market buy/sell balancing:
                #    - Worst case: buy 100-200 of bottlenecked Wood/Food/Stone when floating excess Gold!
                #    - Or sell excess Wood/Food if Gold < 780 during Imp click prep / Imp
                if (t - last_market_trade_t) >= 40:
                    if saving_for_imp and sim.bank.gold >= 1020 and sim.bank.food < 1000:
                        last_market_trade_t = t
                        sim.buy_at_market("food", 200 if sim.bank.gold >= 1220 and sim.bank.food < 850 else 100)
                    elif not saving_for_imp and sim.age == 3 and sim.bank.gold >= 680 and sim.bank.wood < 275 and (ranges_started < 3 or not sw_started or not tc3_started):
                        last_market_trade_t = t
                        sim.buy_at_market("wood", 200 if sim.bank.gold >= 950 and sim.bank.wood < 150 else 100)
                    elif stone_ramp_started and not fwd_castle_started and sim.bank.stone >= 450 and sim.bank.stone < 650 and sim.bank.gold >= (760 if not saving_for_imp else 1050):
                        last_market_trade_t = t
                        sim.buy_at_market("stone", 100)
                    elif not saving_for_imp and sim.age == 3 and sim.bank.gold >= 800 and sim.bank.food < 350:
                        last_market_trade_t = t
                        sim.buy_at_market("food", 100)
                    elif sim.age == 4 and not siege_engineers_started and sim.bank.wood < 620 and sim.bank.gold >= 850:
                        last_market_trade_t = t
                        sim.buy_at_market("wood", 200)
                    elif sim.age == 3 and imp_prep_started and not imp_clicked:
                        if sim.bank.food >= 1000 and sim.bank.gold < 780 and sim.bank.wood >= 350:
                            last_market_trade_t = t
                            sim.sell_at_market("wood", 100)
                        elif sim.bank.food >= 1200 and sim.bank.gold < 780:
                            last_market_trade_t = t
                            sim.sell_at_market("food", 100)
                    elif sim.age == 4 and (sim.bank.wood >= 1200 or sim.bank.food >= 1200) and sim.bank.gold < 1200:
                        if sim.bank.wood >= 1200:
                            last_market_trade_t = t
                            sim.sell_at_market("wood", 200)
                        elif sim.bank.food >= 1200:
                            last_market_trade_t = t
                            sim.sell_at_market("food", 200)

            # Log Vils #32-#37 transition right after Berries finish -> 14 Farms, Wheelbarrow & 3 Wood vils -> Gold
            if (
                sim.age == 3
                and chemistry_logged
                and not v37_loop_logged
                and len(sim.vils) >= 37
                and sim.count_role("gold") >= 7
            ):
                v37_loop_logged = True
                milestones["v37_str"] = sim.fmt_time(t)
                milestones["v37_alloc"] = sim.current_macro_alloc()
                add_row(
                    f"{len(sim.vils)} ({sim.total_pop()})",
                    f"{milestones.get('first_hc_str', sim.fmt_time())} – {sim.fmt_time(t)}",
                    "Castle Age",
                    "Train Hand Cannoneers at Range #1 & 2 Monks (-100G each) at Monastery\nQueue Loom (-50G) at TC\nAt Vil #33: 4 Berry vils finish -> move from Berries to Wood/Stragglers; move 5 Wood/Straggler vils -> Seed Farms #10–#14 (-60W each)\nAt Vil #36: Research Wheelbarrow (-175F, -50W, 75s)\nAt Vil #37: Move 3 Wood vils -> Gold (4 -> 7 Gold)",
                    f"Monk #1 secures Relic (+30G/min); explains Vils #32–#37 transition to 14 Farms / 16 Wood / 7 Gold ({format_army_counts(current_army_dict()).replace('Army: ', '')}).",
                )

            # Log Houfnice research start once 5+ Bombards and 100+ vils are online
            if sim.age == 4 and houfnice_started and not houfnice_logged:
                houfnice_logged = True
                add_row(
                    "",
                    f"{sim.fmt_time(imp_reached_t or t)} – {sim.fmt_time()}",
                    "Imperial Age",
                    "Continue 3-TC Vils (to 124 vils) -> Farms / Wood / Gold\nTrain 5+ Bombard Cannons (-225W, -225G each) from 2 Siege Workshops, then research Houfnice (-1100F, -800G, 140s)\nTrain Hand Cannoneers (5 Ranges), Halberdiers (3 Barracks) & Light Cavalry (3 Stables)\nDrop Castles (-650S each) whenever Stone reaches ~800S",
                    f"5+ Bombard Cannons & {len(sim.vils)} vils online -> Houfnice completes at {milestones.get('houfnice_done_str', '')}.",
                )

        # Completion criterion
        if (
            sim.age == 4
            and len(sim.vils) >= 120
            and "houfnice" in sim.upgrades
            and sim.military_units["bombard_cannon"] >= 5
            and sim.military_units["hand_cannoneer"] >= 34
            and sim.military_units["light_cav"] >= 10
            and sim.military_units["pikeman"] >= 12
            and conscription_started
            and ring_armor_started
            and halberdier_upg_started
            and siege_engineers_started
            and wagenburg_started
            and two_man_saw_started
        ):
            milestones["full_push_str"] = sim.fmt_time(t)
            milestones["final_vils"] = len(sim.vils)
            milestones["final_army"] = current_army_dict()
            milestones["final_bank"] = sim.bank.to_dict()
            milestones["housed_seconds"] = housed_seconds
            milestones["tc_pre_click_idle_s"] = tc_pre_click_idle_s
            milestones["extra_tc_idle_s"] = tc_unplanned_idle_s
            milestones["tc1_idle_before_imp_s"] = tc_pre_click_idle_s + tc_unplanned_idle_s
            milestones["negative_bank_count"] = len(sim.negative_bank_events)
            milestones["max_castle_float"] = {k: round(v, 1) for k, v in max_castle_float.items()}
            milestones["market_trades"] = sim.market_trades
            milestones["castles_built"] = 1 + extra_castles_started
            add_row(
                "",
                f"{sim.fmt_time(houfnice_ready_t or imp_reached_t or t)} – {sim.fmt_time()}" if houfnice_logged else f"{sim.fmt_time(imp_reached_t or t)} – {sim.fmt_time()}",
                "Imperial Age",
                "Finish Houfnice upgrade + remaining Blacksmith/Stable upgrades (Plate Mail, Iron Casting, Blast Furnace, Chain Barding)\nKeep 7 on Stone & build extra Castles (-650S) every time Stone hits ~800S\nMaintain 200-pop composition: ~124 Vils + Hand Cannons, Houfnices, Halberdiers, Light Cav & Trebuchets",
                f"Full Imperial composition online ({len(sim.vils)} Vils + {sum(current_army_dict().values())} Military = {sim.total_pop()} Pop; {1 + extra_castles_started} Castles): {format_army_counts(current_army_dict()).replace('Army: ', '')}. Pre-click TC idle: {tc_pre_click_idle_s}s; unplanned TC idle: {tc_unplanned_idle_s}s.",
            )
            break

        sim.tick_gather(reseed_reserve_w=house_wood_res)
        if t % 10 == 0:
            record_timeline_point()

    if not record_outputs:
        milestones.setdefault("housed_seconds", housed_seconds)
        milestones.setdefault("extra_tc_idle_s", tc_unplanned_idle_s)
        milestones.setdefault("feudal_click_s", feudal_click_t)
        milestones.setdefault("castle_click_s", castle_click_t)
        return BuildOrderDocument("", "Bohemians", variant_label, "", [], []), milestones

    assert imp_reached_t is not None and imp_reached_t < 2400, f"Imperial missed <40:00: {imp_reached_t}"
    assert milestones.get("full_push_str") is not None, "Completion criterion not reached before max_sim_t"
    assert housed_seconds == 0, f"Housed for {housed_seconds}s"
    assert tc_pre_click_idle_s <= int(rules.max_end_of_age_tc_idle_seconds), f"Pre-click TC idle > 5s (rule 5.1): {tc_pre_click_idle_s}s"
    assert tc_unplanned_idle_s <= int(rules.max_end_of_age_tc_idle_seconds), f"Unplanned TC idle: {tc_unplanned_idle_s}s"
    assert not sim.negative_bank_events, f"Negative bank events: {sim.negative_bank_events[:3]}"

    steady_state = planner.compute_steady_state_vils(
        items=[
            ContinuousProductionItem("villager", 3),
            ContinuousProductionItem("hand cannoneer", 5),
            ContinuousProductionItem("bombard cannon", 2),
            ContinuousProductionItem("spearman", 3),
            ContinuousProductionItem("scout cavalry", 3),
        ],
        civ="Bohemians",
        age=4,
        upgrades=[
            "double-bit axe",
            "bow saw",
            "two-man saw",
            "horse collar",
            "heavy plow",
            "wheelbarrow",
            "hand cart",
            "gold mining",
            "gold shaft mining",
            "conscription",
        ],
        food_source="farmer",
        wood_minutes_since_lc=1.0,
    )
    steady_state["title"] = (
        "Steady-State Target (3 TC Vils to 124 + 5-Range Hand Cannons + 2 SW Bombard/Houfnice + 3 Rax Halbs + 3 Stable Light Cav, w/ Stone Castles)"
    )

    I = RTS_ICONS
    fin_vils = len(sim.vils)
    end_alloc = sim.current_macro_alloc()
    imp_c_vils = int(milestones.get("imp_click_vils", 85))
    imp_c_alloc = dict(milestones.get("imp_click_alloc", end_alloc))
    chem_done_str = str(milestones.get("chemistry_done_str", "17:15"))
    first_hc_str = str(milestones.get("first_hc_str", chem_done_str))
    fwd_c_str = str(milestones.get("fwd_castle_ready_str", "30:00"))
    imp_c_str = str(milestones.get("imp_click_str", "30:00"))
    imp_r_str = str(milestones.get("imp_reached_str", "33:10"))
    castle_r_str = str(milestones.get("castle_reached_str", "14:26"))
    castle_arr_alloc = dict(milestones.get("castle_arrival_alloc", {"wood": 12, "food": 10, "gold": 4, "stone": 0}))
    v37_alloc = dict(milestones.get("v37_alloc", {"wood": 16, "food": 14, "gold": 7, "stone": 0}))
    v46_alloc = dict(milestones.get("v46_alloc", {"wood": 22, "food": 14, "gold": 10, "stone": 0}))
    stone_vils_cnt = int(milestones.get("stone_started_vils", 47))
    stone_alloc = dict(milestones.get("stone_started_alloc", {"wood": 16, "food": 14, "gold": 10, "stone": 7}))
    stone_s_str = str(milestones.get("stone_started_str", "24:59"))
    v37_str = str(milestones.get("v37_str", "20:50"))
    v46_str = str(milestones.get("v46_str", "24:45"))
    fwd_src_lbl = str(milestones.get("fwd_vils_src_str", "Wood"))

    rts_steps = [
        RTSOverlayStep(villager_count=6, age=1, wood=0, food=6, gold=0, stone=0, notes=[f"Vils #1-#6: {I['build']} 2 Houses at 0:00, then all 6 on {I['sheep']} under TC."]),
        RTSOverlayStep(villager_count=9, age=1, wood=3, food=6, gold=0, stone=0, notes=[f"Vils #7-#9 (3 vils) -> {I['wood']} (1st vil walks 15s + {I['build']} {I['lumber_camp']} #1)."]),
        RTSOverlayStep(villager_count=11, age=1, wood=4, food=7, gold=0, stone=0, notes=[f"Vil #10 lures 1st {I['boar']} (garrison 7 TC vils 5s on arrival); Vil #11 to {I['wood']} (4 on Wood)."]),
        RTSOverlayStep(villager_count=15, age=1, wood=4, food=11, gold=0, stone=0, notes=[f"Vils #12-#15 (4 vils) -> 6 Chickens on {I['mill']} #1 (Vil #12 builds {I['mill']}, Vil #13 builds House #3). Lure 2nd {I['boar']} before 1st finishes."]),
        RTSOverlayStep(villager_count=19, age=1, wood=4, food=15, gold=0, stone=0, notes=[f"Vils #16-#19 (4 vils) -> {I['berries']} (1st builds {I['mill']} #2, 3rd builds House #4)."]),
        RTSOverlayStep(villager_count=21, age=1, wood=6, food=15, gold=0, stone=0, notes=[f"Vils #20-#21 (2 vils) -> {I['wood']} at {I['lumber_camp']} #1 (skip Dark Age Gold MC!)."]),
        RTSOverlayStep(villager_count=23, age=1, wood=7, food=16, gold=0, stone=0, notes=[f"Vil #22 builds {I['house']} #5 -> {I['wood']} (7 on Wood); Vil #23 -> {I['sheep']}/Food."]),
        RTSOverlayStep(villager_count=24, age=1, wood=7, food=16, gold=1, stone=0, notes=[f"Vil #24 -> Long-distance 10 {I['gold']} (then move from Gold to Stragglers/{I['farm']}s)! Click {I['feudal_age']} (500F) at 08:45; move 12 Sheep vils -> Stragglers & move up to 8 Stragglers -> {I['farm']}s."]),
        RTSOverlayStep(villager_count=26, age=2, wood=9, food=17, gold=0, stone=0, notes=[f"In {I['feudal_age']}: Free Gold/Stone Mining! Vils #25-#26 -> {I['wood']}; 3 Straggler/Wood vils {I['build']} {I['market']} & 1 builds Bohemian {I['blacksmith']} (50W!).", f"Sell 100 {I['stone']} at {I['market']} (+91G -> 201G, saving 200W!) & click {I['castle_age']} (800F, 200G)!"]),
        RTSOverlayStep(
            villager_count=26, age=3,
            wood=castle_arr_alloc["wood"], food=castle_arr_alloc["food"], gold=castle_arr_alloc["gold"], stone=castle_arr_alloc["stone"],
            notes=[
                f"Click {I['castle_age']}: {I['double_bit_axe']} + {I['horse_collar']}, move 4 Straggler/Wood vils -> {I['gold']} ({I['mining_camp']}) & 1 Wood/Straggler vil builds {I['barracks']}.",
                f"Reach {I['castle_age']} ({castle_r_str}): Stay 1 TC! Drop Bohemian {I['university']} (100W!) + {I['archery_range']} #1 + {I['bow_saw']} -> {I['chemistry']} + {I['monastery']} (175W, 2 {I['monk']}s -> Relic) -> 1st {I['hand_cannoneer']} at {first_hc_str}!",
            ],
        ),
        RTSOverlayStep(
            villager_count=37, age=3,
            wood=v37_alloc["wood"], food=v37_alloc["food"], gold=v37_alloc["gold"], stone=v37_alloc["stone"],
            notes=[
                f"Vils #32-#37 ({first_hc_str} - {v37_str}): 4 Berries vils finish -> move from Berries to Wood/Stragglers; move 5 Wood/Stragglers -> {I['farm']}s (to 14 {I['farm']}s); {I['wheelbarrow']} at Vil #36; move 3 Wood vils -> {I['gold']} (7 {I['gold']}).",
            ],
        ),
        RTSOverlayStep(
            villager_count=46, age=3,
            wood=v46_alloc["wood"], food=v46_alloc["food"], gold=v46_alloc["gold"], stone=v46_alloc["stone"],
            notes=[
                f"Vils #38-#46 ({v37_str} - {v46_str}): Wood vils build {I['archery_range']} #2 & #3, {I['lumber_camp']} #2 & {I['siege_workshop']}; {I['pikeman']}; move 3 Wood vils -> {I['gold']} (10 {I['gold']}). Pre-Stone Vil #46: 14F / 22W / 10G.",
            ],
        ),
        RTSOverlayStep(
            villager_count=stone_vils_cnt, age=3,
            wood=stone_alloc["wood"], food=stone_alloc["food"], gold=stone_alloc["gold"], stone=stone_alloc["stone"],
            notes=[
                f"At {stone_s_str} (Vil #47 -> Wood): 1 Wood vil builds {I['mining_camp']} on {I['stone']} (-100W) & move 7 Wood vils -> {I['stone']} (23 -> 16 Wood)!",
                f"Keep all 7 on {I['stone']} permanently for {I['town_center']} #3 (TC #2 uses leftover 100S!), Forward {I['castle']} (-650S), extra Castles & repairs!",
            ],
        ),
        RTSOverlayStep(
            villager_count=imp_c_vils, age=3,
            wood=imp_c_alloc["wood"], food=imp_c_alloc["food"], gold=imp_c_alloc["gold"], stone=imp_c_alloc["stone"],
            notes=[
                f"3-TC Boom + 3-Range {I['hand_cannoneer']}s + {I['mangonel']}s + {I['pikeman']}! Send 8 Loom {fwd_src_lbl} vils forward (60s) -> Forward {I['castle']} (-650S, ready {fwd_c_str}).",
                f"Click {I['imperial_age']} ({imp_c_str}, 1000F, 800G); on the way up add {I['heavy_plow']}, {I['hand_cart']}, {I['fervor']}/{I['sanctity']}, Barracks #2-#3, Ranges #4-#5, 3 {I['stable']}s, SW #2, {I['light_cavalry']} & Forging/Armor!",
            ],
        ),
        RTSOverlayStep(
            villager_count=fin_vils, age=4,
            wood=end_alloc["wood"], food=end_alloc["food"], gold=end_alloc["gold"], stone=end_alloc["stone"],
            notes=[
                f"Reach {I['imperial_age']} ({imp_r_str}): Two-Man Saw, Conscription, Ring Armor, {I['halberdier']}, Siege Engineers, Wagenburg Tactics + 5+ {I['bombard_cannon']} -> Houfnice (at 100+ vils)!",
                f"Keep 3-TC Vils to {fin_vils} (120-130); produce {I['hand_cannoneer']} + {I['light_cavalry']} + {I['halberdier']} + Houfnice & drop a {I['castle']} (-650S) every ~800S!",
            ],
        ),
    ]

    desc = (
        f"Bohemians Arena FC (6 Chickens Milled + Berry Mill, Checked w/ 8) — {variant_label}. "
        f"Long-distance 10G + sell 100S (+91G) to save 200W in Feudal; 3-TC boom to {fin_vils} vils, eco/military upgrades, Houfnice + HC + Light Cav + Halbs + ~800S Castles; synced to rules.md."
    )

    doc = BuildOrderDocument(
        name="Bohemians Arena Fast Castle (1-TC Early Hand Cannoneers)",
        civilization="Bohemians",
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
    for old_name in (
        "bohemians_arena_fc_hand_cannons_pure_boom.json",
        "bohemians_arena_fc_hand_cannons_monastery_fervor.json",
        "bohemians_arena_fc_hand_cannons_24p2_3tc_boom.json",
        "bohemians_arena_fc_hand_cannons_28p2_3tc_boom.json",
    ):
        p = OUT_DIR / old_name
        if p.exists():
            p.unlink()

    doc, ms = run_bohemians_1tc_fast_hc()
    rob = run_late_command_checks(
        "24p2_1tc_fast_hc",
        lambda dfn, chk: run_bohemians_1tc_fast_hc(delay_fn=dfn, chicken_override=chk, record_outputs=False)[1],
        baseline_clicks={"feudal_click_s": int(ms["feudal_click_s"]), "castle_click_s": int(ms["castle_click_s"])},
        chicken_check_counts=(8,),
    )
    ms["robustness_passed"] = rob["passed"]
    ms["robustness_details"] = rob["details"]
    assert rob["passed"], f"Robustness failed: {rob['failures']}"

    json_path = export_rts_overlay_json(doc, OUT_DIR / "bohemians_arena_fc_hand_cannons_24p2_1tc_fast_hc.json")
    print(f"=== {ms['variant']} ===")
    for k, v in ms.items():
        if k != "variant":
            print(f"  {k}: {v}")
    print(f"  Rot telemetry: {doc.telemetry_summary['rotted_food']} (Total: {doc.telemetry_summary['total_rotted_food']}F)")
    print(f"  Wrote RTS Overlay JSON: {json_path} ({len(doc.rts_steps)} steps)\n")

    html_path = export_build_order_html(
        [doc],
        title="Bohemians Arena FC: 24+2 1-TC Fast Hand Cannoneers -> Houfnice, Light Cav, Halbs & ~800S Castles",
        output_path=OUT_DIR / "bohemians_arena_fc_hand_cannons.html",
    )
    print(f"Wrote HTML report: {html_path}")


if __name__ == "__main__":
    main()

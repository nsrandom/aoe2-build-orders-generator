#!/usr/bin/env python3
"""
Generator & 1-Second Discrete-Event Simulator for:
Italians Arena Fast Castle Build Orders (6 Chickens Milled + Berry Mill in Dark Age, Checked w/ 8 Chickens)

2 Distinct Strategies displayed in top-level HTML tabs + Strategy Comparison chart + separate JSONs:
1. Strategy 1: 1 TC Heavy Army Push (`1tc_push`):
   - 26+2 FC -> Defensive Castle (<= 10s wait) -> Genoese + Light Cav
   - Monastery + 2 Monks (conservatively assume max 1 Relic = +30G/min; rule 7.3)
   - Ballistics priority at 20+ Genoese (rule 6.4) -> Forward Siege Workshop & Rams at 30+ army
   - Stick strictly to 1 TC until clicking Imperial Age (<40:00; rule 6.5), then add TC #2 & #3
2. Strategy 2: Balanced 3 TC Boom (`3tc_balanced`):
   - 26+2 FC -> Defensive Castle (<= 10s wait) -> ~20 Army (13 Genoese + 7 Light Cav)
   - Pause military -> Expand to 3 TCs with continuous Villagers until 3-TC boom is set up
   - Resume & maximize Genoese + Light Cav -> Ballistics priority at 20+ Genoese ->
     Forward Castle #2/#3, TC #4 & Siege Workshops -> Imperial Age (<40:00)

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
)
from sim_italians_arena_fc_genoese import ItaliansArenaSimulator
from simulator import run_late_command_checks

OUT_DIR = THIS_DIR


def _pull_builders(
    sim: ItaliansArenaSimulator,
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


def run_italians_arena_strategy(
    strategy: str,
    delay_fn: Optional[Callable[[int], int]] = None,
    chicken_override: Optional[int] = None,
    record_outputs: bool = True,
) -> Tuple[BuildOrderDocument, Dict[str, object]]:
    """Runs a 1-second simulation for `1tc_push` or `3tc_balanced`."""
    if strategy not in ("1tc_push", "3tc_balanced"):
        raise ValueError(f"Unknown strategy: {strategy}")

    is_1tc = strategy == "1tc_push"
    dark_vils = 26
    sim = ItaliansArenaSimulator(dark_vils=dark_vils, chicken_count=chicken_override)
    rules = sim.rules
    planner = BackwardPlanner(sim.db, rules)

    def d_t(planned_t: int) -> int:
        return planned_t if delay_fn is None else delay_fn(planned_t)

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
        if not record_outputs:
            return
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
                army_counts=dict(sim.military_units),
            )
        )
        record_timeline_point()

    # Exact age specs from aoe2_data (Italians -15%)
    feudal_cost, feudal_time, _ = sim.db.get_age_advance_spec(2, "Italians")
    castle_cost, castle_time, _ = sim.db.get_age_advance_spec(3, "Italians")
    imp_cost, imp_time, _ = sim.db.get_age_advance_spec(4, "Italians")

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

    feudal_clicked = False
    feudal_click_t = 0
    feudal_cmd_t: Optional[int] = None
    feudal_vils_queued = 0
    market_started = False
    market_ready_t: Optional[int] = None
    bs_started = False
    bs_ready_t: Optional[int] = None
    stone_sold = False
    castle_clicked = False
    castle_click_t = 0
    castle_cmd_t: Optional[int] = None
    castle_reached_t: Optional[int] = None

    dba_started = False
    hc_started = False
    gold_mc_started = False
    gold_mining_started = False
    barracks_started = False
    barracks_ready_t: Optional[int] = None
    stable_started = False
    stable_ready_t: Optional[int] = None
    stable_count = 0
    stable_busy_until: List[int] = [0] * 6
    lcav_upg_started = False
    house_busy_until = 0

    def_castle_started = False
    def_castle_ready_t: Optional[int] = None
    castle_count = 0
    castle_busy_until: List[int] = [0] * 4

    # Upgrades
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
    silk_road_started = False
    loom_started = False
    wheelbarrow_started = False
    heavy_plow_started = False
    crop_rotation_started = False
    hand_cart_started = False
    gold_shaft_started = False
    stone_mining_started = False
    stone_shaft_started = False
    stone_adjusted_early = False

    monastery_started = False
    monastery_ready_t: Optional[int] = None
    monastery_busy_until = 0
    monks_trained = 0
    relic1_time: Optional[int] = None

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
    masonry_started = False
    chemistry_started = False
    chemistry_ready_t: Optional[int] = None
    siege_engineers_started = False

    fwd_vils_dispatched = False
    fwd_vils_arrive_t: Optional[int] = None
    fwd_vils: List[Dict[str, object]] = []
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
    imp_hold_start_t: Optional[int] = None
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
    last_lc_refresh_t = -999

    castle_loop1_logged = False
    castle_loop2_logged = False
    max_castle_float = {"food": 0.0, "wood": 0.0, "gold": 0.0}

    housed_seconds = 0
    tc_pre_click_idle_s = 0
    tc_unplanned_idle_s = 0
    mil_idle_checks: List[Tuple[int, int]] = []

    def queue_upg(name: str, extra_check: bool = True, res_food: float = 0.0, res_wood: float = 0.0, res_gold: float = 0.0) -> bool:
        if not extra_check:
            return False
        c, rt = sim.db.get_upgrade_spec(name, "Italians")
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

    max_sim_t = 2800
    for t in range(1, max_sim_t + 1):
        sim.time_s = t
        sim.in_age_transition = (feudal_clicked and sim.age == 1) or (castle_clicked and sim.age == 2) or (imp_clicked and sim.age == 3)

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
                        v["busy_until"] = max(int(v["busy_until"]), lure_t + int(2 * rules.boar_lure_walk_time_one_way))
                        boar2_arrive_t = lure_t + int(2 * rules.boar_lure_walk_time_one_way)
                        break

        if boar2_arrive_t is not None and not boar2_shot and t >= boar2_arrive_t:
            boar2_shot = True
            _pull_builders(sim, ("boar", "sheep"), rules.boar_garrison_vils, t + int(rules.boar_garrison_seconds))

        # Relic #1 secured in 1 TC push (rule 7.3)
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
                            sim.vils.append({"id": vid, "role": "wood", "camp_idx": 0, "busy_until": t + int(rules.camp_or_berry_walk_time_one_way)})
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
                            sim.vils.append({"id": vid, "role": "wood", "camp_idx": 0, "busy_until": t + int(rules.camp_or_berry_walk_time_one_way)})
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
                            sim.vils.append({"id": vid, "role": "chicken_mill", "busy_until": comp_t + int(rules.camp_or_berry_walk_time_one_way)})
                        elif vid in (14, 15):
                            sim.vils.append({"id": vid, "role": "chicken_mill", "busy_until": t + int(rules.camp_or_berry_walk_time_one_way)})
                            if vid == 15:
                                add_row(
                                    "12–15 (13–16)",
                                    f"03:45 – {sim.fmt_time()}",
                                    "Dark Age",
                                    "Vil #12 -> Build Mill #1 (-100W, 35s) on Chickens\nVil #13 -> Build House #3 (-25W)\nAssign Vils #12–#15 -> 6 Chickens at Mill #1",
                                    "Mill #1 on Chickens (23.9/min) unlocks Horse Collar & Farms (rule 3.9, 3.10); 2nd Boar lured before 1st finishes.",
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
                        elif vid == 20:
                            sim.spend(ResourceBundle(wood=100), "StoneMC")
                            sim.buildings.append("mining camp")
                            sim.vils.append({"id": vid, "role": "stone", "busy_until": t + 50})
                        elif vid in (21, 22):
                            sim.vils.append({"id": vid, "role": "stone", "busy_until": t + 15})
                        elif vid == 23:
                            sim.spend(ResourceBundle(wood=25), "House5")
                            comp_t = t + 30
                            sim.add_pending_pop_building(comp_t, 5, "house")
                            sim.vils.append({"id": vid, "role": "stone", "busy_until": comp_t + 15})
                            add_row(
                                "20–23 (21–24)",
                                f"07:05 – {sim.fmt_time()}",
                                "Dark Age",
                                "Vil #20 -> Build Mining Camp (-100W, 35s) on Stone\nVil #23 -> Build House #5 (-25W)\nAssign Vils #20–#23 -> Stone",
                                "4 Dark Age Stone miners fund instant Castle drop.",
                            )
                        elif vid in (24, 25):
                            sim.vils.append({"id": vid, "role": "wood", "camp_idx": 0, "busy_until": t + 15})
                        elif vid == 26:
                            sim.vils.append({"id": vid, "role": "wood", "camp_idx": 0, "busy_until": t + 15})
                            add_row(
                                "24–26 (25–27)",
                                f"08:45 – {sim.fmt_time()}",
                                "Dark Age",
                                "Assign Vils #24–#26 -> Wood at LC #1",
                                "15s walk; 26 Dark Age vils complete (7/8 on LC #1).",
                            )

                        if vid < dark_vils and sim.bank.food >= 50:
                            sim.spend(ResourceBundle(food=50), f"vil_{vid+1}")
                            sim.tc_busy_until[0] = t + 25
                            sim.tc_action[0] = f"vil_{vid+1}"

                    elif sim.age == 2:
                        if not gold_mc_started:
                            gold_mc_started = True
                            sim.spend(ResourceBundle(wood=100), "GoldMC")
                            sim.buildings.append("mining camp")
                            sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 50})
                        else:
                            sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                            add_row(
                                "27–28 (28–29)",
                                f"{sim.fmt_time(t-25)} – {sim.fmt_time()}",
                                "Feudal Age",
                                "Vil #27 -> Build Mining Camp (-100W, 35s) on Gold\nAssign Vils #27–#28 -> Gold\nSell 100 Stone at Market (+91G)",
                                "100 starting Gold + 91G Market sale = 191G (>170G Castle Age cost; rule 7.2).",
                            )

                    else:
                        # Castle & Imperial villager routing
                        g_cnt = sim.count_role("gold")
                        w_cnt = sim.count_role("wood", "straggler")
                        f_cnt = sim.count_role("farm")
                        s_cnt = sim.count_role("stone")
                        cur_camp = max(0, len(sim.lumber_camps) - 1)

                        if is_1tc:
                            saving_wood_for_bldg = (
                                (not monastery_started and sim.bank.wood < 175)
                                or (sim.military_units["genoese"] >= 20 and not univ_started and sim.bank.wood < 200)
                                or (univ_ready_t is not None and t >= univ_ready_t and not ballistics_started and sim.bank.wood < 225)
                                or (army30_reached and not fwd_sw1_started and sim.bank.wood < 200)
                                or (imp_clicked and not tc2_started and sim.bank.stone >= 100 and sim.bank.wood < 275)
                                or (imp_clicked and tc2_started and not tc3_started and sim.bank.stone >= 100 and sim.bank.wood < 275)
                            )
                            gold_target = 11 if not imp_clicked else (20 if len(sim.vils) < 75 else 26)
                            farm_target_early = 20 if not imp_clicked else 34
                            wood_target_early = 16 if not imp_clicked else 26
                            stone_target = 2 if not tc3_started else 0

                            if f_cnt < 12 and sim.bank.wood >= 60 and not saving_wood_for_bldg:
                                sim.spend(ResourceBundle(wood=60), "farm_new")
                                sim.register_new_farm(t + int(rules.farm_walk_time) + 15)
                                sim.vils.append({"id": vid, "role": "farm", "busy_until": t + int(rules.farm_walk_time) + 15})
                            elif w_cnt < wood_target_early:
                                sim.vils.append({"id": vid, "role": "wood", "camp_idx": cur_camp, "busy_until": t + 15})
                            elif g_cnt < gold_target and sim.bank.gold < 700:
                                sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                            elif f_cnt < farm_target_early and sim.bank.wood >= 60 and not saving_wood_for_bldg:
                                sim.spend(ResourceBundle(wood=60), "farm_new")
                                sim.register_new_farm(t + int(rules.farm_walk_time) + 15)
                                sim.vils.append({"id": vid, "role": "farm", "busy_until": t + int(rules.farm_walk_time) + 15})
                            elif s_cnt < stone_target and sim.bank.stone < 250:
                                sim.vils.append({"id": vid, "role": "stone", "busy_until": t + 15})
                            elif f_cnt < 38 and sim.bank.wood >= 60 and not saving_wood_for_bldg and sim.bank.food < 1000:
                                sim.spend(ResourceBundle(wood=60), "farm_new")
                                sim.register_new_farm(t + int(rules.farm_walk_time) + 15)
                                sim.vils.append({"id": vid, "role": "farm", "busy_until": t + int(rules.farm_walk_time) + 15})
                            elif g_cnt < 26 and sim.bank.gold < 750:
                                sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                            else:
                                sim.vils.append({"id": vid, "role": "wood", "camp_idx": cur_camp, "busy_until": t + 15})
                        else:
                            saving_wood_for_bldg = (
                                (army20_reached and not tc2_started and sim.bank.stone >= 80 and sim.bank.wood < 275)
                                or (tc2_started and not tc3_started and sim.bank.stone >= 90 and sim.bank.wood < 275)
                                or (boom3tc_ready_logged and sim.military_units["genoese"] >= 20 and not univ_started and sim.bank.wood < 200)
                                or (univ_ready_t is not None and t >= univ_ready_t and not ballistics_started and sim.bank.wood < 225)
                                or (fwd_vils_arrive_t is not None and t >= fwd_vils_arrive_t and not tc4_started and sim.bank.stone >= 100 and sim.bank.wood < 275)
                            )
                            gold_target_early = 7 if not army20_reached else (6 if not boom3tc_ready_logged else 20)
                            if f_cnt < 12 and sim.bank.wood >= 60 and not saving_wood_for_bldg:
                                sim.spend(ResourceBundle(wood=60), "farm_new")
                                sim.register_new_farm(t + int(rules.farm_walk_time) + 15)
                                sim.vils.append({"id": vid, "role": "farm", "busy_until": t + int(rules.farm_walk_time) + 15})
                            elif g_cnt < gold_target_early and sim.bank.gold < 350:
                                sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                            elif w_cnt < 15:
                                sim.vils.append({"id": vid, "role": "wood", "camp_idx": cur_camp, "busy_until": t + 15})
                            elif f_cnt < 24 and sim.bank.wood >= 60 and not saving_wood_for_bldg:
                                sim.spend(ResourceBundle(wood=60), "farm_new")
                                sim.register_new_farm(t + int(rules.farm_walk_time) + 15)
                                sim.vils.append({"id": vid, "role": "farm", "busy_until": t + int(rules.farm_walk_time) + 15})
                            elif tc3_ready_t is not None and t >= tc3_ready_t and len(sim.vils) >= 48 and s_cnt < 6 and not fwd_castle3_started and sim.bank.stone < 800:
                                sim.vils.append({"id": vid, "role": "stone", "busy_until": t + 15})
                            elif w_cnt < 25:
                                sim.vils.append({"id": vid, "role": "wood", "camp_idx": cur_camp, "busy_until": t + 15})
                            elif f_cnt < 34 and sim.bank.wood >= 60 and not saving_wood_for_bldg and sim.bank.food < 1000:
                                sim.spend(ResourceBundle(wood=60), "farm_new")
                                sim.register_new_farm(t + int(rules.farm_walk_time) + 15)
                                sim.vils.append({"id": vid, "role": "farm", "busy_until": t + int(rules.farm_walk_time) + 15})
                            elif g_cnt < 28 and f_cnt >= 22 and sim.bank.gold < 900:
                                sim.vils.append({"id": vid, "role": "gold", "busy_until": t + 15})
                            elif f_cnt < 44 and sim.bank.wood >= 60 and not saving_wood_for_bldg and sim.bank.food < 1000:
                                sim.spend(ResourceBundle(wood=60), "farm_new")
                                sim.register_new_farm(t + int(rules.farm_walk_time) + 15)
                                sim.vils.append({"id": vid, "role": "farm", "busy_until": t + int(rules.farm_walk_time) + 15})
                            else:
                                sim.vils.append({"id": vid, "role": "gold" if sim.bank.gold < 900 else "wood", "camp_idx": cur_camp, "busy_until": t + 15})

                elif act == "feudal":
                    sim.age = 2
                    milestones["feudal_reached_s"] = t
                    milestones["feudal_reached_str"] = sim.fmt_time()

                    if sim.bank.food >= 50:
                        sim.spend(ResourceBundle(food=50), "feudal_vil1")
                        sim.tc_busy_until[0] = t + 25
                        sim.tc_action[0] = f"vil_{len(sim.vils)+1}"
                        feudal_vils_queued = 1

                    # Market (3 vils: 10s + 30s + 10s return = 50s, ready at t+40) & Blacksmith (1 vil: 10 + 40 + 10 = 60s, ready at t+50)
                    if sim.bank.wood >= 325:
                        market_started = True
                        bs_started = True
                        sim.spend(ResourceBundle(wood=325), "Market+Blacksmith")
                        mkt_build = int(round(calc_construction_time(60.0, 3)))  # 36s
                        market_ready_t = t + 10 + mkt_build
                        bs_ready_t = t + 10 + 40
                        _pull_builders(sim, ("straggler", "wood", "berries"), 3, market_ready_t + 10)
                        _pull_builders(sim, ("straggler", "wood", "berries"), 1, bs_ready_t + 10)
                        add_row(
                            f"{len(sim.vils)} ({sim.total_pop()})",
                            sim.fmt_time(),
                            "Feudal Age",
                            f"Queue +2 Feudal Vils -> Gold\n3 Straggler/Wood vils build Market (-175W, {mkt_build}s) -> return to Wood\n1 Straggler/Wood vil builds Blacksmith (-150W, 40s) -> return to Wood",
                            "FC mode: Dark/Feudal runs at 100%, Castle+ macro at 90% (rule 8.2).",
                        )

                elif act == "castle":
                    sim.age = 3
                    castle_reached_t = t
                    milestones["castle_reached_s"] = t
                    milestones["castle_reached_str"] = sim.fmt_time()
                    milestones["castle_arrival_bank"] = sim.bank.to_dict()

                    add_row(
                        f"{len(sim.vils)} ({sim.total_pop()})",
                        f"{sim.fmt_time(castle_click_t)} – {sim.fmt_time()}",
                        "Castle Transition",
                        "Research Double-Bit Axe (-100F, -50W) & Horse Collar (-75F, -75W)\nMove 3 Stragglers/Wood -> Seed Farms #3–#5 (-60W each)\nResearch Gold Mining (-100F, -75W)\n1 Wood/Straggler vil builds Lumber Camp #2 (-100W) -> Wood\n1 Wood/Straggler vil builds Barracks (-175W) -> Stable #1 (-175W) -> Wood\nResearch Fletching (-100F, -50G)",
                        "Castle Transition (160s); DBA deferred until Castle click per tight FC exception (rule 6.3); sequential Barracks -> Stable #1 saves 20s walk.",
                    )

                    if sim.bank.food >= 50:
                        sim.spend(ResourceBundle(food=50), "castle_vil1")
                        sim.tc_busy_until[0] = t + 25
                        sim.tc_action[0] = f"vil_{len(sim.vils)+1}"

                    bow_saw_line = ""
                    if sim.bank.food >= 200 and queue_upg("bow saw"):
                        bow_saw_started = True
                        bow_saw_line = "\nResearch Bow Saw (-150F, -100W, 50s)"

                    if sim.bank.stone >= 650:
                        def_castle_started = True
                        sim.spend(ResourceBundle(stone=650), "DefensiveCastle")
                        c_build = int(round(calc_construction_time(200.0, 6)))  # 75s
                        def_castle_ready_t = t + 10 + c_build
                        sim.add_pending_pop_building(def_castle_ready_t, 20, "castle")
                        milestones["def_castle_started_str"] = sim.fmt_time(t)
                        milestones["castle_wait_s"] = 0
                        _pull_builders(sim, ("straggler", "wood", "stone", "berries"), 6, def_castle_ready_t + 10)
                        add_row(
                            f"{len(sim.vils)} ({sim.total_pop()})",
                            sim.fmt_time(),
                            "Castle Age",
                            f"6 Wood vils build Defensive Castle (-650S, 75s) -> return to Wood{bow_saw_line}\nQueue Vil #{len(sim.vils)+1} (keep TC #1 continuous)",
                            f"Castle ready {sim.fmt_time(def_castle_ready_t)} (0s wait); 90% Castle+ macro efficiency buffer active (rule 8.2).",
                        )
                    else:
                        add_row(
                            f"{len(sim.vils)} ({sim.total_pop()})",
                            sim.fmt_time(),
                            "Castle Age",
                            f"Queue Vil #{len(sim.vils)+1}{bow_saw_line}\n6 Wood/Straggler vils build Defensive Castle (-650S) once 650 Stone arrives",
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

                    trans_txt = (
                        "3 Wood/Farm vils build TC #2 & TC #3 (-275W, -100S each) -> return\nContinue Genoese + Light Cavalry + Battering Rams"
                        if is_1tc
                        else f"Continue 4-TC Vils (to {len(sim.vils)} vils)\nAdd Forward Castles / Siege Workshop #2 (from Wood) & scale military"
                    )
                    add_row(
                        f"{len(sim.vils)} ({sim.total_pop()})",
                        f"{sim.fmt_time(imp_click_t)} – {sim.fmt_time()}",
                        "Imperial Transition",
                        trans_txt,
                        f"Imperial Transition (190s); arrives Imperial Age at {sim.fmt_time()} (target <40:00 per rule 6.5).",
                    )

                    chem_cost, chem_time = sim.db.get_upgrade_spec("chemistry", "Italians")
                    if sim.bank.food >= chem_cost.food + 150 and sim.bank.gold >= chem_cost.gold + 150:
                        chemistry_started = True
                        conscription_started = True
                        sim.spend(chem_cost + ResourceBundle(food=150, gold=150), "Chem+Conscription")
                        chemistry_ready_t = t + int(round(chem_time))
                        sim.queue_upgrade("chemistry", chemistry_ready_t)
                        sim.queue_upgrade("conscription", t + 60)
                    elif sim.bank.food >= 150 and sim.bank.gold >= 150:
                        conscription_started = True
                        sim.spend(ResourceBundle(food=150, gold=150), "Conscription")
                        sim.queue_upgrade("conscription", t + 60)

                    add_row(
                        f"{len(sim.vils)} ({sim.total_pop()})",
                        sim.fmt_time(),
                        "Imperial Age",
                        f"Research Conscription (-150F, -150G)\nResearch Chemistry (-{chem_cost.food:.0f}F, -{chem_cost.gold:.0f}G)\nResearch Bracer, Elite Genoese, Hussar, Pavise, Silk Road & Siege Engineers\nTrain Bombard Cannons (-180W, -180G)",
                        f"Italians -25% University techs; bank on Imp arrival: {sim.bank.food:.0f}F / {sim.bank.wood:.0f}W / {sim.bank.gold:.0f}G / {sim.bank.stone:.0f}S.",
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
                    f"Click Feudal Age (-{feudal_cost.food:.0f}F, 130s)",
                    f"Italians -15% Age Up; {tc_pre_click_idle_s}s TC idle; reaches Feudal Age at {sim.fmt_time(t + int(feudal_time))}. 4 Stone miners actively gathering.",
                )

        # Feudal Transition: Sheep #8 finishes -> move overflow to LC #1 (cap 8) / Stragglers, seed up to 3 Farms (2s walk + 15s build) while reserving 325W for Market + Blacksmith
        if (
            not sheep_post_logged
            and feudal_clicked
            and sim.age == 1
            and sim.undiscovered_sheep == 0
            and sim.remaining_animals["sheep"] == 0
            and sim.active_carcass_food["sheep"] <= 1e-6
        ):
            sheep_post_logged = True
            cur_lc_w = sim.count_role("wood")
            moved_w = 0
            for v in sim.vils:
                if v["role"] in ("straggler", "sheep") and int(v["busy_until"]) <= t and (cur_lc_w + moved_w) < 8:
                    v["role"] = "wood"
                    v["camp_idx"] = 0
                    v["busy_until"] = t + int(rules.camp_or_berry_walk_time_one_way)
                    moved_w += 1
            add_row(
                f"{len(sim.vils)} ({sim.total_pop()})",
                sim.fmt_time(),
                "Feudal Transition",
                f"Move {moved_w} TC Sheep vil -> Wood at LC #1\nMove remaining TC Sheep vils -> Stragglers\nMove up to 2 Straggler vils -> Seed Farms (-60W each)",
                "Sheep #8 finishes; cap LC #1 at 8 vils (rule 3.4); reserve 325W for Market + Blacksmith; 2s TC farm walk (rule 2.7).",
            )

        if sheep_post_logged and not castle_clicked and sim.farms_seeded < 2 and sim.has_building("mill"):
            res_mb = (0 if market_started else 175) + (0 if bs_started else 150)
            if sim.bank.wood >= (60 + res_mb):
                for v in sim.vils:
                    if v["role"] in ("straggler", "sheep") and int(v["busy_until"]) <= t:
                        sim.spend(ResourceBundle(wood=60), "TransitionFarm")
                        v["role"] = "farm"
                        v["busy_until"] = t + int(rules.farm_walk_time) + 15
                        sim.register_new_farm(t + int(rules.farm_walk_time) + 15)
                        break

        # Feudal Age: Queue 2nd Feudal villager
        if sim.age == 2 and not castle_clicked and sim.tc_action[0] == "idle" and feudal_vils_queued == 1:
            if sim.bank.food >= 50:
                sim.spend(ResourceBundle(food=50), "feudal_vil2")
                sim.tc_busy_until[0] = t + 25
                sim.tc_action[0] = f"vil_{len(sim.vils)+1}"
                feudal_vils_queued = 2

        # Feudal Age Market trade: Sell 100 Stone for +91 Gold (rule 7.2)
        if market_ready_t is not None and t >= market_ready_t and not stone_sold and sim.bank.stone >= 100:
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
            and stone_sold
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
                moved_g = 0
                for v in sim.vils:
                    if v["role"] in ("straggler", "wood") and int(v["busy_until"]) <= t and moved_g < 3:
                        v["role"] = "gold"
                        v["busy_until"] = t + 15
                        moved_g += 1
                add_row(
                    f"{len(sim.vils)} ({sim.total_pop()})",
                    sim.fmt_time(),
                    "Feudal Age",
                    f"Click Castle Age (-{castle_cost.food:.0f}F, -{castle_cost.gold:.0f}G, 160s)\nMove {moved_g} Wood/Straggler vils (Market/Blacksmith builders) -> Gold",
                    f"Italians -15% Age Up; {sim.count_role('gold')} total on Gold; reaches Castle Age at {sim.fmt_time(t + int(castle_time))}.",
                )

        # Castle Transition: DBA, Horse Collar, Farms #3-#5, Barracks -> Stable #1, Gold Mining, Fletching
        if castle_clicked and sim.age >= 2 and t >= castle_click_t + 1:
            if not dba_started and queue_upg("double-bit axe"):
                dba_started = True
            if dba_started and not hc_started and queue_upg("horse collar"):
                hc_started = True
            if hc_started and not barracks_started and sim.bank.wood >= 175:
                barracks_started = True
                sim.spend(ResourceBundle(wood=175), "Barracks")
                sim.buildings.append("barracks")
                barracks_ready_t = t + 10 + 50
                _pull_builders(sim, ("wood", "straggler"), 1, barracks_ready_t + 10)
            if barracks_ready_t is not None and t >= barracks_ready_t and not stable_started and sim.bank.wood >= 175:
                stable_started = True
                sim.spend(ResourceBundle(wood=175), "Stable1")
                sim.buildings.append("stable")
                stable_ready_t = t + 50  # 0s walk chained by Barracks builder (rule 2.3)
                _pull_builders(sim, ("wood", "straggler"), 1, stable_ready_t + 10)
                milestones["stable_ready_str"] = sim.fmt_time(stable_ready_t)
            if hc_started and barracks_started and sim.age == 2 and sim.farms_seeded < (5 if is_1tc else 4) and sim.bank.wood >= 60:
                for v in sim.vils:
                    if v["role"] in ("straggler", "wood") and int(v["busy_until"]) <= t:
                        walk_t = int(rules.farm_walk_time) if v["role"] == "straggler" else int(rules.camp_or_berry_walk_time_one_way)
                        sim.spend(ResourceBundle(wood=60), "CastleTransFarm")
                        v["role"] = "farm"
                        v["busy_until"] = t + walk_t + 15
                        sim.register_new_farm(t + walk_t + 15)
                        break
            if not gold_mining_started and hc_started and stable_started and (sim.farms_seeded >= 4 or sim.age >= 3):
                if queue_upg("gold mining", res_food=50):
                    gold_mining_started = True
            if sim.age == 2 and not fletching_started and gold_mining_started and t >= castle_click_t + 100:
                if queue_upg("fletching", res_food=100, res_gold=20):
                    fletching_started = True

        if sim.age >= 3 and not bow_saw_started and queue_upg("bow saw", res_food=50 * sim.tc_count):
            bow_saw_started = True

        if stable_ready_t is not None and t == stable_ready_t and stable_count == 0:
            stable_count = 1

        # Rule 4.4 House management: maintain 2-3 + producing_mil + extra_tcs room at completion; houses come before units
        producing_mil = castle_count + stable_count + (1 if fwd_sw1_ready_t and t >= fwd_sw1_ready_t else 0)
        extra_tcs = max(0, sim.tc_count - 1)
        need_house_room = sim.house_threshold(producing_mil, extra_tcs) + (4 if (producing_mil + extra_tcs) >= 3 else 2)
        pending_houses = sum(1 for _, p in sim.pending_pop_buildings if p == 5)
        pending_house_pop = pending_houses * 5
        projected_free = sim.pop_cap() + pending_house_pop - sim.total_pop()
        house_waiting_wood = (
            sim.age >= 2
            and projected_free <= need_house_room
            and pending_houses < 3
            and (sim.pop_cap() + pending_house_pop) < 200
        )
        if house_waiting_wood and sim.bank.wood >= 25:
            sim.spend(ResourceBundle(wood=25), "House")
            comp_t = t + int(rules.house_walk_time_one_way) + 25
            sim.add_pending_pop_building(comp_t, 5, "house")
            _pull_builders(sim, ("wood", "straggler", "farm"), 1, comp_t + int(rules.house_walk_time_one_way))

        house_wood_res = 25 if house_waiting_wood else 0

        # === CASTLE AGE & IMPERIAL AGE ===
        if sim.age >= 3:
            if not def_castle_started and sim.bank.stone >= 650:
                def_castle_started = True
                sim.spend(ResourceBundle(stone=650), "DefensiveCastle")
                c_build = int(round(calc_construction_time(200.0, 6)))
                def_castle_ready_t = t + 10 + c_build
                sim.add_pending_pop_building(def_castle_ready_t, 20, "castle")
                milestones["def_castle_started_str"] = sim.fmt_time(t)
                milestones["castle_wait_s"] = t - (castle_reached_t or t)
                _pull_builders(sim, ("straggler", "berries", "farm", "gold"), 6, def_castle_ready_t + 10)

            if sim.age == 3 and not imp_clicked:
                max_castle_float["food"] = max(max_castle_float["food"], sim.bank.food)
                max_castle_float["wood"] = max(max_castle_float["wood"], sim.bank.wood)
                max_castle_float["gold"] = max(max_castle_float["gold"], sim.bank.gold)

            # Activate TCs & Castles on completion
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
            if tc4_ready_t is not None and t == tc4_ready_t:
                sim.tc_count += 1
                sim.tc_busy_until.append(t)
                sim.tc_action.append("idle")
                milestones["tc4_ready_str"] = sim.fmt_time(t)

            if def_castle_ready_t is not None and t == def_castle_ready_t:
                castle_count = 1
                milestones["def_castle_ready_str"] = sim.fmt_time(t)
                if is_1tc and not stone_adjusted_early:
                    stone_adjusted_early = True
                    moved_s = 0
                    cur_camp = max(0, len(sim.lumber_camps) - 1)
                    for v in sim.vils:
                        if v["role"] == "stone" and int(v["busy_until"]) <= t and moved_s < 2:
                            v["role"] = "wood"
                            v["camp_idx"] = cur_camp
                            v["busy_until"] = t + int(rules.site_to_site_walk_time_one_way)
                            moved_s += 1
            if fwd_castle2_ready_t is not None and t == fwd_castle2_ready_t:
                castle_count = 2
                milestones["fwd_castle2_ready_str"] = sim.fmt_time(t)
            if fwd_castle3_ready_t is not None and t == fwd_castle3_ready_t:
                castle_count = 3
                milestones["fwd_castle3_ready_str"] = sim.fmt_time(t)

            ballistics_prio = (
                sim.age >= 3
                and sim.military_units["genoese"] >= 20
                and not ballistics_started
                and not imp_prep_started
                and (is_1tc or boom3tc_ready_logged)
            )
            saving_for_imp = imp_prep_started and not imp_clicked

            # STRATEGY 1
            if is_1tc:
                if not monastery_started and def_castle_started and sim.bank.wood >= (175 + house_wood_res):
                    monastery_started = True
                    sim.spend(ResourceBundle(wood=175), "Monastery")
                    monastery_ready_t = t + 10 + 40
                    milestones["monastery_ready_str"] = sim.fmt_time(monastery_ready_t)
                    _pull_builders(sim, ("wood", "straggler", "gold"), 1, monastery_ready_t + 10)
                if (
                    monastery_ready_t is not None
                    and t >= monastery_ready_t
                    and monks_trained < 2
                    and t >= monastery_busy_until
                    and sim.free_pop() >= 1
                    and sim.bank.gold >= 100
                ):
                    monks_trained += 1
                    sim.spend(ResourceBundle(gold=100), "Monk")
                    sim.military_units["monk"] += 1
                    monastery_busy_until = t + 51
                    if monks_trained == 1:
                        relic1_time = t + 51 + 50

                if not army30_reached and army_combat_count() >= 30:
                    army30_reached = True
                    milestones["army30_str"] = sim.fmt_time(t)
                if army30_reached and not fwd_sw_dispatched and "loom" in sim.upgrades:
                    for v in sim.vils:
                        if v["role"] in ("wood", "farm") and int(v["busy_until"]) <= t:
                            fwd_sw_dispatched = True
                            fwd_sw_arrive_t = t + int(rules.forward_walk_time_default)
                            v["role"] = "forward"
                            v["busy_until"] = fwd_sw_arrive_t + 60
                            fwd_vils = [v]
                            break
                if fwd_sw_arrive_t is not None and t >= fwd_sw_arrive_t and not fwd_sw1_started and not (ballistics_prio and not univ_started) and sim.bank.wood >= (200 + house_wood_res):
                    fwd_sw1_started = True
                    sim.spend(ResourceBundle(wood=200), "FwdSW1")
                    fwd_sw1_ready_t = t + 40
                    if fwd_vils:
                        fwd_vils[0]["busy_until"] = fwd_sw1_ready_t
                    milestones["fwd_sw_ready_str"] = sim.fmt_time(fwd_sw1_ready_t)
                    if not castle_loop2_logged:
                        castle_loop2_logged = True
                        add_row(
                            f"{len(sim.vils)} ({sim.total_pop()})",
                            f"{milestones.get('ballistics_str', sim.fmt_time())} – {sim.fmt_time()}",
                            "Castle Age",
                            "Send 1 Wood/Farm Loom vil forward (60s walk) -> Build Forward Siege Workshop (-200W)\nTrain 3–4 Battering Rams (-160W, -75G each)\n1 Wood/Farm vil builds Stable #2 (-175W) -> Wood\nResearch Heavy Plow (-125F, -125W)\nContinue Genoese + Light Cavalry (1 TC)",
                            f"30+ Army Forward Siege Push ({format_army_counts(sim.military_units).replace('Army: ', '')}); keep 1 TC until Imperial click.",
                        )
                if (
                    fwd_sw1_ready_t is not None
                    and t >= fwd_sw1_ready_t
                    and rams_trained < 4
                    and t >= sw_busy_until[0]
                    and not ballistics_prio
                    and sim.free_pop() >= 1
                    and sim.bank.wood >= (160 + house_wood_res)
                    and sim.bank.gold >= 75
                ):
                    rams_trained += 1
                    sim.spend(ResourceBundle(wood=160, gold=75), "BatteringRam")
                    sw_busy_until[0] = t + 36
                    sim.military_units["battering_ram"] += 1

                if sim.age == 3 and not imp_prep_started and ballistics_started and rams_trained >= 3:
                    imp_prep_started = True
                    milestones["imp_prep_str"] = sim.fmt_time(t)

                if sim.age == 3 and not imp_clicked and (t - last_market_trade_t) >= 60 and market_trades_castle < 4:
                    if sim.bank.wood >= 500 and sim.bank.gold < 200:
                        last_market_trade_t = t
                        market_trades_castle += 1
                        sim.sell_at_market("wood", 100)
                    elif imp_prep_started and sim.bank.food >= 850 and 550 <= sim.bank.gold < 680 and sim.bank.wood >= 400:
                        last_market_trade_t = t
                        market_trades_castle += 1
                        sim.sell_at_market("wood", 100)
                    elif imp_prep_started and sim.bank.food >= 1050 and 550 <= sim.bank.gold < 680:
                        last_market_trade_t = t
                        market_trades_castle += 1
                        sim.sell_at_market("food", 100)

                if imp_clicked and not tc2_started and sim.bank.wood >= (275 + house_wood_res) and sim.bank.stone >= 100:
                    tc2_started = True
                    sim.spend(ResourceBundle(wood=275, stone=100), "TC2")
                    tc_b = int(round(calc_construction_time(150.0, 3)))  # 90s
                    tc2_ready_t = t + 10 + tc_b
                    sim.add_pending_pop_building(tc2_ready_t, 5, "town center")
                    _pull_builders(sim, ("wood", "farm"), 3, tc2_ready_t + 10)
                    milestones["tc2_started_str"] = sim.fmt_time(t)
                if imp_clicked and tc2_started and not tc3_started and sim.bank.wood >= (275 + house_wood_res) and sim.bank.stone >= 100:
                    tc3_started = True
                    sim.spend(ResourceBundle(wood=275, stone=100), "TC3")
                    tc_b = int(round(calc_construction_time(150.0, 3)))
                    tc3_ready_t = t + 10 + tc_b
                    sim.add_pending_pop_building(tc3_ready_t, 5, "town center")
                    _pull_builders(sim, ("wood", "farm"), 3, tc3_ready_t + 10)
                    milestones["tc3_started_str"] = sim.fmt_time(t)

            # STRATEGY 2
            else:
                if not army20_reached and sim.military_units["genoese"] >= 13 and sim.military_units["light_cav"] >= 7:
                    army20_reached = True
                    army20_t = t
                    milestones["army20_reached_str"] = sim.fmt_time(t)
                    add_row(
                        f"{len(sim.vils)} ({sim.total_pop()})",
                        f"{sim.fmt_time(castle_reached_t or t)} – {sim.fmt_time()}",
                        "Castle Age",
                        f"Train {sim.military_units['genoese']} Genoese Crossbowmen + {sim.military_units['light_cav']} Light Cavalry\nResearch Light Cavalry + Blacksmith & Bloodlines upgrades\nQueue TC #1 Vils -> Farms / Gold / Wood",
                        "~20 army defense setup complete -> expand to 3 TCs.",
                    )

                if army20_reached and not tc2_started and sim.bank.wood >= (275 + house_wood_res) and sim.bank.stone >= 100:
                    tc2_started = True
                    sim.spend(ResourceBundle(wood=275, stone=100), "TC2")
                    tc_b = int(round(calc_construction_time(150.0, 3)))
                    tc2_ready_t = t + 10 + tc_b
                    sim.add_pending_pop_building(tc2_ready_t, 5, "town center")
                    _pull_builders(sim, ("wood", "farm"), 3, tc2_ready_t + 10)
                    milestones["tc2_started_str"] = sim.fmt_time(t)
                if tc2_started and not tc3_started and sim.bank.wood >= (275 + house_wood_res) and sim.bank.stone >= 100:
                    tc3_started = True
                    sim.spend(ResourceBundle(wood=275, stone=100), "TC3")
                    tc_b = int(round(calc_construction_time(150.0, 3)))
                    tc3_ready_t = t + 10 + tc_b
                    sim.add_pending_pop_building(tc3_ready_t, 5, "town center")
                    _pull_builders(sim, ("wood", "farm"), 3, tc3_ready_t + 10)
                    milestones["tc3_started_str"] = sim.fmt_time(t)

                f_cnt_s2 = sim.count_role("farm")
                boom3tc_ready = tc3_ready_t is not None and t >= tc3_ready_t and f_cnt_s2 >= 22 and wheelbarrow_started
                if boom3tc_ready and not boom3tc_ready_logged:
                    boom3tc_ready_logged = True
                    boom3tc_setup_t = t
                    milestones["boom3tc_setup_str"] = sim.fmt_time(t)
                    add_row(
                        f"{len(sim.vils)} ({sim.total_pop()})",
                        f"{sim.fmt_time(army20_t or t)} – {sim.fmt_time()}",
                        "Castle Age",
                        f"Pause military briefly\n3 Wood/Farm vils build TC #2 (-275W, -100S, 90s) -> return\n3 Wood/Farm vils build TC #3 (-275W, -100S, 90s) -> return\nAssign 3-TC Vils -> Farms (to {f_cnt_s2}+)\nResearch Wheelbarrow (-175F, -50W)",
                        "3-TC boom established -> resume & maximize army.",
                    )

                # Forward expedition (8 vils, 60s default walk per rule 2.10; stay forward to build!)
                if boom3tc_ready and ballistics_started and not fwd_vils_dispatched and "loom" in sim.upgrades and sim.bank.stone >= 700:
                    fwd_vils_dispatched = True
                    fwd_vils_arrive_t = t + int(rules.forward_walk_time_default)
                    milestones["fwd_vils_dispatched_str"] = sim.fmt_time(t)
                    for v in sim.vils:
                        if v["role"] in ("wood", "farm") and int(v["busy_until"]) <= t and len(fwd_vils) < 8:
                            v["role"] = "forward"
                            v["busy_until"] = fwd_vils_arrive_t + 400
                            fwd_vils.append(v)
                if fwd_vils_arrive_t is not None and t >= fwd_vils_arrive_t and not fwd_castle2_started and sim.bank.stone >= 650:
                    fwd_castle2_started = True
                    sim.spend(ResourceBundle(stone=650), "FwdCastle2")
                    c_b = int(round(calc_construction_time(200.0, max(1, len(fwd_vils)))))  # 60s for 8 vils
                    fwd_castle2_ready_t = t + c_b
                    sim.add_pending_pop_building(fwd_castle2_ready_t, 20, "castle")
                    for v in fwd_vils:
                        v["busy_until"] = fwd_castle2_ready_t
                if fwd_castle2_ready_t is not None and t >= fwd_castle2_ready_t and not tc4_started and sim.bank.wood >= (275 + house_wood_res) and sim.bank.stone >= 100:
                    tc4_started = True
                    sim.spend(ResourceBundle(wood=275, stone=100), "TC4")
                    tc4_b = int(round(calc_construction_time(150.0, 4)))  # 75s
                    tc4_ready_t = t + tc4_b
                    sim.add_pending_pop_building(tc4_ready_t, 5, "town center")
                    for v in fwd_vils[:4]:
                        v["busy_until"] = tc4_ready_t
                    milestones["tc4_ready_str"] = sim.fmt_time(tc4_ready_t)
                if fwd_castle2_ready_t is not None and t >= fwd_castle2_ready_t and not fwd_sw1_started and sim.bank.wood >= (200 + house_wood_res):
                    fwd_sw1_started = True
                    sim.spend(ResourceBundle(wood=200), "FwdSW1")
                    fwd_sw1_ready_t = t + 40
                    for v in fwd_vils[4:5]:
                        v["busy_until"] = fwd_sw1_ready_t
                if sim.age == 4 and fwd_sw1_started and not fwd_sw2_started and sim.bank.wood >= (200 + house_wood_res):
                    fwd_sw2_started = True
                    sim.spend(ResourceBundle(wood=200), "FwdSW2")
                    fwd_sw2_ready_t = t + 40
                    for v in fwd_vils[5:6]:
                        v["busy_until"] = fwd_sw2_ready_t
                if fwd_castle2_ready_t is not None and t >= fwd_castle2_ready_t and tc4_started and not fwd_castle3_started and sim.bank.stone >= 650:
                    fwd_castle3_started = True
                    sim.spend(ResourceBundle(stone=650), "FwdCastle3")
                    c_b3 = int(round(calc_construction_time(200.0, 6)))
                    fwd_castle3_ready_t = t + c_b3
                    sim.add_pending_pop_building(fwd_castle3_ready_t, 20, "castle")
                    for v in fwd_vils:
                        v["busy_until"] = max(int(v["busy_until"]), fwd_castle3_ready_t)
                    moved_off_s = 0
                    for v in sim.vils:
                        if v["role"] == "stone" and moved_off_s < 4:
                            v["role"] = "gold"
                            v["busy_until"] = t + int(rules.site_to_site_walk_time_one_way)
                            moved_off_s += 1
                # Return remaining forward vils to wood/gold after Castle #3 & TC4 finish
                if fwd_castle3_ready_t is not None and t >= fwd_castle3_ready_t:
                    cur_camp = max(0, len(sim.lumber_camps) - 1)
                    for v in fwd_vils:
                        if v["role"] == "forward" and int(v["busy_until"]) <= t:
                            v["role"] = "wood"
                            v["camp_idx"] = cur_camp
                            v["busy_until"] = t + int(rules.forward_walk_time_default)

                if sim.age == 3 and not imp_prep_started and ballistics_started and fwd_vils_dispatched and len(sim.vils) >= 85:
                    imp_prep_started = True
                    milestones["imp_prep_str"] = sim.fmt_time(t)
                    if not castle_loop2_logged:
                        castle_loop2_logged = True
                        add_row(
                            f"{len(sim.vils)} ({sim.total_pop()})",
                            f"{sim.fmt_time(boom3tc_setup_t or t)} – {sim.fmt_time()}",
                            "Castle Age",
                            "Train Genoese Crossbowmen + Light Cavalry continuously\n1 Wood/Straggler vil builds University (-200W) -> Research Ballistics\nSend 8 Loom Wood/Farm vils forward (60s walk) -> Build Castles #2/#3, TC #4 & Siege Workshop -> return to Wood\nMove 4 Stone vils -> Gold after Castle #3\nBank 850F / 680G",
                            f"3-TC full flood; Ballistics at 20+ Genoese; army at Imp prep: {format_army_counts(sim.military_units).replace('Army: ', '')}.",
                        )

                if sim.age == 3 and boom3tc_ready and not imp_clicked and (t - last_market_trade_t) >= 60 and market_trades_castle < 4:
                    if imp_prep_started and sim.bank.food >= 850 and 550 <= sim.bank.gold < 680 and sim.bank.wood >= 400:
                        last_market_trade_t = t
                        market_trades_castle += 1
                        sim.sell_at_market("wood", 100)
                    elif imp_prep_started and sim.bank.food >= 1050 and 550 <= sim.bank.gold < 680:
                        last_market_trade_t = t
                        market_trades_castle += 1
                        sim.sell_at_market("food", 100)

            # Anti-float rebalancer (rule 8.4)
            if t % 15 == 0 and t >= (castle_reached_t or 0) + 120:
                g_cnt_r = sim.count_role("gold")
                w_cnt_r = sim.count_role("wood", "straggler")
                f_cnt_r = sim.count_role("farm")
                imp_f_cap = 40 if is_1tc else 48
                cur_camp = max(0, len(sim.lumber_camps) - 1)
                if not saving_for_imp and sim.bank.food > 1050 and sim.bank.wood < 450 and f_cnt_r > 20:
                    moved = 0
                    for v in sim.vils:
                        if v["role"] == "farm" and int(v["busy_until"]) <= t and moved < 3:
                            v["role"] = "wood"
                            v["camp_idx"] = cur_camp
                            v["busy_until"] = t + 15
                            moved += 1
                elif not saving_for_imp and sim.bank.gold > (750 if not imp_clicked else 950) and sim.bank.wood < 450 and g_cnt_r > 6:
                    moved = 0
                    for v in sim.vils:
                        if v["role"] == "gold" and int(v["busy_until"]) <= t and moved < 2:
                            v["role"] = "wood"
                            v["camp_idx"] = cur_camp
                            v["busy_until"] = t + 15
                            moved += 1
                elif sim.bank.gold < (750 if saving_for_imp else (450 if sim.age < 4 else 750)) and (sim.bank.wood > 550 or sim.bank.food > 950) and g_cnt_r < 34:
                    src_role = "farm" if (sim.bank.food > 1050 and f_cnt_r > 24) else ("wood" if w_cnt_r > 16 else None)
                    if src_role:
                        moved = 0
                        for v in sim.vils:
                            if v["role"] == src_role and int(v["busy_until"]) <= t and moved < 3:
                                v["role"] = "gold"
                                v["busy_until"] = t + 15
                                moved += 1
                elif not ballistics_prio and sim.bank.wood > (550 + house_wood_res) and sim.bank.food < 950 and w_cnt_r > 16 and f_cnt_r < imp_f_cap and (not is_1tc or tc3_started or not imp_prep_started):
                    moved = 0
                    for v in sim.vils:
                        if v["role"] == "wood" and int(v["busy_until"]) <= t and moved < 3:
                            sim.spend(ResourceBundle(wood=60), "RebalanceFarm")
                            v["role"] = "farm"
                            v["busy_until"] = t + 30  # 15s wood->TC + 15s build (rules 2.4, 3.10)
                            sim.register_new_farm(t + 30)
                            moved += 1
                            if moved >= 3 or sim.bank.wood < 450:
                                break

                if is_1tc and tc3_started and sim.bank.stone >= 200 and sim.count_role("stone") > 0:
                    for v in sim.vils:
                        if v["role"] == "stone" and int(v["busy_until"]) <= t:
                            v["role"] = "wood" if sim.bank.wood < sim.bank.gold else "gold"
                            v["camp_idx"] = cur_camp
                            v["busy_until"] = t + 15
                if not is_1tc and (fwd_castle3_started or sim.bank.stone >= 800) and sim.count_role("stone") > 1:
                    for v in sim.vils:
                        if v["role"] == "stone" and int(v["busy_until"]) <= t:
                            v["role"] = "wood" if sim.bank.wood < sim.bank.gold else "gold"
                            v["camp_idx"] = cur_camp
                            v["busy_until"] = t + 15
                            if sim.count_role("stone") <= 1:
                                break

            # TC Queue management (rules 4.3, 5.1-5.3)
            for tc_idx in range(sim.tc_count):
                if sim.tc_action[tc_idx] == "idle":
                    f_cnt_now = sim.count_role("farm")
                    can_click_imp = (
                        (is_1tc and ballistics_started and fwd_sw1_started and rams_trained >= 3 and sim.bank.can_afford(imp_cost))
                        or (not is_1tc and imp_prep_started and sim.bank.can_afford(imp_cost))
                    )
                    if tc_idx == 0 and not imp_clicked and can_click_imp:
                        imp_clicked = True
                        imp_click_t = t
                        milestones["imp_click_s"] = t
                        milestones["imp_click_str"] = sim.fmt_time(t)
                        milestones["imp_click_vils"] = len(sim.vils)
                        milestones["imp_click_alloc"] = sim.current_macro_alloc()
                        milestones["imp_click_army"] = dict(sim.military_units)
                        sim.spend(imp_cost, "ImperialClick")
                        sim.tc_busy_until[0] = t + int(imp_time)
                        sim.tc_action[0] = "imperial"
                        add_row(
                            f"{len(sim.vils)} ({sim.total_pop()})",
                            sim.fmt_time(),
                            "Castle Age",
                            f"Click Imperial Age (-{imp_cost.food:.0f}F, -{imp_cost.gold:.0f}G, 190s)",
                            (
                                f"Italians -15% Age Up; army: {format_army_counts(sim.military_units).replace('Army: ', '')}; add TC #2 & TC #3 during Imperial Transition."
                                if is_1tc
                                else f"Italians -15% Age Up; army: {format_army_counts(sim.military_units).replace('Army: ', '')}; 4 TCs continue booming during Imperial Transition."
                            ),
                        )
                    elif tc_idx == 0 and not wheelbarrow_started and f_cnt_now >= 15 and (is_1tc or army20_reached) and sim.bank.food >= 175 and sim.bank.wood >= (50 + house_wood_res):
                        wheelbarrow_started = True
                        sim.spend(ResourceBundle(food=175, wood=50), "Wheelbarrow")
                        sim.tc_busy_until[0] = t + 75
                        sim.tc_action[0] = "wheelbarrow"
                    elif not loom_started and ((is_1tc and army_combat_count() >= 26 and tc_idx == 0) or (not is_1tc and tc3_ready_t is not None and t >= tc3_ready_t and tc_idx > 0)) and sim.bank.gold >= 50:
                        loom_started = True
                        sim.spend(ResourceBundle(gold=50), "Loom")
                        sim.tc_busy_until[tc_idx] = t + 25
                        sim.tc_action[tc_idx] = "loom"
                    elif tc_idx == 0 and wheelbarrow_started and "wheelbarrow" in sim.upgrades and not hand_cart_started and not saving_for_imp and f_cnt_now >= 22 and sim.tc_count >= 3 and sim.bank.food >= 320 and sim.bank.wood >= (200 + house_wood_res):
                        hand_cart_started = True
                        sim.spend(ResourceBundle(food=300, wood=200), "HandCart")
                        sim.tc_busy_until[0] = t + 55
                        sim.tc_action[0] = "hand_cart"
                    else:
                        max_vils_cap = 98 if is_1tc else 112
                        in_flight_vils = sum(1 for a in sim.tc_action if a.startswith("vil_"))
                        # Rule 5.3: only hold TC <= 5s when Imp will be affordable within 5s
                        want_hold_imp = (
                            tc_idx == 0
                            and not imp_clicked
                            and imp_prep_started
                            and sim.bank.gold >= imp_cost.gold - 15
                            and sim.bank.food >= imp_cost.food - 25
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

            # Reservations + Military production + Upgrades
            f_cnt_cur = sim.count_role("farm")
            tc_food_reserve = (120 if is_1tc else 75) * sim.tc_count
            univ_trigger = (is_1tc and sim.military_units["genoese"] >= 20) or (not is_1tc and boom3tc_ready_logged and sim.military_units["genoese"] >= 20)
            bal_cost, bal_time = sim.db.get_upgrade_spec("ballistics", "Italians")

            tc_w_res = (
                (275 if (not is_1tc and army20_reached and not tc2_started) else 0)
                + (275 if (not is_1tc and tc2_started and not tc3_started) else 0)
                + (275 if (is_1tc and imp_clicked and not tc2_started) else 0)
                + (275 if (is_1tc and imp_clicked and tc2_started and not tc3_started) else 0)
                + (275 if (not is_1tc and fwd_castle2_started and not tc4_started) else 0)
            )
            univ_w_res = 200 if (univ_trigger and not univ_started) else (int(bal_cost.wood) if (univ_started and not ballistics_started) else 0)
            univ_g_res = int(bal_cost.gold) if (univ_trigger and not ballistics_started) else 0
            sw_w_res = (
                (200 if (is_1tc and army30_reached and not fwd_sw1_started) else 0)
                + (200 if (not is_1tc and tc4_started and not fwd_sw1_started) else 0)
                + (200 if (not is_1tc and sim.age == 4 and fwd_sw1_started and not fwd_sw2_started) else 0)
            )
            ram_w_res = 160 if (is_1tc and fwd_sw1_ready_t is not None and t >= fwd_sw1_ready_t and rams_trained < 4 and t >= sw_busy_until[0] - 8) else 0
            ram_g_res = 75 if ram_w_res > 0 else 0
            bbc_w_res = 180 if (sim.age == 4 and chemistry_ready_t is not None and t >= chemistry_ready_t and bbc_count_trained < 4 and fwd_sw1_ready_t is not None and t >= fwd_sw1_ready_t) else 0
            monastery_w_res = 175 if (is_1tc and def_castle_started and not monastery_started) else 0
            wb_w_res = 50 if (f_cnt_cur >= 15 and not wheelbarrow_started) else 0
            farm_w_res = 60 if (is_1tc and not saving_for_imp and (f_cnt_cur < 12 or (f_cnt_cur < 15 and sim.bank.food < 250))) else 0
            monk_g_res = 100 if (is_1tc and monastery_ready_t is not None and t >= monastery_ready_t and monks_trained < 2 and t >= monastery_busy_until - 8) else 0

            total_w_res = house_wood_res + tc_w_res + univ_w_res + sw_w_res + ram_w_res + bbc_w_res + wb_w_res + monastery_w_res
            mil_w_res = total_w_res + farm_w_res
            total_g_res = monk_g_res + ram_g_res + univ_g_res

            if is_1tc:
                genoese_allowed = not (saving_for_imp and sim.bank.gold < imp_cost.gold) and not (ballistics_prio and sim.bank.gold < 40 + univ_g_res)
                lcav_allowed = (imp_clicked or sim.military_units["light_cav"] < 20) and not (saving_for_imp and sim.bank.food < imp_cost.food)
            else:
                boom3tc_ready_now = tc3_ready_t is not None and t >= tc3_ready_t and f_cnt_cur >= 22 and wheelbarrow_started
                want_genoese_phase1 = (not army20_reached) and (sim.military_units["genoese"] < 13)
                want_lcav_phase1 = (not army20_reached) and (sim.military_units["light_cav"] < 7)
                genoese_allowed = (want_genoese_phase1 or boom3tc_ready_now) and not (army20_reached and not boom3tc_ready_now) and not (saving_for_imp and sim.bank.gold < imp_cost.gold) and not (ballistics_prio and sim.bank.gold < 40 + univ_g_res)
                lcav_allowed = (want_lcav_phase1 or boom3tc_ready_now) and not (army20_reached and not boom3tc_ready_now) and not (saving_for_imp and sim.bank.food < imp_cost.food)

            genoese_train_s = 11 if "conscription" in sim.upgrades else 14
            hold_genoese_for_elite = sim.age == 4 and sim.military_units["genoese"] >= 45 and not elite_genoese_started
            genoese_pop_cap = 70 if is_1tc else 48
            army_pop_limit = 194 if ((imp_clicked or sim.age == 4) and bbc_count_trained < 3) else 200
            for c_idx in range(castle_count):
                if t >= castle_busy_until[c_idx] and genoese_allowed and not hold_genoese_for_elite and sim.free_pop() >= 1 and sim.total_pop() < army_pop_limit:
                    if sim.bank.wood >= (45 + mil_w_res) and sim.bank.gold >= (40 + total_g_res):
                        sim.spend(ResourceBundle(wood=45, gold=40), "Genoese")
                        castle_busy_until[c_idx] = t + genoese_train_s
                        if sim.military_units["genoese"] >= genoese_pop_cap or sim.total_pop() >= army_pop_limit - 1:
                            sim.casualties["genoese"] += 1
                        else:
                            sim.military_units["genoese"] += 1

            # Stable & Light Cav
            if stable_ready_t is not None and t >= stable_ready_t:
                if not lcav_upg_started and bow_saw_started and def_castle_ready_t is not None and t >= def_castle_ready_t and t >= stable_busy_until[0]:
                    if sim.bank.food >= (150 + tc_food_reserve) and sim.bank.gold >= 50:
                        lcav_upg_started = True
                        sim.spend(ResourceBundle(food=150, gold=50), "LightCavUpg")
                        stable_busy_until[0] = t + 45
                        sim.queue_upgrade("light cavalry", t + 45)
                        if sim.military_units["scout"] > 0:
                            sim.military_units["scout"] -= 1
                            sim.military_units["light_cav"] += 1

                if is_1tc:
                    if stable_count == 1 and not ballistics_prio and ballistics_started and f_cnt_cur >= 16 and sim.bank.wood >= (175 + total_w_res + 80):
                        stable_count = 2
                        sim.spend(ResourceBundle(wood=175), "Stable2")
                        stable_busy_until[1] = t + 10 + 50
                        _pull_builders(sim, ("wood", "farm"), 1, t + 60)
                    if stable_count == 2 and sim.age == 4 and tc3_started and len(sim.vils) >= 70 and sim.bank.wood >= (350 + total_w_res):
                        stable_count = 4
                        sim.spend(ResourceBundle(wood=350), "Stables3-4")
                        stable_busy_until[2] = t + 60
                        stable_busy_until[3] = t + 60
                        _pull_builders(sim, ("wood",), 2, t + 60)
                    if stable_count == 4 and sim.age == 4 and sim.bank.wood >= (350 + total_w_res + 100):
                        stable_count = 6
                        sim.spend(ResourceBundle(wood=350), "Stables5-6")
                        stable_busy_until[4] = t + 45
                        stable_busy_until[5] = t + 45
                        _pull_builders(sim, ("wood",), 2, t + 45)
                    if sim.age == 4 and fwd_sw1_started and not fwd_sw2_started and sim.bank.wood >= (200 + total_w_res):
                        fwd_sw2_started = True
                        sim.spend(ResourceBundle(wood=200), "FwdSW2")
                        fwd_sw2_ready_t = t + 40
                else:
                    if stable_count == 1 and boom3tc_ready_logged and not ballistics_prio and f_cnt_cur >= 24 and sim.bank.wood >= (175 + total_w_res + 80):
                        stable_count = 2
                        sim.spend(ResourceBundle(wood=175), "Stable2")
                        stable_busy_until[1] = t + 60
                        _pull_builders(sim, ("wood", "farm"), 1, t + 60)
                    if stable_count == 2 and not ballistics_prio and fwd_castle2_started and tc4_started and fwd_sw1_started and sim.bank.wood >= (175 + total_w_res):
                        stable_count = 3
                        sim.spend(ResourceBundle(wood=175), "Stable3")
                        stable_busy_until[2] = t + 45
                        _pull_builders(sim, ("wood",), 1, t + 45)
                    if stable_count == 3 and (imp_clicked or sim.age == 4) and f_cnt_cur >= 32 and sim.bank.wood >= (175 + total_w_res):
                        stable_count = 4
                        sim.spend(ResourceBundle(wood=175), "Stable4")
                        stable_busy_until[3] = t + 45
                        _pull_builders(sim, ("wood",), 1, t + 45)
                    if stable_count == 4 and sim.age == 4 and len(sim.vils) >= 105 and sim.bank.wood >= (350 + total_w_res):
                        stable_count = 6
                        sim.spend(ResourceBundle(wood=350), "Stables5-6")
                        stable_busy_until[4] = t + 45
                        stable_busy_until[5] = t + 45
                        _pull_builders(sim, ("wood",), 2, t + 45)

                lcav_train_s = 23 if "conscription" in sim.upgrades else 30
                wb_food_res = (175 if (f_cnt_cur >= 15 and not wheelbarrow_started and (is_1tc or army20_reached)) else 0) + (150 if not bow_saw_started else 0)
                hold_lcav_for_upg = sim.age == 4 and sim.military_units["light_cav"] >= 25 and not (hussar_started and elite_genoese_started)
                lcav_pop_cap = 35 if is_1tc else 34
                for s_idx in range(stable_count):
                    if (
                        "light cavalry" in sim.upgrades
                        and t >= stable_busy_until[s_idx]
                        and lcav_allowed
                        and not hold_lcav_for_upg
                        and sim.free_pop() >= 1
                        and sim.total_pop() < army_pop_limit
                        and sim.bank.food >= (80 + tc_food_reserve + wb_food_res)
                    ):
                        sim.spend(ResourceBundle(food=80), "LightCav")
                        stable_busy_until[s_idx] = t + lcav_train_s
                        if sim.total_pop() >= army_pop_limit - 1 or sim.military_units["light_cav"] >= lcav_pop_cap:
                            sim.casualties["light_cav"] += 1
                        else:
                            sim.military_units["light_cav"] += 1

            # University & Ballistics (rule 6.4)
            if univ_trigger and not univ_started and sim.bank.wood >= (200 + house_wood_res + tc_w_res):
                univ_started = True
                sim.spend(ResourceBundle(wood=200), "University")
                univ_ready_t = t + 10 + 60
                _pull_builders(sim, ("wood", "straggler"), 1, univ_ready_t + 10)
            if univ_ready_t is not None and t >= univ_ready_t and not ballistics_started:
                if sim.bank.wood >= (bal_cost.wood + house_wood_res + tc_w_res) and sim.bank.gold >= bal_cost.gold:
                    ballistics_started = True
                    sim.spend(bal_cost, "Ballistics")
                    b_ready = t + int(round(bal_time))
                    sim.queue_upgrade("ballistics", b_ready)
                    milestones["ballistics_str"] = sim.fmt_time(b_ready)
                    milestones["ballistics_vils"] = len(sim.vils)
                    milestones["ballistics_alloc"] = sim.current_macro_alloc()
                    if is_1tc and not castle_loop1_logged:
                        castle_loop1_logged = True
                        add_row(
                            f"{len(sim.vils)} ({sim.total_pop()})",
                            f"{sim.fmt_time(castle_reached_t or t)} – {sim.fmt_time()}",
                            "Castle Age",
                            f"1 Wood/Straggler/Gold vil builds Monastery (-175W); train 2 Monks (-100G each)\nMove 2 Stone vils -> Wood after Defensive Castle finishes\nTrain Genoese Crossbowmen + Light Cavalry continuously\n1 Wood/Straggler vil builds University (-200W) -> Research Ballistics (-{bal_cost.wood:.0f}W, -{bal_cost.gold:.0f}G)",
                            "Monk #1 secures Relic (+30G/min); Italians -25% University techs; Ballistics prioritized at 20+ Genoese ahead of extra Stables/SW per rule 6.4.",
                        )

            # Castle Age combat & eco upgrades (with real research times!)
            if not saving_for_imp:
                if not fletching_started and (sim.age == 2 or bow_saw_started) and queue_upg("fletching", res_food=tc_food_reserve):
                    fletching_started = True
                if not padded_archer_started and fletching_started and lcav_upg_started and queue_upg("padded archer armor", res_food=tc_food_reserve):
                    padded_archer_started = True
                if not scale_barding_started and lcav_upg_started and queue_upg("scale barding armor", res_food=tc_food_reserve):
                    scale_barding_started = True
                if fletching_started and not bodkin_started and (not is_1tc or monks_trained >= 2) and queue_upg("bodkin arrow", res_food=tc_food_reserve, res_gold=univ_g_res):
                    bodkin_started = True
                if not bloodlines_started and lcav_upg_started and scale_barding_started and (is_1tc or boom3tc_ready_logged or sim.military_units["light_cav"] >= 5) and queue_upg("bloodlines", res_food=tc_food_reserve, res_gold=univ_g_res):
                    bloodlines_started = True
                if not forging_started and scale_barding_started and (is_1tc or boom3tc_ready_logged) and queue_upg("forging", res_food=tc_food_reserve):
                    forging_started = True
                if not husbandry_started and bloodlines_started and (is_1tc or boom3tc_ready_logged) and queue_upg("husbandry", res_food=tc_food_reserve):
                    husbandry_started = True
                if not leather_archer_started and bodkin_started and not ballistics_prio and (is_1tc or boom3tc_ready_logged) and queue_upg("leather archer armor", res_food=tc_food_reserve, res_gold=univ_g_res):
                    leather_archer_started = True
                if not chain_barding_started and forging_started and not ballistics_prio and (is_1tc or boom3tc_ready_logged) and queue_upg("chain barding armor", res_food=tc_food_reserve, res_gold=univ_g_res):
                    chain_barding_started = True
                if not iron_casting_started and chain_barding_started and not ballistics_prio and (is_1tc or boom3tc_ready_logged) and queue_upg("iron casting", res_food=tc_food_reserve, res_gold=univ_g_res):
                    iron_casting_started = True

            if ballistics_started and not heavy_plow_started and not saving_for_imp and queue_upg("heavy plow", res_food=tc_food_reserve, res_wood=total_w_res):
                heavy_plow_started = True
            if not is_1tc and tc3_started and not stone_mining_started and queue_upg("stone mining", res_food=tc_food_reserve, res_wood=house_wood_res + tc_w_res):
                stone_mining_started = True
            if not is_1tc and heavy_plow_started and not stone_shaft_started and not saving_for_imp and len(sim.vils) >= 54 and queue_upg("stone shaft mining", res_food=tc_food_reserve, res_wood=house_wood_res + tc_w_res):
                stone_shaft_started = True
            if heavy_plow_started and not gold_shaft_started and not saving_for_imp and len(sim.vils) >= 48 and queue_upg("gold shaft mining", res_food=tc_food_reserve, res_wood=total_w_res):
                gold_shaft_started = True

            if ballistics_started and not pavise_started and (not is_1tc or tc3_started) and (imp_clicked or sim.age == 4) and queue_upg("pavise", res_wood=total_w_res):
                pavise_started = True
            if imp_clicked and not masonry_started and (not is_1tc or tc3_started) and queue_upg("masonry", res_food=80, res_wood=total_w_res):
                masonry_started = True

            # Lowest-priority Lumber Camp refresh & density check (rule 3.4: 60-65% or >8/camp, movers pay 15s)
            active_wood_vils = sim.count_role("wood")
            camps_needed_density = max(1, (active_wood_vils + rules.max_lumberjacks_per_lc - 1) // rules.max_lumberjacks_per_lc)
            need_lc_refresh = sim.min_active_camp_efficiency() <= rules.wood_refresh_lc_threshold or len(sim.lumber_camps) < camps_needed_density
            if (
                need_lc_refresh
                and (t - last_lc_refresh_t) >= 60
                and sim.bank.wood >= (100 + total_w_res + 120)
            ):
                last_lc_refresh_t = t
                sim.spend(ResourceBundle(wood=100), "LumberCampRefresh")
                comp_t = t + int(rules.camp_or_berry_walk_time_one_way) + 35
                new_idx = sim.add_lumber_camp(comp_t)
                _pull_builders(sim, ("wood", "straggler"), 1, comp_t, camp_idx=new_idx)
                sim.reassign_woodcutters_to_new_camp(new_idx, min(rules.max_lumberjacks_per_lc - 1, max(3, active_wood_vils // 2)))

            # Farm conversion from excess Wood
            reserve_w = total_w_res
            min_wood_keep = 8 if f_cnt_cur < 12 else (12 if f_cnt_cur < 18 else (15 if f_cnt_cur < 28 else (18 if f_cnt_cur < 38 else 22)))
            max_f_cap = 22 if (is_1tc and not imp_clicked) else (38 if is_1tc else 48)
            if f_cnt_cur < max_f_cap and sim.bank.wood >= (60 + reserve_w) and sim.bank.food < 1000:
                w_cnt_cur = sim.count_role("wood", "straggler")
                for v in sim.vils:
                    if (v["role"] == "straggler" or (v["role"] == "wood" and w_cnt_cur > min_wood_keep)) and int(v["busy_until"]) <= t:
                        walk_t = int(rules.farm_walk_time) if v["role"] == "straggler" else int(rules.camp_or_berry_walk_time_one_way)
                        sim.spend(ResourceBundle(wood=60), "MacroFarm")
                        v["role"] = "farm"
                        v["busy_until"] = t + walk_t + 15
                        sim.register_new_farm(t + walk_t + 15)
                        break

        # === IMPERIAL AGE ===
        if sim.age == 4:
            if not conscription_started and queue_upg("conscription"):
                conscription_started = True
            if not chemistry_started:
                chem_c, chem_rt = sim.db.get_upgrade_spec("chemistry", "Italians")
                if sim.bank.can_afford(chem_c):
                    chemistry_started = True
                    sim.spend(chem_c, "Chemistry")
                    chemistry_ready_t = t + int(round(chem_rt))
                    sim.queue_upgrade("chemistry", chemistry_ready_t)
            if not bracer_started and queue_upg("bracer"):
                bracer_started = True
            if not two_man_saw_started and (not is_1tc or tc3_started) and queue_upg("two-man saw", res_wood=total_w_res):
                two_man_saw_started = True
            if is_1tc and not capped_ram_started and queue_upg("capped ram"):
                capped_ram_started = True
            if bracer_started and not ring_archer_started and queue_upg("ring archer armor"):
                ring_archer_started = True
            if chain_barding_started and not plate_barding_started and queue_upg("plate barding armor"):
                plate_barding_started = True
            if iron_casting_started and not blast_furnace_started and queue_upg("blast furnace"):
                blast_furnace_started = True
            if pavise_started and not silk_road_started and queue_upg("silk road", res_wood=total_w_res):
                silk_road_started = True
            if not siege_engineers_started and queue_upg("siege engineers", res_wood=total_w_res):
                siege_engineers_started = True
            if blast_furnace_started and not hussar_started and queue_upg("hussar"):
                hussar_started = True
            if hussar_started and not elite_genoese_started and queue_upg("elite genoese crossbowman"):
                elite_genoese_started = True
                milestones["elite_genoese_str"] = sim.fmt_time(t)
            if siege_engineers_started and not crop_rotation_started and queue_upg("crop rotation", res_wood=total_w_res):
                crop_rotation_started = True

            if chemistry_ready_t is not None and t >= chemistry_ready_t:
                active_sws = (1 if (fwd_sw1_ready_t and t >= fwd_sw1_ready_t) else 0) + (1 if (fwd_sw2_ready_t and t >= fwd_sw2_ready_t) else 0)
                max_bbc_now = 4 if (hussar_started and elite_genoese_started) else 2
                for sw_idx in range(active_sws):
                    if t >= sw_busy_until[sw_idx] and bbc_count_trained < max_bbc_now and sim.free_pop() >= 1 and sim.bank.wood >= (180 + house_wood_res) and sim.bank.gold >= 180:
                        bbc_count_trained += 1
                        sim.spend(ResourceBundle(wood=180, gold=180), "BombardCannon")
                        sw_busy_until[sw_idx] = t + 56
                        sim.military_units["bombard_cannon"] += 1
                        if bbc_count_trained == 1:
                            milestones["bbc_queued_str"] = sim.fmt_time(t)

            max_treb_now = 2 if (hussar_started and elite_genoese_started) else 1
            if not is_1tc and castle_count >= 2 and treb_count_trained < max_treb_now and sim.free_pop() >= 1 and (bbc_count_trained >= 2 or sim.free_pop() >= 3) and sim.bank.wood >= (200 + house_wood_res + sw_w_res) and sim.bank.gold >= 200:
                treb_count_trained += 1
                sim.spend(ResourceBundle(wood=200, gold=200), "Trebuchet")
                sim.military_units["trebuchet"] += 1

            if (t - last_market_trade_t) >= 90 and not elite_genoese_started and sim.bank.gold < 750:
                if sim.bank.wood >= 850:
                    last_market_trade_t = t
                    sim.sell_at_market("wood", 200)
                elif sim.bank.food >= 1200:
                    last_market_trade_t = t
                    sim.sell_at_market("food", 200)

        done_1tc = is_1tc and sim.age == 4 and tc3_ready_t is not None and t >= tc3_ready_t and elite_genoese_started and hussar_started and bbc_count_trained >= 2
        done_3tc = not is_1tc and sim.age == 4 and len(sim.vils) >= 112 and elite_genoese_started and hussar_started and silk_road_started and bbc_count_trained >= 2
        if done_1tc or done_3tc:
            milestones["full_push_str"] = sim.fmt_time(t)
            milestones["final_vils"] = len(sim.vils)
            milestones["final_army"] = dict(sim.military_units)
            milestones["final_bank"] = sim.bank.to_dict()
            milestones["housed_seconds"] = housed_seconds
            milestones["tc_pre_click_idle_s"] = tc_pre_click_idle_s
            milestones["extra_tc_idle_s"] = tc_unplanned_idle_s
            milestones["tc1_idle_before_imp_s"] = tc_pre_click_idle_s + tc_unplanned_idle_s
            milestones["negative_bank_count"] = len(sim.negative_bank_events)
            milestones["max_castle_float"] = {k: round(v, 1) for k, v in max_castle_float.items()}
            milestones["market_trades"] = sim.market_trades
            add_row(
                f"{len(sim.vils)} ({sim.total_pop()})",
                f"{sim.fmt_time(imp_reached_t or t)} – {sim.fmt_time()}",
                "Imperial Age",
                "Train Genoese Crossbowmen + Light Cavalry / Hussars + Trebuchets + Bombard Cannons\nContinue final Imperial upgrades",
                f"Full Imperial composition online ({len(sim.vils)} Vils + {sum(sim.military_units.values())} Military = {sim.total_pop()} Pop): {format_army_counts(sim.military_units).replace('Army: ', '')}. Full upgrades complete (Elite Genoese, Hussar, Bracer, Ballistics, Chemistry, Pavise, Silk Road, Siege Engineers). Pre-click TC idle: {tc_pre_click_idle_s}s; unplanned TC idle: {tc_unplanned_idle_s}s.",
            )
            break

        sim.tick_gather(reseed_reserve_w=house_wood_res)
        if t % 10 == 0:
            record_timeline_point()

    if not record_outputs:
        # Return summary milestones for robustness checking even if loop completed or capped
        milestones.setdefault("housed_seconds", housed_seconds)
        milestones.setdefault("extra_tc_idle_s", tc_unplanned_idle_s)
        milestones.setdefault("feudal_click_s", feudal_click_t)
        milestones.setdefault("castle_click_s", castle_click_t)
        return BuildOrderDocument("", "Italians", variant_label, "", [], []), milestones

    assert imp_reached_t is not None and imp_reached_t < 2400, f"Imperial missed <40:00: {imp_reached_t}"
    assert housed_seconds == 0, f"Housed for {housed_seconds}s"
    assert tc_unplanned_idle_s <= int(rules.max_end_of_age_tc_idle_seconds), f"Unplanned TC idle: {tc_unplanned_idle_s}s"
    assert not sim.negative_bank_events, f"Negative bank events: {sim.negative_bank_events[:3]}"

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
        "Steady-State Target (1 TC Vils + 1 Castle Genoese + 1 Stable Light Cav + Farm Reseed, w/ 10% Castle Buffer)"
        if is_1tc
        else "Steady-State Target (3 TC Vils + 2 Castles Genoese + 2 Stables Light Cav + Farm Reseed, w/ 10% Castle Buffer)"
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
    castle_r_str = str(milestones.get("castle_reached_str", "15:15"))

    if is_1tc:
        castle_steps = [
            RTSOverlayStep(
                villager_count=28, age=3, wood=10, food=9, gold=5, stone=4,
                notes=[
                    f"Click {I['castle_age']}: move 3 Wood/Straggler builders -> {I['gold']}; {I['double_bit_axe']} + {I['horse_collar']}, Farms #3-#5 (from Stragglers/Wood), {I['gold_mining']}, {I['barracks']} -> {I['stable']} #1 (from Wood) & Fletching.",
                    f"Reach {I['castle_age']} ({castle_r_str}, 650+ {I['stone']}): 6 Wood vils build Defensive {I['castle']}, {I['bow_saw']}, continuous 1 {I['town_center']}.",
                ],
            ),
            RTSOverlayStep(
                villager_count=bal_vils, age=3,
                wood=bal_alloc["wood"], food=bal_alloc["food"], gold=bal_alloc["gold"], stone=bal_alloc["stone"],
                notes=[
                    f"Build {I['monastery']} (from Wood/Gold; 2 Monks, 1 Relic = +30G/min) + Genoese & {I['light_cavalry']}; move 2 {I['stone']} vils -> {I['wood']}.",
                    f"At 20+ Genoese: 1 Wood vil builds {I['university']} -> {I['ballistics']} ({bal_str}, -25% Italians) ahead of extra buildings!",
                ],
            ),
            RTSOverlayStep(
                villager_count=imp_c_vils, age=3,
                wood=imp_c_alloc["wood"], food=imp_c_alloc["food"], gold=imp_c_alloc["gold"], stone=imp_c_alloc["stone"],
                notes=[
                    f"At 30+ Army: send 1 Wood/Farm Loom vil forward (60s walk) -> Forward {I['siege_workshop']} & 3-4 {I['battering_ram']}s + Stable #2 (from Wood); stick to 1 {I['town_center']}!",
                    f"Click {I['imperial_age']} ({imp_c_str}, 850F/680G); 3 Wood/Farm vils build {I['town_center']} #2 & #3 after clicking Imp!",
                ],
            ),
            RTSOverlayStep(
                villager_count=fin_vils, age=4,
                wood=end_alloc["wood"], food=end_alloc["food"], gold=end_alloc["gold"], stone=end_alloc["stone"],
                notes=[
                    f"Reach {I['imperial_age']} ({imp_r_str}): Conscription, {I['chemistry']} (-25%), Bracer, Elite Genoese, Hussar, Pavise, Silk Road + {I['bombard_cannon']}s!",
                    f"Anti-Float Rule (8.4): Spend surplus into extra Stables/Castles/upgrades (< 500-1000 float).",
                ],
            ),
        ]
    else:
        castle_steps = [
            RTSOverlayStep(
                villager_count=28, age=3, wood=10, food=9, gold=5, stone=4,
                notes=[
                    f"Click {I['castle_age']}: move 3 Wood/Straggler builders -> {I['gold']}; {I['double_bit_axe']} + {I['horse_collar']}, Farms #3-#5 (from Stragglers/Wood), {I['gold_mining']}, {I['barracks']} -> {I['stable']} #1 (from Wood) & Fletching.",
                    f"Reach {I['castle_age']} ({castle_r_str}, 650+ {I['stone']}): 6 Wood vils build Defensive {I['castle']}, {I['bow_saw']}, continuous {I['town_center']} #1.",
                ],
            ),
            RTSOverlayStep(
                villager_count=42, age=3, wood=14, food=18, gold=6, stone=4,
                notes=[
                    f"Build ~20 Army (13 Genoese + 7 {I['light_cavalry']}) with early upgrades; then PAUSE military & 3 Wood/Farm vils drop {I['town_center']} #2 & #3!",
                    f"Prioritize 3-TC continuous {I['villager']}s, {I['farm']}s (22+) & {I['wheelbarrow']} ({milestones.get('boom3tc_setup_str', '25:00')}).",
                ],
            ),
            RTSOverlayStep(
                villager_count=imp_c_vils, age=3,
                wood=imp_c_alloc["wood"], food=imp_c_alloc["food"], gold=imp_c_alloc["gold"], stone=imp_c_alloc["stone"],
                notes=[
                    f"Maximize Genoese + {I['light_cavalry']}; at 20+ Genoese 1 Wood vil builds {I['university']} -> {I['ballistics']} ({bal_str}, -25%); send 8 Loom Wood/Farm vils forward (60s) for Castle #2/#3, TC #4 & {I['siege_workshop']}!",
                    f"Click {I['imperial_age']} ({imp_c_str}, 850F/680G) well before 40:00.",
                ],
            ),
            RTSOverlayStep(
                villager_count=fin_vils, age=4,
                wood=end_alloc["wood"], food=end_alloc["food"], gold=end_alloc["gold"], stone=end_alloc["stone"],
                notes=[
                    f"Reach {I['imperial_age']} ({imp_r_str}): Conscription, {I['chemistry']} (-25%), Bracer, Elite Genoese, Hussar, Pavise, Silk Road, Siege Engineers + {I['bombard_cannon']}s & {I['trebuchet']}s!",
                ],
            ),
        ]

    rts_steps = [
        RTSOverlayStep(villager_count=6, age=1, wood=0, food=6, gold=0, stone=0, notes=[f"Vils #1-#6: {I['build']} 2 Houses at 0:00, then all 6 on {I['sheep']} under TC."]),
        RTSOverlayStep(villager_count=9, age=1, wood=3, food=6, gold=0, stone=0, notes=[f"Vils #7-#9 (3 vils) -> {I['wood']} (1st vil walks 15s + {I['build']} {I['lumber_camp']} #1)."]),
        RTSOverlayStep(villager_count=11, age=1, wood=4, food=7, gold=0, stone=0, notes=[f"Vil #10 lures 1st {I['boar']} (garrison 7 TC vils 5s on arrival); Vil #11 to {I['wood']} (4 on Wood)."]),
        RTSOverlayStep(villager_count=15, age=1, wood=4, food=11, gold=0, stone=0, notes=[f"Vils #12-#15 (4 vils) -> 6 Chickens on {I['mill']} #1 (Vil #12 builds {I['mill']}, Vil #13 builds House #3). Lure 2nd {I['boar']} before 1st finishes."]),
        RTSOverlayStep(villager_count=19, age=1, wood=4, food=15, gold=0, stone=0, notes=[f"Vils #16-#19 (4 vils) -> {I['berries']} (1st builds {I['mill']} #2, 3rd builds House #4)."]),
        RTSOverlayStep(villager_count=23, age=1, wood=4, food=15, gold=0, stone=4, notes=[f"Vils #20-#23 (4 vils) -> {I['stone']} (1st builds {I['mining_camp']}, 4th builds House #5)."]),
        RTSOverlayStep(villager_count=26, age=1, wood=7, food=15, gold=0, stone=4, notes=[f"Vils #24-#26 (3 vils) -> {I['wood']} (7 on LC #1). Click {I['feudal_age']} (425F); Sheep #8 finishes -> move 1 Sheep vil to {I['wood']} (8 at LC #1), remaining Sheep vils -> Stragglers & move up to 2 Stragglers -> {I['farm']}s."]),
        RTSOverlayStep(villager_count=28, age=2, wood=11, food=11, gold=2, stone=4, notes=[f"In {I['feudal_age']}: Vils #27-#28 -> {I['gold']} (1st builds {I['mining_camp']}); 3 Straggler/Wood vils {I['build']} {I['market']} & 1 builds {I['blacksmith']}.", f"Sell 100 {I['stone']} at {I['market']} (+91G) & click {I['castle_age']} (680F, 170G); move 3 Wood/Straggler builders -> {I['gold']}."]),
        *castle_steps,
    ]

    desc = (
        f"Italians Arena FC (6 Chickens Milled + Berry Mill, Checked w/ 8) — {variant_label}. "
        f"Synced to rules.md (drop-off round trips, 60% wood floor, dynamic Market, real tech/builder times, Italians -25% Univ, late-command check)."
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
        rob = run_late_command_checks(
            strat,
            lambda dfn, chk, _s=strat: run_italians_arena_strategy(_s, delay_fn=dfn, chicken_override=chk, record_outputs=False)[1],
            baseline_clicks={"feudal_click_s": int(ms["feudal_click_s"]), "castle_click_s": int(ms["castle_click_s"])},
            chicken_check_counts=(8,),
        )
        ms["robustness_passed"] = rob["passed"]
        ms["robustness_details"] = rob["details"]
        assert rob["passed"], f"Robustness failed for {strat}: {rob['failures']}"
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
        title="Italians Arena Fast Castle: 1 TC Heavy Army Push vs Balanced 3 TC Boom (6 Chickens Milled, Checked w/ 8)",
        output_path=OUT_DIR / "italians_arena_fc_genoese.html",
    )
    print(f"Wrote HTML report: {html_path}")


if __name__ == "__main__":
    main()

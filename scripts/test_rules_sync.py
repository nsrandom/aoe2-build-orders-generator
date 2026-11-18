#!/usr/bin/env python3
"""Consistency checks asserting `aoe2_data.py`, `simulator.py`, and `backward_planner.py` match `rules.md`."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from aoe2_data import ANIMALS, AoE2Database, MarketState, ResourceBundle, RuleConfig, calc_construction_time
from backward_planner import BackwardPlanner, ContinuousProductionItem
from simulator import BuildOrderSimulator


def main() -> None:
    rules = RuleConfig()
    db = AoE2Database()

    # Rule 1.2 & 1.5
    assert db.get_starting_resources("Generic") == ResourceBundle(food=200, wood=200, gold=100, stone=200)
    assert rules.sheep_discovery_times_s == (90, 150)

    # Rule 2.x walk times
    assert rules.house_walk_time_one_way == 5.0
    assert rules.building_walk_time_one_way == 10.0
    assert rules.camp_or_berry_walk_time_one_way == 15.0
    assert rules.site_to_site_walk_time_one_way == 15.0
    assert rules.tc_food_switch_walk_time == 2.0
    assert rules.farm_walk_time == 2.0
    assert rules.straggler_walk_time == 3.0
    assert rules.forward_walk_time_default == 60.0

    # Rule 3.1 & 3.2 effective gather rates
    assert ANIMALS["chicken"].base_gather_rate == 0.41
    assert ANIMALS["chicken"].carry_capacity == 35.0
    assert abs(db.get_gather_rate("wood") * 60 - 20.4) < 0.1
    assert abs(db.get_gather_rate("gold") * 60 - 20.8) < 0.1
    assert abs(db.get_gather_rate("sheep") * 60 - 18.9) < 0.1
    assert abs(db.get_gather_rate("chicken_mill") * 60 - 23.9) < 0.1
    assert abs(db.get_gather_rate("chicken_ld") * 60 - 18.2) < 0.1

    # Rule 3.4 wood decay floor 60% & mover-only reset
    assert rules.wood_decay_step_seconds == 20.0
    assert rules.wood_efficiency_floor == 0.60
    assert abs(db.get_gather_rate("wood", wood_minutes_since_lc=30.0) - db.get_gather_rate("wood") * 0.60) < 1e-6

    # Rule 7.2 dynamic Market
    m = MarketState.from_rules(rules)
    assert (m.sell_price("wood"), m.sell_price("food"), m.sell_price("stone")) == (70, 81, 91)
    assert (m.buy_price("wood"), m.buy_price("food"), m.buy_price("stone")) == (130, 150, 169)
    assert m.sell("stone", 100) == 91
    assert m.rates["stone"] == 128

    # Rule 9.1 Italians 25% University discount & standard TC 150s (rule 11.3)
    tc_cost, tc_time = db.get_unit_or_building_spec("town center", "Italians", 3)
    assert tc_cost == ResourceBundle(wood=275, stone=100) and tc_time == 150.0
    bal_cost, bal_time = db.get_upgrade_spec("ballistics", "Italians")
    assert bal_cost == ResourceBundle(wood=225, gold=131.25) and bal_time == 60.0
    assert calc_construction_time(25.0, 2) == 18.75

    # Rule 1.3 & 3.8 simulator sheep discovery + deer pushing + mover-only LC reset
    assert rules.default_hunt_variant == "chickens"
    sim = BuildOrderSimulator(civ="Generic", deer_count=2, chicken_count=0)
    assert sim.remaining_animals["sheep"] == 4
    sim.time_s = 90
    sim._process_scheduled_events()
    assert sim.remaining_animals["sheep"] == 6
    sim.time_s = 150
    sim._process_scheduled_events()
    assert sim.remaining_animals["sheep"] == 8

    # Rule 3.10 Mill prerequisite for Horse Collar and Farms
    for fn in (lambda: sim.queue_upgrade("horse collar", 200), lambda: sim.register_new_farm()):
        raised = False
        try:
            fn()
        except ValueError:
            raised = True
        assert raised, "Mill prerequisite must block Horse Collar and Farms before Mill completes"
    sim.add_building("mill", 155)
    sim.time_s = 155
    sim._process_scheduled_events()
    assert sim.has_building("mill")
    sim.queue_upgrade("horse collar", 175)
    sim.register_new_farm()

    # Deer pushing starts at 9 vils on food under TC -> +30s
    for i in range(4, 10):
        sim.vils.append({"id": i, "role": "sheep", "busy_until": 0})
    sim.time_s = 151
    sim._process_scheduled_events()
    assert sim.deer_push_started and sim.next_deer_arrival_s == 181
    sim.time_s = 181
    sim._process_scheduled_events()
    assert sim.remaining_animals["deer"] == 1 and sim.next_deer_arrival_s == 216

    # Wood camp mover-only reset
    sim.add_lumber_camp(120)
    sim.vils.append({"id": 20, "role": "wood", "camp_idx": 0, "busy_until": 0})
    sim.vils.append({"id": 21, "role": "wood", "camp_idx": 0, "busy_until": 0})
    sim.time_s = 920  # 800s elapsed -> 60%
    assert abs(sim.camp_wood_efficiency(0) - 0.60) < 1e-6
    c2 = sim.add_lumber_camp(920)
    sim.reassign_woodcutters_to_new_camp(c2, 1)
    assert abs(sim.camp_wood_efficiency(0) - 0.60) < 1e-6
    assert abs(sim.camp_wood_efficiency(1) - 1.00) < 1e-6

    # BackwardPlanner includes dropoff + macro buffer
    bp = BackwardPlanner(db, rules)
    ss = bp.compute_steady_state_vils([ContinuousProductionItem("villager", 1)], age=3)
    assert ss["gather_rates_per_sec"]["wood"] < 0.34 * 0.91

    # Output rule 2.5: 1 food sub-source omits Total column; >=2 sub-sources includes Total
    import re
    import tempfile
    from exporters import (
        BuildOrderDocument,
        DetailedBuildRow,
        RTSOverlayStep,
        export_build_order_html,
        format_vils_pop_range,
    )

    assert format_vils_pop_range(3, 6, 4, 7, include_start_vil=True) == "3–6 (4–7)"
    assert format_vils_pop_range(22, 34, 24, 42) == "23–34 (24–42)"
    assert format_vils_pop_range(9, 10, 11, 11) == "10 (11)"
    assert format_vils_pop_range(108, 108, 177, 195) == "108 (195)"

    with tempfile.TemporaryDirectory() as tmpd:
        doc = BuildOrderDocument(
            name="Test",
            civilization="Generic",
            variant_label="Test",
            description="Test",
            rows=[
                DetailedBuildRow("6 (7)", "01:15", "Dark Age", "Sheep only", 6, 0, 0, 0, 100, 100, 100, 200, "", sheep_vils=6),
                DetailedBuildRow("30 (31)", "15:00", "Castle Age", "Chickens + Farms", 14, 10, 6, 0, 200, 200, 200, 200, "", chicken_vils=4, farm_vils=10),
            ],
            rts_steps=[RTSOverlayStep(6, 1, 0, 6, 0, 0, ["test"])],
        )
        out_html = export_build_order_html([doc], "Test", Path(tmpd) / "out.html").read_text()
        dark_sec = out_html.split("Dark Age</span>")[1].split("</details>")[0]
        castle_sec = out_html.split("Castle Age</span>")[1].split("</details>")[0]
        assert "Food Villagers Breakdown" not in dark_sec and "Total" not in dark_sec and ">Sheep " in dark_sec
        assert "Food Villagers Breakdown" in castle_sec and "Total" in castle_sec
        assert '<table class="strategy-comp-table">' not in out_html

        # Output rule 2.4: Multi-strategy Strategy Comparison table placed below chart
        doc_a = BuildOrderDocument(
            name="Multi",
            civilization="Generic",
            variant_label="Strat A",
            description="Strat A",
            rows=[
                DetailedBuildRow("19 (20)", "07:05", "Feudal Transition", "Click Feudal Age", 14, 4, 1, 0, 0, 100, 0, 200, "", sheep_vils=14, army_counts={"scout": 1}),
                DetailedBuildRow("19 (23)", "09:15", "Feudal Age", "Reach Feudal Age", 10, 7, 2, 0, 100, 150, 50, 200, "", farm_vils=10, army_counts={"scout": 1, "militia": 3}),
                DetailedBuildRow("37 (41)", "16:45 – 19:25", "Castle Transition", "Reach Castle Age!", 15, 12, 10, 0, 400, 300, 300, 200, "", farm_vils=15, army_counts={"scout": 1, "maa": 3}),
                DetailedBuildRow("38–55 (42–65)", "19:25 – 27:11", "Castle Age", "2-Stable Knights", 25, 16, 14, 0, 200, 200, 200, 200, "", farm_vils=25, army_counts={"scout": 1, "maa": 3, "knight": 27}),
            ],
            rts_steps=[RTSOverlayStep(19, 1, 4, 14, 1, 0, ["test"])],
        )
        doc_b = BuildOrderDocument(
            name="Multi",
            civilization="Generic",
            variant_label="Strat B",
            description="Strat B",
            rows=[
                DetailedBuildRow("21 (22)", "07:55", "Feudal Transition", "Click Feudal Age", 15, 5, 1, 0, 0, 100, 0, 200, "", sheep_vils=15, army_counts={"scout": 1}),
                DetailedBuildRow("21 (22)", "10:05", "Feudal Age", "Queue Vil", 13, 6, 2, 0, 100, 150, 50, 200, "", farm_vils=13, army_counts={"scout": 1}),
                DetailedBuildRow("36 (44)", "19:50", "Castle Age", "Crossbowman", 16, 12, 8, 0, 200, 200, 200, 200, "", farm_vils=16, army_counts={"scout": 1, "archer": 8}),
                DetailedBuildRow("80 (130)", "35:10", "Imperial Age", "Bracer", 38, 22, 20, 0, 400, 400, 400, 200, "", farm_vils=38, army_counts={"crossbow": 40, "knight": 10}),
            ],
            rts_steps=[RTSOverlayStep(21, 1, 5, 15, 1, 0, ["test"])],
        )
        multi_html = export_build_order_html([doc_a, doc_b], "Multi", Path(tmpd) / "multi.html").read_text()
        comp_sec = multi_html.split("strategy-comp-block")[1].split("</details>")[0]
        assert '<table class="strategy-comp-table">' in comp_sec
        assert comp_sec.index('id="strategy-comp-chart"') < comp_sec.index('class="strategy-comp-table"')
        table_html = comp_sec.split('class="strategy-comp-table"')[1]
        assert "09:15" in table_html and "19:25" in table_html and "07:05" not in table_html and "16:45" not in table_html
        assert "3 MAA · 1 Scout" in table_html and "40 Xbows · 10 Knights" in table_html
        assert "&mdash;" in table_html  # Strat A never reached Imperial Age

    # Verify all build generators produce villager ranges for multi-vil rows across all phases,
    # end-of-range resource allocation counts matching the ending villager count, and explicit
    # listing of every eco upgrade researched/granted in the simulation.
    eco_upgrades = (
        "loom",
        "wheelbarrow",
        "hand cart",
        "double-bit axe",
        "bow saw",
        "two-man saw",
        "horse collar",
        "heavy plow",
        "crop rotation",
        "gold mining",
        "gold shaft mining",
        "stone mining",
        "stone shaft mining",
    )
    tracked_upgs: list[str] = []
    last_sim_ref: list[BuildOrderSimulator] = []
    orig_sim_init = BuildOrderSimulator.__init__
    orig_sim_qu = BuildOrderSimulator.queue_upgrade

    def _spy_init(self, *a, **kw):
        last_sim_ref.clear()
        last_sim_ref.append(self)
        return orig_sim_init(self, *a, **kw)

    def _spy_qu(self, name, complete_time):
        tracked_upgs.append(name.lower())
        return orig_sim_qu(self, name, complete_time)

    BuildOrderSimulator.__init__ = _spy_init
    BuildOrderSimulator.queue_upgrade = _spy_qu

    builds_root = Path(__file__).resolve().parent.parent / "builds"
    sys.path.insert(0, str(builds_root / "bohemians_arena_fc_hand_cannons"))
    sys.path.insert(0, str(builds_root / "dravidian_maa_into_archers"))
    sys.path.insert(0, str(builds_root / "italians_arena_fc_genoese"))
    sys.path.insert(0, str(builds_root / "lithuanians_maa_into_knights"))
    from generate_bohemians_arena_fc_hand_cannons import run_bohemians_1tc_fast_hc
    from generate_dravidians_maa import run_dravidians_path
    from generate_italians_arena_fc_genoese import run_italians_arena_strategy
    from generate_lithuanians_maa_into_knights import run_lithuanians_path

    gen_calls = [
        lambda: run_bohemians_1tc_fast_hc(record_outputs=True)[0],
        *(lambda _pk=pk: run_dravidians_path(_pk, _pk, record_outputs=True)[0] for pk in ("1tc_xbow_lc_ram", "1tc_xbow_ls_spear_ram", "3tc_boom_ele_archer")),
        *(lambda _st=st: run_italians_arena_strategy(_st, record_outputs=True)[0] for st in ("1tc_push", "3tc_balanced")),
        *(lambda _pk=pk: run_lithuanians_path(_pk, _pk, record_outputs=True)[0] for pk in ("1tc_fast_push", "1tc_wb_into_3tc")),
    ]
    generated_docs = []
    try:
        for call in gen_calls:
            tracked_upgs.clear()
            gdoc = call()
            generated_docs.append(gdoc)
            sim_inst = last_sim_ref[0]
            all_actions = "\n".join(r.action.lower() for r in gdoc.rows)
            used_eco = set(tracked_upgs) | {u.lower() for u in sim_inst.upgrades}
            for eu in eco_upgrades:
                if eu in used_eco:
                    assert eu in all_actions, (
                        f"Eco upgrade {eu!r} used in simulation of {gdoc.name} ({gdoc.variant_label}) "
                        f"is missing from HTML row actions"
                    )
    finally:
        BuildOrderSimulator.__init__ = orig_sim_init
        BuildOrderSimulator.queue_upgrade = orig_sim_qu
    for gdoc in generated_docs:
        prev_v = 3
        for idx, r in enumerate(gdoc.rows):
            v_end = r.food_vils + r.wood_vils + r.gold_vils + r.stone_vils
            m = re.match(r"^(\d+)(?:–(\d+))?\s*\(", r.pop)
            assert m, f"Unexpected Vils/Pop format {r.pop!r} in {gdoc.name} row {idx}"
            disp_start = int(m.group(1))
            disp_end = int(m.group(2) or m.group(1))
            assert disp_end == v_end, f"Allocation sum {v_end} != end vil {disp_end} in {gdoc.name} row {idx}"
            if idx == 0:
                assert disp_start == 3 and disp_end == v_end
            elif v_end > prev_v + 1:
                assert m.group(2) is not None and disp_start == prev_v + 1, (
                    f"Expected range {prev_v + 1}–{v_end} in {gdoc.name} ({r.age}), got {r.pop!r}"
                )
            else:
                assert m.group(2) is None and disp_start == v_end, (
                    f"Unexpected range {r.pop!r} for delta={v_end - prev_v} in {gdoc.name} ({r.age})"
                )
            prev_v = v_end

    print("ALL RULES SYNC CHECKS PASSED")


if __name__ == "__main__":
    main()

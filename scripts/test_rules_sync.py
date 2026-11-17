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
    import tempfile
    from exporters import BuildOrderDocument, DetailedBuildRow, RTSOverlayStep, export_build_order_html

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

    print("ALL RULES SYNC CHECKS PASSED")


if __name__ == "__main__":
    main()

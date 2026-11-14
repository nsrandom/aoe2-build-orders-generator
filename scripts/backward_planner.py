#!/usr/bin/env python3
"""
Backward Build-Order Planner & Steady-State Resource Solver.

Works backwards from a desired target age / end state:
1. Computes the steady-state villager allocation required to sustain continuous
   unit & villager production at the end state (including farm reseed wood overhead).
2. Computes the lump-sum resource requirements at the end of the age-up transition
   (e.g., Castle drop = 650 stone, immediate eco/unit upgrades, production buildings)
   and solves for the villager allocation needed during the age-up transition window.
3. Computes the pre-click resource budget and minimum population required to click up.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from aoe2_data import AoE2Database, ResourceBundle, RuleConfig


@dataclass
class ContinuousProductionItem:
    unit_name: str
    building_count: int = 1


@dataclass
class AgeTransitionGoal:
    """Specifies what is needed upon reaching `target_age` and during transition."""

    target_age: int  # 2 = Feudal, 3 = Castle, 4 = Imperial
    civ: str = "Generic"
    active_upgrades_during_transition: List[str] = field(default_factory=list)
    active_upgrades_at_end_state: List[str] = field(default_factory=list)
    buildings_during_transition: List[str] = field(default_factory=list)
    buildings_on_age_arrival: List[str] = field(default_factory=list)
    upgrades_on_age_arrival: List[str] = field(default_factory=list)
    units_trained_during_transition: List[Tuple[str, int]] = field(default_factory=list)
    continuous_production: List[ContinuousProductionItem] = field(default_factory=list)
    food_source_end_state: str = "farmer"
    wood_minutes_since_lc: float = 1.0


class BackwardPlanner:
    def __init__(self, db: Optional[AoE2Database] = None, rules: RuleConfig = RuleConfig()) -> None:
        self.db = db or AoE2Database()
        self.rules = rules

    def compute_steady_state_vils(
        self,
        items: Sequence[ContinuousProductionItem],
        civ: str = "Generic",
        age: int = 3,
        upgrades: Sequence[str] = (),
        food_source: str = "farmer",
        wood_minutes_since_lc: float = 1.0,
        include_farm_reseed_wood: bool = True,
    ) -> Dict[str, object]:
        """
        Computes exact fractional and rounded villager counts needed to sustain
        continuous production of `items`.
        """
        total_rate_needed = ResourceBundle()
        per_item_breakdown = []

        for item in items:
            cost, train_time = self.db.get_unit_or_building_spec(
                item.unit_name, civ=civ, age=age
            )
            rate = ResourceBundle(
                food=(cost.food / train_time) * item.building_count,
                wood=(cost.wood / train_time) * item.building_count,
                gold=(cost.gold / train_time) * item.building_count,
                stone=(cost.stone / train_time) * item.building_count,
            )
            total_rate_needed = total_rate_needed + rate
            per_item_breakdown.append(
                {
                    "unit": item.unit_name,
                    "buildings": item.building_count,
                    "cost": cost.to_dict(),
                    "train_time_s": round(train_time, 2),
                    "res_per_sec": {
                        "food": round(rate.food, 3),
                        "wood": round(rate.wood, 3),
                        "gold": round(rate.gold, 3),
                        "stone": round(rate.stone, 3),
                    },
                }
            )

        food_gather = self.db.get_gather_rate(
            food_source, civ=civ, upgrades=upgrades, rules=self.rules
        )
        wood_gather = self.db.get_gather_rate(
            "lumberjack",
            civ=civ,
            upgrades=upgrades,
            wood_minutes_since_lc=wood_minutes_since_lc,
            rules=self.rules,
        )
        gold_gather = self.db.get_gather_rate(
            "gold miner", civ=civ, upgrades=upgrades, rules=self.rules
        )
        stone_gather = self.db.get_gather_rate(
            "stone miner", civ=civ, upgrades=upgrades, rules=self.rules
        )

        exact_food_vils = total_rate_needed.food / food_gather if total_rate_needed.food > 0 else 0.0

        # If farming, calculate wood needed to continuously reseed farms
        reseed_wood_per_sec = 0.0
        if include_farm_reseed_wood and food_source.lower() == "farmer" and exact_food_vils > 0:
            upg_set = {u.lower() for u in upgrades}
            farm_food = 175.0
            if "horse collar" in upg_set:
                farm_food += 75.0
            if "heavy plow" in upg_set:
                farm_food += 125.0
            if "crop rotation" in upg_set:
                farm_food += 175.0
            farm_wood_cost, _ = self.db.get_unit_or_building_spec("farm", civ=civ, age=age)
            reseed_wood_per_sec = total_rate_needed.food * (farm_wood_cost.wood / farm_food)

        total_wood_per_sec = total_rate_needed.wood + reseed_wood_per_sec
        exact_wood_vils = total_wood_per_sec / wood_gather if total_wood_per_sec > 0 else 0.0
        exact_gold_vils = total_rate_needed.gold / gold_gather if total_rate_needed.gold > 0 else 0.0
        exact_stone_vils = total_rate_needed.stone / stone_gather if total_rate_needed.stone > 0 else 0.0

        ceil_vils = {
            "food": math.ceil(exact_food_vils - 1e-6),
            "wood": math.ceil(exact_wood_vils - 1e-6),
            "gold": math.ceil(exact_gold_vils - 1e-6),
            "stone": math.ceil(exact_stone_vils - 1e-6),
        }
        ceil_vils["total"] = sum(ceil_vils.values())

        return {
            "items": per_item_breakdown,
            "rates_per_sec": {
                "food": round(total_rate_needed.food, 3),
                "wood_direct": round(total_rate_needed.wood, 3),
                "wood_farm_reseed": round(reseed_wood_per_sec, 3),
                "wood_total": round(total_wood_per_sec, 3),
                "gold": round(total_rate_needed.gold, 3),
                "stone": round(total_rate_needed.stone, 3),
            },
            "gather_rates_per_sec": {
                "food": round(food_gather, 4),
                "wood": round(wood_gather, 4),
                "gold": round(gold_gather, 4),
                "stone": round(stone_gather, 4),
            },
            "exact_vils": {
                "food": round(exact_food_vils, 2),
                "wood": round(exact_wood_vils, 2),
                "gold": round(exact_gold_vils, 2),
                "stone": round(exact_stone_vils, 2),
                "total": round(
                    exact_food_vils + exact_wood_vils + exact_gold_vils + exact_stone_vils, 2
                ),
            },
            "recommended_vils": ceil_vils,
        }

    def solve_age_transition(self, goal: AgeTransitionGoal) -> Dict[str, object]:
        """
        Works backwards from arrival at `goal.target_age`:
        - Computes total lump resources needed during and immediately upon reaching `target_age`
        - Subtracts any civilization age-up lump bonuses (e.g., Dravidians +200W)
        - Computes the minimum villager seconds and villager counts required during
          the transition window (`130s` Feudal, `160s` Castle).
        """
        age_cost, transition_time, lump_bonus = self.db.get_age_advance_spec(
            goal.target_age, civ=goal.civ
        )

        # Sum costs of buildings/units during transition and immediately on arrival
        needed_on_arrival = ResourceBundle()
        for b_name in goal.buildings_during_transition + goal.buildings_on_age_arrival:
            b_cost, _ = self.db.get_unit_or_building_spec(
                b_name, civ=goal.civ, age=goal.target_age
            )
            needed_on_arrival = needed_on_arrival + b_cost

        for u_name in goal.upgrades_on_age_arrival:
            u_cost, _ = self.db.get_upgrade_spec(u_name, civ=goal.civ)
            needed_on_arrival = needed_on_arrival + u_cost

        for unit_name, count in goal.units_trained_during_transition:
            u_cost, _ = self.db.get_unit_or_building_spec(
                unit_name, civ=goal.civ, age=goal.target_age - 1
            )
            needed_on_arrival = needed_on_arrival + u_cost.scale(count)

        # Also reserve 1 cycle of continuous production upon arrival (e.g. 1 vil + 1 unit)
        first_cycle_buffer = ResourceBundle()
        for item in goal.continuous_production:
            u_cost, _ = self.db.get_unit_or_building_spec(
                item.unit_name, civ=goal.civ, age=goal.target_age
            )
            first_cycle_buffer = first_cycle_buffer + u_cost.scale(item.building_count)

        net_needed_from_gathering = (needed_on_arrival + first_cycle_buffer) - lump_bonus

        steady_state = self.compute_steady_state_vils(
            goal.continuous_production,
            civ=goal.civ,
            age=goal.target_age,
            upgrades=goal.active_upgrades_at_end_state,
            food_source=goal.food_source_end_state,
            wood_minutes_since_lc=goal.wood_minutes_since_lc,
        )

        return {
            "civ": goal.civ,
            "target_age": goal.target_age,
            "age_advance_cost": age_cost.to_dict(),
            "transition_duration_s": transition_time,
            "civ_age_up_lump_bonus": lump_bonus.to_dict(),
            "lump_needed_for_buildings_upgrades_units": needed_on_arrival.to_dict(),
            "first_production_cycle_buffer": first_cycle_buffer.to_dict(),
            "net_resources_to_gather_during_or_before_transition": net_needed_from_gathering.to_dict(),
            "end_state_steady_production": steady_state,
        }


if __name__ == "__main__":
    planner = BackwardPlanner()

    print("=== Example 1: Italians Castle Age -> Castle Drop + 1 TC Vils + 1 Castle Genoese Crossbow ===")
    ex1 = AgeTransitionGoal(
        target_age=3,
        civ="Italians",
        active_upgrades_during_transition=["double-bit axe"],
        active_upgrades_at_end_state=["double-bit axe", "bow saw", "horse collar"],
        buildings_on_age_arrival=["castle"],
        upgrades_on_age_arrival=["bow saw"],
        continuous_production=[
            ContinuousProductionItem("villager", 1),
            ContinuousProductionItem("genoese crossbowman", 1),
        ],
    )
    res1 = planner.solve_age_transition(ex1)
    print(f"  Castle Age Cost (Italians): {res1['age_advance_cost']} ({res1['transition_duration_s']}s)")
    print(f"  Needed on Castle arrival (Castle + Bow Saw + 1st batch): {res1['net_resources_to_gather_during_or_before_transition']}")
    print(f"  Steady-state vils for 1 TC Vils + 1 Castle Genoese Xbow: {res1['end_state_steady_production']['exact_vils']} -> {res1['end_state_steady_production']['recommended_vils']}")

    print("\n=== Example 2: Dravidians Feudal Age -> MAA into Archers + 1 TC Vils ===")
    ex2 = AgeTransitionGoal(
        target_age=2,
        civ="Dravidians",
        active_upgrades_at_end_state=["double-bit axe"],
        buildings_during_transition=["barracks"],
        buildings_on_age_arrival=["archery range", "blacksmith"],
        upgrades_on_age_arrival=["man-at-arms", "double-bit axe", "fletching"],
        units_trained_during_transition=[("militia", 3)],
        continuous_production=[
            ContinuousProductionItem("villager", 1),
            ContinuousProductionItem("archer", 1),
        ],
    )
    res2 = planner.solve_age_transition(ex2)
    print(f"  Feudal Age Cost (Dravidians): {res2['age_advance_cost']} ({res2['transition_duration_s']}s), Lump bonus: {res2['civ_age_up_lump_bonus']}")
    print(f"  Net needed after +200W bonus: {res2['net_resources_to_gather_during_or_before_transition']}")
    print(f"  Steady-state vils for 1 TC Vils + 1 Range Archers: {res2['end_state_steady_production']['exact_vils']} -> {res2['end_state_steady_production']['recommended_vils']}")

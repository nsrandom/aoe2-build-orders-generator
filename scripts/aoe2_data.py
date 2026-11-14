#!/usr/bin/env python3
"""
AoE2:DE Game Data Loader & Mechanics Calculator.

Loads unit, building, technology, gather rate, and civilization bonus data from
`data/` (sourced from PeterWhiteJavascript/aoe2-de-tools) and supplements it
with build-order-specific constants (age-up costs/times, animal decay rates,
and civilization lump/discount bonuses).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class ResourceBundle:
    food: float = 0.0
    wood: float = 0.0
    gold: float = 0.0
    stone: float = 0.0

    def __add__(self, other: "ResourceBundle") -> "ResourceBundle":
        return ResourceBundle(
            food=self.food + other.food,
            wood=self.wood + other.wood,
            gold=self.gold + other.gold,
            stone=self.stone + other.stone,
        )

    def __sub__(self, other: "ResourceBundle") -> "ResourceBundle":
        return ResourceBundle(
            food=self.food - other.food,
            wood=self.wood - other.wood,
            gold=self.gold - other.gold,
            stone=self.stone - other.stone,
        )

    def scale(self, factor: float) -> "ResourceBundle":
        return ResourceBundle(
            food=round(self.food * factor, 2),
            wood=round(self.wood * factor, 2),
            gold=round(self.gold * factor, 2),
            stone=round(self.stone * factor, 2),
        )

    def can_afford(self, cost: "ResourceBundle", eps: float = 1e-6) -> bool:
        return (
            self.food + eps >= cost.food
            and self.wood + eps >= cost.wood
            and self.gold + eps >= cost.gold
            and self.stone + eps >= cost.stone
        )

    def to_dict(self) -> Dict[str, float]:
        return {
            "food": round(self.food, 1),
            "wood": round(self.wood, 1),
            "gold": round(self.gold, 1),
            "stone": round(self.stone, 1),
        }

    def __str__(self) -> str:
        parts = []
        if self.food:
            parts.append(f"{self.food:.0f}F")
        if self.wood:
            parts.append(f"{self.wood:.0f}W")
        if self.gold:
            parts.append(f"{self.gold:.0f}G")
        if self.stone:
            parts.append(f"{self.stone:.0f}S")
        return ", ".join(parts) if parts else "0"


@dataclass(frozen=True)
class AnimalSpec:
    name: str
    initial_food: float
    decay_rate: float  # food lost per second once dead
    base_gather_rate: float  # food gathered per second per villager
    ideal_vils: int
    max_vils: int  # ideal + 2 allowed for short periods


@dataclass(frozen=True)
class RuleConfig:
    """Configurable rules and assumptions corresponding to rules.md."""

    initial_house_return_walk_only: float = 5.0
    house_walk_time_one_way: float = 5.0
    building_walk_time_one_way: float = 10.0
    sequential_building_walk_time: float = 0.0
    boar_lure_walk_time_one_way: float = 15.0
    camp_or_berry_walk_time_one_way: float = 15.0
    farm_walk_time: float = 5.0
    straggler_walk_time: float = 3.0
    wood_decay_step_seconds: float = 20.0  # -1% every 20 seconds (-3% per minute)
    wood_decay_per_step: float = 0.01
    wood_refresh_lc_threshold: float = 0.65  # build new LC when efficiency drops to 60%-65%
    max_lumberjacks_per_lc: int = 8  # add 2nd LC when expanding to 9+ lumberjacks (subject to Wood Priority Rule)
    max_end_of_age_tc_idle_seconds: float = 5.0
    # Assumed Market sell prices (Gold per 100 Food/Wood sold) per rules.md
    market_sell_gold_feudal: int = 70
    market_sell_gold_early_mid_castle: int = 50
    market_sell_gold_late_castle: int = 30
    market_sell_gold_imperial: int = 15


# Standard Animal / Hunt Specs per rules.md & AoE2:DE
ANIMALS: Dict[str, AnimalSpec] = {
    "sheep": AnimalSpec(
        name="sheep",
        initial_food=100.0,
        decay_rate=0.25,
        base_gather_rate=0.33,
        ideal_vils=6,
        max_vils=8,
    ),
    "boar": AnimalSpec(
        name="boar",
        initial_food=340.0,
        decay_rate=0.40,
        base_gather_rate=0.41,
        ideal_vils=7,
        max_vils=9,
    ),
    "deer": AnimalSpec(
        name="deer",
        initial_food=140.0,
        decay_rate=0.25,
        base_gather_rate=0.41,
        ideal_vils=4,
        max_vils=6,
    ),
    "chicken": AnimalSpec(
        name="chicken",
        initial_food=75.0,
        decay_rate=0.125,
        base_gather_rate=0.33,
        ideal_vils=2,
        max_vils=4,
    ),
}

# Age advancement base specifications
AGE_ADVANCE_BASE = {
    2: {"name": "Feudal Age", "cost": ResourceBundle(food=500), "time": 130.0},
    3: {"name": "Castle Age", "cost": ResourceBundle(food=800, gold=200), "time": 160.0},
    4: {"name": "Imperial Age", "cost": ResourceBundle(food=1000, gold=800), "time": 190.0},
}

# Supplemental upgrades not present in aoe2-de-tools combat/eco upgrade list
SUPPLEMENTAL_UPGRADES = {
    "horse collar": {
        "name": "horse collar",
        "ageReq": 2,
        "cost": {"food": 75, "wood": 75},
        "time": 20,
        "effects": {"farmFood": 75},
    },
    "crop rotation": {
        "name": "crop rotation",
        "ageReq": 4,
        "cost": {"food": 250, "wood": 250},
        "time": 70,
        "effects": {"farmFood": 175},
    },
}

# Structured civilization build-order bonuses (supplements ecoBonuses.json & unitVariety.json)
CIV_BUILD_BONUSES = {
    "Generic": {},
    "Italians": {
        "age_up_cost_multiplier": 0.85,  # -15% age advance cost
        "dock_and_university_tech_cost_multiplier": 0.67,
        "fishing_ship_cost_multiplier": 0.85,
    },
    "Dravidians": {
        "on_age_up_lump": {
            2: ResourceBundle(wood=200),
            3: ResourceBundle(wood=200),
            4: ResourceBundle(wood=200),
        },
        "barracks_tech_cost_multiplier": 0.50,  # -50% Barracks tech cost (e.g. MAA = 50F, 20G)
    },
    "Ethiopians": {
        "on_age_up_lump": {
            2: ResourceBundle(food=100, gold=100),
            3: ResourceBundle(food=100, gold=100),
            4: ResourceBundle(food=100, gold=100),
        },
        "free_pikeman": True,
    },
    "Lithuanians": {
        "starting_resource_delta": ResourceBundle(food=100),  # +100F per TC
    },
    "Persians": {
        "starting_resource_delta": ResourceBundle(food=50, wood=50),
        "tc_work_rate_by_age": {1: 1.05, 2: 1.10, 3: 1.15, 4: 1.20},
    },
    "Britons": {
        "gather_rate_multipliers": {"shepherd": 1.25},
        "tc_wood_cost_multiplier_castle": 0.50,
    },
    "Mongols": {
        "gather_rate_multipliers": {"hunter": 1.40},
    },
    "Celts": {
        "gather_rate_multipliers": {"lumberjack": 1.15},
    },
    "Franks": {
        "gather_rate_multipliers": {"forager": 1.15},
        "free_farm_upgrades": True,
    },
    "Malay": {
        "age_up_speed_multiplier": 1.66,  # +66% faster age advancement
    },
}


class AoE2Database:
    """Centralized game data query interface backed by aoe2-de-tools JSON files."""

    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        with open(data_dir / "data.json", "r", encoding="utf-8") as f:
            self.raw_data = json.load(f)
        with open(data_dir / "ecoBonuses.json", "r", encoding="utf-8") as f:
            self.eco_bonuses = json.load(f)
        with open(data_dir / "unitVariety.json", "r", encoding="utf-8") as f:
            self.unit_variety = json.load(f)
        with open(data_dir / "arabia.json", "r", encoding="utf-8") as f:
            self.arabia_map = json.load(f)

        self.units_by_name: Dict[str, dict] = {
            u["name"].lower(): u for u in self.raw_data["units"]
        }
        self.upgrades_by_name: Dict[str, dict] = {
            u["name"].lower(): u for u in self.raw_data["upgrades"]
        }
        for k, v in SUPPLEMENTAL_UPGRADES.items():
            if k not in self.upgrades_by_name:
                self.upgrades_by_name[k] = v

        self.civs_by_name: Dict[str, dict] = {
            c["name"].lower(): c for c in self.raw_data["civilizations"]
        }
        self.base_gathering: Dict[str, dict] = self.units_by_name["villager"]["gathering"]

    def get_starting_resources(self, civ: str = "Generic") -> ResourceBundle:
        sr = self.arabia_map["startingRes"]
        base = ResourceBundle(
            food=float(sr["food"]),
            wood=float(sr["wood"]),
            gold=float(sr["gold"]),
            stone=float(sr["stone"]),
        )
        bonus = CIV_BUILD_BONUSES.get(civ, {}).get("starting_resource_delta")
        if bonus:
            base = base + bonus
        return base

    def get_unit_or_building_spec(
        self, name: str, civ: str = "Generic", age: int = 1
    ) -> Tuple[ResourceBundle, float]:
        """Returns (cost, train_or_build_time_seconds) for any unit or building."""
        key = name.lower()
        if key not in self.units_by_name:
            raise KeyError(f"Unknown unit or building: {name}")
        entry = self.units_by_name[key]
        cost_dict = dict(entry.get("cost", {}))
        train_time = float(entry.get("trainTime", 0.0))

        # Check unitVariety.json for civ-specific cost/trainTime modifiers
        age_names = {1: "Dark Age", 2: "Feudal Age", 3: "Castle Age", 4: "Imperial Age"}
        variety = self.unit_variety.get(key, {}).get("civs", {})
        for v_key, v_mod in variety.items():
            if v_key.startswith(civ):
                if " - " in v_key and not v_key.endswith(age_names.get(age, "")):
                    continue
                if "cost" in v_mod:
                    for res_type, mod_val in v_mod["cost"].items():
                        if v_mod.get("costPercent"):
                            cost_dict[res_type] = cost_dict.get(res_type, 0) * (1.0 - float(mod_val))
                        else:
                            cost_dict[res_type] = cost_dict.get(res_type, 0) + float(mod_val)
                if "trainTime" in v_mod:
                    if v_mod.get("trainTimePercent"):
                        train_time = train_time / float(v_mod["trainTime"])
                    else:
                        train_time = float(v_mod["trainTime"])

        cost = ResourceBundle(
            food=float(cost_dict.get("food", 0.0)),
            wood=float(cost_dict.get("wood", 0.0)),
            gold=float(cost_dict.get("gold", 0.0)),
            stone=float(cost_dict.get("stone", 0.0)),
        )
        return cost, train_time

    def get_upgrade_spec(self, name: str, civ: str = "Generic") -> Tuple[ResourceBundle, float]:
        """Returns (cost, research_time_seconds) for an upgrade/technology."""
        key = name.lower()
        if key not in self.upgrades_by_name:
            raise KeyError(f"Unknown upgrade: {name}")
        entry = self.upgrades_by_name[key]
        cost_dict = dict(entry.get("cost", {}))
        res_time = float(entry.get("time", 0.0))

        cost = ResourceBundle(
            food=float(cost_dict.get("food", 0.0)),
            wood=float(cost_dict.get("wood", 0.0)),
            gold=float(cost_dict.get("gold", 0.0)),
            stone=float(cost_dict.get("stone", 0.0)),
        )

        civ_bonus = CIV_BUILD_BONUSES.get(civ, {})
        barracks_techs = {"man-at-arms", "long swordsman", "two-handed swordsman", "champion", "pikeman", "halberdier", "supplies", "gambesons", "squires", "arson"}
        if key in barracks_techs and "barracks_tech_cost_multiplier" in civ_bonus:
            cost = cost.scale(civ_bonus["barracks_tech_cost_multiplier"])

        university_and_dock_techs = {
            "ballistics", "chemistry", "masonry", "architecture", "murder holes",
            "treadmill crane", "fortified wall", "guard tower", "keep", "bombard tower",
            "siege engineers", "heated shot", "arrowslits", "careening", "dry dock",
            "shipwright", "gillnets", "war galley", "galleon", "fast fire ship",
            "heavy demolition ship", "cannon galleon", "elite cannon galleon",
        }
        if key in university_and_dock_techs and "dock_and_university_tech_cost_multiplier" in civ_bonus:
            cost = cost.scale(civ_bonus["dock_and_university_tech_cost_multiplier"])

        return cost, res_time

    def get_age_advance_spec(
        self, target_age: int, civ: str = "Generic"
    ) -> Tuple[ResourceBundle, float, ResourceBundle]:
        """Returns (cost, research_time_s, lump_bonus_on_completion) for advancing to target_age."""
        base = AGE_ADVANCE_BASE[target_age]
        cost: ResourceBundle = base["cost"]
        res_time: float = base["time"]

        civ_bonus = CIV_BUILD_BONUSES.get(civ, {})
        if "age_up_cost_multiplier" in civ_bonus:
            cost = cost.scale(civ_bonus["age_up_cost_multiplier"])
        if "age_up_speed_multiplier" in civ_bonus:
            res_time = round(res_time / civ_bonus["age_up_speed_multiplier"], 2)

        lump = civ_bonus.get("on_age_up_lump", {}).get(target_age, ResourceBundle())
        return cost, res_time, lump

    def get_gather_rate(
        self,
        role: str,
        civ: str = "Generic",
        upgrades: Sequence[str] = (),
        wood_minutes_since_lc: float = 0.0,
        rules: RuleConfig = RuleConfig(),
    ) -> float:
        """
        Computes effective gather rate (res/sec) for a villager role, accounting for:
        - Base gather rate from aoe2-de-tools
        - Active economy upgrades (double-bit axe, bow saw, wheelbarrow, heavy plow, etc.)
        - Civilization gather rate bonuses
        - Wood cutting efficiency decay (-5% per minute since last Lumber Camp)
        """
        upg_set = {u.lower() for u in upgrades}
        role_key = role.lower()

        if role_key == "farmer":
            if "hand cart" in upg_set:
                rate = 24.0 / 60.0
            elif "wheelbarrow" in upg_set and "heavy plow" in upg_set:
                rate = 23.16 / 60.0
            elif "wheelbarrow" in upg_set:
                rate = 23.03 / 60.0
            elif "heavy plow" in upg_set:
                rate = 21.2 / 60.0
            else:
                rate = float(self.base_gathering["farmer"]["gatherRate"])
        elif role_key in ("lumberjack", "wood"):
            rate = float(self.base_gathering["lumberjack"]["gatherRate"])
            if "double-bit axe" in upg_set:
                rate *= 1.20
            if "bow saw" in upg_set:
                rate *= 1.20
            if "two-man saw" in upg_set:
                rate *= 1.10
            # Apply wood cutting efficiency drop (-1% every 12 seconds since last LC)
            if wood_minutes_since_lc > 0:
                seconds_since_lc = wood_minutes_since_lc * 60.0
                steps = int(seconds_since_lc // rules.wood_decay_step_seconds)
                decay_mult = max(0.20, 1.0 - rules.wood_decay_per_step * steps)
                rate *= decay_mult
        elif role_key == "straggler":
            # Straggler trees around TC do not suffer treeline recession
            rate = float(self.base_gathering["lumberjack"]["gatherRate"])
        elif role_key == "long_distance_gold":
            # 10 gold capacity at base gather rate + 15s walk each way (30s round trip)
            base_r = float(self.base_gathering["gold miner"]["gatherRate"])
            gather_time = 10.0 / base_r
            rate = 10.0 / (gather_time + 2.0 * rules.camp_or_berry_walk_time_one_way)
        elif role_key == "long_distance_stone":
            base_r = float(self.base_gathering["stone miner"]["gatherRate"])
            gather_time = 10.0 / base_r
            rate = 10.0 / (gather_time + 2.0 * rules.camp_or_berry_walk_time_one_way)
        elif role_key in ("gold miner", "gold"):
            rate = float(self.base_gathering["gold miner"]["gatherRate"])
            if "gold mining" in upg_set:
                rate *= 1.15
            if "gold shaft mining" in upg_set:
                rate *= 1.15
        elif role_key in ("stone miner", "stone"):
            rate = float(self.base_gathering["stone miner"]["gatherRate"])
            if "stone mining" in upg_set:
                rate *= 1.15
            if "stone shaft mining" in upg_set:
                rate *= 1.15
        elif role_key in ("shepherd", "sheep"):
            rate = float(self.base_gathering["shepherd"]["gatherRate"])
        elif role_key in ("hunter", "boar", "deer"):
            rate = float(self.base_gathering["hunter"]["gatherRate"])
        elif role_key == "chicken":
            rate = ANIMALS["chicken"].base_gather_rate
        elif role_key in ("forager", "berries"):
            rate = float(self.base_gathering["forager"]["gatherRate"])
        else:
            raise KeyError(f"Unknown gatherer role: {role}")

        # Apply civ gather rate multiplier if present
        civ_mults = CIV_BUILD_BONUSES.get(civ, {}).get("gather_rate_multipliers", {})
        canonical = {
            "sheep": "shepherd",
            "boar": "hunter",
            "deer": "hunter",
            "wood": "lumberjack",
            "berries": "forager",
            "gold": "gold miner",
            "stone": "stone miner",
        }.get(role_key, role_key)
        if canonical in civ_mults:
            rate *= civ_mults[canonical]

        return rate

    def calc_animal_harvest(
        self, animal_type: str, num_vils: int, civ: str = "Generic"
    ) -> Dict[str, float]:
        """
        Computes the exact harvest duration, net food collected, and rot lost
        when `num_vils` harvest a single carcass of `animal_type`.
        """
        spec = ANIMALS[animal_type.lower()]
        gather_rate = self.get_gather_rate(animal_type.lower(), civ=civ)
        total_gather_rate = num_vils * gather_rate
        depletion_rate = total_gather_rate + spec.decay_rate
        duration = spec.initial_food / depletion_rate
        net_food = total_gather_rate * duration
        rot_food = spec.decay_rate * duration
        return {
            "animal": spec.name,
            "num_vils": num_vils,
            "initial_food": spec.initial_food,
            "duration_s": round(duration, 2),
            "net_food": round(net_food, 2),
            "rot_food": round(rot_food, 2),
            "efficiency_pct": round(100.0 * net_food / spec.initial_food, 1),
            "within_ideal": num_vils <= spec.ideal_vils,
            "within_max": num_vils <= spec.max_vils,
        }


def calc_construction_time(base_time: float, num_builders: int = 1) -> float:
    """AoE2:DE multi-villager construction formula: T = 3 * t / (n + 2)."""
    if num_builders < 1:
        raise ValueError("num_builders must be >= 1")
    return (3.0 * base_time) / (num_builders + 2)


if __name__ == "__main__":
    db = AoE2Database()
    print("=== Sample Loaded Game Data ===")
    print("Italians Feudal Advance:", db.get_age_advance_spec(2, "Italians"))
    print("Italians Castle Advance:", db.get_age_advance_spec(3, "Italians"))
    print("Dravidians Feudal Advance:", db.get_age_advance_spec(2, "Dravidians"))
    print("Dravidians MAA Upgrade:", db.get_upgrade_spec("man-at-arms", "Dravidians"))
    print("Genoese Crossbowman:", db.get_unit_or_building_spec("genoese crossbowman", "Italians", 3))
    print("\n=== Animal Decay Table at Ideal Villager Counts ===")
    for anim_name, spec in ANIMALS.items():
        res = db.calc_animal_harvest(anim_name, spec.ideal_vils)
        print(f"  {anim_name.capitalize():8s} ({spec.ideal_vils} vils): {res['net_food']}F collected, {res['rot_food']}F rotted over {res['duration_s']}s ({res['efficiency_pct']}%)")

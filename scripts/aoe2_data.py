#!/usr/bin/env python3
"""
AoE2:DE Game Data Loader & Mechanics Calculator.

Loads unit, building, technology, gather rate, and civilization bonus data from
`data/` (sourced from PeterWhiteJavascript/aoe2-de-tools) and pairs it with
the project's `RuleConfig` and data tables matching `rules.md`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _round_half_up(x: float) -> int:
    return int(x + 0.5)


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
    decay_rate: float  # food lost per second once dead (rule 3.5)
    base_gather_rate: float  # raw food/sec per villager (rule 11.1)
    carry_capacity: float  # hunter carry 35, shepherd carry 10 (rule 11.1)
    ideal_vils: int  # rule 3.6
    max_vils: int  # rule 3.6


@dataclass(frozen=True)
class RuleConfig:
    """Authoritative machine-readable parameters matching `rules.md`."""

    # Walking & setup (rules 1.5, 2.x)
    initial_house_return_walk_only: float = 5.0  # rule 1.5
    house_walk_time_one_way: float = 5.0  # rule 2.1
    building_walk_time_one_way: float = 10.0  # rule 2.2
    sequential_building_walk_time: float = 0.0  # rule 2.3
    camp_or_berry_walk_time_one_way: float = 15.0  # rule 2.4
    site_to_site_walk_time_one_way: float = 15.0  # rule 2.6
    tc_food_switch_walk_time: float = 2.0  # rule 2.7
    farm_walk_time: float = 2.0  # rule 2.7 (around TC)
    straggler_walk_time: float = 3.0  # rule 2.8
    boar_lure_walk_time_one_way: float = 15.0  # rule 2.9
    forward_walk_time_default: float = 60.0  # rule 2.10
    villager_base_speed: float = 0.8  # rule 2.11 (tiles/s)

    # Map resources & scouting timings (rules 1.3, 1.4, 3.8, 3.9)
    default_hunt_variant: str = "chickens"  # rule 1.3 & 3.9
    arabia_deer_count: int = 2  # rule 1.3 (deer-map design target)
    arena_deer_count: int = 3  # rule 1.4 (deer-map design target)
    arabia_chicken_design_count: int = 6  # rule 1.3
    arabia_chicken_check_count: int = 8  # rule 1.3
    arena_chicken_design_count: int = 6  # rule 1.4
    arena_chicken_count: int = 8  # rule 1.4 (chicken-map actual/check count)
    sheep_initial_near_tc: int = 4  # rule 1.3
    sheep_discovery_times_s: Tuple[int, ...] = (90, 150)  # rule 1.3: +2 at 1:30, +2 at 2:30
    deer_push_min_food_vils: int = 9  # rule 3.8
    deer_push_first_delay_s: int = 30  # rule 3.8
    deer_push_interval_s: int = 35  # rule 3.8

    # Boar shooting (rule 3.7)
    boar_garrison_vils: int = 7  # rule 3.7 (6-8 vils garrison in TC)
    boar_garrison_seconds: float = 5.0  # rule 3.7
    open_next_animal_before_empty_s: float = 2.0  # rule 3.6

    # Drop-off round-trip times in seconds (rule 3.2)
    dropoff_round_trips: Dict[str, float] = field(
        default_factory=lambda: {
            "sheep": 1.5,
            "shepherd": 1.5,
            "boar": 1.5,
            "deer": 1.5,
            "hunter": 1.5,
            "deer_mill": 3.0,
            "chicken": 2.5,
            "chicken_mill": 2.5,
            "chicken_ld": 30.0,
            "berries": 2.5,
            "forager": 2.5,
            "wood": 3.75,
            "lumberjack": 3.75,
            "straggler": 2.5,
            "gold": 2.5,
            "gold miner": 2.5,
            "stone": 2.5,
            "stone miner": 2.5,
            "gold_ld": 30.0,
            "long_distance_gold": 30.0,
            "stone_ld": 30.0,
            "long_distance_stone": 30.0,
        }
    )

    # Wood efficiency decay & camp refresh (rule 3.4)
    wood_decay_step_seconds: float = 20.0  # rule 3.4: -1% every 20s (-3%/min)
    wood_decay_per_step: float = 0.01  # rule 3.4
    wood_efficiency_floor: float = 0.60  # rule 3.4
    wood_refresh_lc_threshold: float = 0.65  # rule 3.4
    max_lumberjacks_per_lc: int = 8  # rule 3.4

    # Farms & Population / TC (rules 3.10, 4.4, 5.1)
    tc_farms_ring_capacity: int = 8  # rule 3.10
    house_room_buffer: int = 3  # rule 4.4 (2-3 vils room at completion)
    max_end_of_age_tc_idle_seconds: float = 5.0  # rule 5.1, 5.3

    # Relics & Market (rules 7.2, 7.3)
    relic_gold_per_sec: float = 0.50  # rule 7.3
    market_base_rates: Dict[str, int] = field(
        default_factory=lambda: {"wood": 100, "food": 115, "stone": 130}
    )  # rule 7.2
    market_fee: float = 0.30  # rule 7.2
    market_rate_step: int = 2  # rule 7.2
    market_min_rate: int = 20  # rule 7.2
    market_max_rate: int = 9999  # rule 7.2

    # Macro efficiency & late-command robustness (rules 8.2, 8.3)
    feudal_macro_efficiency: float = 0.92  # rule 8.2
    castle_macro_efficiency: float = 0.90  # rule 8.2
    robustness_fixed_delay_s: int = 3  # rule 8.3
    robustness_random_runs: int = 20  # rule 8.3
    robustness_random_max_delay_s: int = 5  # rule 8.3
    robustness_max_click_delay_s: int = 15  # rule 8.3


@dataclass
class MarketState:
    """Dynamic AoE2:DE Market price tracker matching rule 7.2."""

    rates: Dict[str, int] = field(
        default_factory=lambda: {"wood": 100, "food": 115, "stone": 130}
    )
    fee: float = 0.30
    step: int = 2
    min_rate: int = 20
    max_rate: int = 9999

    @classmethod
    def from_rules(cls, rules: RuleConfig, fee: Optional[float] = None) -> "MarketState":
        return cls(
            rates=dict(rules.market_base_rates),
            fee=rules.market_fee if fee is None else fee,
            step=rules.market_rate_step,
            min_rate=rules.market_min_rate,
            max_rate=rules.market_max_rate,
        )

    def sell_price(self, resource: str) -> int:
        key = resource.lower()
        return _round_half_up(self.rates[key] * (1.0 - self.fee))

    def buy_price(self, resource: str) -> int:
        key = resource.lower()
        return _round_half_up(self.rates[key] * (1.0 + self.fee))

    def sell(self, resource: str, amount: int = 100) -> int:
        if amount <= 0 or amount % 100 != 0:
            raise ValueError("Market trade amount must be a positive multiple of 100.")
        key = resource.lower()
        if key not in self.rates:
            raise ValueError(f"Unsupported market commodity: {resource}")
        gold_total = 0
        for _ in range(amount // 100):
            gold_total += self.sell_price(key)
            self.rates[key] = max(self.min_rate, self.rates[key] - self.step)
        return gold_total

    def buy(self, resource: str, amount: int = 100) -> int:
        if amount <= 0 or amount % 100 != 0:
            raise ValueError("Market trade amount must be a positive multiple of 100.")
        key = resource.lower()
        if key not in self.rates:
            raise ValueError(f"Unsupported market commodity: {resource}")
        gold_cost = 0
        for _ in range(amount // 100):
            gold_cost += self.buy_price(key)
            self.rates[key] = min(self.max_rate, self.rates[key] + self.step)
        return gold_cost


# Standard Animal / Hunt Specs per rules.md §3.1, §3.5, §3.6, §11.2
ANIMALS: Dict[str, AnimalSpec] = {
    "sheep": AnimalSpec(
        name="sheep",
        initial_food=100.0,
        decay_rate=0.25,
        base_gather_rate=0.33,
        carry_capacity=10.0,
        ideal_vils=6,
        max_vils=7,
    ),
    "boar": AnimalSpec(
        name="boar",
        initial_food=340.0,
        decay_rate=0.40,
        base_gather_rate=0.41,
        carry_capacity=35.0,
        ideal_vils=8,
        max_vils=9,  # up to 10 allowed during age-up transition phases (rule 3.6)
    ),
    "deer": AnimalSpec(
        name="deer",
        initial_food=140.0,
        decay_rate=0.25,
        base_gather_rate=0.41,
        carry_capacity=35.0,
        ideal_vils=4,
        max_vils=7,
    ),
    "chicken": AnimalSpec(
        name="chicken",
        initial_food=75.0,
        decay_rate=0.125,
        base_gather_rate=0.41,  # rule 3.1: wild chickens are huntables (0.41/s, carry 35)
        carry_capacity=35.0,
        ideal_vils=2,
        max_vils=4,
    ),
}

# Age advancement base specifications (rule 11.4)
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
        "dock_and_university_tech_cost_multiplier": 0.75,  # -25% since Update 169123
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
        "starting_resource_delta": ResourceBundle(food=100),  # +100F per TC (Update 81058)
        "extra_tc_food_bonus": 100.0,  # +100F per additional TC completed (Update 81058)
        "monastery_work_rate_multiplier": 1.20,  # Team Bonus: Monasteries work 20% faster
        "relic_knight_attack_cap": 4,  # +1 attack to Knights/Leitis per Relic, max +4
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
    "Aztecs": {
        "carry_delta": 3.0,
    },
    "Goths": {
        "hunter_carry_delta": 15.0,
        "hunt_food_multiplier": 1.20,
    },
    "Bohemians": {
        # Update 61321: -100W applies to Blacksmith & University only (Monastery discount removed).
        "building_wood_deltas": {"blacksmith": -100.0, "university": -100.0},
        # Mining Camp upgrades are free upon reaching the respective age.
        "free_mining_camp_upgrades_by_age": {
            2: ("gold mining", "stone mining"),
            3: ("gold shaft mining", "stone shaft mining"),
        },
        "castle_age_chemistry": True,
        "monastery_techs_affect_villagers": ("fervor", "sanctity"),
        "spearman_bonus_damage_multiplier": 1.25,
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

        # data.json carries 270s (Cuman Feudal TC) on Town Center; standard TC is 150s (rule 11.3)
        if key == "town center":
            train_time = 150.0

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

        # Apply civ-specific building wood discounts (e.g., Bohemians -100W Blacksmith/University)
        w_deltas = CIV_BUILD_BONUSES.get(civ, {}).get("building_wood_deltas", {})
        if key in w_deltas:
            cost_dict["wood"] = max(0.0, float(cost_dict.get("wood", 0.0)) + float(w_deltas[key]))

        # Apply civ-specific Monastery work-rate multiplier (e.g., Lithuanians +20% faster Monasteries)
        monastery_mult = CIV_BUILD_BONUSES.get(civ, {}).get("monastery_work_rate_multiplier")
        if monastery_mult and key == "monk":
            train_time = train_time / float(monastery_mult)

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

        # Apply civ-specific building wood discounts (e.g., Bohemians -100W Blacksmith/University)
        w_deltas = CIV_BUILD_BONUSES.get(civ, {}).get("building_wood_deltas", {})
        if key in w_deltas:
            cost_dict["wood"] = max(0.0, float(cost_dict.get("wood", 0.0)) + float(w_deltas[key]))

        # Apply civ-specific Monastery work-rate multiplier (e.g., Lithuanians +20% faster Monasteries)
        monastery_mult = CIV_BUILD_BONUSES.get(civ, {}).get("monastery_work_rate_multiplier")
        if monastery_mult and key == "monk":
            train_time = train_time / float(monastery_mult)

        cost = ResourceBundle(
            food=float(cost_dict.get("food", 0.0)),
            wood=float(cost_dict.get("wood", 0.0)),
            gold=float(cost_dict.get("gold", 0.0)),
            stone=float(cost_dict.get("stone", 0.0)),
        )

        civ_bonus = CIV_BUILD_BONUSES.get(civ, {})
        barracks_techs = {
            "man-at-arms", "long swordsman", "two-handed swordsman", "champion",
            "pikeman", "halberdier", "supplies", "gambesons", "squires", "arson",
        }
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

        monastery_techs = {
            "devotion", "faith", "redemption", "illumination", "atonement",
            "block printing", "herbal medicine", "theocracy", "heresy",
            "sanctity", "fervor",
        }
        if key in monastery_techs and "monastery_work_rate_multiplier" in civ_bonus:
            res_time = res_time / float(civ_bonus["monastery_work_rate_multiplier"])

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

    def get_carry_capacity(
        self, role: str, civ: str = "Generic", upgrades: Sequence[str] = ()
    ) -> float:
        """Carry capacity per role with civ bonuses, Wheelbarrow (+27%), Hand Cart (+50% on WB), Heavy Plow (+1 farmer)."""
        upg_set = {u.lower() for u in upgrades}
        role_key = role.lower()
        is_hunter = role_key in ("hunter", "boar", "deer", "deer_mill", "chicken", "chicken_mill", "chicken_ld")
        base_carry = 35.0 if is_hunter else 10.0

        civ_bonus = CIV_BUILD_BONUSES.get(civ, {})
        base_carry += float(civ_bonus.get("carry_delta", 0.0))
        if is_hunter:
            base_carry += float(civ_bonus.get("hunter_carry_delta", 0.0))

        carry = base_carry
        if "wheelbarrow" in upg_set:
            carry = float(round(carry * 1.2695))
        if "hand cart" in upg_set:
            carry = float(round(carry * 1.5))
        if role_key == "farmer" and "heavy plow" in upg_set:
            carry += 1.0
        return carry

    def get_gather_rate(
        self,
        role: str,
        civ: str = "Generic",
        upgrades: Sequence[str] = (),
        wood_minutes_since_lc: float = 0.0,
        rules: RuleConfig = RuleConfig(),
        include_dropoff: bool = True,
        wood_efficiency_override: Optional[float] = None,
    ) -> float:
        """
        Computes gather rate (res/sec) for a villager role, accounting for:
        - Base work rate from aoe2-de-tools (and rule 3.1/11.1 for chickens)
        - Active economy upgrades (Double-Bit Axe, Bow Saw, Two-Man Saw, Gold/Stone Mining, Farmer upgrades)
        - Civilization gather rate bonuses
        - Drop-off round-trip time (rule 3.2: carry / (carry / raw_rate + round_trip)), shortened by WB/HC speed (rule 2.11)
        - Wood cutting efficiency decay (-1% every 20s since last LC, floor 60%; rule 3.4)
        """
        upg_set = {u.lower() for u in upgrades}
        role_key = role.lower()

        # Farm rates in §11.1 already include standard farm walking (rule 3.2)
        if role_key == "farmer":
            if "hand cart" in upg_set:
                return 24.0 / 60.0
            if "wheelbarrow" in upg_set and "heavy plow" in upg_set:
                return 23.16 / 60.0
            if "wheelbarrow" in upg_set:
                return 23.03 / 60.0
            if "heavy plow" in upg_set:
                return 21.2 / 60.0
            return float(self.base_gathering["farmer"]["gatherRate"])

        is_wood_lc = role_key in ("lumberjack", "wood")
        if is_wood_lc or role_key == "straggler":
            raw_rate = float(self.base_gathering["lumberjack"]["gatherRate"])
            if "double-bit axe" in upg_set:
                raw_rate *= 1.20
            if "bow saw" in upg_set:
                raw_rate *= 1.20
            if "two-man saw" in upg_set:
                raw_rate *= 1.10
        elif role_key in ("gold miner", "gold", "long_distance_gold", "gold_ld"):
            raw_rate = float(self.base_gathering["gold miner"]["gatherRate"])
            if "gold mining" in upg_set:
                raw_rate *= 1.15
            if "gold shaft mining" in upg_set:
                raw_rate *= 1.15
        elif role_key in ("stone miner", "stone", "long_distance_stone", "stone_ld"):
            raw_rate = float(self.base_gathering["stone miner"]["gatherRate"])
            if "stone mining" in upg_set:
                raw_rate *= 1.15
            if "stone shaft mining" in upg_set:
                raw_rate *= 1.15
        elif role_key in ("shepherd", "sheep"):
            raw_rate = float(self.base_gathering["shepherd"]["gatherRate"])
        elif role_key in ("hunter", "boar", "deer", "deer_mill", "chicken", "chicken_mill", "chicken_ld"):
            raw_rate = ANIMALS["chicken"].base_gather_rate if "chicken" in role_key else float(self.base_gathering["hunter"]["gatherRate"])
        elif role_key in ("forager", "berries"):
            raw_rate = float(self.base_gathering["forager"]["gatherRate"])
        else:
            raise KeyError(f"Unknown gatherer role: {role}")

        # Apply civ raw gather rate multiplier before drop-off walking
        civ_mults = CIV_BUILD_BONUSES.get(civ, {}).get("gather_rate_multipliers", {})
        canonical = {
            "sheep": "shepherd",
            "boar": "hunter",
            "deer": "hunter",
            "deer_mill": "hunter",
            "chicken": "hunter",
            "chicken_mill": "hunter",
            "chicken_ld": "hunter",
            "wood": "lumberjack",
            "straggler": "lumberjack",
            "berries": "forager",
            "gold": "gold miner",
            "long_distance_gold": "gold miner",
            "gold_ld": "gold miner",
            "stone": "stone miner",
            "long_distance_stone": "stone miner",
            "stone_ld": "stone miner",
        }.get(role_key, role_key)
        if canonical in civ_mults:
            raw_rate *= civ_mults[canonical]

        # Apply drop-off round trip (rule 3.2) and WB/HC villager speed bonus (rule 2.11)
        rate = raw_rate
        round_trip = rules.dropoff_round_trips.get(role_key, 0.0)
        if include_dropoff and round_trip > 0.0:
            speed_mult = 1.0
            if "wheelbarrow" in upg_set:
                speed_mult *= 1.10
            if "hand cart" in upg_set:
                speed_mult *= 1.10
            if civ == "Bohemians" and "fervor" in upg_set:
                speed_mult *= 1.15
            eff_rt = round_trip / speed_mult
            carry = self.get_carry_capacity(role_key, civ=civ, upgrades=upgrades)
            rate = carry / ((carry / raw_rate) + eff_rt)

        # Apply wood cutting efficiency decay (-1% every 20s since last LC, floor 60%; rule 3.4)
        if is_wood_lc:
            if wood_efficiency_override is not None:
                rate *= max(rules.wood_efficiency_floor, wood_efficiency_override)
            elif wood_minutes_since_lc > 0:
                seconds_since_lc = wood_minutes_since_lc * 60.0
                steps = int(seconds_since_lc // rules.wood_decay_step_seconds)
                decay_mult = max(
                    rules.wood_efficiency_floor, 1.0 - rules.wood_decay_per_step * steps
                )
                rate *= decay_mult

        return rate

    def calc_animal_harvest(
        self,
        animal_type: str,
        num_vils: int,
        civ: str = "Generic",
        include_dropoff: bool = True,
    ) -> Dict[str, float]:
        """
        Computes harvest duration, net food collected, and rot lost when
        `num_vils` harvest a single carcass of `animal_type`.
        """
        spec = ANIMALS[animal_type.lower()]
        gather_rate = self.get_gather_rate(
            animal_type.lower(), civ=civ, include_dropoff=include_dropoff
        )
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


def get_farm_capacity(upgrades: Sequence[str] = ()) -> float:
    """Farm food pool given active Mill upgrades (rule 3.10)."""
    upg_set = {u.lower() for u in upgrades}
    food = 175.0
    if "horse collar" in upg_set:
        food += 75.0
    if "heavy plow" in upg_set:
        food += 125.0
    if "crop rotation" in upg_set:
        food += 175.0
    return food


def calc_construction_time(base_time: float, num_builders: int = 1) -> float:
    """AoE2:DE multi-villager construction formula: T = 3 * t / (n + 2) (rule 4.1)."""
    if num_builders < 1:
        raise ValueError("num_builders must be >= 1")
    return (3.0 * base_time) / (num_builders + 2)


if __name__ == "__main__":
    db = AoE2Database()
    print("=== Sample Loaded Game Data ===")
    print("Italians Feudal Advance:", db.get_age_advance_spec(2, "Italians"))
    print("Italians Castle Advance:", db.get_age_advance_spec(3, "Italians"))
    print("Italians Ballistics:", db.get_upgrade_spec("ballistics", "Italians"))
    print("Dravidians Feudal Advance:", db.get_age_advance_spec(2, "Dravidians"))
    print("Dravidians MAA Upgrade:", db.get_upgrade_spec("man-at-arms", "Dravidians"))
    print("Genoese Crossbowman:", db.get_unit_or_building_spec("genoese crossbowman", "Italians", 3))
    print("\n=== Effective Gather Rates (per min, rule 3.2) ===")
    for role in ("sheep", "boar", "deer", "chicken_mill", "chicken_ld", "berries", "wood", "straggler", "gold", "gold_ld", "stone"):
        r = db.get_gather_rate(role)
        print(f"  {role:12s}: {r:.4f}/s ({r*60:.1f}/min)")
    print("\n=== Animal Decay Table at Ideal Villager Counts (under TC / milled) ===")
    for anim_name, spec in ANIMALS.items():
        res = db.calc_animal_harvest(anim_name, spec.ideal_vils, include_dropoff=True)
        print(f"  {anim_name.capitalize():8s} ({spec.ideal_vils} vils): {res['net_food']}F collected, {res['rot_food']}F rotted over {res['duration_s']}s ({res['efficiency_pct']}%)")

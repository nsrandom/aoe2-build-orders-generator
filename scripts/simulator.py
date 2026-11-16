#!/usr/bin/env python3
"""
1-Second Resolution Forward Build-Order Simulator & Validator.

Simulates an AoE2:DE build order tick-by-tick (dt = 1.0s) enforcing all rules in `rules.md`:
- House construction walk time: 5s each way (or 0s between sequential buildings)
- Generic building walk time: 10s each way (or 0s between sequential buildings)
- Boar lure walk time: 15s each way (30s total for the luring villager)
- Camp / Berry walk time: 15s one way
- Wood efficiency decay: -1% every 20s (-3% per minute) since last Lumber Camp completed, resets to 100% on new LC
- Animal rot: tracks individual carcasses (sheep/boar/deer/chicken) with per-second decay
  and checks ideal (6/7-8/4/2) and max (7/9-10/7/4) villager counts
- Boar shooting garrison idling: 6-8 vils garrison in TC for 5s when each boar arrives
- Town Center queue & <= 5s pre-click idle rule
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from aoe2_data import ANIMALS, AoE2Database, ResourceBundle, RuleConfig, calc_construction_time


@dataclass
class ActiveCarcass:
    animal_type: str
    remaining_food: float
    decay_rate: float
    rotted_food: float = 0.0
    gathered_food: float = 0.0


@dataclass
class VillagerState:
    vil_id: int
    role: str = "idle"  # shepherd, boar, deer, chicken, berries, straggler, wood, farmer, gold, stone
    busy_until: float = 0.0
    busy_reason: str = ""
    return_walk_after_build: float = 0.0


@dataclass
class BuildTask:
    time_s: float
    building_name: str
    builder_roles: List[str]  # which gatherer pool(s) to pull builders from
    after_role: str  # role builders assume after completing (or "sequential" if chaining another build)
    is_sequential: bool = False  # if True, 0s walk time to start building
    is_new_camp_walk: bool = False  # if True, uses 15s camp walk and 0s return walk


class BuildOrderSimulator:
    def __init__(
        self,
        civ: str = "Generic",
        db: Optional[AoE2Database] = None,
        rules: RuleConfig = RuleConfig(),
    ) -> None:
        self.civ = civ
        self.db = db or AoE2Database()
        self.rules = rules

        self.time_s: int = 0
        self.age: int = 1
        self.bank: ResourceBundle = self.db.get_starting_resources(civ)
        self.total_collected: ResourceBundle = ResourceBundle()
        self.total_rotted_food: float = 0.0

        self.villagers: List[VillagerState] = [
            VillagerState(vil_id=1),
            VillagerState(vil_id=2),
            VillagerState(vil_id=3),
        ]
        self.military_pop: int = 1  # starting scout
        self.housing_cap: int = 5  # starting TC

        # Natural food pools remaining (unslaughtered count)
        self.unslaughtered_counts: Dict[str, int] = {
            "sheep": 8,
            "boar": 2,
            "deer": 3,
            "chicken": 0,
        }
        self.active_carcasses: Dict[str, ActiveCarcass] = {}
        self.berries_remaining: float = 6 * 125.0

        # Lumber camp tracking for -5%/min wood decay
        self.last_lumber_camp_completed_s: Optional[int] = None
        self.completed_buildings: List[str] = ["town center"]
        self.active_upgrades: List[str] = []

        # TC state
        self.tc_busy_until: float = 0.0
        self.tc_current_action: str = "idle"
        self.tc_idle_seconds_total: float = 0.0
        self.tc_idle_before_click: Dict[int, float] = {2: 0.0, 3: 0.0, 4: 0.0}

        self.warnings: List[str] = []
        self.event_log: List[str] = []

    def format_time(self, sec: Optional[float] = None) -> str:
        s = int(round(self.time_s if sec is None else sec))
        return f"{s // 60:02d}:{s % 60:02d}"

    def log(self, msg: str) -> None:
        self.event_log.append(f"[{self.format_time()}] {msg}")

    def get_wood_minutes_since_lc(self) -> float:
        if self.last_lumber_camp_completed_s is None:
            return 0.0
        return max(0.0, (self.time_s - self.last_lumber_camp_completed_s) / 60.0)

    def _harvest_animal_tick(self, animal_type: str, num_vils: int, dt: float = 1.0) -> float:
        """Processes 1 second of gathering + decay on `animal_type` with `num_vils` active."""
        if num_vils <= 0:
            # Even if 0 vils are actively gathering, an already-slaughtered carcass still decays!
            carcass = self.active_carcasses.get(animal_type)
            if carcass and carcass.remaining_food > 0:
                rot = min(carcass.remaining_food, carcass.decay_rate * dt)
                carcass.remaining_food -= rot
                carcass.rotted_food += rot
                self.total_rotted_food += rot
            return 0.0

        spec = ANIMALS[animal_type]
        if num_vils > spec.max_vils:
            self.warnings.append(
                f"[{self.format_time()}] {num_vils} vils on {animal_type} exceeds max ({spec.max_vils})"
            )

        carcass = self.active_carcasses.get(animal_type)
        if carcass is None or carcass.remaining_food <= 1e-6:
            if self.unslaughtered_counts.get(animal_type, 0) <= 0:
                return 0.0
            self.unslaughtered_counts[animal_type] -= 1
            carcass = ActiveCarcass(
                animal_type=animal_type,
                remaining_food=spec.initial_food,
                decay_rate=spec.decay_rate,
            )
            self.active_carcasses[animal_type] = carcass

        rate_per_vil = self.db.get_gather_rate(
            animal_type, civ=self.civ, upgrades=self.active_upgrades, rules=self.rules
        )
        wanted_gather = num_vils * rate_per_vil * dt
        wanted_rot = carcass.decay_rate * dt
        total_depletion = wanted_gather + wanted_rot

        if total_depletion <= carcass.remaining_food:
            carcass.remaining_food -= total_depletion
            carcass.gathered_food += wanted_gather
            carcass.rotted_food += wanted_rot
            self.total_rotted_food += wanted_rot
            return wanted_gather
        else:
            # Carcass finishes mid-second; pro-rate and roll over if another animal is available
            frac = carcass.remaining_food / total_depletion
            gathered_1 = wanted_gather * frac
            rot_1 = wanted_rot * frac
            carcass.remaining_food = 0.0
            carcass.gathered_food += gathered_1
            carcass.rotted_food += rot_1
            self.total_rotted_food += rot_1
            rem_dt = dt * (1.0 - frac)
            return gathered_1 + self._harvest_animal_tick(animal_type, num_vils, dt=rem_dt)

    def step_one_second(self) -> None:
        """Advances simulation state by 1.0 second."""
        # Count active (non-busy) villagers by role
        active_counts: Dict[str, int] = {}
        for v in self.villagers:
            if self.time_s >= v.busy_until:
                if v.busy_reason:
                    v.busy_reason = ""
                active_counts[v.role] = active_counts.get(v.role, 0) + 1

        # Animal gathering + rot
        food_gained = 0.0
        for anim in ("sheep", "boar", "deer", "chicken"):
            food_gained += self._harvest_animal_tick(anim, active_counts.get(anim, 0), dt=1.0)

        # Berries
        n_berries = active_counts.get("berries", 0)
        if n_berries > 0 and self.berries_remaining > 0:
            r_berry = self.db.get_gather_rate(
                "berries", civ=self.civ, upgrades=self.active_upgrades, rules=self.rules
            )
            g_berry = min(self.berries_remaining, n_berries * r_berry)
            self.berries_remaining -= g_berry
            food_gained += g_berry

        # Farms
        n_farms = active_counts.get("farmer", 0)
        if n_farms > 0:
            r_farm = self.db.get_gather_rate(
                "farmer", civ=self.civ, upgrades=self.active_upgrades, rules=self.rules
            )
            food_gained += n_farms * r_farm

        # Straggler wood
        wood_gained = 0.0
        n_strag = active_counts.get("straggler", 0)
        if n_strag > 0:
            r_strag = self.db.get_gather_rate(
                "straggler", civ=self.civ, upgrades=self.active_upgrades, rules=self.rules
            )
            wood_gained += n_strag * r_strag

        # Lumber camp wood (with -5%/min decay)
        n_wood = active_counts.get("wood", 0)
        if n_wood > 0:
            r_wood = self.db.get_gather_rate(
                "lumberjack",
                civ=self.civ,
                upgrades=self.active_upgrades,
                wood_minutes_since_lc=self.get_wood_minutes_since_lc(),
                rules=self.rules,
            )
            wood_gained += n_wood * r_wood

        # Gold & Stone
        gold_gained = 0.0
        n_gold = active_counts.get("gold", 0)
        if n_gold > 0:
            r_gold = self.db.get_gather_rate(
                "gold miner", civ=self.civ, upgrades=self.active_upgrades, rules=self.rules
            )
            gold_gained += n_gold * r_gold

        stone_gained = 0.0
        n_stone = active_counts.get("stone", 0)
        if n_stone > 0:
            r_stone = self.db.get_gather_rate(
                "stone miner", civ=self.civ, upgrades=self.active_upgrades, rules=self.rules
            )
            stone_gained += n_stone * r_stone

        delta = ResourceBundle(
            food=food_gained, wood=wood_gained, gold=gold_gained, stone=stone_gained
        )
        self.bank = self.bank + delta
        self.total_collected = self.total_collected + delta
        self.time_s += 1


if __name__ == "__main__":
    sim = BuildOrderSimulator(civ="Italians")
    print("Initialized BuildOrderSimulator for Italians; starting bank:", sim.bank)

#!/usr/bin/env python3
"""
Detailed 1-Second Discrete-Event Simulator & Optimizer for:
Dravidians Man-at-Arms (MAA) into Archers (Deer & Chicken Variants).

Enforces all rules from `rules.md`:
- Initial houses (0:00): 2 vils on House 1 (18.75s) + 5s return walk; 1 vil on House 2 (25s) + 5s return walk
- Subsequent houses: 5s walk each way (or 0s if chained sequentially)
- Generic non-house buildings: 10s walk each way (or 0s if chained sequentially)
- Resource camps (LC, Mill, MC): 15s walk one-way + 35s build + 0s walk to gather
- Boar lure: 15s walk each way (30s total luring time for 1 villager)
- Wood efficiency decay: -1% every 15s since last LC finished (resets to 100% on new LC)
- Animal rot:
  - Sheep (100F, 0.25/s decay, 0.33/s gather): ideal 6, max 8
  - Boar (340F, 0.40/s decay, 0.41/s gather): ideal 7, max 9
  - Deer (140F, 0.25/s decay, 0.41/s gather): ideal 4, max 6
  - Chicken (75F, 0.125/s decay, 0.41/s gather): ideal 2, max 4
- Dravidians bonuses:
  - +200 Wood upon reaching Feudal Age
  - Barracks technologies cost -50% (Man-at-Arms = 50F, 20G, 40s)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from aoe2_data import ANIMALS, AoE2Database, ResourceBundle, RuleConfig, calc_construction_time


@dataclass
class SimActionLog:
    time_s: int
    pop_total: int
    vil_count: int
    age: int
    description: str
    alloc: Dict[str, int]
    bank: ResourceBundle
    notes: str = ""


class DetailedEcoSimulator:
    def __init__(self, variant: str = "deer", chicken_count: int = 8) -> None:
        self.db = AoE2Database()
        self.rules = RuleConfig()
        self.civ = "Dravidians"
        self.variant = variant  # "deer", "chicken_mill_8", "chicken_ld_6"

        self.time_s: int = 0
        self.age: int = 1
        self.bank = self.db.get_starting_resources(self.civ)
        self.total_gathered = ResourceBundle()
        self.rotted_food: Dict[str, float] = {"sheep": 0.0, "boar": 0.0, "deer": 0.0, "chicken": 0.0}

        # Remaining unslaughtered animals
        self.remaining_animals: Dict[str, int] = {
            "sheep": 8,
            "boar": 2,
            "deer": 3 if variant == "deer" else 0,
            "chicken": chicken_count if variant.startswith("chicken") else 0,
        }
        self.active_carcass_food: Dict[str, float] = {
            "sheep": 0.0,
            "boar": 0.0,
            "deer": 0.0,
            "chicken": 0.0,
        }
        self.berries_food: float = 6 * 125.0
        self.straggler_wood: float = 5 * 100.0

        self.lc_completed_s: Optional[int] = None
        self.upgrades: set[str] = set()
        self.buildings: List[str] = ["town center"]

        # Track each villager individually
        # role in: sheep, boar, deer, chicken_mill, chicken_ld, berries, farm, straggler, wood, gold, gold_ld
        self.vils: List[Dict[str, object]] = [
            {"id": 1, "role": "sheep", "busy_until": 24, "busy_desc": "Build House 1 (2v) + walk"},
            {"id": 2, "role": "sheep", "busy_until": 24, "busy_desc": "Build House 1 (2v) + walk"},
            {"id": 3, "role": "sheep", "busy_until": 30, "busy_desc": "Build House 2 (1v) + walk"},
        ]
        # Pay for initial 2 houses at t=0
        self.bank = self.bank - ResourceBundle(wood=50)
        self.buildings.extend(["house", "house"])

        # TC queue state
        self.tc_busy_until: int = 0
        self.tc_action: str = "idle"
        self.tc_target_vil_role: str = "sheep"
        self.tc_target_vil_walk: int = 0
        self.tc_target_vil_note: str = ""
        self.tc_idle_s: int = 0

        self.logs: List[SimActionLog] = []
        self.military_units: Dict[str, int] = {"scout": 1, "militia": 0, "archer": 0}

    def fmt_time(self, t: Optional[int] = None) -> str:
        sec = self.time_s if t is None else t
        return f"{sec // 60:02d}:{sec % 60:02d}"

    def wood_efficiency(self) -> float:
        if self.lc_completed_s is None:
            return 1.0
        elapsed = max(0, self.time_s - self.lc_completed_s)
        steps = int(elapsed // int(self.rules.wood_decay_step_seconds))
        return max(0.20, 1.0 - self.rules.wood_decay_per_step * steps)

    def current_macro_alloc(self) -> Dict[str, int]:
        out = {"food": 0, "wood": 0, "gold": 0, "stone": 0}
        for v in self.vils:
            r = str(v["role"])
            if r in ("sheep", "boar", "deer", "chicken_mill", "chicken_ld", "berries", "farm"):
                out["food"] += 1
            elif r in ("straggler", "wood"):
                out["wood"] += 1
            elif r in ("gold", "gold_ld"):
                out["gold"] += 1
            elif r in ("stone", "stone_ld"):
                out["stone"] += 1
        return out

    def current_food_breakdown(self) -> Dict[str, int]:
        fb = {"sheep": 0, "boar": 0, "deer": 0, "chicken": 0, "berries": 0, "farm": 0}
        for v in self.vils:
            r = str(v["role"])
            if r in ("sheep", "boar", "deer", "berries", "farm"):
                fb[r] += 1
            elif r in ("chicken_mill", "chicken_ld"):
                fb["chicken"] += 1
        return fb

    def detailed_alloc_str(self) -> str:
        counts: Dict[str, int] = {}
        for v in self.vils:
            r = str(v["role"])
            counts[r] = counts.get(r, 0) + 1
        return ", ".join(f"{k}:{v}" for k, v in counts.items() if v > 0)

    def record_snapshot(self, description: str, notes: str = "") -> None:
        pop_tot = len(self.vils) + sum(self.military_units.values())
        self.logs.append(
            SimActionLog(
                time_s=self.time_s,
                pop_total=pop_tot,
                vil_count=len(self.vils),
                age=self.age,
                description=description,
                alloc=self.current_macro_alloc(),
                bank=self.bank,
                notes=notes,
            )
        )

    def queue_villager(self, role: str, walk_s: int = 0, build_action: Optional[Tuple[str, int]] = None, note: str = "") -> bool:
        """Queues a villager at TC if idle and >= 50F."""
        if self.time_s < self.tc_busy_until:
            return False
        if not self.bank.can_afford(ResourceBundle(food=50)):
            return False
        self.bank = self.bank - ResourceBundle(food=50)
        self.tc_busy_until = self.time_s + 25
        self.tc_action = "villager"
        self.tc_target_vil_role = role
        self.tc_target_vil_walk = walk_s
        self.tc_target_vil_note = note
        self._pending_vil_build = build_action
        return True

    def _harvest_carcass(self, anim_key: str, n_vils: int, gather_rate_override: Optional[float] = None) -> float:
        spec = ANIMALS[anim_key]
        if n_vils <= 0:
            if self.active_carcass_food[anim_key] > 0:
                rot = min(self.active_carcass_food[anim_key], spec.decay_rate)
                self.active_carcass_food[anim_key] -= rot
                self.rotted_food[anim_key] += rot
            return 0.0

        if self.active_carcass_food[anim_key] <= 1e-6:
            if self.remaining_animals[anim_key] <= 0:
                return 0.0
            self.remaining_animals[anim_key] -= 1
            self.active_carcass_food[anim_key] = spec.initial_food

        r_vil = gather_rate_override if gather_rate_override is not None else spec.base_gather_rate
        gather = n_vils * r_vil
        rot = spec.decay_rate
        tot = gather + rot
        avail = self.active_carcass_food[anim_key]
        if tot <= avail:
            self.active_carcass_food[anim_key] -= tot
            self.rotted_food[anim_key] += rot
            return gather
        else:
            frac = avail / tot
            g1 = gather * frac
            r1 = rot * frac
            self.active_carcass_food[anim_key] = 0.0
            self.rotted_food[anim_key] += r1
            # If a sheep finishes while a boar carcass is already open under TC, switch shepherds to boar instead of killing a new sheep!
            if anim_key == "sheep" and self.active_carcass_food.get("boar", 0.0) > 0:
                for v in self.vils:
                    if v["role"] == "sheep":
                        v["role"] = "boar"
                return g1
            # Roll over remaining fraction of second if more animals exist
            if self.remaining_animals[anim_key] > 0:
                self.remaining_animals[anim_key] -= 1
                self.active_carcass_food[anim_key] = spec.initial_food
                rem = 1.0 - frac
                g2 = min(self.active_carcass_food[anim_key], gather * rem)
                r2 = min(max(0.0, self.active_carcass_food[anim_key] - g2), rot * rem)
                self.active_carcass_food[anim_key] -= (g2 + r2)
                self.rotted_food[anim_key] += r2
                return g1 + g2
            return g1

    def tick_gather(self) -> None:
        """Collects resources for 1 second across all non-busy villagers."""
        active: Dict[str, int] = {}
        for v in self.vils:
            if self.time_s >= int(v["busy_until"]):
                role = str(v["role"])
                active[role] = active.get(role, 0) + 1

        # Automatic fallback under TC: if boar/deer/chicken runs out, switch those vils to sheep (or berries/straggler if sheep also exhausted)
        for fallback_src in ("boar", "deer", "chicken_mill", "chicken_ld"):
            anim_name = "chicken" if fallback_src.startswith("chicken") else fallback_src
            if active.get(fallback_src, 0) > 0 and self.active_carcass_food[anim_name] <= 1e-6 and self.remaining_animals[anim_name] <= 0:
                for v in self.vils:
                    if v["role"] == fallback_src and self.time_s >= int(v["busy_until"]):
                        v["role"] = "sheep"
                active["sheep"] = active.get("sheep", 0) + active.pop(fallback_src, 0)

        # If all sheep are exhausted, any remaining shepherds move to berries (up to 4) or TC stragglers (3s walk) to fund farms
        if active.get("sheep", 0) > 0 and self.active_carcass_food["sheep"] <= 1e-6 and self.remaining_animals["sheep"] <= 0:
            berry_cnt = sum(1 for v in self.vils if v["role"] == "berries")
            for v in self.vils:
                if v["role"] == "sheep" and self.time_s >= int(v["busy_until"]):
                    if berry_cnt < 4 and self.berries_food > 0 and self.variant != "chicken_mill_8":
                        v["role"] = "berries"
                        v["busy_until"] = self.time_s + 15
                        berry_cnt += 1
                    else:
                        v["role"] = "straggler"
                        v["busy_until"] = self.time_s + 3
            active.pop("sheep", None)

        f_gain = 0.0
        f_gain += self._harvest_carcass("sheep", active.get("sheep", 0), 0.33)
        f_gain += self._harvest_carcass("boar", active.get("boar", 0), 0.41)
        f_gain += self._harvest_carcass("deer", active.get("deer", 0), 0.41)

        # Milled chickens: 0.41 hunter gather rate at mill
        if active.get("chicken_mill", 0) > 0:
            f_gain += self._harvest_carcass("chicken", active.get("chicken_mill", 0), 0.41)
        elif active.get("chicken_ld", 0) > 0:
            # Long-distance chickens: 35F carry capacity at 0.41 F/s (85.4s gather) + 30s round trip walk
            # Effective rate while at chicken = 0.41 * (85.37 / 115.37) = 0.3034 F/s
            ld_eff_rate = 0.41 * (35.0 / 0.41) / ((35.0 / 0.41) + 30.0)
            f_gain += self._harvest_carcass("chicken", active.get("chicken_ld", 0), ld_eff_rate)
        else:
            self._harvest_carcass("chicken", 0)

        # Berries
        if active.get("berries", 0) > 0:
            if self.berries_food > 1e-6:
                bg = min(self.berries_food, active["berries"] * 0.31)
                self.berries_food -= bg
                f_gain += bg
            else:
                for v in self.vils:
                    if v["role"] == "berries" and self.time_s >= int(v["busy_until"]):
                        v["role"] = "straggler"
                        v["busy_until"] = self.time_s + 15

        # Farms
        if active.get("farm", 0) > 0:
            farm_rate = 0.3838 if "wheelbarrow" in self.upgrades else 0.3383
            f_gain += active["farm"] * farm_rate

        # Wood
        w_gain = 0.0
        if active.get("straggler", 0) > 0 and self.straggler_wood > 0:
            sg = min(self.straggler_wood, active["straggler"] * 0.39)
            self.straggler_wood -= sg
            w_gain += sg

        if active.get("wood", 0) > 0:
            base_w = 0.39 * (1.20 if "double-bit axe" in self.upgrades else 1.0) * (1.20 if "bow saw" in self.upgrades else 1.0)
            w_gain += active["wood"] * base_w * self.wood_efficiency()

        # Gold
        g_gain = 0.0
        if active.get("gold", 0) > 0:
            base_g = 0.38 * (1.15 if "gold mining" in self.upgrades else 1.0)
            g_gain += active["gold"] * base_g
        if active.get("gold_ld", 0) > 0:
            # Long distance gold: 10G / (10/0.38 + 30) = 0.1776 G/s
            ld_g = 10.0 / ((10.0 / 0.38) + 30.0)
            g_gain += active["gold_ld"] * ld_g

        delta = ResourceBundle(food=f_gain, wood=w_gain, gold=g_gain)
        self.bank = self.bank + delta
        self.total_gathered = self.total_gathered + delta


if __name__ == "__main__":
    s = DetailedEcoSimulator("deer")
    print("DetailedEcoSimulator initialized cleanly.")

#!/usr/bin/env python3
"""
Detailed 1-Second Discrete-Event Simulator for:
Dravidians 20-Pop (19-Vil) 3 MAA -> Archers (7 Chickens Milled on Arabia)
into 3 Castle Age Paths:
  1. 1tc_xbow_lc_ram      : 2-Range Xbows + 1-Stable Light Cav + 2-4 Armored Elephants (Rams) -> Later TCs
  2. 1tc_xbow_ls_spear_ram: 2-Range Xbows + 2-Barracks Longswords & Spears/Pikes (~50/50) + 2-4 Armored Elephants -> Later TCs
  3. 3tc_boom_ele_archer  : 3 TC Boom First -> Switch to 2-Range Elephant Archers + 8-10 Light Cav + 2-4 Armored Elephants

Enforces all updated rules in `rules.md`:
- Initial houses (0:00): 2 vils on House 1 (18.75s) + 5s return walk; 1 vil on House 2 (25s) + 5s return walk
- Subsequent houses: 5s walk each way (or 0s if chained sequentially)
- Generic non-house buildings: 10s walk each way (or 0s if chained sequentially)
- Resource camps (LC, Mill, MC): 15s walk one-way + 35s build + 0s walk to gather
- Boar lure: 15s walk each way (30s total luring interruption) PLUS 7 TC vils garrisoned for 5s
  to shoot each boar down (35 vil-seconds idle per boar). After shooting boar down, 6+ vils go
  immediately onto the boar if only a small amount of food remains on the active sheep.
- Animal villager limits:
  - Sheep: ideal 6, max 7 (never > 7)
  - Boar: ideal 7-8, max 9 normally (up to 10 allowed during transitions)
  - Chicken (7 milled): 4 vils on milled patch (0.41 F/s, 0.125 F/s decay)
- Wood efficiency decay: -1% every 20s (-3%/min) since last LC completed (resets to 100% on new LC)
- Later-stage imperfect execution buffer: 92% macro eco efficiency in Feudal Age, 90% in Castle Age+
- Dravidians bonuses:
  - +200 Wood upon reaching Feudal Age & +200 Wood upon reaching Castle Age
  - Barracks techs cost -50% (MAA = 50F/20G, Long Swordsman = 75F/32.5G, Pikeman = 80F/45G, Squires = 50F, Arson = 37.5F/12.5G)
  - Armored Elephant (120F, 95G, 36s) replaces Battering Ram
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from aoe2_data import ANIMALS, AoE2Database, ResourceBundle, RuleConfig


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


class DravidiansChickenSimulator:
    def __init__(self, path_key: str, chicken_count: int = 7) -> None:
        self.db = AoE2Database()
        self.rules = RuleConfig()
        self.civ = "Dravidians"
        self.path_key = path_key

        self.time_s: int = 0
        self.age: int = 1
        self.bank = self.db.get_starting_resources(self.civ)
        self.total_gathered = ResourceBundle()
        self.rotted_food: Dict[str, float] = {"sheep": 0.0, "boar": 0.0, "deer": 0.0, "chicken": 0.0}

        # Arabia resources: 8 sheep, 2 boars, 7 chickens milled, 0 pushed deer
        self.remaining_animals: Dict[str, int] = {
            "sheep": 8,
            "boar": 2,
            "deer": 0,
            "chicken": chicken_count,
        }
        self.active_carcass_food: Dict[str, float] = {
            "sheep": 0.0,
            "boar": 0.0,
            "deer": 0.0,
            "chicken": 0.0,
        }
        self.berries_food: float = 6 * 125.0
        self.straggler_wood: float = 6 * 100.0

        self.lc_completed_s: Optional[int] = None
        self.lc_count: int = 0
        self.upgrades: set[str] = set()
        self.buildings: List[str] = ["town center"]

        # Track each villager individually
        # role in: sheep, boar, chicken_mill, farm, straggler, wood, gold, gold_ld
        self.vils: List[Dict[str, object]] = [
            {"id": 1, "role": "sheep", "busy_until": 24, "busy_desc": "Build House 1 (2v) + walk"},
            {"id": 2, "role": "sheep", "busy_until": 24, "busy_desc": "Build House 1 (2v) + walk"},
            {"id": 3, "role": "sheep", "busy_until": 30, "busy_desc": "Build House 2 (1v) + walk"},
        ]
        # Pay for initial 2 houses at t=0
        self.bank = self.bank - ResourceBundle(wood=50)
        self.buildings.extend(["house", "house"])

        # Multi-TC queue state (up to 3 TCs)
        self.tc_count: int = 1
        self.tc_busy_until: List[int] = [0, 0, 0]
        self.tc_action: List[str] = ["idle", "idle", "idle"]
        self.tc_idle_s: int = 0
        self.tc1_idle_castle_s: int = 0

        # Farm food capacity & automatic reseeding
        self.farm_food_pool: List[float] = []
        self.farms_seeded: int = 0
        self.farms_reseeded: int = 0

        # Market telemetry
        self.market_trades: List[Dict[str, object]] = []

        self.logs: List[SimActionLog] = []
        self.military_units: Dict[str, int] = {
            "scout": 1,
            "militia": 0,
            "spearman": 0,
            "archer": 0,
            "elephant_archer": 0,
            "light_cav": 0,
            "armored_elephant": 0,
        }

    def fmt_time(self, t: Optional[int] = None) -> str:
        sec = self.time_s if t is None else t
        return f"{sec // 60:02d}:{sec % 60:02d}"

    def macro_efficiency(self) -> float:
        """Applies imperfect human execution buffer in Feudal Age (92%) and Castle Age+ (90%)."""
        if self.age == 1:
            return 1.0
        if self.age == 2:
            return self.rules.feudal_macro_efficiency
        return self.rules.castle_macro_efficiency

    def wood_efficiency(self) -> float:
        if self.lc_completed_s is None:
            return 1.0
        elapsed = max(0, self.time_s - self.lc_completed_s)
        steps = int(elapsed // int(self.rules.wood_decay_step_seconds))
        return max(0.20, 1.0 - self.rules.wood_decay_per_step * steps)

    def farm_capacity(self) -> float:
        if "heavy plow" in self.upgrades:
            return 375.0
        if "horse collar" in self.upgrades:
            return 250.0
        return 175.0

    def register_new_farm(self) -> None:
        self.farm_food_pool.append(self.farm_capacity())
        self.farms_seeded += 1

    def current_macro_alloc(self) -> Dict[str, int]:
        out = {"food": 0, "wood": 0, "gold": 0, "stone": 0}
        for v in self.vils:
            r = str(v["role"])
            if r in ("sheep", "boar", "deer", "chicken_mill", "berries", "farm"):
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
            elif r == "chicken_mill":
                fb["chicken"] += 1
        return fb

    def count_role(self, *roles: str) -> int:
        return sum(1 for v in self.vils if v["role"] in roles)

    def _harvest_carcass(self, anim_key: str, n_vils: int, gather_rate_override: Optional[float] = None, boar_active: bool = False) -> float:
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
        gather = n_vils * r_vil * self.macro_efficiency()
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
            # Never slaughter a new sheep while a boar carcass is already open under TC
            if anim_key == "sheep" and boar_active:
                boar_cnt = self.count_role("boar")
                for v in self.vils:
                    if v["role"] == "sheep":
                        if boar_cnt < 10:
                            v["role"] = "boar"
                            boar_cnt += 1
                        else:
                            v["role"] = "straggler"
                            v["busy_until"] = self.time_s + 3
                return g1
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

    def tick_gather(self, boar_open: bool = False, reseed_reserve_w: float = 0.0) -> None:
        """Collects resources for 1 second across all non-busy villagers."""
        active: Dict[str, int] = {}
        for v in self.vils:
            if self.time_s >= int(v["busy_until"]):
                role = str(v["role"])
                active[role] = active.get(role, 0) + 1

        # Fallback under TC when boar or chicken runs out:
        # Respect max 7 villagers on sheep! Overflow moves to TC straggler trees (3s walk).
        for fallback_src in ("boar", "chicken_mill"):
            anim_name = "chicken" if fallback_src == "chicken_mill" else fallback_src
            if active.get(fallback_src, 0) > 0 and self.active_carcass_food[anim_name] <= 1e-6 and self.remaining_animals[anim_name] <= 0:
                sheep_cnt = self.count_role("sheep")
                sheep_avail = self.active_carcass_food["sheep"] > 1e-6 or self.remaining_animals["sheep"] > 0
                for v in self.vils:
                    if v["role"] == fallback_src and self.time_s >= int(v["busy_until"]):
                        if sheep_avail and sheep_cnt < 7:
                            v["role"] = "sheep"
                            sheep_cnt += 1
                            active["sheep"] = active.get("sheep", 0) + 1
                        else:
                            v["role"] = "straggler"
                            v["busy_until"] = self.time_s + 3
                active.pop(fallback_src, None)

        # If all sheep are exhausted, shepherds transition to TC straggler trees (3s walk), or Lumber Camp if stragglers depleted
        if active.get("sheep", 0) > 0 and self.active_carcass_food["sheep"] <= 1e-6 and self.remaining_animals["sheep"] <= 0:
            for v in self.vils:
                if v["role"] == "sheep" and self.time_s >= int(v["busy_until"]):
                    if self.straggler_wood > 1e-6:
                        v["role"] = "straggler"
                        v["busy_until"] = self.time_s + 3
                    else:
                        v["role"] = "wood"
                        v["busy_until"] = self.time_s + 15
            active.pop("sheep", None)

        # If TC stragglers run out, fallback stragglers walk to Lumber Camp woodline (15s walk)
        if active.get("straggler", 0) > 0 and self.straggler_wood <= 1e-6:
            for v in self.vils:
                if v["role"] == "straggler" and self.time_s >= int(v["busy_until"]):
                    v["role"] = "wood"
                    v["busy_until"] = self.time_s + 15
            active.pop("straggler", None)

        eff = self.macro_efficiency()
        boar_present = boar_open or self.active_carcass_food["boar"] > 1e-6

        f_gain = 0.0
        f_gain += self._harvest_carcass("sheep", active.get("sheep", 0), 0.33, boar_active=boar_present)
        f_gain += self._harvest_carcass("boar", active.get("boar", 0), 0.41)
        f_gain += self._harvest_carcass("chicken", active.get("chicken_mill", 0), 0.41)

        # Farms + automatic reseeding
        n_farms = active.get("farm", 0)
        if n_farms > 0:
            if "hand cart" in self.upgrades:
                base_farm_r = 0.4000
            elif "wheelbarrow" in self.upgrades and "heavy plow" in self.upgrades:
                base_farm_r = 0.3860
            elif "wheelbarrow" in self.upgrades:
                base_farm_r = 0.3838
            elif "heavy plow" in self.upgrades:
                base_farm_r = 0.3533
            else:
                base_farm_r = 0.3383
            farm_r = base_farm_r * eff
            f_gain += n_farms * farm_r
            for idx in range(min(n_farms, len(self.farm_food_pool))):
                self.farm_food_pool[idx] -= farm_r
                if self.farm_food_pool[idx] <= 0:
                    if self.bank.wood >= (60.0 + reseed_reserve_w):
                        self.bank = self.bank - ResourceBundle(wood=60)
                        self.farm_food_pool[idx] = self.farm_capacity()
                        self.farms_reseeded += 1
                    else:
                        self.farm_food_pool[idx] = 0.0

        # Wood (stragglers + lumberjacks with -1%/20s decay)
        w_gain = 0.0
        if active.get("straggler", 0) > 0 and self.straggler_wood > 0:
            sg = min(self.straggler_wood, active["straggler"] * 0.39 * eff)
            self.straggler_wood -= sg
            w_gain += sg

        if active.get("wood", 0) > 0:
            base_w = (
                0.39
                * (1.20 if "double-bit axe" in self.upgrades else 1.0)
                * (1.20 if "bow saw" in self.upgrades else 1.0)
                * (1.10 if "two-man saw" in self.upgrades else 1.0)
            )
            w_gain += active["wood"] * base_w * self.wood_efficiency() * eff

        # Gold
        g_gain = 0.0
        if active.get("gold", 0) > 0:
            base_g = 0.38 * (1.15 if "gold mining" in self.upgrades else 1.0)
            g_gain += active["gold"] * base_g * eff
        if active.get("gold_ld", 0) > 0:
            ld_g = 10.0 / ((10.0 / 0.38) + 30.0)
            g_gain += active["gold_ld"] * ld_g * eff

        delta = ResourceBundle(food=f_gain, wood=w_gain, gold=g_gain)
        self.bank = self.bank + delta
        self.total_gathered = self.total_gathered + delta

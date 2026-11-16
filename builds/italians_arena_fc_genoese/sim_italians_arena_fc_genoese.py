#!/usr/bin/env python3
"""
Detailed 1-Second Discrete-Event Simulator for:
Italians Arena Fast Castle Build Orders (3 Deer Pushed, No Chickens):
1. Strategy 1: 1 TC Heavy Army Push (Defensive Castle <= 10s -> Genoese + Light Cav
   + Monastery & 2 Monks [assume max 1 Relic] -> Forward Siege Workshop & Rams at 30+ army
   -> Imperial Age -> Add TCs after clicking Imp).
2. Strategy 2: Balanced 3 TC Boom (Defensive Castle <= 10s -> ~20 Army [13 Genoese,
   7 Light Cav] -> Pause military & expand to 3 TCs with continuous Villagers ->
   Maximize army production with full upgrades).

Enforces all updated rules from `rules.md`:
- Initial houses (0:00): 2 vils on House 1 (18.75s) + 5s return walk; 1 vil on House 2 (25s) + 5s return walk
- Subsequent houses: 5s walk each way (or 0s if chained sequentially)
- Generic non-house buildings: 10s walk each way (or 0s if chained sequentially)
- Resource camps (LC, Mill, MC): 15s walk one-way + 35s build + 0s walk to gather
- Boar lure: 15s walk each way (30s total luring interruption) PLUS 7 TC vils garrisoned for 5s
  to shoot each boar down (35 vil-seconds idle per boar). After shooting boar down, 6+ vils go
  immediately onto the boar if only a small amount of food remains on the active sheep.
- Wood efficiency decay & priority rules:
  - -1% every 20s (-3%/min) since last LC finished (resets to 100% on new LC)
  - Refresh target: 60%-65% (700-800s after previous LC) or when expanding to 9+ lumberjacks
  - Wood Priority Rule: never delay essential progression buildings, eco upgrades, houses, or required farms to refresh an LC
- Animal rot & villager caps:
  - Sheep (100F, 0.25/s decay, 0.33/s gather): ideal 6, max 7 (never > 7)
  - Boar (340F, 0.40/s decay, 0.41/s gather): ideal 7-8, max 9 (up to 10 in transition)
  - Deer (140F, 0.25/s decay, 0.41/s gather): ideal 4, max 7
- Later-stage imperfect execution buffer: 92% macro eco efficiency in Feudal Age, 90% in Castle Age+
- Market prices (rules.md 1.4):
  - Feudal Age: ~70G per 100 Food/Wood/Stone sold
  - Early to Mid Castle Age: ~50G per 100 Food/Wood sold
  - Late Castle Age: ~30G per 100 Food/Wood sold
  - Imperial Age: ~15G per 100 Food/Wood sold
- Italians bonuses:
  - Age advancement costs -15%: Feudal 425F (130s), Castle 680F/170G (160s), Imperial 850F/680G (190s)
  - University & Dock technologies cost -33%: Ballistics 201W/117G, Chemistry 201F/134G, Masonry 100F/117W, Siege Engineers 335F/402W
  - Gunpowder units cost -20%: Bombard Cannon 180W/180G (56s)
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


class ItaliansArenaSimulator:
    def __init__(self, dark_vils: int = 26) -> None:
        self.db = AoE2Database()
        self.rules = RuleConfig()
        self.civ = "Italians"
        self.dark_vils = dark_vils

        self.time_s: int = 0
        self.age: int = 1
        self.bank = self.db.get_starting_resources(self.civ)
        self.total_gathered = ResourceBundle()
        self.rotted_food: Dict[str, float] = {"sheep": 0.0, "boar": 0.0, "deer": 0.0, "chicken": 0.0}

        # Remaining unslaughtered animals on Arena (8 sheep, 2 boar, 3 deer, 0 chicken)
        self.remaining_animals: Dict[str, int] = {
            "sheep": 8,
            "boar": 2,
            "deer": 3,
            "chicken": 0,
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
        self.relics_garrisoned: int = 0
        self.upgrades: set[str] = set()
        self.buildings: List[str] = ["town center"]

        # Track each villager individually
        # role in: sheep, boar, deer, berries, farm, straggler, wood, gold, stone
        self.vils: List[Dict[str, object]] = [
            {"id": 1, "role": "sheep", "busy_until": 24, "busy_desc": "Build House 1 (2v) + walk"},
            {"id": 2, "role": "sheep", "busy_until": 24, "busy_desc": "Build House 1 (2v) + walk"},
            {"id": 3, "role": "sheep", "busy_until": 30, "busy_desc": "Build House 2 (1v) + walk"},
        ]
        # Pay for initial 2 houses at t=0
        self.bank = self.bank - ResourceBundle(wood=50)
        self.buildings.extend(["house", "house"])

        # Multi-TC queue state (up to 4 TCs)
        self.tc_count: int = 1
        self.tc_busy_until: List[int] = [0]
        self.tc_action: List[str] = ["idle"]
        self.tc_idle_s: int = 0
        self.tc1_idle_before_imp_s: int = 0

        # Track Farm food capacity and reseeding (-60W per expired farm)
        self.farm_food_pool: List[float] = []
        self.farms_seeded: int = 0
        self.farms_reseeded: int = 0

        # Market telemetry
        self.market_trades: List[Dict[str, object]] = []

        self.logs: List[SimActionLog] = []
        self.military_units: Dict[str, int] = {
            "scout": 1,
            "genoese": 0,
            "light_cav": 0,
            "monk": 0,
            "battering_ram": 0,
            "trebuchet": 0,
            "bombard_cannon": 0,
        }
        self.casualties: Dict[str, int] = {
            "genoese": 0,
            "light_cav": 0,
            "battering_ram": 0,
            "bombard_cannon": 0,
        }

    def macro_efficiency(self) -> float:
        """Applies imperfect human execution buffer in Feudal Age (92%) and Castle Age+ (90%)."""
        if self.age == 1:
            return 1.0
        if self.age == 2:
            return self.rules.feudal_macro_efficiency
        return self.rules.castle_macro_efficiency

    def farm_capacity(self) -> float:
        if "crop rotation" in self.upgrades:
            return 550.0
        if "heavy plow" in self.upgrades:
            return 375.0
        if "horse collar" in self.upgrades:
            return 250.0
        return 175.0

    def register_new_farm(self) -> None:
        self.farm_food_pool.append(self.farm_capacity())
        self.farms_seeded += 1

    def count_role(self, *roles: str) -> int:
        return sum(1 for v in self.vils if v["role"] in roles)

    def fmt_time(self, t: Optional[int] = None) -> str:
        sec = self.time_s if t is None else t
        return f"{sec // 60:02d}:{sec % 60:02d}"

    def wood_efficiency(self) -> float:
        if self.lc_completed_s is None:
            return 1.0
        elapsed = max(0, self.time_s - self.lc_completed_s)
        steps = int(elapsed // int(self.rules.wood_decay_step_seconds))
        return max(0.20, 1.0 - self.rules.wood_decay_per_step * steps)

    def market_sell_price(self, castle_reached_s: Optional[int] = None) -> int:
        """
        Returns Gold gained per 100 resource sold per rules.md 1.4:
        - Feudal Age: ~70G (high prices)
        - Early to Mid Castle Age (< 8 min in Castle): ~50G
        - Late Castle Age (>= 8 min in Castle): ~30G
        - Imperial Age: ~15G
        """
        if self.age <= 2:
            return self.rules.market_sell_gold_feudal
        if self.age == 3:
            if castle_reached_s is not None and (self.time_s - castle_reached_s) >= 480:
                return self.rules.market_sell_gold_late_castle
            return self.rules.market_sell_gold_early_mid_castle
        return self.rules.market_sell_gold_imperial

    def sell_at_market(
        self,
        resource: str,
        amount: int = 100,
        castle_reached_s: Optional[int] = None,
    ) -> int:
        """Sells `amount` (multiple of 100) of `resource` ('food'|'wood'|'stone') and returns Gold gained."""
        if amount <= 0 or amount % 100 != 0:
            raise ValueError("Market trade amount must be a positive multiple of 100.")
        price_per_100 = self.market_sell_price(castle_reached_s)
        gold_gained = (amount // 100) * price_per_100
        if resource == "food":
            self.bank = self.bank - ResourceBundle(food=amount) + ResourceBundle(gold=gold_gained)
        elif resource == "wood":
            self.bank = self.bank - ResourceBundle(wood=amount) + ResourceBundle(gold=gold_gained)
        elif resource == "stone":
            self.bank = self.bank - ResourceBundle(stone=amount) + ResourceBundle(gold=gold_gained)
        else:
            raise ValueError(f"Unsupported sell resource: {resource}")
        self.market_trades.append(
            {
                "t": self.time_s,
                "ts": self.fmt_time(),
                "sold": f"{amount} {resource}",
                "gold_gained": gold_gained,
                "rate": price_per_100,
            }
        )
        return gold_gained

    def current_macro_alloc(self) -> Dict[str, int]:
        out = {"food": 0, "wood": 0, "gold": 0, "stone": 0}
        for v in self.vils:
            r = str(v["role"])
            if r in ("sheep", "boar", "deer", "berries", "farm"):
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
            if r in fb:
                fb[r] += 1
        return fb

    def _harvest_carcass(
        self,
        anim_key: str,
        n_vils: int,
        gather_rate_override: Optional[float] = None,
        boar_active: bool = False,
    ) -> float:
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
            # Never slaughter a new sheep while a boar carcass is open under the TC
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

        # Automatic fallback under TC when boar or deer finishes:
        # Respect max 7 villagers on a single sheep carcass!
        for fallback_src in ("boar", "deer"):
            if (
                active.get(fallback_src, 0) > 0
                and self.active_carcass_food[fallback_src] <= 1e-6
                and self.remaining_animals[fallback_src] <= 0
            ):
                cur_sheep_vils = self.count_role("sheep")
                sheep_avail = (
                    self.active_carcass_food["sheep"] > 1e-6
                    or self.remaining_animals["sheep"] > 0
                )
                for v in self.vils:
                    if v["role"] == fallback_src and self.time_s >= int(v["busy_until"]):
                        if sheep_avail and cur_sheep_vils < 7:
                            v["role"] = "sheep"
                            cur_sheep_vils += 1
                            active["sheep"] = active.get("sheep", 0) + 1
                        elif self.straggler_wood > 1e-6:
                            v["role"] = "straggler"
                            v["busy_until"] = self.time_s + 3
                        else:
                            v["role"] = "wood"
                            v["busy_until"] = self.time_s + 15
                active.pop(fallback_src, None)

        # When all sheep are exhausted, remaining shepherds switch to straggler trees (3s walk) or LC wood (15s)
        if (
            active.get("sheep", 0) > 0
            and self.active_carcass_food["sheep"] <= 1e-6
            and self.remaining_animals["sheep"] <= 0
        ):
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
        f_gain += self._harvest_carcass("deer", active.get("deer", 0), 0.41)

        # Berries
        if active.get("berries", 0) > 0:
            if self.berries_food > 1e-6:
                bg = min(self.berries_food, active["berries"] * 0.31 * eff)
                self.berries_food -= bg
                f_gain += bg
            else:
                for v in self.vils:
                    if v["role"] == "berries" and self.time_s >= int(v["busy_until"]):
                        v["role"] = "straggler" if self.straggler_wood > 1e-6 else "wood"
                        v["busy_until"] = self.time_s + 15

        # Farms (with realistic farm expiration and -60W automatic reseeding)
        if active.get("farm", 0) > 0:
            if "hand cart" in self.upgrades:
                base_farm_r = 0.4000
            elif "wheelbarrow" in self.upgrades and "heavy plow" in self.upgrades:
                base_farm_r = 23.16 / 60.0
            elif "wheelbarrow" in self.upgrades:
                base_farm_r = 0.3838
            elif "heavy plow" in self.upgrades:
                base_farm_r = 0.3533
            else:
                base_farm_r = 0.3383
            farm_rate = base_farm_r * eff
            n_farmers = active["farm"]
            while len(self.farm_food_pool) < n_farmers:
                self.farm_food_pool.append(self.farm_capacity())
            for i in range(n_farmers):
                self.farm_food_pool[i] -= farm_rate
                if self.farm_food_pool[i] <= 0.0:
                    if self.bank.wood >= (60.0 + reseed_reserve_w):
                        self.bank = self.bank - ResourceBundle(wood=60.0)
                        self.farm_food_pool[i] += self.farm_capacity()
                        self.farms_reseeded += 1
                    else:
                        self.farm_food_pool[i] = 50.0
            f_gain += n_farmers * farm_rate

        # Wood
        w_gain = 0.0
        tms_mult = 1.10 if "two-man saw" in self.upgrades else 1.0
        if active.get("straggler", 0) > 0 and self.straggler_wood > 0:
            base_strag = (
                0.39
                * (1.20 if "double-bit axe" in self.upgrades else 1.0)
                * (1.20 if "bow saw" in self.upgrades else 1.0)
                * tms_mult
                * eff
            )
            sg = min(self.straggler_wood, active["straggler"] * base_strag)
            self.straggler_wood -= sg
            w_gain += sg

        if active.get("wood", 0) > 0:
            base_w = (
                0.39
                * (1.20 if "double-bit axe" in self.upgrades else 1.0)
                * (1.20 if "bow saw" in self.upgrades else 1.0)
                * tms_mult
            )
            w_gain += active["wood"] * base_w * self.wood_efficiency() * eff

        # Gold (miners + garrisoned relics at 0.50 G/s per relic)
        g_gain = 0.50 * self.relics_garrisoned
        if active.get("gold", 0) > 0:
            base_g = (
                0.38
                * (1.15 if "gold mining" in self.upgrades else 1.0)
                * (1.15 if "gold shaft mining" in self.upgrades else 1.0)
            )
            g_gain += active["gold"] * base_g * eff

        # Stone
        s_gain = 0.0
        if active.get("stone", 0) > 0:
            base_s = (
                0.36
                * (1.15 if "stone mining" in self.upgrades else 1.0)
                * (1.15 if "stone shaft mining" in self.upgrades else 1.0)
            )
            s_gain += active["stone"] * base_s * eff

        delta = ResourceBundle(food=f_gain, wood=w_gain, gold=g_gain, stone=s_gain)
        self.bank = self.bank + delta
        self.total_gathered = self.total_gathered + delta


if __name__ == "__main__":
    s = ItaliansArenaSimulator(26)
    print(
        "ItaliansArenaSimulator initialized cleanly (wood decay step =",
        s.rules.wood_decay_step_seconds,
        "s; Feudal eff =",
        s.rules.feudal_macro_efficiency,
        "; Castle+ eff =",
        s.rules.castle_macro_efficiency,
        ").",
    )

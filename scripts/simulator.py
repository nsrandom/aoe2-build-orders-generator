#!/usr/bin/env python3
"""
Shared 1-Second Discrete-Event Build-Order Simulator.

Enforces the authoritative rules in `rules.md` via `RuleConfig` and `AoE2Database`:
- Effective gather rates with drop-off round trips & WB/HC speed scaling (rule 3.2, 2.11)
- Per-lumber-camp efficiency decay (-1%/20s, 60% floor) & mover-only reset (rule 3.4)
- Scheduled sheep discovery (4 at 0:00, +2 at 1:30, +2 at 2:30; rule 1.3)
- Deer pushing schedule (starts at 9 food vils under TC, +30s first, +35s interval, Dark Age only; rule 3.8)
- Animal rot, carcass caps, and sheep-vs-boar protection (rules 3.5-3.7)
- Real farm expiration & 15s reseed interruption (rule 3.10)
- Dynamic Market pricing (100W/115F/130S, 70%/130%, +/-2 per 100 traded, min 20; rule 7.2)
- Relic gold (0.5 G/s; rule 7.3) & macro efficiency buffers (92% Feudal, 90% Castle+; rule 8.2)
- Housing cap tracking on completion, negative bank detection, and late-command robustness (rules 4.3, 8.3)
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from aoe2_data import (
    ANIMALS,
    AoE2Database,
    MarketState,
    ResourceBundle,
    RuleConfig,
    get_farm_capacity,
)


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


class BuildOrderSimulator:
    """Shared 1-second resolution simulation engine for all build orders."""

    def __init__(
        self,
        civ: str = "Generic",
        db: Optional[AoE2Database] = None,
        rules: RuleConfig = RuleConfig(),
        *,
        sheep_count: int = 8,
        boar_count: int = 2,
        deer_count: int = 0,
        chicken_count: int = 6,
        fast_castle_mode: bool = False,
        do_opening_houses: bool = True,
    ) -> None:
        self.db = db or AoE2Database()
        self.rules = rules
        self.civ = civ
        self.fast_castle_mode = fast_castle_mode

        self.time_s: int = 0
        self.age: int = 1
        self.feudal_clicked: bool = False
        self.in_age_transition: bool = False
        self.bank: ResourceBundle = self.db.get_starting_resources(civ)
        self.total_gathered: ResourceBundle = ResourceBundle()
        self.rotted_food: Dict[str, float] = {
            "sheep": 0.0,
            "boar": 0.0,
            "deer": 0.0,
            "chicken": 0.0,
        }

        # Sheep discovery schedule (rule 1.3): 4 near TC, +2 at 1:30, +2 at 2:30
        initial_sheep = min(sheep_count, self.rules.sheep_initial_near_tc)
        self.undiscovered_sheep: int = max(0, sheep_count - initial_sheep)
        self.sheep_discovery_schedule: List[int] = list(self.rules.sheep_discovery_times_s)

        # Deer pushing schedule (rule 3.8): pushed in Dark Age once 9 vils on food under TC
        self.unpushed_deer: int = deer_count
        self.deer_push_started: bool = False
        self.next_deer_arrival_s: Optional[int] = None

        self.remaining_animals: Dict[str, int] = {
            "sheep": initial_sheep,
            "boar": boar_count,
            "deer": 0,  # pushed deer become available on arrival
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

        # Per-lumber-camp efficiency tracking (rule 3.4)
        self.lumber_camps: List[Dict[str, int]] = []
        self.lc_completed_s: Optional[int] = None
        self.lc_count: int = 0

        self.relics_garrisoned: int = 0
        self.upgrades: set[str] = set()
        self.buildings: List[str] = ["town center"]
        self.pending_buildings: List[Tuple[int, str]] = []  # (complete_t, name)
        self.pending_pop_buildings: List[Tuple[int, int]] = []  # (complete_t, pop_granted)
        self.housing_cap: int = 5  # starting TC (rule 4.3)

        # Villager pool (rule 1.5 opening)
        if do_opening_houses:
            self.vils: List[Dict[str, object]] = [
                {"id": 1, "role": "sheep", "busy_until": 24, "busy_desc": "Build House 1 (2v) + walk"},
                {"id": 2, "role": "sheep", "busy_until": 24, "busy_desc": "Build House 1 (2v) + walk"},
                {"id": 3, "role": "sheep", "busy_until": 30, "busy_desc": "Build House 2 (1v) + walk"},
            ]
            self.bank = self.bank - ResourceBundle(wood=50)
            self.pending_pop_buildings.append((19, 5))
            self.pending_pop_buildings.append((25, 5))
        else:
            self.vils = [
                {"id": 1, "role": "sheep", "busy_until": 0},
                {"id": 2, "role": "sheep", "busy_until": 0},
                {"id": 3, "role": "sheep", "busy_until": 0},
            ]

        # Multi-TC state
        self.tc_count: int = 1
        self.tc_busy_until: List[int] = [0]
        self.tc_action: List[str] = ["idle"]
        self.tc_idle_s: int = 0
        self.tc1_idle_before_imp_s: int = 0
        self.tc1_idle_castle_s: int = 0

        # Pending upgrade research completions: (complete_t, upgrade_name)
        self.pending_upgrades: List[Tuple[int, str]] = []

        # Farm state (rule 3.10): each farm tracks remaining food & reseed_ready_t
        self.farms: List[Dict[str, float]] = []
        self.farms_seeded: int = 0
        self.farms_reseeded: int = 0
        self.farm_idle_seconds: int = 0

        # Dynamic Market state (rule 7.2)
        self.market = MarketState.from_rules(self.rules)
        self.market_trades: List[Dict[str, object]] = []

        self.logs: List[SimActionLog] = []
        self.military_units: Dict[str, int] = {"scout": 1}
        self.casualties: Dict[str, int] = {}
        self.warnings: List[str] = []
        self.negative_bank_events: List[str] = []

    def fmt_time(self, t: Optional[int] = None) -> str:
        sec = self.time_s if t is None else t
        return f"{sec // 60:02d}:{sec % 60:02d}"

    def total_pop(self) -> int:
        return len(self.vils) + sum(self.military_units.values())

    def pop_cap(self) -> int:
        return min(200, self.housing_cap)

    def free_pop(self) -> int:
        return self.pop_cap() - self.total_pop()

    def house_threshold(self, producing_mil_buildings: int = 0, extra_tcs: int = 0) -> int:
        """Pop room threshold at which a new house is started (rule 4.4)."""
        return self.rules.house_room_buffer + producing_mil_buildings + extra_tcs

    def add_pending_pop_building(self, complete_t: int, pop_amount: int, name: str = "house") -> None:
        self.pending_pop_buildings.append((complete_t, pop_amount))
        self.buildings.append(name.lower())

    def add_building(self, name: str, complete_t: int) -> None:
        key = name.lower()
        if self.time_s >= complete_t:
            self.buildings.append(key)
        else:
            self.pending_buildings.append((complete_t, key))

    def has_building(self, name: str) -> bool:
        key = name.lower()
        return any(b.lower() == key for b in self.buildings)

    def queue_upgrade(self, name: str, complete_t: int) -> None:
        key = name.lower()
        if key in ("horse collar", "heavy plow", "crop rotation") and not self.has_building("mill"):
            raise ValueError(f"Cannot research {name} without a completed Mill (rule 3.10)")
        self.pending_upgrades.append((complete_t, key))

    def add_lumber_camp(self, completed_s: int) -> int:
        idx = len(self.lumber_camps)
        self.lumber_camps.append({"completed_s": completed_s})
        self.lc_completed_s = completed_s
        self.lc_count = len(self.lumber_camps)
        return idx

    def camp_wood_efficiency(self, camp_idx: int) -> float:
        """Wood efficiency for a specific Lumber Camp (rule 3.4: -1% per 20s, floor 60%)."""
        if camp_idx < 0 or camp_idx >= len(self.lumber_camps):
            return 1.0
        comp_t = self.lumber_camps[camp_idx]["completed_s"]
        if self.time_s <= comp_t:
            return 1.0
        elapsed = self.time_s - comp_t
        steps = int(elapsed // int(self.rules.wood_decay_step_seconds))
        return max(
            self.rules.wood_efficiency_floor,
            1.0 - self.rules.wood_decay_per_step * steps,
        )

    def wood_efficiency(self) -> float:
        """Average active woodcutter camp efficiency (or latest camp if no woodcutters)."""
        wood_vils = [v for v in self.vils if v["role"] == "wood"]
        if not wood_vils:
            if not self.lumber_camps:
                return 1.0
            return self.camp_wood_efficiency(len(self.lumber_camps) - 1)
        return sum(self.camp_wood_efficiency(int(v.get("camp_idx", 0))) for v in wood_vils) / len(wood_vils)

    def min_active_camp_efficiency(self) -> float:
        wood_vils = [v for v in self.vils if v["role"] == "wood"]
        if not wood_vils or not self.lumber_camps:
            return 1.0
        return min(self.camp_wood_efficiency(int(v.get("camp_idx", 0))) for v in wood_vils)

    def reassign_woodcutters_to_new_camp(self, camp_idx: int, count: int) -> int:
        """Moves up to `count` woodcutters from older camps/stragglers to `camp_idx` with 15s walk (rule 2.6, 3.4)."""
        moved = 0
        # Prefer moving from the oldest/lowest-efficiency camp first
        candidates = [
            v for v in self.vils
            if v["role"] == "wood" and int(v.get("camp_idx", 0)) != camp_idx and self.time_s >= int(v["busy_until"])
        ]
        candidates.sort(key=lambda v: int(v.get("camp_idx", 0)))
        for v in candidates:
            if moved >= count:
                break
            v["camp_idx"] = camp_idx
            v["busy_until"] = self.time_s + int(self.rules.site_to_site_walk_time_one_way)
            moved += 1
        return moved

    def macro_efficiency(self) -> float:
        """Applies imperfect execution buffer (rule 8.2: 92% Feudal for non-FC, 90% Castle+)."""
        if self.age == 1:
            return 1.0
        if self.age == 2:
            return 1.0 if self.fast_castle_mode else self.rules.feudal_macro_efficiency
        return self.rules.castle_macro_efficiency

    def farm_capacity(self) -> float:
        return get_farm_capacity(self.upgrades)

    def register_new_farm(self, ready_t: Optional[int] = None) -> None:
        if self.civ != "Khmer" and not self.has_building("mill"):
            raise ValueError("Cannot build Farm without a completed Mill (rule 3.10)")
        self.farms.append(
            {
                "remaining": self.farm_capacity(),
                "reseed_ready_t": float(self.time_s if ready_t is None else ready_t),
            }
        )
        self.farms_seeded += 1

    def count_role(self, *roles: str) -> int:
        return sum(1 for v in self.vils if v["role"] in roles)

    def spend(self, cost: ResourceBundle, label: str = "") -> bool:
        """Deducts `cost` from bank and records a violation if bank goes negative (rule 4.2)."""
        ok = self.bank.can_afford(cost)
        self.bank = self.bank - cost
        if not ok:
            self.negative_bank_events.append(
                f"[{self.fmt_time()}] Negative bank on {label}: cost={cost}, after={self.bank}"
            )
        return ok

    def market_sell_price(self, resource: str) -> int:
        return self.market.sell_price(resource)

    def sell_at_market(self, resource: str, amount: int = 100) -> int:
        """Sells `amount` (multiple of 100) at dynamic Market price (rule 7.2)."""
        gold_gained = self.market.sell(resource, amount)
        res_key = resource.lower()
        if res_key == "food":
            self.bank = self.bank - ResourceBundle(food=amount) + ResourceBundle(gold=gold_gained)
        elif res_key == "wood":
            self.bank = self.bank - ResourceBundle(wood=amount) + ResourceBundle(gold=gold_gained)
        elif res_key == "stone":
            self.bank = self.bank - ResourceBundle(stone=amount) + ResourceBundle(gold=gold_gained)
        self.market_trades.append(
            {
                "t": self.time_s,
                "ts": self.fmt_time(),
                "sold": f"{amount} {res_key}",
                "gold_gained": gold_gained,
                "rate": gold_gained // (amount // 100),
            }
        )
        return gold_gained

    def current_macro_alloc(self) -> Dict[str, int]:
        out = {"food": 0, "wood": 0, "gold": 0, "stone": 0}
        for v in self.vils:
            r = str(v["role"])
            if r == "forward":
                r = str(v.get("orig_role", "wood"))
            if r in ("sheep", "boar", "deer", "deer_mill", "chicken_mill", "chicken_ld", "berries", "farm"):
                out["food"] += 1
            elif r in ("straggler", "wood"):
                out["wood"] += 1
            elif r in ("gold", "gold_ld"):
                out["gold"] += 1
            elif r in ("stone", "stone_ld"):
                out["stone"] += 1
            else:
                out["wood"] += 1
        return out

    def current_food_breakdown(self) -> Dict[str, int]:
        fb = {"sheep": 0, "boar": 0, "deer": 0, "chicken": 0, "berries": 0, "farm": 0}
        for v in self.vils:
            r = str(v["role"])
            if r in ("sheep", "boar", "deer", "berries", "farm"):
                fb[r] += 1
            elif r == "deer_mill":
                fb["deer"] += 1
            elif r in ("chicken_mill", "chicken_ld"):
                fb["chicken"] += 1
        return fb

    def _process_scheduled_events(self) -> None:
        # 1) Housing / pop completions (rule 4.3)
        remaining_pop: List[Tuple[int, int]] = []
        for comp_t, pop_amt in self.pending_pop_buildings:
            if self.time_s >= comp_t:
                self.housing_cap += pop_amt
            else:
                remaining_pop.append((comp_t, pop_amt))
        self.pending_pop_buildings = remaining_pop

        # 1b) Completed buildings (e.g. Mill prerequisite for Farms & Horse Collar; rule 3.10)
        remaining_bldgs: List[Tuple[int, str]] = []
        for comp_t, b_name in self.pending_buildings:
            if self.time_s >= comp_t:
                self.buildings.append(b_name)
            else:
                remaining_bldgs.append((comp_t, b_name))
        self.pending_buildings = remaining_bldgs

        # 2) Pending upgrade completions (rule 11.4)
        remaining_upg: List[Tuple[int, str]] = []
        for comp_t, upg_name in self.pending_upgrades:
            if self.time_s >= comp_t:
                self.upgrades.add(upg_name)
            else:
                remaining_upg.append((comp_t, upg_name))
        self.pending_upgrades = remaining_upg

        # 3) Sheep discovery (rule 1.3: +2 at 1:30, +2 at 2:30)
        while self.sheep_discovery_schedule and self.time_s >= self.sheep_discovery_schedule[0]:
            self.sheep_discovery_schedule.pop(0)
            found = min(2, self.undiscovered_sheep)
            if found > 0:
                self.undiscovered_sheep -= found
                self.remaining_animals["sheep"] += found

        # 4) Deer pushing (rule 3.8: starts at 9 vils on food under TC, +30s first, +35s interval, Dark Age only)
        if not self.feudal_clicked and self.unpushed_deer > 0:
            food_under_tc = self.count_role("sheep", "boar", "deer")
            if not self.deer_push_started and food_under_tc >= self.rules.deer_push_min_food_vils:
                self.deer_push_started = True
                self.next_deer_arrival_s = self.time_s + self.rules.deer_push_first_delay_s
            if self.deer_push_started and self.next_deer_arrival_s is not None and self.time_s >= self.next_deer_arrival_s:
                self.unpushed_deer -= 1
                self.remaining_animals["deer"] += 1
                if self.unpushed_deer > 0:
                    self.next_deer_arrival_s = self.time_s + self.rules.deer_push_interval_s
                else:
                    self.next_deer_arrival_s = None

    def _harvest_carcass(
        self,
        anim_key: str,
        role_key: str,
        n_vils: int,
        boar_active: bool = False,
    ) -> float:
        spec = ANIMALS[anim_key]
        if n_vils <= 0:
            if self.active_carcass_food[anim_key] > 0:
                rot = min(self.active_carcass_food[anim_key], spec.decay_rate)
                self.active_carcass_food[anim_key] -= rot
                self.rotted_food[anim_key] += rot
            return 0.0

        max_allowed = spec.max_vils + (1 if anim_key == "boar" and self.in_age_transition else 0)
        if n_vils > max_allowed:
            self.warnings.append(
                f"[{self.fmt_time()}] {n_vils} vils on {anim_key} exceeds max ({max_allowed})"
            )

        if self.active_carcass_food[anim_key] <= 1e-6:
            if self.remaining_animals[anim_key] <= 0:
                return 0.0
            self.remaining_animals[anim_key] -= 1
            self.active_carcass_food[anim_key] = spec.initial_food

        r_vil = self.db.get_gather_rate(
            role_key,
            civ=self.civ,
            upgrades=list(self.upgrades),
            rules=self.rules,
            include_dropoff=True,
        )
        gather = n_vils * r_vil * self.macro_efficiency()
        rot = spec.decay_rate
        tot = gather + rot
        avail = self.active_carcass_food[anim_key]

        if tot <= avail:
            self.active_carcass_food[anim_key] -= tot
            self.rotted_food[anim_key] += rot
            return gather

        frac = avail / tot
        g1 = gather * frac
        r1 = rot * frac
        self.active_carcass_food[anim_key] = 0.0
        self.rotted_food[anim_key] += r1

        # Rule 3.7: never slaughter a new sheep while a boar carcass is open under the TC
        if anim_key == "sheep" and boar_active:
            boar_cnt = self.count_role("boar")
            boar_cap = 10 if self.in_age_transition else ANIMALS["boar"].max_vils
            for v in self.vils:
                if v["role"] == "sheep":
                    if boar_cnt < boar_cap:
                        v["role"] = "boar"
                        v["busy_until"] = max(int(v["busy_until"]), self.time_s + int(self.rules.tc_food_switch_walk_time))
                        boar_cnt += 1
                    else:
                        v["role"] = "straggler"
                        v["busy_until"] = max(int(v["busy_until"]), self.time_s + int(self.rules.straggler_walk_time))
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

    def tick_gather(
        self,
        boar_open: bool = False,
        reseed_reserve_w: float = 0.0,
        fallback_order: Tuple[str, ...] = ("boar", "deer", "chicken_mill", "chicken_ld"),
    ) -> None:
        """Advances world state by 1s: completions, discoveries, gathering, decay, and farm reseeding."""
        self._process_scheduled_events()

        active: Dict[str, int] = {}
        for v in self.vils:
            if self.time_s >= int(v["busy_until"]):
                role = str(v["role"])
                active[role] = active.get(role, 0) + 1

        # Under-TC / hunt fallback when a carcass pool finishes (rule 3.12, 2.7, 2.8)
        for fallback_src in fallback_order:
            anim_name = (
                "chicken"
                if fallback_src in ("chicken_mill", "chicken_ld")
                else ("deer" if fallback_src == "deer_mill" else fallback_src)
            )
            if (
                active.get(fallback_src, 0) > 0
                and self.active_carcass_food[anim_name] <= 1e-6
                and self.remaining_animals[anim_name] <= 0
                and not (anim_name == "deer" and self.deer_push_started and self.unpushed_deer > 0)
            ):
                cur_sheep_vils = self.count_role("sheep")
                sheep_avail = (
                    self.active_carcass_food["sheep"] > 1e-6
                    or self.remaining_animals["sheep"] > 0
                )
                for v in self.vils:
                    if v["role"] == fallback_src and self.time_s >= int(v["busy_until"]):
                        if sheep_avail and cur_sheep_vils < ANIMALS["sheep"].max_vils:
                            v["role"] = "sheep"
                            v["busy_until"] = self.time_s + (
                                int(self.rules.camp_or_berry_walk_time_one_way)
                                if fallback_src in ("chicken_mill", "chicken_ld", "deer_mill")
                                else int(self.rules.tc_food_switch_walk_time)
                            )
                            cur_sheep_vils += 1
                            active["sheep"] = active.get("sheep", 0) + 1
                        elif self.straggler_wood > 1e-6:
                            v["role"] = "straggler"
                            v["busy_until"] = self.time_s + int(self.rules.straggler_walk_time)
                        else:
                            v["role"] = "wood"
                            v["camp_idx"] = max(0, len(self.lumber_camps) - 1)
                            v["busy_until"] = self.time_s + int(self.rules.camp_or_berry_walk_time_one_way)
                active.pop(fallback_src, None)

        # Sheep exhausted -> stragglers (3s) or LC wood (15s)
        if (
            active.get("sheep", 0) > 0
            and self.active_carcass_food["sheep"] <= 1e-6
            and self.remaining_animals["sheep"] <= 0
        ):
            for v in self.vils:
                if v["role"] == "sheep" and self.time_s >= int(v["busy_until"]):
                    if self.straggler_wood > 1e-6:
                        v["role"] = "straggler"
                        v["busy_until"] = self.time_s + int(self.rules.straggler_walk_time)
                    else:
                        v["role"] = "wood"
                        v["camp_idx"] = max(0, len(self.lumber_camps) - 1)
                        v["busy_until"] = self.time_s + int(self.rules.camp_or_berry_walk_time_one_way)
            active.pop("sheep", None)

        # Stragglers exhausted -> LC wood (15s)
        if active.get("straggler", 0) > 0 and self.straggler_wood <= 1e-6:
            for v in self.vils:
                if v["role"] == "straggler" and self.time_s >= int(v["busy_until"]):
                    v["role"] = "wood"
                    v["camp_idx"] = max(0, len(self.lumber_camps) - 1)
                    v["busy_until"] = self.time_s + int(self.rules.camp_or_berry_walk_time_one_way)
            active.pop("straggler", None)

        eff = self.macro_efficiency()
        boar_present = boar_open or self.active_carcass_food["boar"] > 1e-6
        upg_list = list(self.upgrades)

        # Animal gathering + rot (effective rates via aoe2_data)
        f_gain = 0.0
        f_gain += self._harvest_carcass("sheep", "sheep", active.get("sheep", 0), boar_active=boar_present)
        f_gain += self._harvest_carcass("boar", "boar", active.get("boar", 0))
        f_gain += self._harvest_carcass("deer", "deer", active.get("deer", 0))
        if active.get("chicken_mill", 0) > 0:
            f_gain += self._harvest_carcass("chicken", "chicken_mill", active["chicken_mill"])
        elif active.get("chicken_ld", 0) > 0:
            f_gain += self._harvest_carcass("chicken", "chicken_ld", active["chicken_ld"])
        else:
            f_gain += self._harvest_carcass("chicken", "chicken_mill", 0)

        # Berries (effective rate via aoe2_data)
        if active.get("berries", 0) > 0:
            if self.berries_food > 1e-6:
                r_berry = self.db.get_gather_rate("berries", civ=self.civ, upgrades=upg_list, rules=self.rules)
                bg = min(self.berries_food, active["berries"] * r_berry * eff)
                self.berries_food -= bg
                f_gain += bg
            else:
                for v in self.vils:
                    if v["role"] == "berries" and self.time_s >= int(v["busy_until"]):
                        v["role"] = "straggler" if self.straggler_wood > 1e-6 else "wood"
                        v["camp_idx"] = max(0, len(self.lumber_camps) - 1)
                        v["busy_until"] = self.time_s + int(self.rules.camp_or_berry_walk_time_one_way)

        # Farms with expiration, 15s reseed time, and idle if < 60W (rule 3.10)
        n_farmers = active.get("farm", 0)
        if n_farmers > 0:
            r_farm = self.db.get_gather_rate("farmer", civ=self.civ, upgrades=upg_list, rules=self.rules) * eff
            while len(self.farms) < n_farmers:
                self.farms.append({"remaining": self.farm_capacity(), "reseed_ready_t": float(self.time_s)})
            for i in range(n_farmers):
                f_obj = self.farms[i]
                if self.time_s < f_obj["reseed_ready_t"]:
                    continue  # farmer is spending 15s reseeding
                if f_obj["remaining"] > 1e-6:
                    g = min(f_obj["remaining"], r_farm)
                    f_obj["remaining"] -= g
                    f_gain += g
                if f_obj["remaining"] <= 1e-6:
                    if self.bank.wood >= (60.0 + reseed_reserve_w):
                        self.bank = self.bank - ResourceBundle(wood=60.0)
                        f_obj["remaining"] = self.farm_capacity()
                        f_obj["reseed_ready_t"] = float(self.time_s + 15)
                        self.farms_reseeded += 1
                    else:
                        self.farm_idle_seconds += 1

        # Wood: stragglers + per-camp lumberjacks (rule 3.4)
        w_gain = 0.0
        if active.get("straggler", 0) > 0 and self.straggler_wood > 0:
            r_strag = self.db.get_gather_rate("straggler", civ=self.civ, upgrades=upg_list, rules=self.rules) * eff
            sg = min(self.straggler_wood, active["straggler"] * r_strag)
            self.straggler_wood -= sg
            w_gain += sg

        for v in self.vils:
            if v["role"] == "wood" and self.time_s >= int(v["busy_until"]):
                c_idx = int(v.get("camp_idx", 0))
                c_eff = self.camp_wood_efficiency(c_idx)
                r_wood = self.db.get_gather_rate(
                    "lumberjack",
                    civ=self.civ,
                    upgrades=upg_list,
                    rules=self.rules,
                    wood_efficiency_override=c_eff,
                )
                w_gain += r_wood * eff

        # Gold (camp + LD + relics; rules 3.2, 7.3)
        g_gain = self.rules.relic_gold_per_sec * self.relics_garrisoned
        if active.get("gold", 0) > 0:
            r_gold = self.db.get_gather_rate("gold", civ=self.civ, upgrades=upg_list, rules=self.rules)
            g_gain += active["gold"] * r_gold * eff
        if active.get("gold_ld", 0) > 0:
            r_gold_ld = self.db.get_gather_rate("gold_ld", civ=self.civ, upgrades=upg_list, rules=self.rules)
            g_gain += active["gold_ld"] * r_gold_ld * eff

        # Stone (camp + LD)
        s_gain = 0.0
        if active.get("stone", 0) > 0:
            r_stone = self.db.get_gather_rate("stone", civ=self.civ, upgrades=upg_list, rules=self.rules)
            s_gain += active["stone"] * r_stone * eff
        if active.get("stone_ld", 0) > 0:
            r_stone_ld = self.db.get_gather_rate("stone_ld", civ=self.civ, upgrades=upg_list, rules=self.rules)
            s_gain += active["stone_ld"] * r_stone_ld * eff

        delta = ResourceBundle(food=f_gain, wood=w_gain, gold=g_gain, stone=s_gain)
        self.bank = self.bank + delta
        self.total_gathered = self.total_gathered + delta


def run_late_command_checks(
    label: str,
    run_once: Callable[[Callable[[int], int], Optional[int]], Dict[str, object]],
    baseline_clicks: Dict[str, int],
    rules: RuleConfig = RuleConfig(),
    chicken_check_counts: Optional[Tuple[int, ...]] = None,
    seed: int = 42,
) -> Dict[str, object]:
    """
    Executes rule 8.3 robustness suite:
    - Fixed +3s delay on every non-0:00 command
    - 20 runs with each command delayed by random [0, 5]s
    - Optional chicken count checks (e.g., 8 chickens instead of 6)
    Passes when TC is never housed, non-click TC idle <= 5s, and clicks <= 15s later than planned.
    """
    results: Dict[str, object] = {"label": label, "passed": True, "failures": [], "details": {}}

    def _eval(run_name: str, res: Dict[str, object]) -> None:
        housed = int(res.get("housed_seconds", 0))
        extra_idle = int(res.get("extra_tc_idle_s", 0))
        feudal_late = int(res.get("feudal_click_s", 0)) - baseline_clicks.get("feudal_click_s", 0) if "feudal_click_s" in baseline_clicks else 0
        castle_late = int(res.get("castle_click_s", 0)) - baseline_clicks.get("castle_click_s", 0) if "castle_click_s" in baseline_clicks else 0
        bad = []
        if housed > 0:
            bad.append(f"housed={housed}s")
        if extra_idle > int(rules.max_end_of_age_tc_idle_seconds):
            bad.append(f"extra_tc_idle={extra_idle}s")
        if feudal_late > rules.robustness_max_click_delay_s:
            bad.append(f"feudal_late=+{feudal_late}s")
        if castle_late > rules.robustness_max_click_delay_s:
            bad.append(f"castle_late=+{castle_late}s")
        if bad:
            results["passed"] = False
            results["failures"].append(f"{run_name}: {', '.join(bad)}")

    # 1) Fixed +3s late check
    res_3s = run_once(lambda t: 0 if t == 0 else t + rules.robustness_fixed_delay_s, None)
    _eval("+3s_all", res_3s)
    results["details"]["fixed_3s"] = res_3s

    # 2) 20 random 0-5s runs
    rng = random.Random(seed)
    worst_feudal = 0
    worst_castle = 0
    for i in range(rules.robustness_random_runs):
        delays: Dict[int, int] = {}

        def _jitter(t: int, _rng: random.Random = rng, _d: Dict[int, int] = delays) -> int:
            if t == 0:
                return 0
            if t not in _d:
                _d[t] = _rng.randint(0, rules.robustness_random_max_delay_s)
            return t + _d[t]

        res_i = run_once(_jitter, None)
        _eval(f"rand_{i+1}", res_i)
        if "feudal_click_s" in baseline_clicks:
            worst_feudal = max(worst_feudal, int(res_i.get("feudal_click_s", 0)) - baseline_clicks["feudal_click_s"])
        if "castle_click_s" in baseline_clicks:
            worst_castle = max(worst_castle, int(res_i.get("castle_click_s", 0)) - baseline_clicks["castle_click_s"])
    results["details"]["random_20_worst_delay_s"] = {"feudal": worst_feudal, "castle": worst_castle}

    # 3) Chicken count check (e.g. 8 chickens instead of 6)
    if chicken_check_counts:
        for cnt in chicken_check_counts:
            res_c = run_once(lambda t: t, cnt)
            _eval(f"{cnt}_chickens", res_c)
            results["details"][f"chickens_{cnt}"] = res_c

    return results


if __name__ == "__main__":
    sim = BuildOrderSimulator(civ="Italians", chicken_count=6, fast_castle_mode=True)
    print("Initialized BuildOrderSimulator for Italians; starting bank:", sim.bank)

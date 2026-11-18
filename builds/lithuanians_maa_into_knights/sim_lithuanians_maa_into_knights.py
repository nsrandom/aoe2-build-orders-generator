#!/usr/bin/env python3
"""
Build-specific simulator configuration for:
Lithuanians 20-Pop (19-Vil) 3 MAA -> Fast Castle Priority (1 TC) -> 2-Stable Knights + 3 Monks
(Arabia: 6 Chickens on a Mill, Checked with 8 Chickens).

Inherits the shared 1-second discrete-event engine from `scripts/simulator.py` and models
verified Lithuanians mechanics:
- +100 Food starting bonus on TC #1 and +100 Food on completing each additional Town Center (Update 81058)
- +20% faster working Monasteries (Monks 42.5s, Sanctity 50.0s, Fervor 41.67s)
- Relic bonus (+1 attack per garrisoned Relic to Knights/Leitis, up to +4; +0.5 G/s per Relic)
- Full dynamic Market trading (Rule 7.2)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from aoe2_data import AoE2Database, CIV_BUILD_BONUSES, ResourceBundle, RuleConfig
from simulator import BuildOrderSimulator, SimActionLog


class LithuaniansKnightSimulator(BuildOrderSimulator):
    def __init__(
        self,
        path_key: str,
        deer_count: int = 0,
        chicken_count: int = 6,
        db: Optional[AoE2Database] = None,
        rules: RuleConfig = RuleConfig(),
    ) -> None:
        super().__init__(
            civ="Lithuanians",
            db=db,
            rules=rules,
            sheep_count=8,
            boar_count=2,
            deer_count=deer_count,
            chicken_count=chicken_count,
            fast_castle_mode=False,
            do_opening_houses=True,
        )
        self.path_key = path_key
        self.extra_tc_food_bonus: float = float(
            CIV_BUILD_BONUSES.get("Lithuanians", {}).get("extra_tc_food_bonus", 100.0)
        )
        self.military_units.update(
            {
                "militia": 0,
                "knight": 0,
                "monk": 0,
                "mangonel": 0,
                "battering_ram": 0,
            }
        )

    def complete_extra_tc(self, time_s: Optional[int] = None) -> float:
        """Registers a completed additional Town Center and applies Lithuanians' +100F TC bonus."""
        now = self.time_s if time_s is None else time_s
        self.tc_count += 1
        self.tc_busy_until.append(now)
        self.tc_action.append("idle")
        bonus_f = self.extra_tc_food_bonus
        self.bank = self.bank + ResourceBundle(food=bonus_f)
        self.logs.append(
            SimActionLog(
                time_s=now,
                pop_total=self.total_pop(),
                vil_count=len(self.vils),
                age=self.age,
                description=f"TC #{self.tc_count} completed (+{int(bonus_f)}F Lithuanians bonus)",
                alloc=self.current_macro_alloc(),
                bank=ResourceBundle(
                    food=self.bank.food,
                    wood=self.bank.wood,
                    gold=self.bank.gold,
                    stone=self.bank.stone,
                ),
            )
        )
        return bonus_f

    def buy_at_market(self, resource: str, amount: int = 100) -> int:
        """Buys `amount` (multiple of 100) at dynamic Market price (Rule 7.2)."""
        gold_cost = self.market.buy(resource, amount)
        res_key = resource.lower()
        if self.bank.gold < gold_cost:
            raise ValueError(
                f"Insufficient gold to buy {amount} {res_key}: need {gold_cost}, have {self.bank.gold:.1f}"
            )
        if res_key == "food":
            self.bank = self.bank - ResourceBundle(gold=gold_cost) + ResourceBundle(food=amount)
        elif res_key == "wood":
            self.bank = self.bank - ResourceBundle(gold=gold_cost) + ResourceBundle(wood=amount)
        elif res_key == "stone":
            self.bank = self.bank - ResourceBundle(gold=gold_cost) + ResourceBundle(stone=amount)
        else:
            raise ValueError(f"Unsupported market commodity: {resource}")
        self.market_trades.append(
            {
                "t": self.time_s,
                "ts": self.fmt_time(),
                "bought": f"{amount} {res_key}",
                "gold_spent": gold_cost,
                "rate": gold_cost // (amount // 100),
            }
        )
        return gold_cost


__all__ = ["LithuaniansKnightSimulator", "SimActionLog"]

if __name__ == "__main__":
    s = LithuaniansKnightSimulator("1tc_fast_push", deer_count=0, chicken_count=6)
    print("LithuaniansKnightSimulator initialized; bank:", s.bank, "bonus/TC:", s.extra_tc_food_bonus)

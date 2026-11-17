#!/usr/bin/env python3
"""
Build-specific simulator configuration for:
Bohemians Arena Fast Castle Build Orders (6 Chickens Milled + Berry Mill, Checked w/ 8 Chickens;
Rules 1.4, 3.9, 6.2, 6.3, 8.2, 9.1).

Inherits the shared 1-second discrete-event engine from `scripts/simulator.py` and encodes
verified Bohemians civilization mechanics:
- Blacksmith (-100W -> 50W) and University (-100W -> 100W) wood discount (Monastery stays 175W per Update 61321)
- Free Mining Camp technologies on age-up (Feudal: Gold/Stone Mining; Castle: Gold/Stone Shaft Mining)
- Castle Age Chemistry & Hand Cannoneers (45F, 50G, 34s)
- Fervor (+15% villager speed) & Sanctity (+15 villager HP) affecting Villagers
- Spearman-line +25% bonus damage
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from aoe2_data import AoE2Database, ResourceBundle, RuleConfig
from simulator import BuildOrderSimulator, SimActionLog


class BohemiansArenaSimulator(BuildOrderSimulator):
    def __init__(
        self,
        dark_vils: int = 25,
        chicken_count: Optional[int] = None,
        db: Optional[AoE2Database] = None,
        rules: RuleConfig = RuleConfig(),
    ) -> None:
        chk = rules.arena_chicken_design_count if chicken_count is None else chicken_count
        super().__init__(
            civ="Bohemians",
            db=db,
            rules=rules,
            sheep_count=8,
            boar_count=2,
            deer_count=0,
            chicken_count=chk,
            fast_castle_mode=True,
            do_opening_houses=True,
        )
        self.dark_vils = dark_vils
        self.military_units.update(
            {
                "hand_cannoneer": 0,
                "mangonel": 0,
                "battering_ram": 0,
                "pikeman": 0,
                "monk": 0,
                "trebuchet": 0,
                "bombard_cannon": 0,
            }
        )
        self.casualties.update(
            {
                "hand_cannoneer": 0,
                "mangonel": 0,
                "battering_ram": 0,
                "pikeman": 0,
                "trebuchet": 0,
            }
        )

    def buy_at_market(self, resource: str, amount: int = 100) -> int:
        """Buys `amount` (multiple of 100) at dynamic Market price (rule 7.2)."""
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

    def villager_speed_mult(self) -> float:
        """Rule 2.11 + Bohemians Fervor villager movement speed bonus."""
        mult = 1.0
        if "wheelbarrow" in self.upgrades:
            mult *= 1.10
        if "hand cart" in self.upgrades:
            mult *= 1.10
        if "fervor" in self.upgrades:
            mult *= 1.15
        return mult


__all__ = ["BohemiansArenaSimulator", "SimActionLog"]

if __name__ == "__main__":
    s = BohemiansArenaSimulator(25)
    print(
        "BohemiansArenaSimulator initialized (starting bank =",
        s.bank,
        ", Feudal FC eff =",
        s.macro_efficiency(),
        ", Castle+ eff =",
        s.rules.castle_macro_efficiency,
        ").",
    )

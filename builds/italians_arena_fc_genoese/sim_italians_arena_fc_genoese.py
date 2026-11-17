#!/usr/bin/env python3
"""
Build-specific simulator configuration for:
Italians Arena Fast Castle Build Orders (6 Chickens Milled, Checked w/ 8, Rules 1.4, 3.9, 6.2, 6.3, 8.2).
Inherits the shared 1-second discrete-event engine from `scripts/simulator.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from aoe2_data import AoE2Database, RuleConfig
from simulator import BuildOrderSimulator, SimActionLog


class ItaliansArenaSimulator(BuildOrderSimulator):
    def __init__(
        self,
        dark_vils: int = 26,
        chicken_count: Optional[int] = None,
        db: Optional[AoE2Database] = None,
        rules: RuleConfig = RuleConfig(),
    ) -> None:
        chk = rules.arena_chicken_design_count if chicken_count is None else chicken_count
        super().__init__(
            civ="Italians",
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
                "genoese": 0,
                "light_cav": 0,
                "monk": 0,
                "battering_ram": 0,
                "trebuchet": 0,
                "bombard_cannon": 0,
            }
        )
        self.casualties.update(
            {
                "genoese": 0,
                "light_cav": 0,
                "battering_ram": 0,
                "bombard_cannon": 0,
            }
        )


__all__ = ["ItaliansArenaSimulator", "SimActionLog"]

if __name__ == "__main__":
    s = ItaliansArenaSimulator(26)
    print(
        "ItaliansArenaSimulator initialized (rules.md synced: wood floor =",
        s.rules.wood_efficiency_floor,
        ", Feudal FC eff =",
        s.macro_efficiency(),
        ", Castle+ eff =",
        s.rules.castle_macro_efficiency,
        ").",
    )

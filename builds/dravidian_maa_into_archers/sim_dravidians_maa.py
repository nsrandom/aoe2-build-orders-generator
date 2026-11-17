#!/usr/bin/env python3
"""
Build-specific simulator configuration for:
Dravidians 20-Pop (19-Vil) 3 MAA -> Archers (Arabia: 6 Chickens on a Mill / 8-Chicken Check).
Inherits the shared 1-second discrete-event engine from `scripts/simulator.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from aoe2_data import AoE2Database, RuleConfig
from simulator import BuildOrderSimulator, SimActionLog


class DravidiansSimulator(BuildOrderSimulator):
    def __init__(
        self,
        path_key: str,
        deer_count: int = 0,
        chicken_count: int = 6,
        db: Optional[AoE2Database] = None,
        rules: RuleConfig = RuleConfig(),
    ) -> None:
        super().__init__(
            civ="Dravidians",
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
        self.military_units.update(
            {
                "militia": 0,
                "spearman": 0,
                "archer": 0,
                "elephant_archer": 0,
                "light_cav": 0,
                "armored_elephant": 0,
            }
        )


__all__ = ["DravidiansSimulator", "SimActionLog"]

if __name__ == "__main__":
    s = DravidiansSimulator("1tc_xbow_lc_ram", deer_count=0, chicken_count=6)
    print("DravidiansSimulator initialized cleanly; bank:", s.bank)

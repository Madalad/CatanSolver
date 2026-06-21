"""Tier 2 — mid-game turn advisor (Phase 3). See plan.md §6.4.

Given a mid-game ``GameState``, recommends the current player's action(s) with a
per-action win-probability estimate.

* :func:`recommend_actions` — Phase 3.2 baseline: determinized flat Monte-Carlo over
  the legal actions (treats the position as fully observed).
* :func:`recommend_actions_pimc` — Phase 3.4: PIMC + UCT search that samples the hidden
  dev cards from the belief and looks ahead within each world.
* :func:`recommend_actions_ismcts` — one tree over information sets, re-determinized per
  iteration (fixes PIMC's strategy fusion).
"""

from .pimc import recommend_actions_ismcts, recommend_actions_pimc
from .turn_advisor import recommend_actions

__all__ = ["recommend_actions", "recommend_actions_pimc", "recommend_actions_ismcts"]

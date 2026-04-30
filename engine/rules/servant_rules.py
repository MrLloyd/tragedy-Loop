"""从者相关的共享目标集合。"""

from __future__ import annotations

from engine.game_state import GameState

_DEFAULT_SERVANT_TARGET_IDS = frozenset({"vip", "ojousama"})


def servant_target_ids(state: GameState, servant_id: str) -> set[str]:
    """返回从者当前会跟随 / 代死的目标集合。"""
    target_ids = set(_DEFAULT_SERVANT_TARGET_IDS)
    target_ids.update(state.trait_target_overrides.get(servant_id, set()))
    target_ids.discard(servant_id)
    return target_ids

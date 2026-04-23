"""运行时身份工具。"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from engine.models.character import CharacterState
from engine.models.identity import IdentityDef
from engine.rules.module_loader import load_module

if TYPE_CHECKING:
    from engine.game_state import GameState

_IDENTITY_FALLBACK_MODULES = ("basic_tragedy_x", "first_steps")
_RUNTIME_IDENTITY_CACHE: dict[str, IdentityDef] = {}


def apply_identity_change(
    state: "GameState",
    character_id: str,
    *,
    identity_id: str,
    reason: str | None = None,
) -> None:
    """显式应用身份变更效果。"""
    character = state.characters.get(character_id)
    if character is None:
        return
    _apply_identity_change(state, character, identity_id, reason=reason)


def _apply_identity_change(
    state: "GameState",
    character: CharacterState,
    identity_id: str,
    *,
    reason: str | None,
) -> bool:
    if identity_id != "平民" and identity_id not in state.identity_defs:
        fallback = _load_runtime_identity_def(identity_id)
        if fallback is None:
            raise ValueError(f"Unknown identity_id for runtime change: {identity_id}")
        state.identity_defs[identity_id] = fallback
    changed = (
        character.identity_id != identity_id
        or character.identity_change_reason != reason
    )
    character.identity_id = identity_id
    character.identity_change_reason = reason
    return changed


def _load_runtime_identity_def(identity_id: str) -> IdentityDef | None:
    cached = _RUNTIME_IDENTITY_CACHE.get(identity_id)
    if cached is not None:
        return copy.deepcopy(cached)

    for module_id in _IDENTITY_FALLBACK_MODULES:
        loaded = load_module(module_id)
        identity_def = loaded.identity_defs.get(identity_id)
        if identity_def is None:
            continue
        _RUNTIME_IDENTITY_CACHE[identity_id] = copy.deepcopy(identity_def)
        return copy.deepcopy(identity_def)

    return None

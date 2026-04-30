"""运行时 trait 聚合与派生层。"""

from __future__ import annotations

from engine.game_state import GameState
from engine.models.enums import Trait
from engine.rules.persistent_effects import settle_persistent_effects


def active_traits(state: GameState, character_id: str) -> set[Trait]:
    """角色当前生效 trait：基础 trait + 当前身份 trait + 运行时派生增减层。"""
    settle_persistent_effects(state)
    character = state.characters.get(character_id)
    if character is None:
        return set()

    traits = set(character.base_traits)
    identity_def = state.identity_defs.get(character.identity_id)
    if identity_def is not None:
        traits.update(identity_def.traits)
    traits.update(character.derived_traits)
    traits.difference_update(character.suppressed_traits)
    return traits


def has_trait(state: GameState, character_id: str, trait: Trait) -> bool:
    return trait in active_traits(state, character_id)


def add_derived_trait(state: GameState, character_id: str, trait: Trait) -> bool:
    character = state.characters.get(character_id)
    if character is None or trait in character.derived_traits:
        return False
    character.derived_traits.add(trait)
    return True


def suppress_trait(state: GameState, character_id: str, trait: Trait) -> bool:
    character = state.characters.get(character_id)
    if character is None or trait in character.suppressed_traits:
        return False
    character.suppressed_traits.add(trait)
    return True


def clear_derived_trait(state: GameState, character_id: str, trait: Trait) -> bool:
    character = state.characters.get(character_id)
    if character is None or trait not in character.derived_traits:
        return False
    character.derived_traits.remove(trait)
    return True


def clear_suppressed_trait(state: GameState, character_id: str, trait: Trait) -> bool:
    character = state.characters.get(character_id)
    if character is None or trait not in character.suppressed_traits:
        return False
    character.suppressed_traits.remove(trait)
    return True

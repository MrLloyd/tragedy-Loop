"""Phase 1 核心回归：状态机分支、同时裁定、事件触发链。"""

from __future__ import annotations

from engine.event_bus import EventBus, GameEventType
from engine.game_state import GameState
from engine.models.board import BoardState
from engine.models.ability import Ability
from engine.models.character import CharacterState
from engine.models.effects import Effect
from engine.models.enums import AbilityTiming, AbilityType, AreaId, CharacterLifeState, EffectType, GamePhase, Outcome, TokenType
from engine.models.identity import IdentityDef
from engine.phases.phase_base import LoopEndHandler, PhaseComplete
from engine.resolvers.atomic_resolver import AtomicResolver
from engine.resolvers.death_resolver import DeathResolver
from engine.rules.module_loader import apply_loaded_module, load_module
from engine.state_machine import StateMachine


def test_state_machine_loop_end_branches() -> None:
    sm = StateMachine()
    sm.current_phase = GamePhase.LOOP_END
    assert sm.advance(
        failure_reached=False,
        protagonist_dead=False,
        is_last_loop=False,
        has_final_guess=True,
    ) == GamePhase.GAME_END

    sm.current_phase = GamePhase.LOOP_END
    assert sm.advance(
        failure_reached=True,
        protagonist_dead=False,
        is_last_loop=False,
        has_final_guess=True,
    ) == GamePhase.NEXT_LOOP

    sm.current_phase = GamePhase.LOOP_END
    assert sm.advance(
        failure_reached=True,
        protagonist_dead=False,
        is_last_loop=True,
        has_final_guess=True,
    ) == GamePhase.FINAL_GUESS

    sm.current_phase = GamePhase.LOOP_END
    assert sm.advance(
        failure_reached=True,
        protagonist_dead=False,
        is_last_loop=True,
        has_final_guess=False,
    ) == GamePhase.GAME_END

def test_state_machine_force_loop_end_jump() -> None:
    sm = StateMachine()
    sm.current_phase = GamePhase.INCIDENT
    sm.force_loop_end()

    assert sm.advance() == GamePhase.LOOP_END


def test_atomic_resolver_death_has_priority_over_failure() -> None:
    bus = EventBus()
    resolver = AtomicResolver(bus, DeathResolver())
    state = GameState.create_minimal_test_state()

    result = resolver.resolve(
        state,
        effects=[
            Effect(effect_type=EffectType.PROTAGONIST_DEATH, value="test"),
            Effect(effect_type=EffectType.PROTAGONIST_FAILURE, value="test"),
        ],
        sequential=False,
    )

    assert result.outcome == Outcome.PROTAGONIST_DEATH
    assert any(e.event_type == GameEventType.PROTAGONIST_DEATH for e in bus.log)
    assert not any(e.event_type == GameEventType.PROTAGONIST_FAILURE for e in bus.log)


def test_atomic_resolver_failure_when_soldier_blocks_death() -> None:
    bus = EventBus()
    resolver = AtomicResolver(bus, DeathResolver())
    state = GameState.create_minimal_test_state()
    state.soldier_protection_active = True

    result = resolver.resolve(
        state,
        effects=[
            Effect(effect_type=EffectType.PROTAGONIST_DEATH, value="test"),
            Effect(effect_type=EffectType.PROTAGONIST_FAILURE, value="test"),
        ],
        sequential=False,
    )

    assert result.outcome == Outcome.PROTAGONIST_FAILURE
    assert state.protagonist_dead is False
    assert any(e.event_type == GameEventType.PROTAGONIST_FAILURE for e in bus.log)


def test_game_state_available_enterable_areas_filters_forbidden_areas() -> None:
    state = GameState.create_minimal_test_state()
    state.characters["mover"] = CharacterState(
        character_id="mover",
        name="移动者",
        area=AreaId.SHRINE,
        initial_area=AreaId.SHRINE,
        identity_id="平民",
        original_identity_id="平民",
        base_forbidden_areas=[AreaId.HOSPITAL, AreaId.CITY],
        forbidden_areas=[AreaId.HOSPITAL, AreaId.CITY],
    )

    assert state.get_character_forbidden_areas("mover") == [AreaId.HOSPITAL, AreaId.CITY]
    assert state.can_character_enter_area("mover", AreaId.HOSPITAL) is False
    assert state.can_character_enter_area("mover", AreaId.SCHOOL) is True
    assert state.available_enterable_areas(
        "mover",
        [AreaId.HOSPITAL, AreaId.SCHOOL, AreaId.SHRINE, AreaId.CITY],
    ) == [AreaId.SCHOOL.value, AreaId.SHRINE.value]


def test_character_state_activity_helpers_distinguish_removed_from_dead() -> None:
    alive = CharacterState(
        character_id="alive",
        name="存活者",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="平民",
        original_identity_id="平民",
    )
    corpse = CharacterState(
        character_id="corpse",
        name="尸体",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="平民",
        original_identity_id="平民",
        life_state=CharacterLifeState.DEAD,
    )
    removed = CharacterState(
        character_id="removed",
        name="移除者",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="平民",
        original_identity_id="平民",
        life_state=CharacterLifeState.REMOVED,
    )

    assert alive.is_active() is True
    assert alive.is_dead() is False
    assert alive.life_state == CharacterLifeState.ALIVE
    assert corpse.is_active() is False
    assert corpse.is_dead() is True
    assert corpse.life_state == CharacterLifeState.DEAD
    assert removed.is_active() is False
    assert removed.is_dead() is False
    assert removed.life_state == CharacterLifeState.REMOVED
    assert removed.is_removed() is True


def test_character_life_state_helpers_switch_explicit_states() -> None:
    character = CharacterState(
        character_id="sample",
        name="样本",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="平民",
        original_identity_id="平民",
    )

    assert character.life_state == CharacterLifeState.ALIVE

    character.mark_dead()
    assert character.life_state == CharacterLifeState.DEAD
    assert character.is_dead() is True

    character.mark_removed()
    assert character.life_state == CharacterLifeState.REMOVED
    assert character.is_removed() is True

    character.mark_alive()
    assert character.life_state == CharacterLifeState.ALIVE
    assert character.is_active() is True


def test_atomic_resolver_move_character_respects_forbidden_areas() -> None:
    bus = EventBus()
    resolver = AtomicResolver(bus, DeathResolver())
    state = GameState.create_minimal_test_state()
    state.characters["mover"] = CharacterState(
        character_id="mover",
        name="移动者",
        area=AreaId.SHRINE,
        initial_area=AreaId.SHRINE,
        identity_id="平民",
        original_identity_id="平民",
        base_forbidden_areas=[AreaId.SCHOOL],
        forbidden_areas=[AreaId.SCHOOL],
    )

    result = resolver.resolve(
        state,
        effects=[Effect(effect_type=EffectType.MOVE_CHARACTER, target="mover", value=AreaId.SCHOOL.value)],
        sequential=False,
    )

    assert result.outcome == Outcome.NONE
    assert state.characters["mover"].area == AreaId.SHRINE
    assert not any(e.event_type == GameEventType.CHARACTER_MOVED for e in bus.log)


def test_atomic_resolver_remove_character_uses_unified_life_state() -> None:
    bus = EventBus()
    resolver = AtomicResolver(bus, DeathResolver())
    state = GameState.create_minimal_test_state()
    state.characters["target"] = CharacterState(
        character_id="target",
        name="目标",
        area=AreaId.SHRINE,
        initial_area=AreaId.SHRINE,
        identity_id="平民",
        original_identity_id="平民",
    )

    resolver.resolve(
        state,
        effects=[Effect(effect_type=EffectType.REMOVE_CHARACTER, target="target")],
        sequential=False,
    )
    assert state.characters["target"].life_state == CharacterLifeState.REMOVED
    assert state.characters["target"].is_removed() is True


def test_board_state_adjacency_handles_grid_and_faraway() -> None:
    board = BoardState()

    assert board.get_horizontal_adjacent(AreaId.HOSPITAL) == AreaId.SHRINE
    assert board.get_vertical_adjacent(AreaId.HOSPITAL) == AreaId.CITY
    assert board.get_diagonal_adjacent(AreaId.HOSPITAL) == AreaId.SCHOOL
    assert board.get_clockwise_adjacent(AreaId.HOSPITAL) == AreaId.SHRINE
    assert board.get_counterclockwise_adjacent(AreaId.HOSPITAL) == AreaId.CITY
    assert board.get_all_adjacent(AreaId.HOSPITAL) == [AreaId.SHRINE, AreaId.CITY]
    assert board.is_adjacent(AreaId.HOSPITAL, AreaId.SHRINE) is True
    assert board.is_adjacent(AreaId.HOSPITAL, AreaId.SCHOOL) is False

    assert board.get_horizontal_adjacent(AreaId.FARAWAY) is None
    assert board.get_vertical_adjacent(AreaId.FARAWAY) is None
    assert board.get_diagonal_adjacent(AreaId.FARAWAY) is None
    assert board.get_clockwise_adjacent(AreaId.FARAWAY) is None
    assert board.get_counterclockwise_adjacent(AreaId.FARAWAY) is None
    assert board.get_all_adjacent(AreaId.FARAWAY) == []
    assert board.is_adjacent(AreaId.FARAWAY, AreaId.HOSPITAL) is False


def test_game_state_move_character_handles_valid_and_invalid_targets() -> None:
    state = GameState.create_minimal_test_state()
    state.characters["mover"] = CharacterState(
        character_id="mover",
        name="移动者",
        area=AreaId.HOSPITAL,
        initial_area=AreaId.HOSPITAL,
        identity_id="平民",
        original_identity_id="平民",
    )

    assert state.move_character("mover", AreaId.HOSPITAL) is False
    assert state.move_character("mover", AreaId.SHRINE.value) is True
    assert state.characters["mover"].area == AreaId.SHRINE

    state.characters["mover"].mark_dead()
    assert state.move_character("mover", AreaId.SCHOOL) is False
    state.characters["mover"].mark_alive()
    state.characters["mover"].mark_removed()
    assert state.move_character("mover", AreaId.CITY) is False


def test_loop_end_handler_emits_loop_ended_event() -> None:
    bus = EventBus()
    resolver = AtomicResolver(bus, DeathResolver())
    handler = LoopEndHandler(bus, resolver)
    state = GameState.create_minimal_test_state()
    state.current_loop = 2

    signal = handler.execute(state)

    assert isinstance(signal, PhaseComplete)
    assert any(
        e.event_type == GameEventType.LOOP_ENDED and e.data.get("loop") == 2
        for e in bus.log
    )


def test_on_death_ability_is_published_and_triggered() -> None:
    bus = EventBus()
    resolver = AtomicResolver(bus, DeathResolver())
    state = GameState()
    loaded = load_module("first_steps")
    apply_loaded_module(state, loaded)

    state.characters["key"] = CharacterState(
        character_id="key",
        name="关键人物",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="key_person",
        original_identity_id="key_person",
    )

    result = resolver.resolve(
        state,
        effects=[Effect(effect_type=EffectType.KILL_CHARACTER, target="key")],
        sequential=False,
    )

    assert result.outcome == Outcome.PROTAGONIST_FAILURE
    assert any(
        e.event_type == GameEventType.ABILITY_DECLARED
        and e.data.get("ability_id") == "key_person_on_death"
        for e in bus.log
    )
    assert any(e.event_type == GameEventType.PROTAGONIST_FAILURE for e in bus.log)


def test_derived_on_death_ability_is_published_and_triggered() -> None:
    bus = EventBus()
    resolver = AtomicResolver(bus, DeathResolver())
    state = GameState()
    loaded = load_module("basic_tragedy_x")
    apply_loaded_module(state, loaded)

    state.characters["unstable"] = CharacterState(
        character_id="unstable",
        name="不安定因子",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="unstable_factor",
        original_identity_id="unstable_factor",
    )
    state.board.areas[AreaId.SCHOOL].tokens.add(TokenType.INTRIGUE, 2)
    state.board.areas[AreaId.CITY].tokens.add(TokenType.INTRIGUE, 2)

    result = resolver.resolve(
        state,
        effects=[Effect(effect_type=EffectType.KILL_CHARACTER, target="unstable")],
        sequential=False,
    )

    assert result.outcome == Outcome.PROTAGONIST_FAILURE
    assert "key_person_dead" in state.failure_flags
    assert any(
        e.event_type == GameEventType.ABILITY_DECLARED
        and e.data.get("ability_id") == "key_person_on_death"
        and e.data.get("source_kind") == "derived"
        for e in bus.log
    )
    assert any(e.event_type == GameEventType.PROTAGONIST_FAILURE for e in bus.log)


def test_on_other_death_ability_is_published_and_triggered() -> None:
    bus = EventBus()
    resolver = AtomicResolver(bus, DeathResolver())
    state = GameState()
    loaded = load_module("basic_tragedy_x")
    apply_loaded_module(state, loaded)

    state.characters["beloved"] = CharacterState(
        character_id="beloved",
        name="心上人",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="beloved",
        original_identity_id="beloved",
    )
    state.characters["lover"] = CharacterState(
        character_id="lover",
        name="求爱者",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="lover",
        original_identity_id="lover",
    )

    result = resolver.resolve(
        state,
        effects=[Effect(effect_type=EffectType.KILL_CHARACTER, target="lover")],
        sequential=False,
    )

    assert result.outcome == Outcome.NONE
    assert state.characters["beloved"].tokens.get(TokenType.PARANOIA) == 6
    assert any(
        e.event_type == GameEventType.ABILITY_DECLARED
        and e.data.get("ability_id") == "beloved_on_lover_death_gain_paranoia"
        for e in bus.log
    )


def test_lover_gains_paranoia_when_beloved_dies() -> None:
    bus = EventBus()
    resolver = AtomicResolver(bus, DeathResolver())
    state = GameState()
    loaded = load_module("basic_tragedy_x")
    apply_loaded_module(state, loaded)

    state.characters["beloved"] = CharacterState(
        character_id="beloved",
        name="心上人",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="beloved",
        original_identity_id="beloved",
    )
    state.characters["lover"] = CharacterState(
        character_id="lover",
        name="求爱者",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="lover",
        original_identity_id="lover",
    )

    result = resolver.resolve(
        state,
        effects=[Effect(effect_type=EffectType.KILL_CHARACTER, target="beloved")],
        sequential=False,
    )

    assert result.outcome == Outcome.NONE
    assert state.characters["lover"].tokens.get(TokenType.PARANOIA) == 6
    assert any(
        e.event_type == GameEventType.ABILITY_DECLARED
        and e.data.get("ability_id") == "lover_on_beloved_death_gain_paranoia"
        for e in bus.log
    )


def test_beloved_and_lover_do_not_gain_paranoia_when_they_die_simultaneously() -> None:
    bus = EventBus()
    resolver = AtomicResolver(bus, DeathResolver())
    state = GameState()
    loaded = load_module("basic_tragedy_x")
    apply_loaded_module(state, loaded)

    state.characters["beloved"] = CharacterState(
        character_id="beloved",
        name="心上人",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="beloved",
        original_identity_id="beloved",
    )
    state.characters["lover"] = CharacterState(
        character_id="lover",
        name="求爱者",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="lover",
        original_identity_id="lover",
    )

    result = resolver.resolve(
        state,
        effects=[
            Effect(effect_type=EffectType.KILL_CHARACTER, target="beloved"),
            Effect(effect_type=EffectType.KILL_CHARACTER, target="lover"),
        ],
        sequential=False,
    )

    declared_ids = [
        e.data.get("ability_id")
        for e in bus.log
        if e.event_type == GameEventType.ABILITY_DECLARED
    ]

    assert result.outcome == Outcome.NONE
    assert state.characters["beloved"].life_state == CharacterLifeState.DEAD
    assert state.characters["lover"].life_state == CharacterLifeState.DEAD
    assert state.characters["beloved"].tokens.get(TokenType.PARANOIA) == 0
    assert state.characters["lover"].tokens.get(TokenType.PARANOIA) == 0
    assert "beloved_on_lover_death_gain_paranoia" not in declared_ids
    assert "lover_on_beloved_death_gain_paranoia" not in declared_ids


def test_same_batch_deaths_still_collect_all_on_death_effects() -> None:
    bus = EventBus()
    resolver = AtomicResolver(bus, DeathResolver())
    state = GameState()
    state.identity_defs["death_burst"] = IdentityDef(
        identity_id="death_burst",
        name="死亡爆发",
        module="test",
        abilities=[
            Ability(
                ability_id="death_burst_on_death",
                name="死亡时放置密谋",
                ability_type=AbilityType.MANDATORY,
                timing=AbilityTiming.ON_DEATH,
                effects=[
                    Effect(
                        effect_type=EffectType.PLACE_TOKEN,
                        target={"scope": "same_area", "subject": "board"},
                        token_type=TokenType.INTRIGUE,
                        amount=1,
                    )
                ],
            )
        ],
    )
    state.characters["a"] = CharacterState(
        character_id="a",
        name="A",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="death_burst",
        original_identity_id="death_burst",
    )
    state.characters["b"] = CharacterState(
        character_id="b",
        name="B",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="death_burst",
        original_identity_id="death_burst",
    )

    resolver.resolve(
        state,
        effects=[
            Effect(effect_type=EffectType.KILL_CHARACTER, target="a"),
            Effect(effect_type=EffectType.KILL_CHARACTER, target="b"),
        ],
        sequential=False,
    )

    assert state.characters["a"].life_state == CharacterLifeState.DEAD
    assert state.characters["b"].life_state == CharacterLifeState.DEAD
    assert state.board.areas[AreaId.SCHOOL].tokens.get(TokenType.INTRIGUE) == 2
    declared_ids = [
        e.data.get("ability_id")
        for e in bus.log
        if e.event_type == GameEventType.ABILITY_DECLARED
    ]
    assert declared_ids.count("death_burst_on_death") == 2


def test_same_batch_dead_character_does_not_trigger_on_other_death() -> None:
    bus = EventBus()
    resolver = AtomicResolver(bus, DeathResolver())
    state = GameState()
    state.identity_defs["death_echo"] = IdentityDef(
        identity_id="death_echo",
        name="死亡回响",
        module="test",
        abilities=[
            Ability(
                ability_id="death_echo_on_other_death",
                name="他者死亡时回响",
                ability_type=AbilityType.MANDATORY,
                timing=AbilityTiming.ON_OTHER_DEATH,
                effects=[
                    Effect(
                        effect_type=EffectType.PLACE_TOKEN,
                        target={"scope": "same_area", "subject": "other_character"},
                        token_type=TokenType.PARANOIA,
                        amount=1,
                    )
                ],
            )
        ],
    )
    state.characters["a"] = CharacterState(
        character_id="a",
        name="A",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="death_echo",
        original_identity_id="death_echo",
    )
    state.characters["b"] = CharacterState(
        character_id="b",
        name="B",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="death_echo",
        original_identity_id="death_echo",
    )

    resolver.resolve(
        state,
        effects=[
            Effect(effect_type=EffectType.KILL_CHARACTER, target="a"),
            Effect(effect_type=EffectType.KILL_CHARACTER, target="b"),
        ],
        sequential=False,
    )

    assert state.characters["a"].life_state == CharacterLifeState.DEAD
    assert state.characters["b"].life_state == CharacterLifeState.DEAD
    assert state.characters["a"].tokens.get(TokenType.PARANOIA) == 0
    assert state.characters["b"].tokens.get(TokenType.PARANOIA) == 0


def test_earlier_dead_character_is_not_targeted_by_later_death_trigger_without_corpse_rule() -> None:
    bus = EventBus()
    resolver = AtomicResolver(bus, DeathResolver())
    state = GameState()
    state.identity_defs["death_echo"] = IdentityDef(
        identity_id="death_echo",
        name="死亡回响",
        module="test",
        abilities=[
            Ability(
                ability_id="death_echo_on_other_death",
                name="他者死亡时回响",
                ability_type=AbilityType.MANDATORY,
                timing=AbilityTiming.ON_OTHER_DEATH,
                effects=[
                    Effect(
                        effect_type=EffectType.PLACE_TOKEN,
                        target={"scope": "same_area", "subject": "other_character"},
                        token_type=TokenType.PARANOIA,
                        amount=1,
                    )
                ],
            )
        ],
    )
    state.characters["a"] = CharacterState(
        character_id="a",
        name="A",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="death_echo",
        original_identity_id="death_echo",
    )
    state.characters["b"] = CharacterState(
        character_id="b",
        name="B",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="death_echo",
        original_identity_id="death_echo",
    )

    resolver.resolve(
        state,
        effects=[
            Effect(effect_type=EffectType.KILL_CHARACTER, target="a"),
            Effect(effect_type=EffectType.KILL_CHARACTER, target="b"),
        ],
        sequential=True,
    )

    assert state.characters["a"].life_state == CharacterLifeState.DEAD
    assert state.characters["b"].life_state == CharacterLifeState.DEAD
    assert state.characters["a"].tokens.get(TokenType.PARANOIA) == 0
    assert state.characters["b"].tokens.get(TokenType.PARANOIA) == 0

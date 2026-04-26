from __future__ import annotations

from engine.event_bus import EventBus, GameEventType
from engine.game_state import GameState
from engine.models.ability import Ability
from engine.models.cards import ActionCard, CardPlacement
from engine.models.character import CharacterState
from engine.models.effects import Effect
from engine.models.enums import AbilityTiming, AbilityType, AreaId, CardType, EffectType, PlayerRole, TokenType
from engine.models.identity import IdentityDef
from engine.models.script import CharacterSetup
from engine.phases.phase_base import (
    ActionResolveHandler,
    ForceLoopEnd,
    FinalGuessHandler,
    LoopEndHandler,
    LoopStartHandler,
    PhaseComplete,
    PlaywrightAbilityHandler,
    ProtagonistAbilityHandler,
    TurnEndHandler,
    WaitForInput,
)
from engine.resolvers.atomic_resolver import AtomicResolver
from engine.resolvers.death_resolver import DeathResolver
from engine.rules.module_loader import apply_loaded_module, build_game_state_from_module, load_module
from engine.visibility import Visibility


def _resolver_bundle() -> tuple[EventBus, AtomicResolver]:
    bus = EventBus()
    return bus, AtomicResolver(bus, DeathResolver())


def _ability_choice(wait: WaitForInput, ability_id: str):
    return next(
        option for option in wait.options
        if getattr(option, "ability", None) is not None
        and option.ability.ability_id == ability_id
    )


def _install_identity(state: GameState, identity_id: str, abilities: list[Ability]) -> None:
    state.identity_defs[identity_id] = IdentityDef(
        identity_id=identity_id,
        name=identity_id,
        module="test",
        abilities=abilities,
    )


def test_loop_start_handler_executes_friend_reveal_effect() -> None:
    bus, resolver = _resolver_bundle()
    handler = LoopStartHandler(bus, resolver)
    state = GameState()
    apply_loaded_module(state, load_module("basic_tragedy_x"))
    state.characters["friend"] = CharacterState(
        character_id="friend",
        name="亲友",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="friend",
        original_identity_id="friend",
        revealed=True,
    )

    signal = handler.execute(state)

    assert isinstance(signal, PhaseComplete)
    assert state.characters["friend"].tokens.get(TokenType.GOODWILL) == 1


def test_loop_start_handler_applies_causal_line_from_last_snapshot() -> None:
    bus, resolver = _resolver_bundle()
    handler = LoopStartHandler(bus, resolver)
    state = GameState()
    loaded = load_module("basic_tragedy_x")
    apply_loaded_module(state, loaded)
    state.script.rules_x = [
        next(rule for rule in loaded.module_def.rules_x if rule.rule_id == "btx_causal_line")
    ]
    state.characters["survivor"] = CharacterState(
        character_id="survivor",
        name="角色A",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.characters["dead"] = CharacterState(
        character_id="dead",
        name="角色B",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="平民",
        original_identity_id="平民",
        is_alive=False,
    )
    state.characters["survivor"].tokens.add(TokenType.GOODWILL, 1)
    state.characters["dead"].tokens.add(TokenType.GOODWILL, 2)
    state.save_loop_snapshot()
    state.reset_for_new_loop()

    signal = handler.execute(state)

    assert isinstance(signal, PhaseComplete)
    assert state.characters["survivor"].tokens.get(TokenType.PARANOIA) == 2
    assert state.characters["dead"].tokens.get(TokenType.PARANOIA) == 2


def test_loop_start_handler_applies_causal_line_and_friend_reveal_together() -> None:
    bus, resolver = _resolver_bundle()
    handler = LoopStartHandler(bus, resolver)
    state = GameState()
    loaded = load_module("basic_tragedy_x")
    apply_loaded_module(state, loaded)
    state.script.rules_x = [
        next(rule for rule in loaded.module_def.rules_x if rule.rule_id == "btx_causal_line")
    ]
    state.characters["friend"] = CharacterState(
        character_id="friend",
        name="亲友",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="friend",
        original_identity_id="friend",
        revealed=True,
    )
    state.characters["friend"].tokens.add(TokenType.GOODWILL, 1)
    state.save_loop_snapshot()
    state.reset_for_new_loop()
    state.characters["friend"].revealed = True

    signal = handler.execute(state)

    assert isinstance(signal, PhaseComplete)
    assert state.characters["friend"].tokens.get(TokenType.PARANOIA) == 2
    assert state.characters["friend"].tokens.get(TokenType.GOODWILL) == 1


def test_playwright_ability_handler_declares_and_resolves_targeted_ability() -> None:
    bus, resolver = _resolver_bundle()
    handler = PlaywrightAbilityHandler(bus, resolver)
    state = GameState()
    apply_loaded_module(state, load_module("first_steps"))
    state.characters["mastermind"] = CharacterState(
        character_id="mastermind",
        name="主谋",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="mastermind",
        original_identity_id="mastermind",
    )
    state.characters["target"] = CharacterState(
        character_id="target",
        name="目标",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="平民",
        original_identity_id="平民",
    )

    signal = handler.execute(state)

    assert isinstance(signal, WaitForInput)
    assert signal.input_type == "choose_playwright_ability"
    choice = next(
        option for option in signal.options
        if getattr(option, "ability", None) is not None
        and option.ability.ability_id == "mastermind_playwright_place_intrigue_character"
    )
    target_wait = signal.callback(choice)
    assert isinstance(target_wait, WaitForInput)
    assert target_wait.input_type == "choose_ability_target"

    follow_up = target_wait.callback("target")

    assert isinstance(follow_up, WaitForInput)
    assert state.characters["target"].tokens.get(TokenType.INTRIGUE) == 1
    assert any(
        event.event_type == GameEventType.ABILITY_DECLARED
        and event.data.get("ability_id") == "mastermind_playwright_place_intrigue_character"
        for event in bus.log
    )


def test_mastermind_playwright_ability_places_intrigue_on_board() -> None:
    bus, resolver = _resolver_bundle()
    handler = PlaywrightAbilityHandler(bus, resolver)
    state = GameState()
    apply_loaded_module(state, load_module("first_steps"))
    state.characters["mastermind"] = CharacterState(
        character_id="mastermind",
        name="主谋",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="mastermind",
        original_identity_id="mastermind",
    )

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    choice = _ability_choice(signal, "mastermind_playwright_place_intrigue_board")

    follow_up = signal.callback(choice)

    assert isinstance(follow_up, WaitForInput)
    assert state.board.areas[AreaId.SCHOOL].tokens.get(TokenType.INTRIGUE) == 1
    assert any(
        event.event_type == GameEventType.ABILITY_DECLARED
        and event.data.get("ability_id") == "mastermind_playwright_place_intrigue_board"
        for event in bus.log
    )


def test_rumormonger_playwright_ability_places_paranoia_in_same_area() -> None:
    bus, resolver = _resolver_bundle()
    handler = PlaywrightAbilityHandler(bus, resolver)
    state = GameState()
    apply_loaded_module(state, load_module("first_steps"))
    state.characters["rumor"] = CharacterState(
        character_id="rumor",
        name="传谣人",
        area=AreaId.HOSPITAL,
        initial_area=AreaId.HOSPITAL,
        identity_id="rumormonger",
        original_identity_id="rumormonger",
    )
    state.characters["target"] = CharacterState(
        character_id="target",
        name="目标",
        area=AreaId.HOSPITAL,
        initial_area=AreaId.HOSPITAL,
        identity_id="平民",
        original_identity_id="平民",
    )

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    choice = _ability_choice(signal, "rumormonger_playwright_place_paranoia")
    target_wait = signal.callback(choice)
    assert isinstance(target_wait, WaitForInput)

    follow_up = target_wait.callback("target")

    assert isinstance(follow_up, WaitForInput)
    assert state.characters["target"].tokens.get(TokenType.PARANOIA) == 1
    assert any(
        event.event_type == GameEventType.ABILITY_DECLARED
        and event.data.get("ability_id") == "rumormonger_playwright_place_paranoia"
        for event in bus.log
    )


def test_unstable_factor_derives_rumormonger_through_playwright_handler() -> None:
    bus, resolver = _resolver_bundle()
    handler = PlaywrightAbilityHandler(bus, resolver)
    state = GameState()
    apply_loaded_module(state, load_module("basic_tragedy_x"))
    state.characters["unstable"] = CharacterState(
        character_id="unstable",
        name="不安定因子",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="unstable_factor",
        original_identity_id="unstable_factor",
    )
    state.characters["target"] = CharacterState(
        character_id="target",
        name="目标",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.board.areas[AreaId.SCHOOL].tokens.add(TokenType.INTRIGUE, 2)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    choice = _ability_choice(signal, "rumormonger_playwright_place_paranoia")

    target_wait = signal.callback(choice)
    assert isinstance(target_wait, WaitForInput)

    follow_up = target_wait.callback("target")

    assert isinstance(follow_up, WaitForInput)
    assert state.characters["target"].tokens.get(TokenType.PARANOIA) == 1
    assert any(
        event.event_type == GameEventType.ABILITY_DECLARED
        and event.data.get("ability_id") == "rumormonger_playwright_place_paranoia"
        for event in bus.log
    )


def test_action_resolve_handler_executes_time_traveler_mandatory_before_cards() -> None:
    bus, resolver = _resolver_bundle()
    handler = ActionResolveHandler(bus, resolver)
    state = GameState()
    apply_loaded_module(state, load_module("basic_tragedy_x"))
    state.characters["traveler"] = CharacterState(
        character_id="traveler",
        name="时间旅者",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="time_traveler",
        original_identity_id="time_traveler",
    )
    state.placed_cards = [
        CardPlacement(
            ActionCard(CardType.FORBID_GOODWILL, PlayerRole.MASTERMIND),
            PlayerRole.MASTERMIND,
            "character",
            "traveler",
            face_down=True,
        ),
        CardPlacement(
            ActionCard(CardType.GOODWILL_PLUS_1, PlayerRole.PROTAGONIST_0),
            PlayerRole.PROTAGONIST_0,
            "character",
            "traveler",
            face_down=True,
        ),
    ]

    signal = handler.execute(state)

    assert isinstance(signal, PhaseComplete)
    assert all(not placement.face_down for placement in state.placed_cards)
    assert state.placed_cards[0].nullified is True
    assert state.placed_cards[1].nullified is False
    assert state.characters["traveler"].tokens.get(TokenType.GOODWILL) == 1
    assert any(
        event.event_type == GameEventType.ABILITY_DECLARED
        and event.data.get("ability_id") == "time_traveler_action_resolve_ignore_forbid_goodwill"
        for event in bus.log
    )


def test_action_resolve_handler_prompts_and_executes_cultist_optional_character_nullify() -> None:
    bus, resolver = _resolver_bundle()
    handler = ActionResolveHandler(bus, resolver)
    state = GameState()
    apply_loaded_module(state, load_module("basic_tragedy_x"))
    state.characters["cultist"] = CharacterState(
        character_id="cultist",
        name="邪教徒",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="cultist",
        original_identity_id="cultist",
    )
    state.characters["target"] = CharacterState(
        character_id="target",
        name="目标",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.characters["other"] = CharacterState(
        character_id="other",
        name="其他目标",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.placed_cards = [
        CardPlacement(
            ActionCard(CardType.FORBID_INTRIGUE, PlayerRole.PROTAGONIST_0),
            PlayerRole.PROTAGONIST_0,
            "character",
            "target",
            face_down=True,
        ),
        CardPlacement(
            ActionCard(CardType.FORBID_INTRIGUE, PlayerRole.PROTAGONIST_1),
            PlayerRole.PROTAGONIST_1,
            "character",
            "other",
            face_down=True,
        ),
        CardPlacement(
            ActionCard(CardType.INTRIGUE_PLUS_1, PlayerRole.MASTERMIND),
            PlayerRole.MASTERMIND,
            "character",
            "target",
            face_down=True,
        ),
    ]

    signal = handler.execute(state)

    assert isinstance(signal, WaitForInput)
    assert signal.input_type == "choose_action_resolve_ability"
    choice = _ability_choice(signal, "cultist_action_resolve_nullify_forbid_intrigue_character")
    target_wait = signal.callback(choice)
    assert isinstance(target_wait, WaitForInput)
    assert target_wait.input_type == "choose_ability_target"

    next_wait = target_wait.callback("target")
    assert isinstance(next_wait, WaitForInput)
    assert next_wait.input_type == "choose_action_resolve_ability"

    result = next_wait.callback("pass")

    assert isinstance(result, PhaseComplete)
    assert state.placed_cards[0].nullified is True
    assert state.placed_cards[1].nullified is False
    assert state.characters["target"].tokens.get(TokenType.INTRIGUE) == 1
    assert any(
        event.event_type == GameEventType.ABILITY_DECLARED
        and event.data.get("ability_id") == "cultist_action_resolve_nullify_forbid_intrigue_character"
        for event in bus.log
    )


def test_action_resolve_handler_executes_cultist_board_nullify_without_target_prompt() -> None:
    bus, resolver = _resolver_bundle()
    handler = ActionResolveHandler(bus, resolver)
    state = GameState()
    apply_loaded_module(state, load_module("basic_tragedy_x"))
    state.characters["cultist"] = CharacterState(
        character_id="cultist",
        name="邪教徒",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="cultist",
        original_identity_id="cultist",
    )
    state.placed_cards = [
        CardPlacement(
            ActionCard(CardType.FORBID_INTRIGUE, PlayerRole.PROTAGONIST_0),
            PlayerRole.PROTAGONIST_0,
            "board",
            AreaId.SCHOOL.value,
            face_down=True,
        ),
        CardPlacement(
            ActionCard(CardType.INTRIGUE_PLUS_1, PlayerRole.MASTERMIND),
            PlayerRole.MASTERMIND,
            "board",
            AreaId.SCHOOL.value,
            face_down=True,
        ),
    ]

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    choice = _ability_choice(signal, "cultist_action_resolve_nullify_forbid_intrigue_board")
    result = signal.callback(choice)

    assert isinstance(result, PhaseComplete)
    assert state.placed_cards[0].nullified is True
    assert state.placed_cards[1].nullified is False
    assert state.board.areas[AreaId.SCHOOL].tokens.get(TokenType.INTRIGUE) == 1


def test_protagonist_ability_handler_supports_refuse_and_allow() -> None:
    bus, resolver = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, resolver)
    state = GameState()
    state.characters["ai"] = CharacterState(
        character_id="ai",
        name="AI",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
        goodwill_ability_texts=["能力1", "", "", ""],
        goodwill_ability_goodwill_requirements=[1, 0, 0, 0],
        goodwill_ability_once_per_loop=[False],
    )
    state.characters["ai"].tokens.add(TokenType.GOODWILL, 2)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    choice = next(option for option in signal.options if getattr(option, "ability", None) is not None)

    refuse_wait = signal.callback(choice)
    assert isinstance(refuse_wait, WaitForInput)
    assert refuse_wait.input_type == "respond_goodwill_ability"
    next_signal = refuse_wait.callback("refuse")
    assert isinstance(next_signal, WaitForInput)
    assert state.characters["ai"].tokens.get(TokenType.GOODWILL) == 2
    assert any(event.event_type == GameEventType.ABILITY_REFUSED for event in bus.log)

    allow_wait = next_signal.callback(choice)
    assert isinstance(allow_wait, WaitForInput)
    done = allow_wait.callback("allow")
    assert isinstance(done, WaitForInput)
    assert state.characters["ai"].tokens.get(TokenType.GOODWILL) == 2


def test_protagonist_ability_refuse_consumes_once_per_loop_without_spending_goodwill() -> None:
    bus, resolver = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, resolver)
    state = GameState()
    state.characters["ai"] = CharacterState(
        character_id="ai",
        name="AI",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
        goodwill_ability_texts=["能力1", "", "", ""],
        goodwill_ability_goodwill_requirements=[1, 0, 0, 0],
        goodwill_ability_once_per_loop=[True],
    )
    state.characters["ai"].tokens.add(TokenType.GOODWILL, 2)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    choice = next(option for option in signal.options if getattr(option, "ability", None) is not None)
    refuse_wait = signal.callback(choice)
    assert isinstance(refuse_wait, WaitForInput)

    next_signal = refuse_wait.callback("refuse")

    assert isinstance(next_signal, PhaseComplete)
    assert state.characters["ai"].tokens.get(TokenType.GOODWILL) == 2
    assert any(event.event_type == GameEventType.ABILITY_REFUSED for event in bus.log)


def test_protagonist_ability_ignores_refusal_when_identity_ignores_goodwill() -> None:
    bus, resolver = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, resolver)
    state = GameState()
    apply_loaded_module(state, load_module("first_steps"))
    state.characters["killer"] = CharacterState(
        character_id="killer",
        name="杀手",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="killer",
        original_identity_id="killer",
        goodwill_ability_texts=["能力1", "", "", ""],
        goodwill_ability_goodwill_requirements=[1, 0, 0, 0],
        goodwill_ability_once_per_loop=[False],
    )
    state.characters["killer"].tokens.add(TokenType.GOODWILL, 1)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    choice = next(option for option in signal.options if getattr(option, "ability", None) is not None)
    follow_up = signal.callback(choice)

    assert isinstance(follow_up, WaitForInput)
    assert state.characters["killer"].tokens.get(TokenType.GOODWILL) == 1


def test_turn_end_handler_executes_mandatory_then_optional() -> None:
    bus, resolver = _resolver_bundle()
    handler = TurnEndHandler(bus, resolver)
    state = GameState()
    apply_loaded_module(state, load_module("first_steps"))
    state.characters["serial"] = CharacterState(
        character_id="serial",
        name="杀人狂",
        area=AreaId.SHRINE,
        initial_area=AreaId.SHRINE,
        identity_id="serial_killer",
        original_identity_id="serial_killer",
    )
    state.characters["victim"] = CharacterState(
        character_id="victim",
        name="牺牲者",
        area=AreaId.SHRINE,
        initial_area=AreaId.SHRINE,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.characters["killer"] = CharacterState(
        character_id="killer",
        name="杀手",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="killer",
        original_identity_id="killer",
    )
    state.characters["key"] = CharacterState(
        character_id="key",
        name="关键人物",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="key_person",
        original_identity_id="key_person",
    )
    state.characters["key"].tokens.add(TokenType.INTRIGUE, 2)

    signal = handler.execute(state)

    assert isinstance(signal, WaitForInput)
    assert not state.characters["victim"].is_alive
    assert signal.input_type == "choose_turn_end_ability"


def test_killer_turn_end_ability_kills_key_person_and_forces_loop_end() -> None:
    bus, resolver = _resolver_bundle()
    handler = TurnEndHandler(bus, resolver)
    state = GameState()
    apply_loaded_module(state, load_module("first_steps"))
    state.characters["killer"] = CharacterState(
        character_id="killer",
        name="杀手",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="killer",
        original_identity_id="killer",
    )
    state.characters["key"] = CharacterState(
        character_id="key",
        name="关键人物",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="key_person",
        original_identity_id="key_person",
    )
    state.characters["key"].tokens.add(TokenType.INTRIGUE, 2)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    choice = _ability_choice(signal, "killer_turn_end_kill_key_person")

    result = signal.callback(choice)

    assert isinstance(result, ForceLoopEnd)
    assert result.reason == "killer_turn_end_kill_key_person"
    assert not state.characters["key"].is_alive
    assert "key_person_dead" in state.failure_flags


def test_killer_turn_end_ability_causes_protagonist_death_at_four_intrigue() -> None:
    bus, resolver = _resolver_bundle()
    handler = TurnEndHandler(bus, resolver)
    state = GameState()
    apply_loaded_module(state, load_module("first_steps"))
    state.characters["killer"] = CharacterState(
        character_id="killer",
        name="杀手",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="killer",
        original_identity_id="killer",
    )
    state.characters["killer"].tokens.add(TokenType.INTRIGUE, 4)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    choice = _ability_choice(signal, "killer_turn_end_protagonist_death")

    result = signal.callback(choice)

    assert isinstance(result, ForceLoopEnd)
    assert result.reason == "killer_turn_end_protagonist_death"
    assert state.protagonist_dead is True


def test_serial_killer_mandatory_turn_end_ability_kills_other_lone_character() -> None:
    bus, resolver = _resolver_bundle()
    handler = TurnEndHandler(bus, resolver)
    state = GameState()
    apply_loaded_module(state, load_module("first_steps"))
    state.characters["serial"] = CharacterState(
        character_id="serial",
        name="杀人狂",
        area=AreaId.SHRINE,
        initial_area=AreaId.SHRINE,
        identity_id="serial_killer",
        original_identity_id="serial_killer",
    )
    state.characters["victim"] = CharacterState(
        character_id="victim",
        name="牺牲者",
        area=AreaId.SHRINE,
        initial_area=AreaId.SHRINE,
        identity_id="平民",
        original_identity_id="平民",
    )

    signal = handler.execute(state)

    assert isinstance(signal, PhaseComplete)
    assert state.characters["serial"].is_alive
    assert not state.characters["victim"].is_alive
    assert any(
        event.event_type == GameEventType.ABILITY_DECLARED
        and event.data.get("ability_id") == "serial_killer_turn_end_kill_lone_target"
        for event in bus.log
    )


def test_turn_end_handler_batches_mandatory_effects_in_same_window() -> None:
    bus, resolver = _resolver_bundle()
    handler = TurnEndHandler(bus, resolver)
    state = GameState()
    apply_loaded_module(state, load_module("basic_tragedy_x"))
    _install_identity(
        state,
        "batch_killer_a",
        [
            Ability(
                ability_id="batch_killer_a_turn_end",
                name="批次杀手A",
                ability_type=AbilityType.MANDATORY,
                timing=AbilityTiming.TURN_END,
                effects=[Effect(effect_type=EffectType.KILL_CHARACTER, target="beloved")],
            )
        ],
    )
    _install_identity(
        state,
        "batch_killer_b",
        [
            Ability(
                ability_id="batch_killer_b_turn_end",
                name="批次杀手B",
                ability_type=AbilityType.MANDATORY,
                timing=AbilityTiming.TURN_END,
                effects=[Effect(effect_type=EffectType.KILL_CHARACTER, target="lover")],
            )
        ],
    )
    state.characters["killer_a"] = CharacterState(
        character_id="killer_a",
        name="杀手A",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="batch_killer_a",
        original_identity_id="batch_killer_a",
    )
    state.characters["killer_b"] = CharacterState(
        character_id="killer_b",
        name="杀手B",
        area=AreaId.HOSPITAL,
        initial_area=AreaId.HOSPITAL,
        identity_id="batch_killer_b",
        original_identity_id="batch_killer_b",
    )
    state.characters["beloved"] = CharacterState(
        character_id="beloved",
        name="心上人",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="beloved",
        original_identity_id="beloved",
    )
    state.characters["lover"] = CharacterState(
        character_id="lover",
        name="求爱者",
        area=AreaId.SHRINE,
        initial_area=AreaId.SHRINE,
        identity_id="lover",
        original_identity_id="lover",
    )

    signal = handler.execute(state)

    assert isinstance(signal, PhaseComplete)
    assert state.characters["beloved"].is_alive is False
    assert state.characters["lover"].is_alive is False
    assert state.characters["beloved"].tokens.get(TokenType.PARANOIA) == 0
    assert state.characters["lover"].tokens.get(TokenType.PARANOIA) == 0


def test_single_mandatory_turn_end_preserves_ability_reason() -> None:
    bus, resolver = _resolver_bundle()
    handler = TurnEndHandler(bus, resolver)
    state = GameState()
    apply_loaded_module(state, load_module("basic_tragedy_x"))
    _install_identity(
        state,
        "force_end_identity",
        [
            Ability(
                ability_id="force_end_turn_end",
                name="强制结束",
                ability_type=AbilityType.MANDATORY,
                timing=AbilityTiming.TURN_END,
                effects=[
                    Effect(effect_type=EffectType.FORCE_LOOP_END, target={"ref": "none"}),
                ],
            )
        ],
    )
    state.characters["forcer"] = CharacterState(
        character_id="forcer",
        name="执行者",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="force_end_identity",
        original_identity_id="force_end_identity",
    )

    signal = handler.execute(state)

    assert isinstance(signal, ForceLoopEnd)
    assert signal.reason == "force_end_turn_end"


def test_turn_end_handler_collects_all_mandatory_choices_before_resolution() -> None:
    bus, resolver = _resolver_bundle()
    handler = TurnEndHandler(bus, resolver)
    state = GameState()
    apply_loaded_module(state, load_module("basic_tragedy_x"))
    _install_identity(
        state,
        "choice_killer_a",
        [
            Ability(
                ability_id="choice_killer_a_turn_end",
                name="选目标A",
                ability_type=AbilityType.MANDATORY,
                timing=AbilityTiming.TURN_END,
                effects=[
                    Effect(
                        effect_type=EffectType.PLACE_TOKEN,
                        target={"scope": "any_area", "subject": "character"},
                        token_type=TokenType.INTRIGUE,
                        amount=1,
                    )
                ],
            )
        ],
    )
    _install_identity(
        state,
        "choice_killer_b",
        [
            Ability(
                ability_id="choice_killer_b_turn_end",
                name="选目标B",
                ability_type=AbilityType.MANDATORY,
                timing=AbilityTiming.TURN_END,
                effects=[
                    Effect(
                        effect_type=EffectType.PLACE_TOKEN,
                        target={"scope": "any_area", "subject": "character"},
                        token_type=TokenType.PARANOIA,
                        amount=1,
                    )
                ],
            )
        ],
    )
    state.characters["chooser_a"] = CharacterState(
        character_id="chooser_a",
        name="选择者A",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="choice_killer_a",
        original_identity_id="choice_killer_a",
    )
    state.characters["chooser_b"] = CharacterState(
        character_id="chooser_b",
        name="选择者B",
        area=AreaId.HOSPITAL,
        initial_area=AreaId.HOSPITAL,
        identity_id="choice_killer_b",
        original_identity_id="choice_killer_b",
    )
    state.characters["target_a"] = CharacterState(
        character_id="target_a",
        name="目标A",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.characters["target_b"] = CharacterState(
        character_id="target_b",
        name="目标B",
        area=AreaId.SHRINE,
        initial_area=AreaId.SHRINE,
        identity_id="平民",
        original_identity_id="平民",
    )

    wait = handler.execute(state)

    assert isinstance(wait, WaitForInput)
    assert wait.input_type == "choose_ability_target"
    follow_up = wait.callback("target_a")

    assert isinstance(follow_up, WaitForInput)
    assert state.characters["target_a"].tokens.get(TokenType.INTRIGUE) == 0
    assert state.characters["target_b"].tokens.get(TokenType.PARANOIA) == 0

    result = follow_up.callback("target_b")

    assert isinstance(result, PhaseComplete)
    assert state.characters["target_a"].tokens.get(TokenType.INTRIGUE) == 1
    assert state.characters["target_b"].tokens.get(TokenType.PARANOIA) == 1


def test_turn_end_handler_executes_time_traveler_final_day_failure() -> None:
    bus, resolver = _resolver_bundle()
    handler = TurnEndHandler(bus, resolver)
    state = GameState()
    state.script.days_per_loop = 3
    state.current_day = 3
    apply_loaded_module(state, load_module("basic_tragedy_x"))
    state.characters["traveler"] = CharacterState(
        character_id="traveler",
        name="时间旅者",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="time_traveler",
        original_identity_id="time_traveler",
    )
    state.characters["traveler"].tokens.add(TokenType.GOODWILL, 2)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    choice = next(
        option for option in signal.options
        if getattr(option, "ability", None) is not None
        and option.ability.ability_id == "time_traveler_final_day_failure"
    )

    result = signal.callback(choice)

    assert isinstance(result, ForceLoopEnd)
    assert result.reason == "time_traveler_final_day_failure"
    assert "time_traveler_goodwill_2" in state.failure_flags


def test_loop_end_handler_resolves_loss_conditions_and_saves_snapshot() -> None:
    bus, resolver = _resolver_bundle()
    handler = LoopEndHandler(bus, resolver)
    state = GameState()
    apply_loaded_module(state, load_module("basic_tragedy_x"))
    state.characters["friend"] = CharacterState(
        character_id="friend",
        name="亲友",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="friend",
        original_identity_id="friend",
        is_alive=False,
    )

    signal = handler.execute(state)

    assert isinstance(signal, PhaseComplete)
    assert "friend_dead" in state.failure_flags
    assert state.characters["friend"].revealed is True
    assert len(state.loop_history) == 1
    assert state.cross_loop_memory.revealed_identities_last_loop == {"friend": True}


def test_friend_death_failure_reveals_identity_to_protagonist_view() -> None:
    bus, resolver = _resolver_bundle()
    handler = LoopEndHandler(bus, resolver)
    state = GameState()
    apply_loaded_module(state, load_module("basic_tragedy_x"))
    state.characters["friend"] = CharacterState(
        character_id="friend",
        name="亲友",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="friend",
        original_identity_id="friend",
        is_alive=False,
    )

    before = Visibility.filter_for_role(state, PlayerRole.PROTAGONIST_0)
    before_friend = next(ch for ch in before.characters if ch.character_id == "friend")

    signal = handler.execute(state)

    after = Visibility.filter_for_role(state, PlayerRole.PROTAGONIST_0)
    after_friend = next(ch for ch in after.characters if ch.character_id == "friend")

    assert isinstance(signal, PhaseComplete)
    assert before_friend.identity == "???"
    assert after_friend.identity == "friend"
    assert "friend_dead" in state.failure_flags


def test_final_guess_handler_accepts_correct_guess() -> None:
    bus, resolver = _resolver_bundle()
    handler = FinalGuessHandler(bus, resolver)
    loaded = load_module("basic_tragedy_x")
    state = build_game_state_from_module(
        "basic_tragedy_x",
        loop_count=1,
        days_per_loop=1,
        rule_y_id="btx_murder_plan",
        rule_x_ids=["btx_rumors", "btx_latent_serial_killer"],
        character_setups=[
            CharacterSetup("male_student", "mastermind"),
            CharacterSetup("female_student", "key_person"),
            CharacterSetup("idol", "rumormonger"),
            CharacterSetup("office_worker", "killer"),
            CharacterSetup("shrine_maiden", "serial_killer"),
            CharacterSetup("doctor", "friend"),
        ],
        incidents=[],
    )
    state.module_def = loaded.module_def

    signal = handler.execute(state)

    assert isinstance(signal, WaitForInput)
    assert signal.input_type == "final_guess"
    assert signal.context["rule_y_id"] == "btx_murder_plan"
    assert signal.context["rule_x_ids"] == ["btx_rumors", "btx_latent_serial_killer"]

    result = signal.callback(
        {
            "rule_y_id": "btx_murder_plan",
            "rule_x_ids": ["btx_latent_serial_killer", "btx_rumors"],
            "character_identities": {
                "male_student": "mastermind",
                "female_student": "key_person",
                "idol": "rumormonger",
                "office_worker": "killer",
                "shrine_maiden": "serial_killer",
                "doctor": "friend",
            },
        }
    )

    assert isinstance(result, PhaseComplete)
    assert state.final_guess_correct is True


def test_final_guess_handler_reprompts_on_invalid_payload() -> None:
    bus, resolver = _resolver_bundle()
    handler = FinalGuessHandler(bus, resolver)
    state = build_game_state_from_module(
        "basic_tragedy_x",
        loop_count=1,
        days_per_loop=1,
        rule_y_id="btx_murder_plan",
        rule_x_ids=["btx_rumors", "btx_latent_serial_killer"],
        character_setups=[
            CharacterSetup("male_student", "mastermind"),
            CharacterSetup("female_student", "key_person"),
        ],
        incidents=[],
        skip_script_validation=True,
    )

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    retry = signal.callback(
        {
            "rule_y_id": "btx_murder_plan",
            "rule_x_ids": ["btx_rumors", "btx_latent_serial_killer"],
            "character_identities": {
                "male_student": "mastermind",
            },
        }
    )

    assert isinstance(retry, WaitForInput)
    assert retry.input_type == "final_guess"
    assert retry.context["errors"]
    assert state.final_guess_correct is None

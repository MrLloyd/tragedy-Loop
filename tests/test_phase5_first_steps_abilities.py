from __future__ import annotations

from engine.event_bus import EventBus
from engine.game_state import GameState
from engine.models.character import CharacterState
from engine.models.enums import AbilityTiming, AreaId, TokenType
from engine.phases.phase_base import (
    PhaseComplete,
    PlaywrightAbilityHandler,
    ProtagonistAbilityHandler,
    TurnEndHandler,
    WaitForInput,
)
from engine.resolvers.ability_resolver import AbilityResolver
from engine.resolvers.atomic_resolver import AtomicResolver
from engine.resolvers.death_resolver import DeathResolver
from engine.rules.module_loader import apply_loaded_module, load_module


def _resolver_bundle() -> tuple[EventBus, AtomicResolver]:
    bus = EventBus()
    return bus, AtomicResolver(bus, DeathResolver())


def _protagonist_allow(signal: WaitForInput, ability_id: str):
    choice = next(
        option for option in signal.options
        if getattr(option, "ability", None) is not None
        and option.ability.ability_id == ability_id
    )
    response = signal.callback(choice)
    assert isinstance(response, WaitForInput)
    assert response.input_type == "respond_goodwill_ability"
    return response.callback("allow")


def test_phase5_identity_abilities_are_available_for_configured_cast() -> None:
    state = GameState()
    apply_loaded_module(state, load_module("first_steps"))
    state.characters["male_student"] = CharacterState(
        character_id="male_student",
        name="男子学生",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="mastermind",
        original_identity_id="mastermind",
    )
    state.characters["female_student"] = CharacterState(
        character_id="female_student",
        name="女子学生",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="key_person",
        original_identity_id="key_person",
    )
    state.characters["idol"] = CharacterState(
        character_id="idol",
        name="偶像",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="rumormonger",
        original_identity_id="rumormonger",
    )
    state.characters["office_worker"] = CharacterState(
        character_id="office_worker",
        name="职员",
        area=AreaId.SCHOOL,
        initial_area=AreaId.CITY,
        identity_id="killer",
        original_identity_id="killer",
    )
    state.characters["shrine_maiden"] = CharacterState(
        character_id="shrine_maiden",
        name="巫女",
        area=AreaId.SHRINE,
        initial_area=AreaId.SHRINE,
        identity_id="serial_killer",
        original_identity_id="serial_killer",
    )
    state.characters["office_worker"].tokens.add(TokenType.INTRIGUE, 4)
    state.characters["female_student"].tokens.add(TokenType.INTRIGUE, 2)
    state.characters["victim"] = CharacterState(
        character_id="victim",
        name="路人",
        area=AreaId.SHRINE,
        initial_area=AreaId.SHRINE,
        identity_id="平民",
        original_identity_id="平民",
    )

    resolver = AbilityResolver()
    playwright = resolver.collect_abilities(
        state,
        timing=AbilityTiming.PLAYWRIGHT_ABILITY,
    )
    turn_end = resolver.collect_abilities(
        state,
        timing=AbilityTiming.TURN_END,
    )

    assert {c.ability.ability_id for c in playwright} == {
        "mastermind_playwright_place_intrigue_board",
        "mastermind_playwright_place_intrigue_character",
        "rumormonger_playwright_place_paranoia",
    }
    assert {c.ability.ability_id for c in turn_end} == {
        "killer_turn_end_kill_key_person",
        "killer_turn_end_protagonist_death",
        "serial_killer_turn_end_kill_lone_target",
    }


def test_phase5_female_student_goodwill_removes_paranoia() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["female_student"] = CharacterState(
        character_id="female_student",
        name="女子学生",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="key_person",
        original_identity_id="key_person",
        goodwill_ability_texts=["移除同一区域另外1名角色身上的1枚不安指示物", "", "", ""],
        goodwill_ability_goodwill_requirements=[2, 0, 0, 0],
        goodwill_ability_once_per_loop=[False, False],
    )
    state.characters["male_student"] = CharacterState(
        character_id="male_student",
        name="男子学生",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.characters["female_student"].tokens.add(TokenType.GOODWILL, 2)
    state.characters["male_student"].tokens.add(TokenType.PARANOIA, 1)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    result = _protagonist_allow(signal, "goodwill:female_student:1")

    assert isinstance(result, WaitForInput)
    assert state.characters["female_student"].tokens.get(TokenType.GOODWILL) == 2
    assert state.characters["male_student"].tokens.get(TokenType.PARANOIA) == 0


def test_phase5_idol_goodwill_places_goodwill_on_other_character() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["idol"] = CharacterState(
        character_id="idol",
        name="偶像",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="rumormonger",
        original_identity_id="rumormonger",
        goodwill_ability_texts=[
            "移除同一区域另1名角色身上的1枚不安指示物",
            "往同一区域另1名角色身上放置1枚友好指示物",
            "",
            "",
        ],
        goodwill_ability_goodwill_requirements=[3, 4, 0, 0],
        goodwill_ability_once_per_loop=[False, False],
    )
    state.characters["male_student"] = CharacterState(
        character_id="male_student",
        name="男子学生",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.characters["idol"].tokens.add(TokenType.GOODWILL, 4)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    result = _protagonist_allow(signal, "goodwill:idol:2")

    assert isinstance(result, WaitForInput)
    assert state.characters["idol"].tokens.get(TokenType.GOODWILL) == 4
    assert state.characters["male_student"].tokens.get(TokenType.GOODWILL) == 1


def test_phase5_male_student_goodwill_can_be_refused() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["male_student"] = CharacterState(
        character_id="male_student",
        name="男子学生",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="平民",
        original_identity_id="平民",
        goodwill_ability_texts=["移除同一区域另外1名角色身上的1枚不安指示物", "", "", ""],
        goodwill_ability_goodwill_requirements=[2, 0, 0, 0],
        goodwill_ability_once_per_loop=[False, False],
    )
    state.characters["female_student"] = CharacterState(
        character_id="female_student",
        name="女子学生",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.characters["male_student"].tokens.add(TokenType.GOODWILL, 2)
    state.characters["female_student"].tokens.add(TokenType.PARANOIA, 1)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    choice = next(
        option for option in signal.options
        if getattr(option, "ability", None) is not None
        and option.ability.ability_id == "goodwill:male_student:1"
    )

    response = signal.callback(choice)
    assert isinstance(response, WaitForInput)
    assert response.input_type == "respond_goodwill_ability"

    follow_up = response.callback("refuse")

    assert isinstance(follow_up, WaitForInput)
    assert state.characters["male_student"].tokens.get(TokenType.GOODWILL) == 2
    assert state.characters["female_student"].tokens.get(TokenType.PARANOIA) == 1


def test_phase5_office_worker_goodwill_reveals_identity() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["office_worker"] = CharacterState(
        character_id="office_worker",
        name="职员",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="killer",
        original_identity_id="killer",
        goodwill_ability_texts=["公开该角色的身份", "", "", ""],
        goodwill_ability_goodwill_requirements=[3, 0, 0, 0],
        goodwill_ability_once_per_loop=[False, False],
    )
    state.characters["office_worker"].tokens.add(TokenType.GOODWILL, 3)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    result = _protagonist_allow(signal, "goodwill:office_worker:1")

    assert isinstance(result, WaitForInput)
    assert state.characters["office_worker"].revealed is True


def test_phase5_shrine_maiden_goodwill_requires_shrine_and_removes_intrigue() -> None:
    state = GameState()
    state.characters["shrine_maiden"] = CharacterState(
        character_id="shrine_maiden",
        name="巫女",
        area=AreaId.CITY,
        initial_area=AreaId.SHRINE,
        identity_id="serial_killer",
        original_identity_id="serial_killer",
        goodwill_ability_texts=[
            "必须位于神社才可使用，移除神社的1枚密谋指示物",
            "公开同一区域任意1名角色的身份",
            "",
            "",
        ],
        goodwill_ability_goodwill_requirements=[3, 5, 0, 0],
        goodwill_ability_once_per_loop=[False, True],
    )
    state.characters["shrine_maiden"].tokens.add(TokenType.GOODWILL, 5)

    resolver = AbilityResolver()
    abilities = resolver.collect_goodwill_abilities(state)

    assert {ability.ability.ability_id for ability in abilities} == {"goodwill:shrine_maiden:2"}

    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state.characters["shrine_maiden"].area = AreaId.SHRINE
    state.board.areas[AreaId.SHRINE].tokens.add(TokenType.INTRIGUE, 1)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    result = _protagonist_allow(signal, "goodwill:shrine_maiden:1")

    assert isinstance(result, WaitForInput)
    assert state.board.areas[AreaId.SHRINE].tokens.get(TokenType.INTRIGUE) == 0


def test_phase5_playwright_and_turn_end_identity_effects_execute() -> None:
    bus, atomic = _resolver_bundle()
    playwright_handler = PlaywrightAbilityHandler(bus, atomic)
    turn_end_handler = TurnEndHandler(bus, atomic)
    state = GameState()
    apply_loaded_module(state, load_module("first_steps"))
    state.characters["male_student"] = CharacterState(
        character_id="male_student",
        name="男子学生",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="mastermind",
        original_identity_id="mastermind",
    )
    state.characters["female_student"] = CharacterState(
        character_id="female_student",
        name="女子学生",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="key_person",
        original_identity_id="key_person",
    )
    state.characters["idol"] = CharacterState(
        character_id="idol",
        name="偶像",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="rumormonger",
        original_identity_id="rumormonger",
    )
    state.characters["office_worker"] = CharacterState(
        character_id="office_worker",
        name="职员",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="killer",
        original_identity_id="killer",
    )
    state.characters["shrine_maiden"] = CharacterState(
        character_id="shrine_maiden",
        name="巫女",
        area=AreaId.SHRINE,
        initial_area=AreaId.SHRINE,
        identity_id="serial_killer",
        original_identity_id="serial_killer",
    )
    state.characters["victim"] = CharacterState(
        character_id="victim",
        name="路人",
        area=AreaId.SHRINE,
        initial_area=AreaId.SHRINE,
        identity_id="平民",
        original_identity_id="平民",
    )

    playwright_signal = playwright_handler.execute(state)
    assert isinstance(playwright_signal, WaitForInput)
    mastermind_choice = next(
        option for option in playwright_signal.options
        if getattr(option, "ability", None) is not None
        and option.ability.ability_id == "mastermind_playwright_place_intrigue_character"
    )
    target_wait = playwright_signal.callback(mastermind_choice)
    assert isinstance(target_wait, WaitForInput)
    target_wait.callback("female_student")
    assert state.characters["female_student"].tokens.get(TokenType.INTRIGUE) == 1

    rumor_signal = playwright_handler.execute(state)
    assert isinstance(rumor_signal, WaitForInput)
    rumor_choice = next(
        option for option in rumor_signal.options
        if getattr(option, "ability", None) is not None
        and option.ability.ability_id == "rumormonger_playwright_place_paranoia"
    )
    rumor_result = rumor_signal.callback(rumor_choice)
    assert isinstance(rumor_result, WaitForInput)
    assert state.characters["idol"].tokens.get(TokenType.PARANOIA) == 1

    state.characters["female_student"].tokens.add(TokenType.INTRIGUE, 1)
    turn_signal = turn_end_handler.execute(state)
    assert isinstance(turn_signal, WaitForInput)
    killer_choice = next(
        option for option in turn_signal.options
        if getattr(option, "ability", None) is not None
        and option.ability.ability_id == "killer_turn_end_kill_key_person"
    )
    turn_signal.callback(killer_choice)
    assert state.characters["female_student"].is_alive is False

    serial_signal = turn_end_handler.execute(state)
    assert isinstance(serial_signal, PhaseComplete)
    assert state.characters["victim"].is_alive is False

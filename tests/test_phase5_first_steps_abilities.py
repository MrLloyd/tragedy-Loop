from __future__ import annotations

from engine.event_bus import EventBus
from engine.game_state import GameState
from engine.models.ability import Ability
from engine.models.character import CharacterState
from engine.models.effects import Effect
from engine.models.enums import AbilityTiming, AbilityType, AreaId, Attribute, CharacterLifeState, EffectType, TokenType, Trait
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
    if isinstance(response, WaitForInput) and response.input_type == "respond_goodwill_ability":
        if "allow" in response.options:
            return response.callback("allow")
        return response.callback("refuse")
    return response


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


def test_phase5_male_student_goodwill_commoner_executes_without_refusal_prompt() -> None:
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
    assert not (isinstance(response, WaitForInput) and response.input_type == "respond_goodwill_ability")
    assert state.characters["male_student"].tokens.get(TokenType.GOODWILL) == 2
    assert state.characters["female_student"].tokens.get(TokenType.PARANOIA) == 0


def test_phase5_sister_forces_adult_goodwill_without_refusal() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["sister"] = CharacterState(
        character_id="sister",
        name="妹妹",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="sister",
        original_identity_id="sister",
        attributes={Attribute.GIRL, Attribute.SISTER},
        goodwill_ability_texts=[
            "同一区域的1名成人使用1个友好能力，此时无视该成人的友好指示物数量。即使该成人带有无视友好特性，也不能拒绝使用那个能力。但能力依然受到次数限制。",
            "",
            "",
            "",
        ],
        goodwill_ability_goodwill_requirements=[5, 0, 0, 0],
        goodwill_ability_once_per_loop=[True, False],
    )
    state.characters["soldier"] = CharacterState(
        character_id="soldier",
        name="军人",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="soldier",
        original_identity_id="soldier",
        attributes={Attribute.ADULT, Attribute.MALE},
        base_traits={Trait.IGNORE_GOODWILL},
        goodwill_abilities=[
            Ability(
                ability_id="goodwill:soldier:1",
                name="军人 友好能力1",
                ability_type=AbilityType.OPTIONAL,
                timing=AbilityTiming.PROTAGONIST_ABILITY,
                description="往同一区域任意1名角色身上放置2枚不安指示物",
                effects=[
                    Effect(
                        effect_type=EffectType.PLACE_TOKEN,
                        target={
                            "scope": "same_area",
                            "subject": "character",
                        },
                        token_type=TokenType.PARANOIA,
                        amount=2,
                    )
                ],
                goodwill_requirement=2,
                once_per_loop=True,
                can_be_refused=True,
            )
        ],
    )
    state.characters["victim"] = CharacterState(
        character_id="victim",
        name="路人",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
        attributes={Attribute.ADULT},
    )
    state.characters["sister"].tokens.add(TokenType.GOODWILL, 5)
    state.characters["soldier"].tokens.add(TokenType.GOODWILL, 2)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    sister_choice = next(
        option for option in signal.options
        if getattr(option, "ability", None) is not None
        and option.ability.ability_id == "goodwill:sister:1"
    )

    target_wait = signal.callback(sister_choice)
    assert isinstance(target_wait, WaitForInput)
    assert target_wait.input_type == "choose_ability_target"

    soldier_wait = target_wait.callback("soldier")
    assert isinstance(soldier_wait, WaitForInput)
    assert soldier_wait.input_type == "choose_ability_target"
    assert "victim" in soldier_wait.options

    result = soldier_wait.callback("victim")
    assert isinstance(result, PhaseComplete)
    assert state.characters["victim"].tokens.get(TokenType.PARANOIA) == 2
    assert state.ability_runtime.usages_this_loop["goodwill:sister:goodwill:sister:1"] == 1
    assert state.ability_runtime.usages_this_loop["goodwill:soldier:goodwill:soldier:1"] == 1


def test_phase5_sister_forced_goodwill_refreshes_list_for_remaining_goodwill_candidates() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["sister"] = CharacterState(
        character_id="sister",
        name="妹妹",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="sister",
        original_identity_id="sister",
        attributes={Attribute.GIRL, Attribute.SISTER},
        goodwill_ability_texts=[
            "同一区域的1名成人使用1个友好能力，此时无视该成人的友好指示物数量。",
            "",
            "",
            "",
        ],
        goodwill_ability_goodwill_requirements=[5, 0, 0, 0],
        goodwill_ability_once_per_loop=[True, False],
    )
    state.characters["soldier"] = CharacterState(
        character_id="soldier",
        name="军人",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="soldier",
        original_identity_id="soldier",
        attributes={Attribute.ADULT, Attribute.MALE},
        base_traits={Trait.IGNORE_GOODWILL},
        goodwill_abilities=[
            Ability(
                ability_id="goodwill:soldier:1",
                name="军人 友好能力1",
                ability_type=AbilityType.OPTIONAL,
                timing=AbilityTiming.PROTAGONIST_ABILITY,
                description="往同一区域任意1名角色身上放置2枚不安指示物",
                effects=[
                    Effect(
                        effect_type=EffectType.PLACE_TOKEN,
                        target={"scope": "same_area", "subject": "character"},
                        token_type=TokenType.PARANOIA,
                        amount=2,
                    )
                ],
                goodwill_requirement=2,
                once_per_loop=True,
                can_be_refused=True,
            )
        ],
    )
    state.characters["office_worker"] = CharacterState(
        character_id="office_worker",
        name="职员",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="killer",
        original_identity_id="killer",
        goodwill_ability_texts=["公开该角色的身份", "", "", ""],
        goodwill_ability_goodwill_requirements=[3, 0, 0, 0],
        goodwill_ability_once_per_loop=[True, False],
    )
    state.characters["victim"] = CharacterState(
        character_id="victim",
        name="路人",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
        attributes={Attribute.ADULT},
    )
    state.characters["sister"].tokens.add(TokenType.GOODWILL, 5)
    state.characters["soldier"].tokens.add(TokenType.GOODWILL, 2)
    state.characters["office_worker"].tokens.add(TokenType.GOODWILL, 3)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    sister_choice = next(
        option
        for option in signal.options
        if getattr(option, "ability", None) is not None
        and option.ability.ability_id == "goodwill:sister:1"
    )
    target_wait = signal.callback(sister_choice)
    assert isinstance(target_wait, WaitForInput)
    soldier_wait = target_wait.callback("soldier")
    assert isinstance(soldier_wait, WaitForInput)

    refreshed_wait = soldier_wait.callback("victim")
    assert isinstance(refreshed_wait, WaitForInput)
    assert refreshed_wait.input_type == "choose_goodwill_ability"
    refreshed_ids = {
        option.ability.ability_id
        for option in refreshed_wait.options
        if getattr(option, "ability", None) is not None
    }
    assert "goodwill:office_worker:1" in refreshed_ids
    assert "goodwill:sister:1" not in refreshed_ids
    assert "goodwill:soldier:1" not in refreshed_ids


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
    assert state.characters["female_student"].life_state == CharacterLifeState.DEAD

    serial_signal = turn_end_handler.execute(state)
    assert isinstance(serial_signal, PhaseComplete)
    assert state.characters["victim"].life_state == CharacterLifeState.DEAD

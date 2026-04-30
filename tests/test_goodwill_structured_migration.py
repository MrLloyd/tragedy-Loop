from __future__ import annotations

from engine.event_bus import EventBus
from engine.game_state import GameState
from engine.models.ability import Ability
from engine.models.cards import CardPlacement
from engine.models.character import CharacterState
from engine.models.effects import Effect
from engine.models.enums import AbilityTiming, AbilityType, AreaId, Attribute, CharacterLifeState, EffectType, PlayerRole, TokenType, Trait
from engine.models.identity import IdentityDef
from engine.models.script import CharacterSetup, IncidentSchedule
from engine.phases.phase_base import IncidentHandler, PhaseComplete, PlaywrightAbilityHandler, ProtagonistAbilityHandler, WaitForInput
from engine.resolvers.ability_resolver import AbilityResolver
from engine.resolvers.atomic_resolver import AtomicResolver
from engine.resolvers.death_resolver import DeathResolver
from engine.rules.character_loader import instantiate_character_state, load_character_defs
from engine.rules.module_loader import apply_loaded_module, load_module

_CHARACTER_DEFS = load_character_defs()


def _resolver_bundle() -> tuple[EventBus, AtomicResolver]:
    bus = EventBus()
    return bus, AtomicResolver(bus, DeathResolver())


def _instantiate(character_id: str, *, identity_id: str = "平民") -> CharacterState:
    return instantiate_character_state(
        CharacterSetup(character_id=character_id, identity_id=identity_id),
        _CHARACTER_DEFS,
    )


def _choose_goodwill(signal: WaitForInput, ability_id: str):
    choice = next(
        option
        for option in signal.options
        if getattr(option, "ability", None) is not None
        and option.ability.ability_id == ability_id
    )
    response = signal.callback(choice)
    if isinstance(response, WaitForInput) and response.input_type == "respond_goodwill_ability":
        if "allow" in response.options:
            return response.callback("allow")
        return response.callback("refuse")
    return response


def _choose_playwright_ability(signal: WaitForInput, ability_id: str):
    choice = next(
        option
        for option in signal.options
        if getattr(option, "ability", None) is not None
        and option.ability.ability_id == ability_id
    )
    return signal.callback(choice)


def test_resolve_targets_supports_extended_structured_selectors() -> None:
    state = GameState()
    state.characters["teacher"] = CharacterState(
        character_id="teacher",
        name="教师",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="mastermind",
        original_identity_id="mastermind",
        attributes={Attribute.ADULT},
    )
    state.characters["student"] = CharacterState(
        character_id="student",
        name="学生",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="key_person",
        original_identity_id="key_person",
        attributes={Attribute.STUDENT},
    )
    state.characters["limit"] = CharacterState(
        character_id="limit",
        name="达限者",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="killer",
        original_identity_id="killer",
        paranoia_limit=2,
    )
    state.characters["limit"].tokens.add(TokenType.PARANOIA, 2)
    state.characters["corpse"] = CharacterState(
        character_id="corpse",
        name="尸体",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="cultist",
        original_identity_id="cultist",
        life_state=CharacterLifeState.DEAD,
    )
    state.characters["other_limit"] = CharacterState(
        character_id="other_limit",
        name="异地达限者",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="cultist",
        original_identity_id="cultist",
        paranoia_limit=1,
    )
    state.characters["other_limit"].tokens.add(TokenType.PARANOIA, 1)

    resolver = AbilityResolver()

    assert set(
        resolver.resolve_targets(
            state,
            owner_id="teacher",
            selector={
                "scope": "same_area",
                "subject": "character",
                "filters": {"attribute": "student"},
            },
        )
    ) == {"student"}
    assert set(
        resolver.resolve_targets(
            state,
            owner_id="teacher",
            selector={"scope": "same_area", "subject": "character_or_board"},
        )
    ) == {"teacher", "student", "limit", "school"}
    assert set(
        resolver.resolve_targets(
            state,
            owner_id="teacher",
            selector={
                "scope": "same_area",
                "subject": "other_character",
                "filters": {
                    "limit_reached": True,
                },
            },
        )
    ) == {"limit"}
    assert set(
        resolver.resolve_targets(
            state,
            owner_id="teacher",
            selector={
                "scope": "same_area",
                "subject": "dead_character",
            },
        )
    ) == {"corpse"}
    assert set(
        resolver.resolve_targets(
            state,
            owner_id="teacher",
            selector={
                "scope": "any_area",
                "subject": "other_character",
            },
        )
    ) == {"student", "limit", "other_limit"}
    assert set(
        resolver.resolve_targets(
            state,
            owner_id="teacher",
            selector={
                "scope": "any_area",
                "subject": "character",
                "filters": {"limit_reached": True},
            },
        )
    ) == {"limit", "other_limit"}
    assert set(
        resolver.resolve_targets(
            state,
            owner_id="teacher",
            selector={
                "scope": "any_area",
                "subject": "dead_character",
            },
        )
    ) == {"corpse"}
    assert set(
        resolver.resolve_targets(
            state,
            owner_id="teacher",
            selector={
                "scope": "any_area",
                "subject": "character",
                "filters": {"identity_id": "key_person"},
            },
        )
    ) == {"student"}
    assert set(
        resolver.resolve_targets(
            state,
            owner_id="teacher",
            selector={
                "scope": "same_area",
                "subject": "character",
                "filters": {"attribute": "student"},
            },
        )
    ) == {"student"}


def test_teacher_structured_goodwill_keeps_mode_choice_after_auto_target() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["teacher"] = _instantiate("teacher")
    state.characters["teacher"].tokens.add(TokenType.GOODWILL, 3)
    state.characters["student"] = CharacterState(
        character_id="student",
        name="学生",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="平民",
        original_identity_id="平民",
        attributes={Attribute.STUDENT},
    )
    state.characters["student"].tokens.add(TokenType.PARANOIA, 1)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    mode_wait = _choose_goodwill(signal, "goodwill:teacher:1")
    assert isinstance(mode_wait, WaitForInput)
    assert set(mode_wait.options) == {"place", "remove"}

    result = mode_wait.callback("remove")
    assert isinstance(result, (WaitForInput, PhaseComplete))
    assert state.characters["student"].tokens.get(TokenType.PARANOIA) == 0


def test_office_worker_structured_goodwill_reveals_self() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["office_worker"] = _instantiate("office_worker", identity_id="killer")
    state.characters["office_worker"].tokens.add(TokenType.GOODWILL, 3)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    result = _choose_goodwill(signal, "goodwill:office_worker:1")
    assert isinstance(result, WaitForInput)
    assert state.characters["office_worker"].revealed is True


def test_temp_worker_alt_structured_goodwill_reveals_self_and_places_two_goodwill() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["temp_worker_alt"] = _instantiate("temp_worker_alt", identity_id="mastermind")
    state.characters["temp_worker_alt"].tokens.add(TokenType.GOODWILL, 2)
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
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
    )

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    target_wait = _choose_goodwill(signal, "goodwill:temp_worker_alt:1")
    assert isinstance(target_wait, WaitForInput)
    assert target_wait.input_type == "choose_ability_target"
    assert set(target_wait.options) == {"temp_worker_alt", "target_a", "target_b"}

    result = target_wait.callback("target_b")
    assert isinstance(result, PhaseComplete)
    assert state.characters["temp_worker_alt"].revealed is True
    assert state.characters["target_a"].tokens.get(TokenType.GOODWILL) == 0
    assert state.characters["target_b"].tokens.get(TokenType.GOODWILL) == 2


def test_outsider_structured_goodwill_requires_loop_two_and_is_not_refusable() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["outsider"] = _instantiate("outsider", identity_id="cultist")
    state.characters["outsider"].tokens.add(TokenType.GOODWILL, 3)

    signal = handler.execute(state)
    assert isinstance(signal, PhaseComplete)

    state.current_loop = 2
    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    choice = next(
        option
        for option in signal.options
        if getattr(option, "ability", None) is not None
        and option.ability.ability_id == "goodwill:outsider:1"
    )
    result = signal.callback(choice)
    assert not (isinstance(result, WaitForInput) and result.input_type == "respond_goodwill_ability")
    assert state.characters["outsider"].revealed is True


def test_shrine_maiden_structured_goodwill_reveals_selected_same_area_character() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["shrine_maiden"] = _instantiate("shrine_maiden", identity_id="serial_killer")
    state.characters["shrine_maiden"].tokens.add(TokenType.GOODWILL, 5)
    state.characters["target_a"] = CharacterState(
        character_id="target_a",
        name="目标A",
        area=AreaId.SHRINE,
        initial_area=AreaId.SHRINE,
        identity_id="mastermind",
        original_identity_id="mastermind",
    )
    state.characters["target_b"] = CharacterState(
        character_id="target_b",
        name="目标B",
        area=AreaId.SHRINE,
        initial_area=AreaId.SHRINE,
        identity_id="killer",
        original_identity_id="killer",
    )

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    target_wait = _choose_goodwill(signal, "goodwill:shrine_maiden:2")
    assert isinstance(target_wait, WaitForInput)
    assert target_wait.input_type == "choose_ability_target"
    assert set(target_wait.options) == {"shrine_maiden", "target_a", "target_b"}

    result = target_wait.callback("target_b")
    assert isinstance(result, (WaitForInput, PhaseComplete))
    assert state.characters["target_a"].revealed is False
    assert state.characters["target_b"].revealed is True


def test_cult_leader_structured_goodwill_reveals_selected_limit_reached_other_character() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["cult_leader"] = _instantiate("cult_leader")
    state.characters["cult_leader"].tokens.add(TokenType.GOODWILL, 4)
    state.characters["target_a"] = CharacterState(
        character_id="target_a",
        name="达限A",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="mastermind",
        original_identity_id="mastermind",
        paranoia_limit=2,
    )
    state.characters["target_a"].tokens.add(TokenType.PARANOIA, 2)
    state.characters["target_b"] = CharacterState(
        character_id="target_b",
        name="达限B",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="killer",
        original_identity_id="killer",
        paranoia_limit=1,
    )
    state.characters["target_b"].tokens.add(TokenType.PARANOIA, 1)
    state.characters["safe"] = CharacterState(
        character_id="safe",
        name="未达限",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
        paranoia_limit=2,
    )

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    target_wait = _choose_goodwill(signal, "goodwill:cult_leader:2")
    assert isinstance(target_wait, WaitForInput)
    assert target_wait.input_type == "choose_ability_target"
    assert set(target_wait.options) == {"target_a", "target_b"}

    result = target_wait.callback("target_a")
    assert isinstance(result, (WaitForInput, PhaseComplete))
    assert state.characters["target_a"].revealed is True
    assert state.characters["target_b"].revealed is False
    assert state.characters["safe"].revealed is False


def test_teacher_structured_goodwill_reveals_selected_student() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["teacher"] = _instantiate("teacher")
    state.characters["teacher"].tokens.add(TokenType.GOODWILL, 4)
    state.characters["student_a"] = CharacterState(
        character_id="student_a",
        name="学生A",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="mastermind",
        original_identity_id="mastermind",
        attributes={Attribute.STUDENT},
    )
    state.characters["student_b"] = CharacterState(
        character_id="student_b",
        name="学生B",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="killer",
        original_identity_id="killer",
        attributes={Attribute.STUDENT},
    )
    state.characters["adult"] = CharacterState(
        character_id="adult",
        name="成年人",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="平民",
        original_identity_id="平民",
        attributes={Attribute.ADULT},
    )

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    target_wait = _choose_goodwill(signal, "goodwill:teacher:2")
    assert isinstance(target_wait, WaitForInput)
    assert target_wait.input_type == "choose_ability_target"
    assert set(target_wait.options) == {"student_a", "student_b"}

    result = target_wait.callback("student_b")
    assert isinstance(result, (WaitForInput, PhaseComplete))
    assert state.characters["student_a"].revealed is False
    assert state.characters["student_b"].revealed is True
    assert state.characters["adult"].revealed is False


def test_appraiser_structured_goodwill_reveals_selected_corpse() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["appraiser"] = _instantiate("appraiser")
    state.characters["appraiser"].tokens.add(TokenType.GOODWILL, 5)
    state.characters["corpse_a"] = CharacterState(
        character_id="corpse_a",
        name="尸体A",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="mastermind",
        original_identity_id="mastermind",
        life_state=CharacterLifeState.DEAD,
    )
    state.characters["corpse_b"] = CharacterState(
        character_id="corpse_b",
        name="尸体B",
        area=AreaId.HOSPITAL,
        initial_area=AreaId.HOSPITAL,
        identity_id="killer",
        original_identity_id="killer",
        life_state=CharacterLifeState.DEAD,
    )
    state.characters["alive"] = CharacterState(
        character_id="alive",
        name="活人",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
    )

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    target_wait = _choose_goodwill(signal, "goodwill:appraiser:2")
    assert isinstance(target_wait, WaitForInput)
    assert target_wait.input_type == "choose_ability_target"
    assert set(target_wait.options) == {"corpse_a", "corpse_b"}

    result = target_wait.callback("corpse_b")
    assert isinstance(result, (WaitForInput, PhaseComplete))
    assert state.characters["corpse_a"].revealed is False
    assert state.characters["corpse_b"].revealed is True
    assert state.characters["alive"].revealed is False


def test_generic_token_choice_survives_auto_target_resolution() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["higher_being"] = CharacterState(
        character_id="higher_being",
        name="上位存在",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
        goodwill_abilities=[
            Ability(
                ability_id="goodwill:higher_being:test",
                name="上位存在 测试能力",
                ability_type=AbilityType.OPTIONAL,
                timing=AbilityTiming.PROTAGONIST_ABILITY,
                effects=[
                    Effect(
                        effect_type=EffectType.PLACE_TOKEN,
                        target={"scope": "same_area", "subject": "character"},
                        amount=1,
                        value={"choice": "choose_token_type", "options": ["hope", "despair"]},
                    )
                ],
                goodwill_requirement=2,
                once_per_loop=True,
                can_be_refused=True,
            )
        ],
    )
    state.characters["higher_being"].tokens.add(TokenType.GOODWILL, 2)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    token_wait = _choose_goodwill(signal, "goodwill:higher_being:test")
    assert isinstance(token_wait, WaitForInput)
    assert set(token_wait.options) == {"hope", "despair"}

    result = token_wait.callback("hope")
    assert isinstance(result, PhaseComplete)
    assert state.characters["higher_being"].tokens.get(TokenType.HOPE) == 1
    assert state.characters["higher_being"].tokens.get(TokenType.DESPAIR) == 0


def test_playwright_can_use_higher_being_goodwill_when_ignore_goodwill() -> None:
    bus, atomic = _resolver_bundle()
    handler = PlaywrightAbilityHandler(bus, atomic)
    state = GameState()
    state.identity_defs["ignore_identity"] = IdentityDef(
        identity_id="ignore_identity",
        name="无视友好身份",
        module="test",
        traits={Trait.IGNORE_GOODWILL},
    )
    state.characters["higher_being"] = _instantiate("higher_being", identity_id="ignore_identity")
    state.characters["higher_being"].tokens.add(TokenType.GOODWILL, 2)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    assert signal.input_type == "choose_playwright_ability"

    token_wait = _choose_playwright_ability(signal, "goodwill:higher_being:1")
    assert isinstance(token_wait, WaitForInput)
    assert set(token_wait.options) == {"hope", "despair"}

    result = token_wait.callback("despair")
    assert isinstance(result, PhaseComplete)
    assert state.characters["higher_being"].tokens.get(TokenType.DESPAIR) == 1


def test_playwright_can_use_doctor_goodwill_when_must_ignore_goodwill() -> None:
    bus, atomic = _resolver_bundle()
    handler = PlaywrightAbilityHandler(bus, atomic)
    state = GameState()
    state.identity_defs["must_ignore_identity"] = IdentityDef(
        identity_id="must_ignore_identity",
        name="必定无视友好身份",
        module="test",
        traits={Trait.MUST_IGNORE_GOODWILL},
    )
    state.characters["doctor"] = _instantiate("doctor", identity_id="must_ignore_identity")
    state.characters["doctor"].tokens.add(TokenType.GOODWILL, 2)
    state.characters["target"] = CharacterState(
        character_id="target",
        name="目标",
        area=state.characters["doctor"].area,
        initial_area=state.characters["doctor"].area,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.characters["target"].tokens.add(TokenType.PARANOIA, 1)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    assert signal.input_type == "choose_playwright_ability"

    mode_wait = _choose_playwright_ability(signal, "goodwill:doctor:1")
    assert isinstance(mode_wait, WaitForInput)
    assert set(mode_wait.options) == {"place", "remove"}

    result = mode_wait.callback("remove")
    assert isinstance(result, (WaitForInput, PhaseComplete))
    assert state.characters["target"].tokens.get(TokenType.PARANOIA) == 0


def test_scholar_structured_goodwill_skips_ex_choice_without_ex_gauge() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    apply_loaded_module(state, load_module("first_steps"))
    state.characters["scholar"] = _instantiate("scholar")
    state.characters["scholar"].tokens.add(TokenType.GOODWILL, 3)
    state.characters["scholar"].tokens.add(TokenType.PARANOIA, 1)
    state.characters["scholar"].tokens.add(TokenType.INTRIGUE, 1)
    state.ex_gauge = 0

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    result = _choose_goodwill(signal, "goodwill:scholar:1")
    assert isinstance(result, PhaseComplete)
    assert state.characters["scholar"].tokens.total() == 0
    assert state.ex_gauge == 0


def test_henchman_structured_goodwill_suppresses_only_own_incident_for_current_loop() -> None:
    bus, atomic = _resolver_bundle()
    ability_handler = ProtagonistAbilityHandler(bus, atomic)
    incident_handler = IncidentHandler(bus, atomic)
    state = GameState()
    state.current_day = 1
    state.characters["henchman"] = _instantiate("henchman")
    state.characters["henchman"].tokens.add(TokenType.GOODWILL, 3)
    state.characters["henchman"].tokens.add(
        TokenType.PARANOIA,
        state.characters["henchman"].paranoia_limit,
    )
    state.characters["other"] = CharacterState(
        character_id="other",
        name="其他角色",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
        paranoia_limit=1,
    )
    state.characters["other"].tokens.add(TokenType.PARANOIA, 1)
    state.script.incidents = [
        IncidentSchedule("henchman_incident", day=1, perpetrator_id="henchman"),
        IncidentSchedule("other_incident", day=1, perpetrator_id="other"),
    ]

    signal = ability_handler.execute(state)
    assert isinstance(signal, WaitForInput)

    result = _choose_goodwill(signal, "goodwill:henchman:1")
    assert isinstance(result, (WaitForInput, PhaseComplete))
    assert "henchman" in state.suppressed_incident_perpetrators

    incident_signal = incident_handler.execute(state)
    assert isinstance(incident_signal, PhaseComplete)
    assert state.script.incidents[0].occurred is False
    assert state.script.incidents[1].occurred is True
    assert state.incidents_occurred_this_loop == ["other_incident"]


def test_henchman_structured_goodwill_refuse_does_not_suppress_incident() -> None:
    bus, atomic = _resolver_bundle()
    ability_handler = ProtagonistAbilityHandler(bus, atomic)
    incident_handler = IncidentHandler(bus, atomic)
    state = GameState()
    state.identity_defs["ignore_identity"] = IdentityDef(
        identity_id="ignore_identity",
        name="无视友好身份",
        module="test",
        traits={Trait.IGNORE_GOODWILL},
    )
    state.current_day = 1
    state.characters["henchman"] = _instantiate("henchman", identity_id="ignore_identity")
    state.characters["henchman"].tokens.add(TokenType.GOODWILL, 3)
    state.characters["henchman"].tokens.add(
        TokenType.PARANOIA,
        state.characters["henchman"].paranoia_limit,
    )
    state.script.incidents = [
        IncidentSchedule("henchman_incident", day=1, perpetrator_id="henchman"),
    ]

    signal = ability_handler.execute(state)
    assert isinstance(signal, WaitForInput)

    choice = next(
        option
        for option in signal.options
        if getattr(option, "ability", None) is not None
        and option.ability.ability_id == "goodwill:henchman:1"
    )
    refuse_wait = signal.callback(choice)
    assert isinstance(refuse_wait, WaitForInput)
    assert refuse_wait.input_type == "respond_goodwill_ability"

    result = refuse_wait.callback("refuse")
    assert isinstance(result, (WaitForInput, PhaseComplete))
    assert "henchman" not in state.suppressed_incident_perpetrators

    incident_signal = incident_handler.execute(state)
    assert isinstance(incident_signal, PhaseComplete)
    assert state.script.incidents[0].occurred is True


def test_servant_structured_goodwill_adds_trait_target_override() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["servant"] = _instantiate("servant")
    state.characters["servant"].tokens.add(TokenType.GOODWILL, 4)
    state.characters["vip"] = CharacterState(
        character_id="vip",
        name="大人物",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.characters["ojousama"] = CharacterState(
        character_id="ojousama",
        name="大小姐",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="平民",
        original_identity_id="平民",
    )

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    target_wait = _choose_goodwill(signal, "goodwill:servant:1")
    assert isinstance(target_wait, WaitForInput)
    assert target_wait.input_type == "choose_ability_target"
    assert set(target_wait.options) == {"vip", "ojousama"}

    result = target_wait.callback("vip")
    assert isinstance(result, PhaseComplete)
    assert state.trait_target_overrides["servant"] == {"vip"}


def test_class_rep_structured_goodwill_returns_only_current_leader_once_per_loop_card() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.leader_index = 1
    state.init_protagonist_hands()
    state.characters["class_rep"] = _instantiate("class_rep")
    state.characters["class_rep"].tokens.add(TokenType.GOODWILL, 2)

    leader_once = state.protagonist_hands[1].cards[1]
    leader_once.is_used_this_loop = True
    leader_once_second = state.protagonist_hands[1].cards[3]
    leader_once_second.is_used_this_loop = True
    other_once = state.protagonist_hands[0].cards[1]
    other_once.is_used_this_loop = True
    mastermind_once = state.mastermind_hand.cards[0]
    mastermind_once.is_used_this_loop = True
    leader_hidden_once = state.protagonist_hands[1].cards[7]
    leader_hidden_once.is_used_this_loop = True
    leader_non_once = state.protagonist_hands[1].cards[0]

    state.placed_cards = [
        CardPlacement(leader_once, PlayerRole.PROTAGONIST_1, "board", AreaId.CITY.value, face_down=False),
        CardPlacement(leader_once_second, PlayerRole.PROTAGONIST_1, "board", AreaId.SCHOOL.value, face_down=False),
        CardPlacement(other_once, PlayerRole.PROTAGONIST_0, "board", AreaId.SCHOOL.value, face_down=False),
        CardPlacement(mastermind_once, PlayerRole.MASTERMIND, "board", AreaId.HOSPITAL.value, face_down=False),
        CardPlacement(leader_non_once, PlayerRole.PROTAGONIST_1, "board", AreaId.SHRINE.value, face_down=False),
        CardPlacement(leader_hidden_once, PlayerRole.PROTAGONIST_1, "board", AreaId.CITY.value, face_down=True),
    ]

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    card_wait = _choose_goodwill(signal, "goodwill:class_rep:1")
    assert isinstance(card_wait, WaitForInput)
    assert card_wait.options == ["0", "1"]

    result = card_wait.callback("0")
    assert isinstance(result, (WaitForInput, PhaseComplete))
    assert leader_once.is_used_this_loop is False
    assert leader_once in state.protagonist_hands[1].get_available()
    assert all(placement.card is not leader_once for placement in state.placed_cards)


def test_class_rep_structured_goodwill_is_hidden_without_returnable_card() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.leader_index = 1
    state.init_protagonist_hands()
    state.characters["class_rep"] = _instantiate("class_rep")
    state.characters["class_rep"].tokens.add(TokenType.GOODWILL, 2)

    signal = handler.execute(state)

    assert isinstance(signal, PhaseComplete)


def test_media_person_structured_goodwill_can_target_board() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["media_person"] = _instantiate("media_person")
    state.characters["media_person"].tokens.add(TokenType.GOODWILL, 2)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    target_wait = _choose_goodwill(signal, "goodwill:media_person:2")
    assert isinstance(target_wait, WaitForInput)
    assert "city" in target_wait.options

    result = target_wait.callback("city")
    assert isinstance(result, (WaitForInput, PhaseComplete))
    assert state.board.areas[AreaId.CITY].tokens.get(TokenType.INTRIGUE) == 1


def test_alien_structured_goodwill_revives_dead_character() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["alien"] = _instantiate("alien")
    state.characters["alien"].tokens.add(TokenType.GOODWILL, 5)
    state.characters["corpse_a"] = CharacterState(
        character_id="corpse_a",
        name="尸体A",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
        life_state=CharacterLifeState.DEAD,
    )
    state.characters["corpse_b"] = CharacterState(
        character_id="corpse_b",
        name="尸体B",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
        life_state=CharacterLifeState.DEAD,
    )
    state.characters["living"] = CharacterState(
        character_id="living",
        name="活人",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
    )

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    target_wait = _choose_goodwill(signal, "goodwill:alien:2")
    assert isinstance(target_wait, WaitForInput)
    assert target_wait.input_type == "choose_ability_target"
    assert set(target_wait.options) == {"corpse_a", "corpse_b"}

    result = target_wait.callback("corpse_a")
    assert isinstance(result, (WaitForInput, PhaseComplete))
    assert state.characters["corpse_a"].life_state == CharacterLifeState.ALIVE
    assert state.characters["corpse_b"].life_state == CharacterLifeState.DEAD


def test_alien_structured_goodwill_refreshes_options_after_kill_then_can_revive() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["alien"] = _instantiate("alien")
    state.characters["alien"].tokens.add(TokenType.GOODWILL, 6)
    state.characters["victim_a"] = CharacterState(
        character_id="victim_a",
        name="受害者A",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.characters["victim_b"] = CharacterState(
        character_id="victim_b",
        name="受害者B",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
    )

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    assert signal.input_type == "choose_goodwill_ability"
    first_ids = {
        option.ability.ability_id
        for option in signal.options
        if getattr(option, "ability", None) is not None
    }
    assert first_ids == {"goodwill:alien:1"}

    kill_choice = next(
        option
        for option in signal.options
        if getattr(option, "ability", None) is not None
        and option.ability.ability_id == "goodwill:alien:1"
    )
    kill_target_wait = signal.callback(kill_choice)
    assert isinstance(kill_target_wait, WaitForInput)
    assert kill_target_wait.input_type == "choose_ability_target"
    assert set(kill_target_wait.options) == {"victim_a", "victim_b"}

    refreshed_wait = kill_target_wait.callback("victim_a")
    assert isinstance(refreshed_wait, WaitForInput)
    assert refreshed_wait.input_type == "choose_goodwill_ability"
    assert state.characters["victim_a"].life_state == CharacterLifeState.DEAD

    refreshed_ids = {
        option.ability.ability_id
        for option in refreshed_wait.options
        if getattr(option, "ability", None) is not None
    }
    assert refreshed_ids == {"goodwill:alien:2"}

    revive_choice = next(
        option
        for option in refreshed_wait.options
        if getattr(option, "ability", None) is not None
        and option.ability.ability_id == "goodwill:alien:2"
    )
    revive_target_wait = refreshed_wait.callback(revive_choice)
    if isinstance(revive_target_wait, WaitForInput):
        assert revive_target_wait.input_type == "choose_ability_target"
        assert set(revive_target_wait.options) == {"victim_a"}
        done = revive_target_wait.callback("victim_a")
        assert isinstance(done, PhaseComplete)
    else:
        assert isinstance(revive_target_wait, PhaseComplete)
    assert state.characters["victim_a"].life_state == CharacterLifeState.ALIVE


def test_hermit_goodwill_moves_then_revives_selected_corpse_and_places_scripted_x_goodwill() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["hermit"] = _instantiate("hermit")
    state.characters["hermit"].tokens.add(TokenType.GOODWILL, 5)
    state.script.private_table.characters = [
        CharacterSetup(character_id="hermit", identity_id="平民", hermit_x=2),
    ]
    state.characters["corpse_city_a"] = CharacterState(
        character_id="corpse_city_a",
        name="都市尸体A",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
        life_state=CharacterLifeState.DEAD,
    )
    state.characters["corpse_city_b"] = CharacterState(
        character_id="corpse_city_b",
        name="都市尸体B",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
        life_state=CharacterLifeState.DEAD,
    )
    state.characters["corpse_hospital"] = CharacterState(
        character_id="corpse_hospital",
        name="医院尸体",
        area=AreaId.HOSPITAL,
        initial_area=AreaId.HOSPITAL,
        identity_id="平民",
        original_identity_id="平民",
        life_state=CharacterLifeState.DEAD,
    )
    state.characters["corpse_faraway"] = CharacterState(
        character_id="corpse_faraway",
        name="远方尸体",
        area=AreaId.FARAWAY,
        initial_area=AreaId.FARAWAY,
        identity_id="平民",
        original_identity_id="平民",
        life_state=CharacterLifeState.DEAD,
    )

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    destination_wait = _choose_goodwill(signal, "goodwill:hermit:1")
    assert isinstance(destination_wait, WaitForInput)
    assert destination_wait.input_type == "choose_ability_target"
    assert AreaId.CITY.value in destination_wait.options
    assert AreaId.FARAWAY.value in destination_wait.options

    corpse_wait = destination_wait.callback(AreaId.CITY.value)
    assert isinstance(corpse_wait, WaitForInput)
    assert corpse_wait.input_type == "choose_ability_target"
    assert set(corpse_wait.options) == {"corpse_city_a", "corpse_city_b"}

    result = corpse_wait.callback("corpse_city_b")

    assert isinstance(result, PhaseComplete)
    assert state.characters["hermit"].area == AreaId.CITY
    assert state.characters["corpse_city_a"].life_state == CharacterLifeState.DEAD
    assert state.characters["corpse_city_b"].life_state == CharacterLifeState.ALIVE
    assert state.characters["corpse_city_b"].tokens.get(TokenType.GOODWILL) == 2
    assert state.characters["corpse_hospital"].life_state == CharacterLifeState.DEAD
    assert state.characters["corpse_faraway"].life_state == CharacterLifeState.DEAD


def test_hermit_goodwill_is_hidden_without_any_destination_with_a_corpse() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["hermit"] = _instantiate("hermit")
    state.characters["hermit"].tokens.add(TokenType.GOODWILL, 5)
    state.script.private_table.characters = [
        CharacterSetup(character_id="hermit", identity_id="平民", hermit_x=2),
    ]

    signal = handler.execute(state)

    assert isinstance(signal, PhaseComplete)


def test_alien_structured_goodwill_kills_same_area_target_via_death_resolver(monkeypatch) -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["alien"] = _instantiate("alien")
    state.characters["alien"].tokens.add(TokenType.GOODWILL, 4)
    state.characters["victim_a"] = CharacterState(
        character_id="victim_a",
        name="受害者A",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.characters["victim_b"] = CharacterState(
        character_id="victim_b",
        name="受害者B",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
    )

    calls: list[str] = []
    original_process_death = atomic.death_resolver.process_death

    def _spy_process_death(character, game_state):
        calls.append(character.character_id)
        return original_process_death(character, game_state)

    monkeypatch.setattr(atomic.death_resolver, "process_death", _spy_process_death)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    target_wait = _choose_goodwill(signal, "goodwill:alien:1")
    assert isinstance(target_wait, WaitForInput)
    assert target_wait.input_type == "choose_ability_target"
    assert set(target_wait.options) == {"victim_a", "victim_b"}

    result = target_wait.callback("victim_a")
    assert isinstance(result, PhaseComplete)
    assert calls == ["victim_a"]
    assert state.characters["victim_a"].life_state == CharacterLifeState.DEAD
    assert state.characters["victim_b"].life_state == CharacterLifeState.ALIVE


def test_nurse_structured_goodwill_is_hidden_without_limit_reached_target() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["nurse"] = _instantiate("nurse")
    state.characters["nurse"].tokens.add(TokenType.GOODWILL, 2)
    state.characters["patient"] = CharacterState(
        character_id="patient",
        name="患者",
        area=AreaId.HOSPITAL,
        initial_area=AreaId.HOSPITAL,
        identity_id="平民",
        original_identity_id="平民",
        paranoia_limit=2,
    )

    signal = handler.execute(state)
    assert isinstance(signal, PhaseComplete)

    state.characters["patient"].tokens.add(TokenType.PARANOIA, 2)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    assert any(
        getattr(option, "ability", None) is not None
        and option.ability.ability_id == "goodwill:nurse:1"
        for option in signal.options
    )


def test_soldier_structured_goodwill_protects_protagonist() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["soldier"] = _instantiate("soldier")
    state.characters["soldier"].tokens.add(TokenType.GOODWILL, 5)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    result = _choose_goodwill(signal, "goodwill:soldier:2")
    assert isinstance(result, (WaitForInput, PhaseComplete))
    assert state.soldier_protection_active is True

    atomic.resolve(
        state,
        [Effect(effect_type=EffectType.PROTAGONIST_DEATH)],
    )
    assert state.protagonist_dead is False


def test_soldier_structured_goodwill_places_two_paranoia() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["soldier"] = _instantiate("soldier")
    state.characters["soldier"].tokens.add(TokenType.GOODWILL, 2)
    state.characters["target"] = CharacterState(
        character_id="target",
        name="目标",
        area=state.characters["soldier"].area,
        initial_area=state.characters["soldier"].area,
        identity_id="平民",
        original_identity_id="平民",
    )

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    result = _choose_goodwill(signal, "goodwill:soldier:1")
    assert isinstance(result, WaitForInput)
    assert result.input_type == "choose_ability_target"
    follow_up = result.callback("target")
    assert isinstance(follow_up, (WaitForInput, PhaseComplete))
    assert state.characters["target"].tokens.get(TokenType.PARANOIA) == 2


def test_detective_structured_goodwill_places_guard() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["detective"] = _instantiate("detective")
    state.characters["detective"].tokens.add(TokenType.GOODWILL, 5)
    state.characters["target"] = CharacterState(
        character_id="target",
        name="目标",
        area=state.characters["detective"].area,
        initial_area=state.characters["detective"].area,
        identity_id="平民",
        original_identity_id="平民",
    )

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    result = _choose_goodwill(signal, "goodwill:detective:2")
    assert isinstance(result, WaitForInput)
    assert result.input_type == "choose_ability_target"
    follow_up = result.callback("target")
    assert isinstance(follow_up, (WaitForInput, PhaseComplete))
    assert state.characters["target"].tokens.get(TokenType.GUARD) == 1


def test_detective_structured_goodwill_reveals_occurred_incident_perpetrator() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["detective"] = _instantiate("detective")
    state.characters["detective"].tokens.add(TokenType.GOODWILL, 4)
    state.script.incidents = [
        IncidentSchedule("murder", day=1, perpetrator_id="male_student"),
        IncidentSchedule("suicide", day=2, perpetrator_id="female_student"),
    ]
    state.incidents_occurred_this_loop = ["murder"]

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    incident_wait = _choose_goodwill(signal, "goodwill:detective:1")
    assert isinstance(incident_wait, PhaseComplete)
    assert state.revealed_incident_perpetrators_this_loop[-1] == {
        "incident_id": "murder",
        "perpetrator_id": "male_student",
        "day": 1,
    }
    assert any(
        event.event_type.name == "INCIDENT_REVEALED"
        and event.data == {
            "incident_id": "murder",
            "perpetrator_id": "male_student",
            "day": 1,
        }
        for event in bus.log
    )


def test_ojousama_structured_goodwill_requires_city_or_school() -> None:
    state = GameState()
    state.characters["ojousama"] = _instantiate("ojousama")
    state.characters["ojousama"].tokens.add(TokenType.GOODWILL, 3)
    state.characters["target"] = CharacterState(
        character_id="target",
        name="目标",
        area=AreaId.HOSPITAL,
        initial_area=AreaId.HOSPITAL,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.characters["ojousama"].area = AreaId.HOSPITAL

    resolver = AbilityResolver()
    assert {
        candidate.ability.ability_id
        for candidate in resolver.collect_goodwill_abilities(state)
    } == set()

    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state.characters["ojousama"].area = AreaId.SCHOOL
    state.characters["target"].area = AreaId.SCHOOL
    state.characters["target"].initial_area = AreaId.SCHOOL

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    result = _choose_goodwill(signal, "goodwill:ojousama:1")
    assert isinstance(result, WaitForInput)
    assert result.input_type == "choose_ability_target"
    follow_up = result.callback("target")
    assert isinstance(follow_up, (WaitForInput, PhaseComplete))
    assert state.characters["target"].tokens.get(TokenType.GOODWILL) == 1


def test_media_person_structured_goodwill_places_paranoia_on_other_character() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["media_person"] = _instantiate("media_person")
    state.characters["media_person"].tokens.add(TokenType.GOODWILL, 2)
    state.characters["target"] = CharacterState(
        character_id="target",
        name="异地区目标",
        area=AreaId.CITY if state.characters["media_person"].area != AreaId.CITY else AreaId.SCHOOL,
        initial_area=AreaId.CITY if state.characters["media_person"].area != AreaId.CITY else AreaId.SCHOOL,
        identity_id="平民",
        original_identity_id="平民",
    )

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    result = _choose_goodwill(signal, "goodwill:media_person:1")
    assert isinstance(result, (WaitForInput, PhaseComplete))
    assert state.characters["target"].tokens.get(TokenType.PARANOIA) == 1


def test_phantom_structured_goodwill_moves_same_area_target_via_game_state_move_character(monkeypatch) -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["phantom"] = _instantiate("phantom")
    state.characters["phantom"].tokens.add(TokenType.GOODWILL, 3)
    state.characters["target"] = CharacterState(
        character_id="target",
        name="目标",
        area=state.characters["phantom"].area,
        initial_area=state.characters["phantom"].area,
        identity_id="平民",
        original_identity_id="平民",
    )

    calls: list[tuple[str, object]] = []
    original_move_character = state.move_character

    def _spy_move_character(character_id: str, destination: object) -> bool:
        calls.append((character_id, destination))
        return original_move_character(character_id, destination)

    monkeypatch.setattr(state, "move_character", _spy_move_character)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    target_wait = _choose_goodwill(signal, "goodwill:phantom:1")
    assert isinstance(target_wait, WaitForInput)
    assert target_wait.input_type == "choose_ability_target"
    assert set(target_wait.options) == {"phantom", "target"}

    area_wait = target_wait.callback("target")
    assert isinstance(area_wait, WaitForInput)
    assert area_wait.input_type == "choose_ability_target"
    assert set(area_wait.options) == {
        AreaId.HOSPITAL.value,
        AreaId.SHRINE.value,
        AreaId.CITY.value,
        AreaId.SCHOOL.value,
    }

    result = area_wait.callback(AreaId.HOSPITAL.value)
    assert isinstance(result, PhaseComplete)
    assert state.characters["target"].area == AreaId.HOSPITAL
    assert calls == [("target", AreaId.HOSPITAL.value)]


def test_phantom_structured_goodwill_removes_self_via_unified_life_state() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["phantom"] = _instantiate("phantom")
    state.characters["phantom"].tokens.add(TokenType.GOODWILL, 4)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    result = _choose_goodwill(signal, "goodwill:phantom:2")
    assert isinstance(result, PhaseComplete)
    assert state.characters["phantom"].life_state == CharacterLifeState.REMOVED
    assert state.characters["phantom"].is_removed() is True


def test_little_girl_structured_goodwill_moves_to_adjacent_area_only_via_game_state_move_character(monkeypatch) -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["little_girl"] = _instantiate("little_girl")
    state.characters["little_girl"].tokens.add(TokenType.GOODWILL, 3)

    calls: list[tuple[str, object]] = []
    original_move_character = state.move_character

    def _spy_move_character(character_id: str, destination: object) -> bool:
        calls.append((character_id, destination))
        return original_move_character(character_id, destination)

    monkeypatch.setattr(state, "move_character", _spy_move_character)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    after_lift = _choose_goodwill(signal, "goodwill:little_girl:1")
    assert isinstance(after_lift, WaitForInput)
    assert state.characters["little_girl"].forbidden_areas == []

    area_wait = _choose_goodwill(after_lift, "goodwill:little_girl:2")
    assert isinstance(area_wait, WaitForInput)
    assert area_wait.input_type == "choose_ability_target"
    assert set(area_wait.options) == {AreaId.SHRINE.value, AreaId.CITY.value}

    result = area_wait.callback(AreaId.CITY.value)
    assert isinstance(result, WaitForInput)
    assert state.characters["little_girl"].area == AreaId.CITY
    assert calls == [("little_girl", AreaId.CITY.value)]


def test_doctor_structured_goodwill_lifts_inpatient_forbidden_areas_for_current_loop() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["doctor"] = _instantiate("doctor")
    state.characters["doctor"].tokens.add(TokenType.GOODWILL, 3)
    state.characters["inpatient"] = _instantiate("inpatient")

    assert state.characters["inpatient"].forbidden_areas == [AreaId.SHRINE, AreaId.SCHOOL, AreaId.CITY]
    assert state.move_character("inpatient", AreaId.CITY) is False

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    result = _choose_goodwill(signal, "goodwill:doctor:2")
    assert isinstance(result, (WaitForInput, PhaseComplete))
    assert state.characters["inpatient"].forbidden_areas == []
    assert state.move_character("inpatient", AreaId.CITY) is True
    assert state.characters["inpatient"].area == AreaId.CITY


def test_vip_structured_goodwill_reveals_territory_character_identity() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["vip"] = _instantiate("vip")
    state.characters["vip"].area = AreaId.CITY
    state.characters["vip"].initial_area = AreaId.CITY
    state.characters["vip"].territory_area = AreaId.SHRINE
    state.characters["vip"].tokens.add(TokenType.GOODWILL, 5)
    state.characters["office_worker"] = _instantiate("office_worker", identity_id="killer")
    state.characters["office_worker"].area = AreaId.SHRINE
    state.characters["office_worker"].initial_area = AreaId.SHRINE
    state.characters["teacher"] = _instantiate("teacher", identity_id="cultist")
    state.characters["teacher"].area = AreaId.CITY
    state.characters["teacher"].initial_area = AreaId.CITY

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    result = _choose_goodwill(signal, "goodwill:vip:1")

    assert isinstance(result, PhaseComplete)
    assert state.characters["office_worker"].revealed is True
    assert state.characters["teacher"].revealed is False
    assert state.characters["vip"].revealed is False


def test_vip_structured_goodwill_in_territory_does_not_reveal_vip_self() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["vip"] = _instantiate("vip")
    state.characters["vip"].area = AreaId.SHRINE
    state.characters["vip"].initial_area = AreaId.CITY
    state.characters["vip"].territory_area = AreaId.SHRINE
    state.characters["vip"].tokens.add(TokenType.GOODWILL, 5)
    state.characters["office_worker"] = _instantiate("office_worker", identity_id="killer")
    state.characters["office_worker"].area = AreaId.SHRINE
    state.characters["office_worker"].initial_area = AreaId.SHRINE

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    result = _choose_goodwill(signal, "goodwill:vip:1")

    assert isinstance(result, PhaseComplete)
    assert state.characters["office_worker"].revealed is True
    assert state.characters["vip"].revealed is False


def test_nurse_structured_goodwill_removes_paranoia_from_limit_reached_target() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["nurse"] = _instantiate("nurse")
    state.characters["nurse"].tokens.add(TokenType.GOODWILL, 2)
    state.characters["patient"] = CharacterState(
        character_id="patient",
        name="患者",
        area=state.characters["nurse"].area,
        initial_area=state.characters["nurse"].area,
        identity_id="平民",
        original_identity_id="平民",
        paranoia_limit=2,
    )
    state.characters["patient"].tokens.add(TokenType.PARANOIA, 2)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    result = _choose_goodwill(signal, "goodwill:nurse:1")
    assert isinstance(result, PhaseComplete)
    assert state.characters["patient"].tokens.get(TokenType.PARANOIA) == 1


def test_cult_leader_structured_goodwill_places_goodwill_on_limit_reached_target() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["cult_leader"] = _instantiate("cult_leader")
    state.characters["cult_leader"].tokens.add(TokenType.GOODWILL, 3)
    state.characters["target"] = CharacterState(
        character_id="target",
        name="达限目标",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
        paranoia_limit=2,
    )
    state.characters["target"].tokens.add(TokenType.PARANOIA, 2)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    result = _choose_goodwill(signal, "goodwill:cult_leader:1")
    assert isinstance(result, (WaitForInput, PhaseComplete))
    assert state.characters["target"].tokens.get(TokenType.GOODWILL) == 1


def test_deity_structured_goodwill_can_remove_intrigue_from_board() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["deity"] = _instantiate("deity")
    state.characters["deity"].tokens.add(TokenType.GOODWILL, 5)
    area = state.characters["deity"].area
    state.board.areas[area].tokens.add(TokenType.INTRIGUE, 1)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    target_wait = _choose_goodwill(signal, "goodwill:deity:2")
    assert isinstance(target_wait, WaitForInput)
    assert area.value in target_wait.options

    result = target_wait.callback(area.value)
    assert isinstance(result, (WaitForInput, PhaseComplete))
    assert state.board.areas[area].tokens.get(TokenType.INTRIGUE) == 0


def test_deity_structured_goodwill_reveals_incident_perpetrator() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["deity"] = _instantiate("deity")
    state.characters["deity"].tokens.add(TokenType.GOODWILL, 4)
    state.script.incidents = [
        IncidentSchedule("murder", day=1, perpetrator_id="male_student"),
        IncidentSchedule("suicide", day=2, perpetrator_id="female_student"),
    ]

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    incident_wait = _choose_goodwill(signal, "goodwill:deity:1")
    assert isinstance(incident_wait, WaitForInput)
    assert incident_wait.input_type == "choose_ability_target"
    assert set(incident_wait.options) == {"murder", "suicide"}

    result = incident_wait.callback("suicide")
    assert isinstance(result, (WaitForInput, PhaseComplete))
    assert state.revealed_incident_perpetrators_this_loop[-1] == {
        "incident_id": "suicide",
        "perpetrator_id": "female_student",
        "day": 2,
    }
    assert any(
        event.event_type.name == "INCIDENT_REVEALED"
        and event.data == {
            "incident_id": "suicide",
            "perpetrator_id": "female_student",
            "day": 2,
        }
        for event in bus.log
    )


def test_transfer_student_structured_goodwill_replaces_intrigue_with_goodwill() -> None:
    bus, atomic = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, atomic)
    state = GameState()
    state.characters["transfer_student"] = _instantiate("transfer_student")
    state.characters["transfer_student"].tokens.add(TokenType.GOODWILL, 3)
    state.characters["target"] = CharacterState(
        character_id="target",
        name="目标",
        area=state.characters["transfer_student"].area,
        initial_area=state.characters["transfer_student"].area,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.characters["target"].tokens.add(TokenType.INTRIGUE, 1)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    result = _choose_goodwill(signal, "goodwill:transfer_student:1")
    assert isinstance(result, (WaitForInput, PhaseComplete))
    assert state.characters["target"].tokens.get(TokenType.INTRIGUE) == 0
    assert state.characters["target"].tokens.get(TokenType.GOODWILL) == 1

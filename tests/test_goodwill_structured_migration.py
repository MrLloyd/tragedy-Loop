from __future__ import annotations

from engine.event_bus import EventBus
from engine.game_state import GameState
from engine.models.ability import Ability
from engine.models.character import CharacterState
from engine.models.effects import Effect
from engine.models.enums import AbilityTiming, AbilityType, AreaId, Attribute, EffectType, TokenType
from engine.models.script import CharacterSetup, IncidentSchedule
from engine.phases.phase_base import PhaseComplete, ProtagonistAbilityHandler, WaitForInput
from engine.resolvers.ability_resolver import AbilityResolver
from engine.resolvers.atomic_resolver import AtomicResolver
from engine.resolvers.death_resolver import DeathResolver
from engine.rules.character_loader import instantiate_character_state, load_character_defs

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
        return response.callback("allow")
    return response


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
        is_alive=False,
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
        is_alive=False,
    )
    state.characters["corpse_b"] = CharacterState(
        character_id="corpse_b",
        name="尸体B",
        area=AreaId.HOSPITAL,
        initial_area=AreaId.HOSPITAL,
        identity_id="killer",
        original_identity_id="killer",
        is_alive=False,
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
        is_alive=False,
    )
    state.characters["corpse_b"] = CharacterState(
        character_id="corpse_b",
        name="尸体B",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
        is_alive=False,
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
    assert state.characters["corpse_a"].is_alive is True
    assert state.characters["corpse_a"].is_removed is False
    assert state.characters["corpse_b"].is_alive is False


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
    assert state.characters["victim_a"].is_alive is False
    assert state.characters["victim_b"].is_alive is True


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

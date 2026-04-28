from __future__ import annotations

from engine.event_bus import EventBus, GameEventType
from engine.game_controller import GameController
from engine.game_state import GameState
from engine.models.ability import Ability
from engine.models.cards import ActionCard, CardPlacement
from engine.models.character import CharacterState
from engine.models.effects import Effect
from engine.models.enums import AbilityTiming, AbilityType, AreaId, CardType, CharacterLifeState, DeathResult, EffectType, GamePhase, Outcome, PlayerRole, TokenType
from engine.models.identity import IdentityDef
from engine.models.incident import IncidentSchedule
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
from engine.resolvers.ability_resolver import AbilityResolver
from engine.resolvers.atomic_resolver import AtomicResolver
from engine.resolvers.death_resolver import DeathResolver
from engine.rules.character_loader import instantiate_character_state, load_character_defs
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


def _build_reference_btx_state() -> GameState:
    return build_game_state_from_module(
        "basic_tragedy_x",
        loop_count=3,
        days_per_loop=3,
        rule_y_id="btx_sealed_evil",
        rule_x_ids=["btx_friends_circle", "btx_love_scenic_line"],
        character_setups=[
            CharacterSetup("male_student", "commoner"),
            CharacterSetup("female_student", "cultist"),
            CharacterSetup("idol", "rumormonger"),
            CharacterSetup("office_worker", "friend"),
            CharacterSetup("shrine_maiden", "friend"),
            CharacterSetup("alien", "beloved"),
            CharacterSetup("inpatient", "lover"),
            CharacterSetup("nurse", "mastermind"),
            CharacterSetup("appraiser", "commoner"),
        ],
        incidents=[
            IncidentSchedule("suicide", day=3, perpetrator_id="female_student"),
        ],
    )


def _appraiser_move_option(source_id: str, token_type: str, target_id: str) -> str:
    return f"{source_id}|{token_type}|{target_id}"


def _install_identity(state: GameState, identity_id: str, abilities: list[Ability]) -> None:
    state.identity_defs[identity_id] = IdentityDef(
        identity_id=identity_id,
        name=identity_id,
        module="test",
        abilities=abilities,
    )


def test_entry_sync_handles_deity_loop_and_transfer_student_day_gates() -> None:
    controller = GameController()
    controller.state.characters["deity"] = CharacterState(
        character_id="deity",
        name="神灵",
        area=AreaId.SHRINE,
        initial_area=AreaId.SHRINE,
        identity_id="friend",
        original_identity_id="friend",
        entry_loop=2,
    )
    controller.state.characters["transfer_student"] = CharacterState(
        character_id="transfer_student",
        name="转校生",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="friend",
        original_identity_id="friend",
        entry_day=3,
    )

    controller.state.current_loop = 1
    controller.state.current_day = 1
    controller._sync_entry_characters_for_phase(GamePhase.LOOP_START)
    assert controller.state.characters["deity"].is_removed()
    assert controller.state.characters["transfer_student"].is_removed()

    controller.state.current_loop = 2
    controller._sync_entry_characters_for_phase(GamePhase.LOOP_START)
    assert controller.state.characters["deity"].is_active()
    assert controller.state.characters["transfer_student"].is_removed()

    controller.state.current_day = 2
    controller._sync_entry_characters_for_phase(GamePhase.TURN_START)
    assert controller.state.characters["transfer_student"].is_removed()

    controller.state.current_day = 3
    controller._sync_entry_characters_for_phase(GamePhase.TURN_START)
    assert controller.state.characters["transfer_student"].is_active()


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
        life_state=CharacterLifeState.DEAD,
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


def test_loop_start_handler_executes_black_cat_character_trait_ability() -> None:
    bus, resolver = _resolver_bundle()
    handler = LoopStartHandler(bus, resolver)
    state = GameState()
    apply_loaded_module(state, load_module("first_steps"))
    defs = load_character_defs()
    state.characters["black_cat"] = instantiate_character_state(
        CharacterSetup(character_id="black_cat", identity_id="commoner"),
        defs,
    )

    signal = handler.execute(state)

    assert isinstance(signal, PhaseComplete)
    assert state.board.areas[AreaId.SHRINE].tokens.get(TokenType.INTRIGUE) == 1


def test_playwright_ability_handler_waits_for_servant_follow_choice() -> None:
    bus, resolver = _resolver_bundle()
    handler = PlaywrightAbilityHandler(bus, resolver)
    state = GameState()
    state.characters["controller"] = CharacterState(
        character_id="controller",
        name="控制者",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="controller_identity",
        original_identity_id="controller_identity",
    )
    state.characters["servant"] = CharacterState(
        character_id="servant",
        name="从者",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="平民",
        original_identity_id="平民",
    )
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
    _install_identity(
        state,
        "controller_identity",
        [
            Ability(
                ability_id="controller_move_pair",
                name="控制者双重移动",
                ability_type=AbilityType.OPTIONAL,
                timing=AbilityTiming.PLAYWRIGHT_ABILITY,
                once_per_loop=True,
                effects=[
                    Effect(
                        effect_type=EffectType.MOVE_CHARACTER,
                        target="vip",
                        value=AreaId.CITY.value,
                    ),
                    Effect(
                        effect_type=EffectType.MOVE_CHARACTER,
                        target="ojousama",
                        value=AreaId.HOSPITAL.value,
                    ),
                ],
            )
        ],
    )

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    choice = _ability_choice(signal, "controller_move_pair")

    follow_wait = signal.callback(choice)

    assert isinstance(follow_wait, WaitForInput)
    assert follow_wait.player == "protagonist_0"
    assert follow_wait.options == ["ojousama", "vip"]

    result = follow_wait.callback("vip")

    assert isinstance(result, PhaseComplete)
    assert state.characters["vip"].area == AreaId.CITY
    assert state.characters["ojousama"].area == AreaId.HOSPITAL
    assert state.characters["servant"].area == AreaId.CITY


def test_servant_follow_targets_include_runtime_trait_target_overrides() -> None:
    bus, resolver = _resolver_bundle()
    state = GameState()
    state.characters["servant"] = CharacterState(
        character_id="servant",
        name="从者",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.characters["teacher"] = CharacterState(
        character_id="teacher",
        name="老师",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.trait_target_overrides["servant"] = {"teacher"}

    result = resolver.resolve(
        state,
        [
            Effect(
                effect_type=EffectType.MOVE_CHARACTER,
                target="teacher",
                value=AreaId.CITY.value,
            )
        ],
    )

    assert result.outcome == Outcome.NONE
    assert state.characters["teacher"].area == AreaId.CITY
    assert state.characters["servant"].area == AreaId.CITY


def test_servant_death_substitutes_for_runtime_override_target() -> None:
    bus, resolver = _resolver_bundle()
    state = GameState()
    state.characters["servant"] = CharacterState(
        character_id="servant",
        name="从者",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.characters["teacher"] = CharacterState(
        character_id="teacher",
        name="老师",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.trait_target_overrides["servant"] = {"teacher"}

    result = resolver.resolve(
        state,
        [
            Effect(
                effect_type=EffectType.KILL_CHARACTER,
                target="teacher",
            )
        ],
    )

    assert result.outcome == Outcome.NONE
    assert result.mutations[0].details["death_result"] == DeathResult.PREVENTED_BY_SERVANT
    assert result.mutations[0].details["death_target_id"] == "servant"
    assert state.characters["teacher"].is_active()
    assert state.characters["servant"].is_dead()


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


def test_vip_cultist_can_nullify_forbid_intrigue_at_territory_board() -> None:
    bus, resolver = _resolver_bundle()
    handler = ActionResolveHandler(bus, resolver)
    state = GameState()
    apply_loaded_module(state, load_module("basic_tragedy_x"))
    state.characters["vip"] = CharacterState(
        character_id="vip",
        name="大人物",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        territory_area=AreaId.SHRINE,
        identity_id="cultist",
        original_identity_id="cultist",
    )
    state.placed_cards = [
        CardPlacement(
            ActionCard(CardType.FORBID_INTRIGUE, PlayerRole.PROTAGONIST_0),
            PlayerRole.PROTAGONIST_0,
            "board",
            AreaId.SHRINE.value,
            face_down=True,
        ),
        CardPlacement(
            ActionCard(CardType.INTRIGUE_PLUS_1, PlayerRole.MASTERMIND),
            PlayerRole.MASTERMIND,
            "board",
            AreaId.SHRINE.value,
            face_down=True,
        ),
    ]

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    choice = _ability_choice(signal, "cultist_action_resolve_nullify_forbid_intrigue_board")

    location_wait = signal.callback(choice)
    assert isinstance(location_wait, WaitForInput)
    assert location_wait.input_type == "choose_ability_location"
    assert set(location_wait.options) == {AreaId.CITY.value, AreaId.SHRINE.value}

    result = location_wait.callback(AreaId.SHRINE.value)

    assert isinstance(result, PhaseComplete)
    assert state.placed_cards[0].nullified is True
    assert state.placed_cards[1].nullified is False
    assert state.board.areas[AreaId.SHRINE].tokens.get(TokenType.INTRIGUE) == 1


def test_vip_cultist_can_choose_body_area_to_nullify_character_forbid_intrigue() -> None:
    bus, resolver = _resolver_bundle()
    handler = ActionResolveHandler(bus, resolver)
    state = GameState()
    apply_loaded_module(state, load_module("basic_tragedy_x"))
    state.characters["vip"] = CharacterState(
        character_id="vip",
        name="大人物",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        territory_area=AreaId.SHRINE,
        identity_id="cultist",
        original_identity_id="cultist",
    )
    state.characters["teacher"] = CharacterState(
        character_id="teacher",
        name="教师",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.characters["shrine_maiden"] = CharacterState(
        character_id="shrine_maiden",
        name="巫女",
        area=AreaId.SHRINE,
        initial_area=AreaId.SHRINE,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.placed_cards = [
        CardPlacement(
            ActionCard(CardType.FORBID_INTRIGUE, PlayerRole.PROTAGONIST_0),
            PlayerRole.PROTAGONIST_0,
            "character",
            "teacher",
            face_down=True,
        ),
        CardPlacement(
            ActionCard(CardType.INTRIGUE_PLUS_1, PlayerRole.MASTERMIND),
            PlayerRole.MASTERMIND,
            "character",
            "teacher",
            face_down=True,
        ),
        CardPlacement(
            ActionCard(CardType.FORBID_INTRIGUE, PlayerRole.PROTAGONIST_1),
            PlayerRole.PROTAGONIST_1,
            "character",
            "shrine_maiden",
            face_down=True,
        ),
    ]

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    choice = _ability_choice(signal, "cultist_action_resolve_nullify_forbid_intrigue_character")

    location_wait = signal.callback(choice)
    assert isinstance(location_wait, WaitForInput)
    assert location_wait.input_type == "choose_ability_location"

    next_wait = location_wait.callback(AreaId.CITY.value)
    assert isinstance(next_wait, WaitForInput)
    assert next_wait.input_type == "choose_action_resolve_ability"
    result = next_wait.callback("pass")

    assert isinstance(result, PhaseComplete)
    assert state.placed_cards[0].nullified is True
    assert state.placed_cards[1].nullified is False
    assert state.placed_cards[2].nullified is False


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


def test_ai_goodwill_uses_public_incident_and_does_not_mark_incident_occurred() -> None:
    bus, resolver = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, resolver)
    state = GameState()
    loaded = load_module("basic_tragedy_x")
    apply_loaded_module(state, loaded)
    state.script.private_table.rule_y = next(
        rule for rule in loaded.module_def.rules_y if rule.rule_id == "btx_change_future"
    )
    state.script.private_table.rules_x = [
        next(rule for rule in loaded.module_def.rules_x if rule.rule_id == "btx_friends_circle"),
        next(rule for rule in loaded.module_def.rules_x if rule.rule_id == "btx_love_scenic_line"),
    ]
    state.script.public_table.incidents = [
        {"name": "公开蝴蝶", "day": 2},
    ]
    state.script.private_table.public_incident_refs = ["butterfly_effect"]
    state.script.private_table.incidents = [
        IncidentSchedule("suicide", day=3, perpetrator_id="other"),
    ]
    state.characters["ai"] = CharacterState(
        character_id="ai",
        name="AI",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="mastermind",
        original_identity_id="mastermind",
        goodwill_ability_texts=["能力1", "", "", ""],
        goodwill_ability_goodwill_requirements=[3, 0, 0, 0],
        goodwill_ability_once_per_loop=[True],
    )
    state.characters["ai"].tokens.add(TokenType.GOODWILL, 3)
    state.characters["target"] = CharacterState(
        character_id="target",
        name="目标",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
    )

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    public_wait = signal.callback(_ability_choice(signal, "goodwill:ai:1"))
    assert isinstance(public_wait, WaitForInput)
    assert public_wait.input_type == "choose_public_incident"
    assert public_wait.player == "protagonist_0"
    assert len(public_wait.options) == 1
    assert public_wait.options[0]["name"] == "公开蝴蝶"
    assert public_wait.options[0]["day"] == 2

    character_wait = public_wait.callback(public_wait.options[0])
    assert isinstance(character_wait, WaitForInput)
    assert character_wait.input_type == "choose_incident_character"
    assert character_wait.player == "protagonist_0"
    assert character_wait.options == ["ai", "target"]

    token_wait = character_wait.callback("target")
    assert isinstance(token_wait, WaitForInput)
    assert token_wait.input_type == "choose_incident_token_type"
    assert token_wait.player == "protagonist_0"
    assert set(token_wait.options) == {"goodwill", "paranoia", "intrigue"}

    done = token_wait.callback("intrigue")

    assert isinstance(done, PhaseComplete)
    assert state.characters["target"].tokens.get(TokenType.INTRIGUE) == 1
    assert state.incidents_occurred_this_loop == []
    assert state.incident_results_this_loop == []
    assert not any(
        event.event_type == GameEventType.INCIDENT_OCCURRED
        and event.data.get("incident_id") == "butterfly_effect"
        for event in bus.log
    )

    loop_end_failures = AbilityResolver().collect_abilities(
        state,
        timing=AbilityTiming.LOOP_END,
        ability_type=AbilityType.LOSS_CONDITION,
    )
    assert "btx_fail_butterfly_effect_occurred" not in {
        candidate.ability.ability_id for candidate in loop_end_failures
    }


def test_informant_goodwill_reveals_other_selected_rule_x_after_declaration() -> None:
    bus, resolver = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, resolver)
    state = build_game_state_from_module(
        "basic_tragedy_x",
        loop_count=1,
        days_per_loop=1,
        rule_y_id="btx_murder_plan",
        rule_x_ids=["btx_rumors", "btx_latent_serial_killer"],
        character_setups=[
            CharacterSetup("informant", "commoner"),
            CharacterSetup("male_student", "mastermind"),
            CharacterSetup("female_student", "key_person"),
            CharacterSetup("idol", "killer"),
            CharacterSetup("office_worker", "friend"),
            CharacterSetup("shrine_maiden", "serial_killer"),
        ],
        incidents=[],
        skip_script_validation=True,
    )
    state.characters["informant"].tokens.add(TokenType.GOODWILL, 5)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    choose_wait = signal.callback(_ability_choice(signal, "goodwill:informant:1"))
    assert isinstance(choose_wait, WaitForInput)
    assert choose_wait.input_type == "respond_goodwill_ability"

    declared_wait = choose_wait.callback("allow")
    assert isinstance(declared_wait, WaitForInput)
    assert declared_wait.input_type == "choose_rule_x_declaration"

    revealed = declared_wait.callback("btx_rumors")

    assert isinstance(revealed, PhaseComplete)
    assert state.revealed_rule_x_ids == ["btx_latent_serial_killer"]
    assert any(
        event.event_type == GameEventType.RULE_X_REVEALED
        and event.data.get("rule_x_id") == "btx_latent_serial_killer"
        for event in bus.log
    )


def test_informant_goodwill_allows_playwright_choice_when_both_selected_rules_differ() -> None:
    bus, resolver = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, resolver)
    state = build_game_state_from_module(
        "basic_tragedy_x",
        loop_count=1,
        days_per_loop=1,
        rule_y_id="btx_murder_plan",
        rule_x_ids=["btx_rumors", "btx_latent_serial_killer"],
        character_setups=[
            CharacterSetup("informant", "commoner"),
            CharacterSetup("male_student", "mastermind"),
            CharacterSetup("female_student", "key_person"),
            CharacterSetup("idol", "killer"),
            CharacterSetup("office_worker", "friend"),
            CharacterSetup("shrine_maiden", "serial_killer"),
        ],
        incidents=[],
        skip_script_validation=True,
    )
    state.characters["informant"].tokens.add(TokenType.GOODWILL, 5)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    response_wait = signal.callback(_ability_choice(signal, "goodwill:informant:1"))
    assert isinstance(response_wait, WaitForInput)

    declared_wait = response_wait.callback("allow")
    assert isinstance(declared_wait, WaitForInput)

    reveal_wait = declared_wait.callback("btx_causal_line")
    assert isinstance(reveal_wait, WaitForInput)
    assert reveal_wait.input_type == "choose_rule_x_reveal"
    assert set(reveal_wait.options) == {"btx_rumors", "btx_latent_serial_killer"}

    done = reveal_wait.callback("btx_rumors")

    assert isinstance(done, PhaseComplete)
    assert state.revealed_rule_x_ids == ["btx_rumors"]


def test_informant_goodwill_reveals_first_steps_rule_x_directly() -> None:
    bus, resolver = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, resolver)
    state = build_game_state_from_module(
        "first_steps",
        loop_count=1,
        days_per_loop=1,
        rule_y_id="fs_murder_plan",
        rule_x_ids=["fs_ripper_shadow"],
        character_setups=[
            CharacterSetup("informant", "commoner"),
            CharacterSetup("male_student", "mastermind"),
            CharacterSetup("female_student", "key_person"),
            CharacterSetup("idol", "killer"),
            CharacterSetup("office_worker", "friend"),
            CharacterSetup("shrine_maiden", "serial_killer"),
        ],
        incidents=[],
        skip_script_validation=True,
    )
    state.characters["informant"].tokens.add(TokenType.GOODWILL, 5)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    response_wait = signal.callback(_ability_choice(signal, "goodwill:informant:1"))
    assert isinstance(response_wait, WaitForInput)

    done = response_wait.callback("allow")

    assert isinstance(done, PhaseComplete)
    assert state.revealed_rule_x_ids == ["fs_ripper_shadow"]
    assert any(
        event.event_type == GameEventType.RULE_X_REVEALED
        and event.data.get("rule_x_id") == "fs_ripper_shadow"
        for event in bus.log
    )


def test_appraiser_goodwill_moves_selected_token_between_two_same_area_characters() -> None:
    bus, resolver = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, resolver)
    state = _build_reference_btx_state()
    state.characters["appraiser"].tokens.add(TokenType.GOODWILL, 2)
    state.characters["appraiser"].area = AreaId.CITY
    state.characters["male_student"].area = AreaId.CITY
    state.characters["female_student"].area = AreaId.CITY
    state.characters["idol"].area = AreaId.SCHOOL
    state.characters["office_worker"].area = AreaId.HOSPITAL
    state.characters["alien"].area = AreaId.SHRINE
    state.characters["male_student"].tokens.add(TokenType.PARANOIA, 1)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    response_wait = signal.callback(_ability_choice(signal, "goodwill:appraiser:1"))
    assert isinstance(response_wait, WaitForInput)
    assert response_wait.input_type == "respond_goodwill_ability"

    source_wait = response_wait.callback("allow")
    assert isinstance(source_wait, WaitForInput)
    assert source_wait.input_type == "choose_ability_target"
    assert set(source_wait.options) == {"male_student", "female_student"}

    target_wait = source_wait.callback("male_student")
    assert isinstance(target_wait, WaitForInput)
    assert target_wait.input_type == "choose_ability_target"
    assert set(target_wait.options) == {"female_student"}

    token_wait = target_wait.callback("female_student")
    assert isinstance(token_wait, WaitForInput)
    assert token_wait.input_type == "choose_ability_token_move"
    assert token_wait.options == [
        _appraiser_move_option("male_student", "paranoia", "female_student")
    ]

    done = token_wait.callback(_appraiser_move_option("male_student", "paranoia", "female_student"))

    assert isinstance(done, PhaseComplete)
    assert state.characters["male_student"].tokens.get(TokenType.PARANOIA) == 0
    assert state.characters["female_student"].tokens.get(TokenType.PARANOIA) == 1


def test_appraiser_goodwill_can_select_two_empty_characters_and_resolve_no_effect() -> None:
    bus, resolver = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, resolver)
    state = _build_reference_btx_state()
    state.characters["appraiser"].tokens.add(TokenType.GOODWILL, 2)
    state.characters["appraiser"].area = AreaId.CITY
    state.characters["male_student"].area = AreaId.CITY
    state.characters["female_student"].area = AreaId.CITY
    state.characters["idol"].area = AreaId.SCHOOL
    state.characters["office_worker"].area = AreaId.HOSPITAL
    state.characters["alien"].area = AreaId.SHRINE

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)

    response_wait = signal.callback(_ability_choice(signal, "goodwill:appraiser:1"))
    assert isinstance(response_wait, WaitForInput)

    source_wait = response_wait.callback("allow")
    assert isinstance(source_wait, WaitForInput)

    target_wait = source_wait.callback("male_student")
    assert isinstance(target_wait, WaitForInput)

    done = target_wait.callback("female_student")

    assert isinstance(done, PhaseComplete)
    assert state.characters["male_student"].tokens.get(TokenType.PARANOIA) == 0
    assert state.characters["female_student"].tokens.get(TokenType.PARANOIA) == 0


def test_appraiser_goodwill_must_choose_one_available_move_after_targets_selected() -> None:
    bus, resolver = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, resolver)
    state = _build_reference_btx_state()
    state.characters["appraiser"].tokens.add(TokenType.GOODWILL, 2)
    state.characters["appraiser"].area = AreaId.CITY
    state.characters["male_student"].area = AreaId.CITY
    state.characters["female_student"].area = AreaId.CITY
    state.characters["idol"].area = AreaId.SCHOOL
    state.characters["office_worker"].area = AreaId.HOSPITAL
    state.characters["alien"].area = AreaId.SHRINE
    state.characters["male_student"].tokens.add(TokenType.PARANOIA, 1)
    state.characters["male_student"].tokens.add(TokenType.GOODWILL, 1)
    state.characters["female_student"].tokens.add(TokenType.INTRIGUE, 1)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    response_wait = signal.callback(_ability_choice(signal, "goodwill:appraiser:1"))
    assert isinstance(response_wait, WaitForInput)

    source_wait = response_wait.callback("allow")
    assert isinstance(source_wait, WaitForInput)
    target_wait = source_wait.callback("male_student")
    assert isinstance(target_wait, WaitForInput)
    token_wait = target_wait.callback("female_student")

    assert isinstance(token_wait, WaitForInput)
    assert token_wait.input_type == "choose_ability_token_move"
    assert set(token_wait.options) == {
        _appraiser_move_option("male_student", "paranoia", "female_student"),
        _appraiser_move_option("male_student", "goodwill", "female_student"),
        _appraiser_move_option("female_student", "intrigue", "male_student"),
    }


def test_appraiser_goodwill_must_move_from_b_when_only_b_has_tokens() -> None:
    bus, resolver = _resolver_bundle()
    handler = ProtagonistAbilityHandler(bus, resolver)
    state = _build_reference_btx_state()
    state.characters["appraiser"].tokens.add(TokenType.GOODWILL, 2)
    state.characters["appraiser"].area = AreaId.CITY
    state.characters["male_student"].area = AreaId.CITY
    state.characters["female_student"].area = AreaId.CITY
    state.characters["idol"].area = AreaId.SCHOOL
    state.characters["office_worker"].area = AreaId.HOSPITAL
    state.characters["alien"].area = AreaId.SHRINE
    state.characters["female_student"].tokens.add(TokenType.PARANOIA, 1)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    response_wait = signal.callback(_ability_choice(signal, "goodwill:appraiser:1"))
    assert isinstance(response_wait, WaitForInput)

    source_wait = response_wait.callback("allow")
    assert isinstance(source_wait, WaitForInput)
    target_wait = source_wait.callback("male_student")
    assert isinstance(target_wait, WaitForInput)
    move_wait = target_wait.callback("female_student")

    assert isinstance(move_wait, WaitForInput)
    assert move_wait.input_type == "choose_ability_token_move"
    assert move_wait.options == [
        _appraiser_move_option("female_student", "paranoia", "male_student")
    ]

    done = move_wait.callback(_appraiser_move_option("female_student", "paranoia", "male_student"))

    assert isinstance(done, PhaseComplete)
    assert state.characters["female_student"].tokens.get(TokenType.PARANOIA) == 0
    assert state.characters["male_student"].tokens.get(TokenType.PARANOIA) == 1


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
    assert state.characters["victim"].life_state == CharacterLifeState.DEAD
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
    assert state.characters["key"].life_state == CharacterLifeState.DEAD
    assert "key_person_dead" in state.failure_flags


def test_vip_killer_can_choose_territory_to_kill_key_person_without_hitting_body_area() -> None:
    bus, resolver = _resolver_bundle()
    handler = TurnEndHandler(bus, resolver)
    state = GameState()
    apply_loaded_module(state, load_module("first_steps"))
    state.characters["vip"] = CharacterState(
        character_id="vip",
        name="大人物",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        territory_area=AreaId.SHRINE,
        identity_id="killer",
        original_identity_id="killer",
    )
    state.characters["key"] = CharacterState(
        character_id="key",
        name="关键人物",
        area=AreaId.SHRINE,
        initial_area=AreaId.SHRINE,
        identity_id="key_person",
        original_identity_id="key_person",
    )
    state.characters["teacher"] = CharacterState(
        character_id="teacher",
        name="教师",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.characters["key"].tokens.add(TokenType.INTRIGUE, 2)

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    choice = _ability_choice(signal, "killer_turn_end_kill_key_person")

    location_wait = signal.callback(choice)
    assert isinstance(location_wait, WaitForInput)
    assert location_wait.input_type == "choose_ability_location"
    assert set(location_wait.options) == {AreaId.CITY.value, AreaId.SHRINE.value}

    result = location_wait.callback(AreaId.SHRINE.value)

    assert isinstance(result, ForceLoopEnd)
    assert result.reason == "killer_turn_end_kill_key_person"
    assert state.characters["key"].life_state == CharacterLifeState.DEAD
    assert state.characters["teacher"].life_state == CharacterLifeState.ALIVE
    assert state.characters["vip"].life_state == CharacterLifeState.ALIVE
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
    assert state.characters["serial"].life_state == CharacterLifeState.ALIVE
    assert state.characters["victim"].life_state == CharacterLifeState.DEAD
    assert any(
        event.event_type == GameEventType.ABILITY_DECLARED
        and event.data.get("ability_id") == "serial_killer_turn_end_kill_lone_target"
        for event in bus.log
    )


def test_vip_serial_killer_can_choose_territory_to_kill_lone_target_without_killing_teacher_in_body_area() -> None:
    bus, resolver = _resolver_bundle()
    handler = TurnEndHandler(bus, resolver)
    state = GameState()
    apply_loaded_module(state, load_module("first_steps"))
    state.characters["vip"] = CharacterState(
        character_id="vip",
        name="大人物",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        territory_area=AreaId.SHRINE,
        identity_id="serial_killer",
        original_identity_id="serial_killer",
    )
    state.characters["shrine_maiden"] = CharacterState(
        character_id="shrine_maiden",
        name="巫女",
        area=AreaId.SHRINE,
        initial_area=AreaId.SHRINE,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.characters["teacher"] = CharacterState(
        character_id="teacher",
        name="教师",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
    )

    signal = handler.execute(state)
    assert isinstance(signal, WaitForInput)
    assert signal.input_type == "choose_ability_location"
    assert set(signal.options) == {AreaId.CITY.value, AreaId.SHRINE.value}

    result = signal.callback(AreaId.SHRINE.value)

    assert isinstance(result, PhaseComplete)
    assert state.characters["shrine_maiden"].life_state == CharacterLifeState.DEAD
    assert state.characters["teacher"].life_state == CharacterLifeState.ALIVE
    assert state.characters["vip"].life_state == CharacterLifeState.ALIVE


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
    assert state.characters["beloved"].life_state == CharacterLifeState.DEAD
    assert state.characters["lover"].life_state == CharacterLifeState.DEAD
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
        life_state=CharacterLifeState.DEAD,
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
        life_state=CharacterLifeState.DEAD,
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

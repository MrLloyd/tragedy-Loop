"""Phase 4 P4-5 / P4-6 回归测试。"""

from __future__ import annotations

import pytest

from engine.event_bus import EventBus
from engine.game_controller import GameController
from engine.game_state import GameState
from engine.models.character import CharacterState
from engine.models.effects import Effect
from engine.models.enums import AbilityTiming, AbilityType, AreaId, EffectType, GamePhase, TokenType, Trait
from engine.models.incident import IncidentSchedule
from engine.models.script import CharacterSetup
from engine.resolvers.ability_resolver import AbilityResolver
from engine.resolvers.atomic_resolver import AtomicResolver
from engine.resolvers.death_resolver import DeathResolver
from engine.rules.module_loader import apply_loaded_module, build_game_state_from_module, load_module
from engine.rules.script_validator import ScriptValidationError


def test_change_identity_effect_and_loop_reset_restore_original_identity() -> None:
    state = GameState()
    apply_loaded_module(state, load_module("basic_tragedy_x"))
    state.characters["target"] = CharacterState(
        character_id="target",
        name="目标",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
    )

    resolver = AtomicResolver(EventBus(), DeathResolver())
    resolver.resolve(
        state,
        [Effect(effect_type=EffectType.CHANGE_IDENTITY, target="target", value="killer")],
    )

    assert state.characters["target"].identity_id == "killer"
    assert Trait.IGNORE_GOODWILL in AbilityResolver().active_traits(state, "target")

    state.reset_for_new_loop()

    assert state.characters["target"].identity_id == "平民"
    assert state.characters["target"].original_identity_id == "平民"


def test_paranoia_expansion_virus_switches_commoner_identity_realtime() -> None:
    state = GameState()
    loaded = load_module("basic_tragedy_x")
    apply_loaded_module(state, loaded)
    state.script.rules_x = [
        next(rule for rule in loaded.module_def.rules_x if rule.rule_id == "btx_delusion_spread_virus")
    ]
    state.characters["commoner"] = CharacterState(
        character_id="commoner",
        name="平民",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.characters["victim"] = CharacterState(
        character_id="victim",
        name="目标",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="friend",
        original_identity_id="friend",
    )
    resolver = AbilityResolver()

    state.characters["commoner"].tokens.add(TokenType.PARANOIA, 3)
    abilities = resolver.collect_abilities(
        state,
        timing=AbilityTiming.TURN_END,
        ability_type=AbilityType.MANDATORY,
    )

    assert state.characters["commoner"].identity_id == "serial_killer"
    assert any(candidate.source_id == "commoner" for candidate in abilities)

    state.characters["commoner"].tokens.remove(TokenType.PARANOIA, 1)
    abilities = resolver.collect_abilities(
        state,
        timing=AbilityTiming.TURN_END,
        ability_type=AbilityType.MANDATORY,
    )

    assert state.characters["commoner"].identity_id == "平民"
    assert not any(candidate.source_id == "commoner" for candidate in abilities)


def test_paranoia_expansion_virus_is_inactive_without_selected_rule() -> None:
    state = GameState()
    apply_loaded_module(state, load_module("basic_tragedy_x"))
    state.characters["commoner"] = CharacterState(
        character_id="commoner",
        name="平民",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.characters["victim"] = CharacterState(
        character_id="victim",
        name="目标",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="friend",
        original_identity_id="friend",
    )

    state.characters["commoner"].tokens.add(TokenType.PARANOIA, 3)
    abilities = AbilityResolver().collect_abilities(
        state,
        timing=AbilityTiming.TURN_END,
        ability_type=AbilityType.MANDATORY,
    )

    assert state.characters["commoner"].identity_id == "平民"
    assert not any(candidate.source_id == "commoner" for candidate in abilities)


def test_paranoia_expansion_virus_can_generate_serial_killer_without_module_definition() -> None:
    state = GameState()
    loaded = load_module("basic_tragedy_x")
    state.script.rules_x = [
        next(rule for rule in loaded.module_def.rules_x if rule.rule_id == "btx_delusion_spread_virus")
    ]
    state.characters["commoner"] = CharacterState(
        character_id="commoner",
        name="平民",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.characters["victim"] = CharacterState(
        character_id="victim",
        name="目标",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="friend",
        original_identity_id="friend",
    )
    state.identity_defs["friend"] = loaded.identity_defs["friend"]

    state.characters["commoner"].tokens.add(TokenType.PARANOIA, 3)
    abilities = AbilityResolver().collect_abilities(
        state,
        timing=AbilityTiming.TURN_END,
        ability_type=AbilityType.MANDATORY,
    )

    assert state.characters["commoner"].identity_id == "serial_killer"
    assert "serial_killer" in state.identity_defs
    assert any(candidate.source_id == "commoner" for candidate in abilities)


def test_persistent_effects_settle_after_atomic_writes_using_original_commoner_identity() -> None:
    state = GameState()
    loaded = load_module("basic_tragedy_x")
    apply_loaded_module(state, loaded)
    state.script.rules_x = [
        next(rule for rule in loaded.module_def.rules_x if rule.rule_id == "btx_delusion_spread_virus")
    ]
    state.characters["target"] = CharacterState(
        character_id="target",
        name="目标",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
    )
    resolver = AtomicResolver(EventBus(), DeathResolver())

    resolver.resolve(
        state,
        [
            Effect(
                effect_type=EffectType.PLACE_TOKEN,
                target="target",
                token_type=TokenType.PARANOIA,
                amount=3,
            )
        ],
    )

    assert state.characters["target"].original_identity_id == "平民"
    assert state.characters["target"].identity_id == "serial_killer"

    resolver.resolve(
        state,
        [
            Effect(
                effect_type=EffectType.REMOVE_TOKEN,
                target="target",
                token_type=TokenType.PARANOIA,
                amount=1,
            )
        ],
    )

    assert state.characters["target"].identity_id == "平民"


def test_paranoia_expansion_virus_ignores_non_original_commoner_and_corpses() -> None:
    state = GameState()
    loaded = load_module("basic_tragedy_x")
    apply_loaded_module(state, loaded)
    state.script.rules_x = [
        next(rule for rule in loaded.module_def.rules_x if rule.rule_id == "btx_delusion_spread_virus")
    ]
    state.characters["non_original_commoner"] = CharacterState(
        character_id="non_original_commoner",
        name="非原始平民",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="friend",
    )
    state.characters["corpse"] = CharacterState(
        character_id="corpse",
        name="尸体",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
        is_alive=False,
    )
    state.characters["non_original_commoner"].tokens.add(TokenType.PARANOIA, 3)
    state.characters["corpse"].tokens.add(TokenType.PARANOIA, 3)

    AbilityResolver().collect_abilities(
        state,
        timing=AbilityTiming.TURN_END,
        ability_type=AbilityType.MANDATORY,
    )

    assert state.characters["non_original_commoner"].identity_id == "平民"
    assert state.characters["corpse"].identity_id == "平民"


def test_phase_start_settles_persistent_effects_before_turn_end_collection() -> None:
    class PhaseStartProbe:
        observed_identity_id = ""

        def on_phase_changed(self, phase: GamePhase, visible_state: object) -> None:
            if phase == GamePhase.TURN_END:
                self.observed_identity_id = controller.state.characters["commoner"].identity_id

        def on_wait_for_input(self, wait: object) -> None:
            pass

        def on_state_changed(self, protagonist_visible_state: object, mastermind_visible_state: object) -> None:
            pass

        def on_announcement(self, text: str) -> None:
            pass

        def on_game_over(self, outcome: object) -> None:
            pass

    probe = PhaseStartProbe()
    controller = GameController(probe)
    loaded = load_module("basic_tragedy_x")
    apply_loaded_module(controller.state, loaded)
    controller.state.script.days_per_loop = 1
    controller.state.current_day = 1
    controller.state.script.rules_x = [
        next(rule for rule in loaded.module_def.rules_x if rule.rule_id == "btx_delusion_spread_virus")
    ]
    controller.state.characters["commoner"] = CharacterState(
        character_id="commoner",
        name="平民",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
    )
    controller.state.characters["victim"] = CharacterState(
        character_id="victim",
        name="目标",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="friend",
        original_identity_id="friend",
    )
    controller.state.characters["commoner"].tokens.add(TokenType.PARANOIA, 3)
    controller.state_machine.current_phase = GamePhase.TURN_END

    controller._run_phase()

    assert probe.observed_identity_id == "serial_killer"


def test_time_traveler_immortal_trait_uses_current_identity_traits() -> None:
    state = GameState()
    apply_loaded_module(state, load_module("basic_tragedy_x"))
    state.characters["traveler"] = CharacterState(
        character_id="traveler",
        name="时间旅者",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="time_traveler",
        original_identity_id="time_traveler",
    )

    AtomicResolver(EventBus(), DeathResolver()).resolve(
        state,
        [Effect(effect_type=EffectType.KILL_CHARACTER, target="traveler")],
    )

    assert state.characters["traveler"].is_alive is True


def test_btx_script_validator_accepts_valid_cursed_contract_script() -> None:
    state = build_game_state_from_module(
        "basic_tragedy_x",
        loop_count=2,
        days_per_loop=3,
        rule_y_id="btx_cursed_contract",
        rule_x_ids=["btx_rumors", "btx_latent_serial_killer"],
        character_setups=[
            CharacterSetup("idol", "key_person"),
            CharacterSetup("male_student", "rumormonger"),
            CharacterSetup("soldier", "serial_killer"),
            CharacterSetup("detective", "friend"),
        ],
        incidents=[IncidentSchedule("murder", day=1, perpetrator_id="idol")],
    )

    assert state.script.rule_y is not None
    assert state.script.rule_y.rule_id == "btx_cursed_contract"


def test_first_steps_darkest_script_allows_zero_to_two_thugs() -> None:
    for extra_thugs in range(3):
        setups = [
            CharacterSetup("female_student", "key_person"),
            CharacterSetup("soldier", "killer"),
            CharacterSetup("office_worker", "mastermind"),
            CharacterSetup("male_student", "rumormonger"),
            CharacterSetup("detective", "friend"),
        ]
        for character_id in ["idol", "doctor"][:extra_thugs]:
            setups.append(CharacterSetup(character_id, "thug"))

        state = build_game_state_from_module(
            "first_steps",
            loop_count=2,
            days_per_loop=3,
            rule_y_id="fs_murder_plan",
            rule_x_ids=["fs_darkest_script"],
            character_setups=setups,
            incidents=[IncidentSchedule("murder", day=1, perpetrator_id="female_student")],
        )

        assert state.script.rules_x[0].rule_id == "fs_darkest_script"


def test_first_steps_darkest_script_rejects_more_than_two_thugs() -> None:
    with pytest.raises(ScriptValidationError) as excinfo:
        build_game_state_from_module(
            "first_steps",
            loop_count=2,
            days_per_loop=3,
            rule_y_id="fs_murder_plan",
            rule_x_ids=["fs_darkest_script"],
            character_setups=[
                CharacterSetup("female_student", "key_person"),
                CharacterSetup("soldier", "killer"),
                CharacterSetup("office_worker", "mastermind"),
                CharacterSetup("male_student", "rumormonger"),
                CharacterSetup("detective", "friend"),
                CharacterSetup("idol", "thug"),
                CharacterSetup("doctor", "thug"),
                CharacterSetup("vip", "thug"),
            ],
            incidents=[IncidentSchedule("murder", day=1, perpetrator_id="female_student")],
        )

    assert any("expected 0..2" in issue.message for issue in excinfo.value.issues)


def test_btx_script_validator_rejects_key_person_not_girl() -> None:
    with pytest.raises(ScriptValidationError) as excinfo:
        build_game_state_from_module(
            "basic_tragedy_x",
            loop_count=2,
            days_per_loop=3,
            rule_y_id="btx_cursed_contract",
            rule_x_ids=["btx_rumors", "btx_latent_serial_killer"],
            character_setups=[
                CharacterSetup("soldier", "key_person"),
                CharacterSetup("male_student", "rumormonger"),
                CharacterSetup("detective", "serial_killer"),
                CharacterSetup("idol", "friend"),
            ],
            incidents=[IncidentSchedule("murder", day=1, perpetrator_id="soldier")],
        )

    assert any("key_person must be assigned to a girl" in issue.message for issue in excinfo.value.issues)


def test_script_validator_supports_skip_for_debug_or_partial_import() -> None:
    state = build_game_state_from_module(
        "first_steps",
        rule_y_id="fs_murder_plan",
        rule_x_ids=["fs_ripper_shadow"],
        character_setups=[CharacterSetup("ai", "平民")],
        incidents=[IncidentSchedule("murder", day=1, perpetrator_id="ai")],
        skip_script_validation=True,
    )

    assert state.characters["ai"].identity_id == "平民"


def test_script_validator_rejects_character_script_creation_constraints() -> None:
    with pytest.raises(ScriptValidationError) as excinfo:
        build_game_state_from_module(
            "first_steps",
            rule_y_id="fs_murder_plan",
            rule_x_ids=["fs_ripper_shadow"],
            character_setups=[
                CharacterSetup("ai", "平民"),
                CharacterSetup("female_student", "key_person"),
                CharacterSetup("soldier", "killer"),
                CharacterSetup("office_worker", "mastermind"),
                CharacterSetup("male_student", "rumormonger"),
                CharacterSetup("detective", "serial_killer"),
            ],
            incidents=[IncidentSchedule("murder", day=1, perpetrator_id="ai")],
        )

    assert any("cannot be assigned commoner" in issue.message for issue in excinfo.value.issues)

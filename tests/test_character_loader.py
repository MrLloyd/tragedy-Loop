"""Phase 4 P4-0: character_loader 与测试导入实例链路。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.models.enums import AreaId, Attribute, EffectType
from engine.models.incident import IncidentSchedule
from engine.models.script import CharacterSetup
from engine.rules.character_loader import (
    instantiate_character_state,
    load_character_defs,
)
from engine.rules.module_loader import build_game_state_from_module


def test_load_character_defs_reads_character_templates() -> None:
    defs = load_character_defs()
    assert "ai" in defs

    ai = defs["ai"]
    assert ai.name == "AI"
    assert ai.initial_area == AreaId.CITY
    assert ai.paranoia_limit == 4
    assert len(ai.goodwill_ability_texts) == 4
    assert len(ai.goodwill_ability_goodwill_requirements) == 4
    assert len(ai.goodwill_ability_once_per_loop) == 2
    assert len(ai.goodwill_abilities) == 1
    assert ai.goodwill_abilities[0].ability_id == "goodwill:ai:1"


@pytest.mark.parametrize(
    ("character_id", "ability_ids", "requirements", "once_per_loop"),
    [
        ("ai", ["goodwill:ai:1"], [3], [True]),
        ("streamer", ["goodwill:streamer:1"], [3], [False]),
        ("servant", ["goodwill:servant:1"], [4], [True]),
        ("sister", ["goodwill:sister:1"], [5], [True]),
        ("informant", ["goodwill:informant:1"], [5], [True]),
        ("copycat", ["goodwill:copycat:1"], [3], [False]),
    ],
)
def test_data_only_structured_goodwill_migrations_preserve_legacy_empty_runtime(
    character_id: str,
    ability_ids: list[str],
    requirements: list[int],
    once_per_loop: list[bool],
) -> None:
    defs = load_character_defs()
    char_def = defs[character_id]

    assert [ability.ability_id for ability in char_def.goodwill_abilities] == ability_ids
    assert [ability.goodwill_requirement for ability in char_def.goodwill_abilities] == requirements
    assert [ability.once_per_loop for ability in char_def.goodwill_abilities] == once_per_loop
    assert all(ability.effects == [] for ability in char_def.goodwill_abilities)
    assert all(ability.condition is None for ability in char_def.goodwill_abilities)
    assert all(ability.can_be_refused is True for ability in char_def.goodwill_abilities)


def test_structured_reveal_goodwill_characters_drop_legacy_fields_in_json() -> None:
    raw = json.loads((Path(__file__).resolve().parent.parent / "data" / "characters.json").read_text(encoding="utf-8"))
    by_id = {
        entry["character_id"]: entry
        for entry in raw["characters"]
    }
    legacy_keys = {
        "goodwill_ability_texts",
        "goodwill_ability_goodwill_requirements",
        "goodwill_ability_once_per_loop",
    }

    for character_id in (
        "office_worker",
        "temp_worker_alt",
        "outsider",
        "shrine_maiden",
        "cult_leader",
        "teacher",
        "appraiser",
    ):
        assert legacy_keys.isdisjoint(by_id[character_id])


def test_appraiser_structured_goodwill_reveal_targets_dead_characters() -> None:
    defs = load_character_defs()
    appraiser = defs["appraiser"]

    reveal = next(
        ability
        for ability in appraiser.goodwill_abilities
        if ability.ability_id == "goodwill:appraiser:2"
    )

    assert len(reveal.effects) == 1
    assert reveal.effects[0].effect_type == EffectType.REVEAL_IDENTITY
    assert reveal.effects[0].target == {
        "scope": "any_area",
        "subject": "dead_character",
    }


def test_instantiate_character_state_applies_template_and_identity_alias() -> None:
    defs = load_character_defs()
    setup = CharacterSetup(character_id="ai", identity_id="commoner")
    state = instantiate_character_state(setup, defs)

    assert state.character_id == "ai"
    assert state.identity_id == "平民"
    assert state.original_identity_id == "平民"
    assert state.paranoia_limit == 4
    assert Attribute.CREATION in state.attributes
    assert len(state.goodwill_ability_texts) == 4
    assert len(state.goodwill_ability_goodwill_requirements) == 4
    assert len(state.goodwill_ability_once_per_loop) == 2
    assert len(state.goodwill_abilities) == 1
    assert state.goodwill_abilities[0].goodwill_requirement == 3


def test_instantiate_character_state_keeps_base_and_current_forbidden_areas() -> None:
    defs = load_character_defs()
    setup = CharacterSetup(character_id="office_worker", identity_id="平民")
    state = instantiate_character_state(setup, defs)

    assert state.base_forbidden_areas == [AreaId.SCHOOL]
    assert state.forbidden_areas == [AreaId.SCHOOL]


def test_character_forbidden_areas_reset_for_new_loop() -> None:
    defs = load_character_defs()
    setup = CharacterSetup(character_id="office_worker", identity_id="平民")
    state = instantiate_character_state(setup, defs)

    state.clear_forbidden_areas()
    assert state.forbidden_areas == []

    state.reset_for_new_loop()

    assert state.forbidden_areas == [AreaId.SCHOOL]


def test_build_game_state_from_module_supports_test_instance_import() -> None:
    setups = [
        CharacterSetup(character_id="ai", identity_id="killer"),
        CharacterSetup(character_id="streamer", identity_id="平民"),
    ]
    incidents = [
        IncidentSchedule(
            incident_id="murder",
            day=1,
            perpetrator_id="ai",
        )
    ]

    state = build_game_state_from_module(
        "first_steps",
        loop_count=1,
        days_per_loop=2,
        character_setups=setups,
        incidents=incidents,
        rule_y_id="fs_murder_plan",
        rule_x_ids=["fs_ripper_shadow"],
        skip_script_validation=True,
    )

    assert state.script.loop_count == 1
    assert state.script.days_per_loop == 2
    assert state.script.rule_y is not None
    assert state.script.rule_y.rule_id == "fs_murder_plan"
    assert len(state.script.rules_x) == 1
    assert state.script.rules_x[0].rule_id == "fs_ripper_shadow"

    assert set(state.characters.keys()) == {"ai", "streamer"}
    assert state.characters["ai"].identity_id == "killer"
    assert state.characters["ai"].paranoia_limit == 4
    assert state.characters["ai"].initial_area == AreaId.CITY
    assert Attribute.CREATION in state.characters["ai"].attributes

    assert len(state.script.incidents) == 1
    assert state.script.incidents[0].incident_id == "murder"
    assert len(state.script.incident_public) == 1
    assert state.script.incident_public[0]["name"] == "谋杀"
    assert state.script.incident_public[0]["day"] == 1


def test_build_game_state_from_module_applies_script_selected_initial_area() -> None:
    setups = [
        CharacterSetup(character_id="servant", identity_id="killer", initial_area="city"),
    ]

    state = build_game_state_from_module(
        "first_steps",
        character_setups=setups,
        incidents=[],
        rule_y_id="fs_murder_plan",
        rule_x_ids=["fs_ripper_shadow"],
        skip_script_validation=True,
    )

    assert state.characters["servant"].initial_area == AreaId.CITY
    assert state.characters["servant"].area == AreaId.CITY


def test_build_game_state_from_module_applies_vip_territory_area() -> None:
    setups = [
        CharacterSetup(character_id="vip", identity_id="killer", initial_area="city", territory_area="shrine"),
    ]

    state = build_game_state_from_module(
        "first_steps",
        character_setups=setups,
        incidents=[],
        rule_y_id="fs_murder_plan",
        rule_x_ids=["fs_ripper_shadow"],
        skip_script_validation=True,
    )

    assert state.characters["vip"].initial_area == AreaId.CITY
    assert state.characters["vip"].area == AreaId.CITY
    assert state.characters["vip"].territory_area == AreaId.SHRINE


def test_build_game_state_from_module_rejects_unknown_identity() -> None:
    setups = [CharacterSetup(character_id="ai", identity_id="unknown_identity")]
    with pytest.raises(ValueError, match="Unknown identity_id"):
        build_game_state_from_module(
            "first_steps",
            character_setups=setups,
        )

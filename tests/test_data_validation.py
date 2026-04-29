"""Smoke test: committed data/ passes validate_data_root."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from engine.validation.modules import validate_module_file
from engine.validation.runner import default_data_dir, validate_data_root
from engine.validation.static_data import validate_characters
from engine.models.enums import Trait
from engine.models.identity import IdentityDef
from engine.models.script import CharacterSetup, ModuleDef, PrivateScriptInfo, RuleDef
from engine.rules.character_loader import load_character_defs
from engine.rules.module_loader import load_module
from engine.rules.script_validator import ScriptValidationContext, validate_script


def test_committed_data_passes_validation() -> None:
    root = default_data_dir()
    assert root.is_dir(), f"expected data dir at {root}"
    issues = validate_data_root(root)
    assert not issues, "\n".join(f"{i.path}: {i.message}" for i in issues)


def test_validate_data_root_accepts_explicit_path() -> None:
    here = Path(__file__).resolve().parent
    project = here.parent
    data = project / "data"
    issues = validate_data_root(data)
    assert not issues


def test_validate_module_file_rejects_mandatory_sequential_ability(
    tmp_path: Path,
) -> None:
    module_path = tmp_path / "mandatory_sequential.json"
    module_path.write_text(
        json.dumps(
            {
                "module": {
                    "module_id": "mandatory_sequential",
                    "name": "mandatory_sequential",
                },
                "rules_y": [],
                "rules_x": [],
                "identities": [
                    {
                        "identity_id": "seq_identity",
                        "traits": [],
                        "abilities": [
                            {
                                "ability_id": "seq_identity_turn_end",
                                "name": "seq identity turn end",
                                "ability_type": "mandatory",
                                "timing": "turn_end",
                                "sequential": True,
                                "effects": [
                                    {
                                        "effect_type": "force_loop_end",
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "incidents": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    issues = validate_module_file(module_path, "modules/mandatory_sequential.json")

    assert any(
        issue.path.endswith("identities[0].abilities[0].sequential")
        and "must not set sequential=true" in issue.message
        for issue in issues
    )


def test_validate_module_file_accepts_selector_targets_in_conditions(
    tmp_path: Path,
) -> None:
    module_path = tmp_path / "selector_conditions.json"
    module_path.write_text(
        json.dumps(
            {
                "module": {
                    "module_id": "selector_conditions",
                    "name": "selector_conditions",
                },
                "rules_y": [],
                "rules_x": [],
                "identities": [
                    {
                        "identity_id": "selector_identity",
                        "traits": [],
                        "abilities": [
                            {
                                "ability_id": "selector_identity_turn_end",
                                "name": "selector identity turn end",
                                "ability_type": "optional",
                                "timing": "turn_end",
                                "condition": {
                                    "condition_type": "token_check",
                                    "params": {
                                        "target": {
                                            "scope": "fixed_area",
                                            "subject": "board",
                                            "area": "school",
                                        },
                                        "token": "intrigue",
                                        "operator": ">=",
                                        "value": 2,
                                    },
                                },
                                "effects": [
                                    {
                                        "effect_type": "force_loop_end",
                                        "condition": {
                                            "condition_type": "token_check",
                                            "params": {
                                                "target": {"ref": "other"},
                                                "token": "intrigue",
                                                "operator": ">=",
                                                "value": 1,
                                            },
                                        },
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "incidents": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    issues = validate_module_file(module_path, "modules/selector_conditions.json")

    assert not issues


def test_validate_characters_accepts_selector_targets_in_goodwill_conditions(
    tmp_path: Path,
) -> None:
    characters_path = tmp_path / "characters.json"
    characters_path.write_text(
        json.dumps(
            {
                "characters": [
                    {
                        "character_id": "selector_char",
                        "name": "Selector Char",
                        "trait_rule": "",
                        "initial_area": "shrine",
                        "forbidden_areas": [],
                        "attributes": ["female", "student"],
                        "paranoia_limit": 2,
                        "base_traits": [],
                        "goodwill_ability_texts": ["", "", "", ""],
                        "goodwill_ability_goodwill_requirements": [0, 0, 0, 0],
                        "goodwill_ability_once_per_loop": [False, False],
                        "goodwill_abilities": [
                            {
                                "ability_id": "goodwill:selector_char:1",
                                "name": "Selector Char 友好能力1",
                                "ability_type": "optional",
                                "timing": "protagonist_ability",
                                "description": "test",
                                "condition": {
                                    "condition_type": "area_is",
                                    "params": {
                                        "target": {"ref": "self"},
                                        "value": "shrine",
                                    },
                                },
                                "effects": [
                                    {
                                        "effect_type": "remove_token",
                                        "target": {
                                            "scope": "same_area",
                                            "subject": "board",
                                        },
                                        "token_type": "intrigue",
                                        "amount": 1,
                                        "condition": {
                                            "condition_type": "token_check",
                                            "params": {
                                                "target": {
                                                    "scope": "fixed_area",
                                                    "subject": "board",
                                                    "area": "shrine",
                                                },
                                                "token": "intrigue",
                                                "operator": ">=",
                                                "value": 1,
                                            },
                                        },
                                    }
                                ],
                                "goodwill_requirement": 3,
                                "once_per_loop": False,
                                "can_be_refused": True,
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    issues = validate_characters(
        characters_path,
        "characters.json",
        frozenset({"school", "city", "hospital", "shrine"}),
    )

    assert not issues


def test_validate_script_rejects_streamer_until_ex_rules_exist() -> None:
    character_defs = load_character_defs()
    streamer = character_defs["streamer"]
    context = ScriptValidationContext(
        module_def=ModuleDef(
            module_id="test_module",
            name="test module",
            rule_x_count=0,
            has_final_guess=False,
            rules_y=[RuleDef(rule_id="rule_y", name="rule y", rule_type="Y", module="test_module")],
        ),
        identity_defs={},
        incident_defs={},
        character_defs=character_defs,
    )
    script = PrivateScriptInfo(
        module_id="test_module",
        rule_y=context.module_def.rules_y[0],
        characters=[CharacterSetup(character_id=streamer.character_id, identity_id="平民")],
        incidents=[],
    )

    issues = validate_script(script, context)

    assert any("disabled until EX-card rules are implemented" in issue.message for issue in issues)


def test_validate_script_rejects_sister_with_puppet_ignore_goodwill_identity() -> None:
    character_defs = load_character_defs()
    sister = character_defs["sister"]
    context = ScriptValidationContext(
        module_def=ModuleDef(
            module_id="basic_tragedy_x",
            name="basic_tragedy_x",
            rule_x_count=0,
            has_final_guess=False,
            rules_y=[
                RuleDef(
                    rule_id="rule_y",
                    name="rule y",
                    rule_type="Y",
                    module="basic_tragedy_x",
                    identity_slots={"puppet_ignore": 1},
                )
            ],
        ),
        identity_defs={
            "puppet_ignore": IdentityDef(
                identity_id="puppet_ignore",
                name="puppet ignore",
                module="basic_tragedy_x",
                traits={Trait.PUPPET_IGNORE_GOODWILL},
            ),
        },
        incident_defs={},
        character_defs=character_defs,
    )
    script = PrivateScriptInfo(
        module_id="basic_tragedy_x",
        rule_y=context.module_def.rules_y[0],
        characters=[CharacterSetup(character_id=sister.character_id, identity_id="puppet_ignore")],
        incidents=[],
    )

    issues = validate_script(script, context)

    assert any("cannot be assigned an identity with ignore-goodwill trait" in issue.message for issue in issues)


def test_validate_script_allows_only_deity_and_transfer_student_entry_fields() -> None:
    character_defs = load_character_defs()
    context = ScriptValidationContext(
        module_def=ModuleDef(
            module_id="test_module",
            name="test module",
            rule_x_count=0,
            has_final_guess=False,
            rules_y=[RuleDef(rule_id="rule_y", name="rule y", rule_type="Y", module="test_module")],
        ),
        identity_defs={},
        incident_defs={},
        character_defs=character_defs,
    )
    script = PrivateScriptInfo(
        module_id="test_module",
        rule_y=context.module_def.rules_y[0],
        characters=[
            CharacterSetup(character_id="deity", identity_id="平民", entry_loop=2),
            CharacterSetup(character_id="transfer_student", identity_id="平民", entry_day=3),
            CharacterSetup(character_id="office_worker", identity_id="平民", entry_loop=1, entry_day=1),
        ],
        incidents=[],
    )

    issues = validate_script(script, context)

    assert not any(issue.path.endswith("deity.entry_loop") for issue in issues)
    assert not any(issue.path.endswith("transfer_student.entry_day") for issue in issues)
    assert any(issue.path.endswith(".entry_loop") and "cannot set entry_loop" in issue.message for issue in issues)
    assert any(issue.path.endswith(".entry_day") and "cannot set entry_day" in issue.message for issue in issues)


def test_validate_script_allows_hermit_x_zero_for_hermit() -> None:
    character_defs = load_character_defs()
    context = ScriptValidationContext(
        module_def=ModuleDef(
            module_id="test_module",
            name="test module",
            rule_x_count=0,
            has_final_guess=False,
            rules_y=[RuleDef(rule_id="rule_y", name="rule y", rule_type="Y", module="test_module")],
        ),
        identity_defs={},
        incident_defs={},
        character_defs=character_defs,
    )
    script = PrivateScriptInfo(
        module_id="test_module",
        rule_y=context.module_def.rules_y[0],
        characters=[CharacterSetup(character_id="hermit", identity_id="平民", hermit_x=0)],
        incidents=[],
    )

    issues = validate_script(script, context)

    assert not any(issue.path.endswith(".hermit_x") for issue in issues)


def test_validate_script_rejects_hermit_x_for_non_hermit() -> None:
    character_defs = load_character_defs()
    context = ScriptValidationContext(
        module_def=ModuleDef(
            module_id="test_module",
            name="test module",
            rule_x_count=0,
            has_final_guess=False,
            rules_y=[RuleDef(rule_id="rule_y", name="rule y", rule_type="Y", module="test_module")],
        ),
        identity_defs={},
        incident_defs={},
        character_defs=character_defs,
    )
    script = PrivateScriptInfo(
        module_id="test_module",
        rule_y=context.module_def.rules_y[0],
        characters=[CharacterSetup(character_id="office_worker", identity_id="平民", hermit_x=1)],
        incidents=[],
    )

    issues = validate_script(script, context)

    assert any(issue.path.endswith(".hermit_x") and "cannot set hermit_x" in issue.message for issue in issues)


def test_validate_script_allows_outsider_to_use_identity_outside_rule_pool() -> None:
    loaded = load_module("basic_tragedy_x")
    character_defs = load_character_defs()
    context = ScriptValidationContext(
        module_def=replace(loaded.module_def, rule_x_count=1),
        identity_defs=loaded.identity_defs,
        incident_defs=loaded.incident_defs,
        character_defs=character_defs,
    )
    script = PrivateScriptInfo(
        module_id="basic_tragedy_x",
        rule_y=next(rule for rule in loaded.module_def.rules_y if rule.rule_id == "btx_murder_plan"),
        rules_x=[next(rule for rule in loaded.module_def.rules_x if rule.rule_id == "btx_causal_line")],
        characters=[
            CharacterSetup(character_id="idol", identity_id="key_person"),
            CharacterSetup(character_id="soldier", identity_id="killer"),
            CharacterSetup(character_id="detective", identity_id="mastermind"),
            CharacterSetup(character_id="office_worker", identity_id="rumormonger"),
            CharacterSetup(character_id="male_student", identity_id="friend"),
            CharacterSetup(character_id="outsider", identity_id="friend"),
        ],
        incidents=[],
    )

    issues = validate_script(script, context)

    assert not issues


def test_validate_script_allows_copycat_to_copy_rumormonger_and_enter_script() -> None:
    loaded = load_module("basic_tragedy_x")
    character_defs = load_character_defs()
    context = ScriptValidationContext(
        module_def=loaded.module_def,
        identity_defs=loaded.identity_defs,
        incident_defs=loaded.incident_defs,
        character_defs=character_defs,
    )
    script = PrivateScriptInfo(
        module_id="basic_tragedy_x",
        rule_y=next(rule for rule in loaded.module_def.rules_y if rule.rule_id == "btx_murder_plan"),
        rules_x=[
            next(rule for rule in loaded.module_def.rules_x if rule.rule_id == "btx_rumors"),
            next(rule for rule in loaded.module_def.rules_x if rule.rule_id == "btx_unknown_factor_chi"),
        ],
        characters=[
            CharacterSetup(character_id="idol", identity_id="key_person"),
            CharacterSetup(character_id="soldier", identity_id="killer"),
            CharacterSetup(character_id="detective", identity_id="mastermind"),
            CharacterSetup(character_id="office_worker", identity_id="unstable_factor"),
            CharacterSetup(character_id="male_student", identity_id="rumormonger"),
            CharacterSetup(character_id="copycat", identity_id="rumormonger"),
        ],
        incidents=[],
    )

    issues = validate_script(script, context)

    assert not issues


def test_validate_script_allows_copycat_to_copy_outsider_identity() -> None:
    loaded = load_module("basic_tragedy_x")
    character_defs = load_character_defs()
    context = ScriptValidationContext(
        module_def=loaded.module_def,
        identity_defs=loaded.identity_defs,
        incident_defs=loaded.incident_defs,
        character_defs=character_defs,
    )
    script = PrivateScriptInfo(
        module_id="basic_tragedy_x",
        rule_y=next(rule for rule in loaded.module_def.rules_y if rule.rule_id == "btx_murder_plan"),
        rules_x=[
            next(rule for rule in loaded.module_def.rules_x if rule.rule_id == "btx_causal_line"),
            next(rule for rule in loaded.module_def.rules_x if rule.rule_id == "btx_unknown_factor_chi"),
        ],
        characters=[
            CharacterSetup(character_id="idol", identity_id="key_person"),
            CharacterSetup(character_id="soldier", identity_id="killer"),
            CharacterSetup(character_id="detective", identity_id="mastermind"),
            CharacterSetup(character_id="office_worker", identity_id="unstable_factor"),
            CharacterSetup(character_id="outsider", identity_id="beloved"),
            CharacterSetup(character_id="copycat", identity_id="beloved"),
        ],
        incidents=[],
    )

    issues = validate_script(script, context)

    assert not issues


def test_validate_script_copycat_still_fails_when_cursed_contract_target_lacks_girl_attribute() -> None:
    loaded = load_module("basic_tragedy_x")
    character_defs = load_character_defs()
    context = ScriptValidationContext(
        module_def=loaded.module_def,
        identity_defs=loaded.identity_defs,
        incident_defs=loaded.incident_defs,
        character_defs=character_defs,
    )
    script = PrivateScriptInfo(
        module_id="basic_tragedy_x",
        rule_y=next(rule for rule in loaded.module_def.rules_y if rule.rule_id == "btx_cursed_contract"),
        rules_x=[
            next(rule for rule in loaded.module_def.rules_x if rule.rule_id == "btx_causal_line"),
            next(rule for rule in loaded.module_def.rules_x if rule.rule_id == "btx_unknown_factor_chi"),
        ],
        characters=[
            CharacterSetup(character_id="office_worker", identity_id="unstable_factor"),
            CharacterSetup(character_id="idol", identity_id="key_person"),
            CharacterSetup(character_id="copycat", identity_id="key_person"),
        ],
        incidents=[],
    )

    issues = validate_script(script, context)

    assert not any(issue.path.startswith("script.identity_slots.key_person") for issue in issues)
    assert any(
        issue.path == "script.rule_y.btx_cursed_contract"
        and "key_person must be assigned to a girl character" in issue.message
        for issue in issues
    )

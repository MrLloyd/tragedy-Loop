"""Smoke test: committed data/ passes validate_data_root."""

from __future__ import annotations

import json
from pathlib import Path

from engine.validation.modules import validate_module_file
from engine.validation.runner import default_data_dir, validate_data_root
from engine.validation.static_data import validate_characters


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

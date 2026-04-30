"""剧本实例校验入口（P4-6）。"""

from __future__ import annotations

from dataclasses import dataclass

from engine.models.enums import AreaId, Attribute, TokenType, Trait
from engine.models.script import CharacterSetup, PrivateScriptInfo, RuleDef
from engine.rules.character_loader import (
    CharacterDef,
    ENTRY_DAY_CHARACTER_IDS,
    ENTRY_LOOP_CHARACTER_IDS,
    normalize_identity_id,
)
from engine.models.identity import IdentityDef
from engine.models.incident import IncidentDef
from engine.models.script import ModuleDef
from engine.validation.common import ValidationIssue

_SPECIAL_SCRIPT_CREATION_IDENTITY_CHARACTER_IDS = {"outsider", "copycat"}
_HERMIT_CHARACTER_ID = "hermit"
_IGNORE_GOODWILL_TRAITS = frozenset(
    {
        Trait.IGNORE_GOODWILL,
        Trait.MUST_IGNORE_GOODWILL,
        Trait.PUPPET_IGNORE_GOODWILL,
    }
)


@dataclass
class ScriptValidationContext:
    module_def: ModuleDef
    identity_defs: dict[str, IdentityDef]
    incident_defs: dict[str, IncidentDef]
    character_defs: dict[str, CharacterDef]


class ScriptValidationError(ValueError):
    """剧本实例校验失败。"""

    def __init__(self, issues: list[ValidationIssue]) -> None:
        self.issues = issues
        message = "; ".join(f"{issue.path}: {issue.message}" for issue in issues)
        super().__init__(message)


def validate_script(script: PrivateScriptInfo, context: ScriptValidationContext) -> list[ValidationIssue]:
    """总入口：基础剧本校验 → SCRIPT_CREATION 规则校验。"""
    issues = validate_basic_script(script, context)
    if issues:
        return issues
    issues.extend(validate_script_creation_constraints(script, context))
    return issues


def validate_basic_script(
    script: PrivateScriptInfo,
    context: ScriptValidationContext,
) -> list[ValidationIssue]:
    """基础剧本结构校验，与具体规则文字无关。"""
    issues: list[ValidationIssue] = []
    module = context.module_def

    if script.rule_y is None:
        issues.append(ValidationIssue("script.rule_y", "rule_y is required"))
    elif script.rule_y.rule_id not in {rule.rule_id for rule in module.rules_y}:
        issues.append(ValidationIssue("script.rule_y", f"unknown rule_y: {script.rule_y.rule_id!r}"))

    selected_rule_x_ids = [rule.rule_id for rule in script.rules_x]
    known_rule_x_ids = {rule.rule_id for rule in module.rules_x}
    if len(script.rules_x) != module.rule_x_count:
        issues.append(
            ValidationIssue(
                "script.rules_x",
                f"expected {module.rule_x_count} rule_x, got {len(script.rules_x)}",
            )
        )
    if len(set(selected_rule_x_ids)) != len(selected_rule_x_ids):
        issues.append(ValidationIssue("script.rules_x", "duplicated rule_x"))
    for idx, rule in enumerate(script.rules_x):
        if rule.rule_id not in known_rule_x_ids:
            issues.append(ValidationIssue(f"script.rules_x[{idx}]", f"unknown rule_x: {rule.rule_id!r}"))

    seen_characters: set[str] = set()
    for idx, setup in enumerate(script.characters):
        path = f"script.characters[{idx}]"
        if setup.character_id in seen_characters:
            issues.append(ValidationIssue(f"{path}.character_id", f"duplicated character: {setup.character_id!r}"))
        seen_characters.add(setup.character_id)

        if setup.character_id not in context.character_defs:
            issues.append(ValidationIssue(f"{path}.character_id", f"unknown character: {setup.character_id!r}"))
            continue
        character_def = context.character_defs[setup.character_id]
        issues.extend(_validate_character_initial_area(path, setup, character_def))
        issues.extend(_validate_character_territory_area(path, setup, character_def))
        identity_id = normalize_identity_id(setup.identity_id)
        if identity_id != "平民" and identity_id not in context.identity_defs:
            issues.append(ValidationIssue(f"{path}.identity_id", f"unknown identity: {setup.identity_id!r}"))
        if setup.entry_loop > 0 and setup.character_id not in ENTRY_LOOP_CHARACTER_IDS:
            issues.append(
                ValidationIssue(
                    f"{path}.entry_loop",
                    f"{character_def.name} cannot set entry_loop",
                )
            )
        if setup.entry_day > 0 and setup.character_id not in ENTRY_DAY_CHARACTER_IDS:
            issues.append(
                ValidationIssue(
                    f"{path}.entry_day",
                    f"{character_def.name} cannot set entry_day",
                )
            )
        hermit_x = int(getattr(setup, "hermit_x", 0) or 0)
        if setup.character_id == _HERMIT_CHARACTER_ID:
            if hermit_x < 0:
                issues.append(
                    ValidationIssue(
                        f"{path}.hermit_x",
                        f"{character_def.name} requires hermit_x >= 0",
                    )
                )
        elif hermit_x != 0:
            issues.append(
                ValidationIssue(
                    f"{path}.hermit_x",
                    f"{character_def.name} cannot set hermit_x",
                )
            )
        if setup.character_id in ENTRY_LOOP_CHARACTER_IDS:
            if setup.entry_loop <= 0:
                issues.append(
                    ValidationIssue(
                        f"{path}.entry_loop",
                        f"{character_def.name} requires entry_loop",
                    )
                )
            elif setup.entry_loop > script.loop_count:
                issues.append(
                    ValidationIssue(
                        f"{path}.entry_loop",
                        f"{character_def.name} entry_loop must be in 1..{script.loop_count}",
                    )
                )
        if setup.character_id in ENTRY_DAY_CHARACTER_IDS:
            if setup.entry_day <= 0:
                issues.append(
                    ValidationIssue(
                        f"{path}.entry_day",
                        f"{character_def.name} requires entry_day",
                    )
                )
            elif setup.entry_day > script.days_per_loop:
                issues.append(
                    ValidationIssue(
                        f"{path}.entry_day",
                        f"{character_def.name} entry_day must be in 1..{script.days_per_loop}",
                    )
                )
        if _has_script_constraint(character_def, "disabled_until_ex_rules"):
            issues.append(
                ValidationIssue(
                    f"{path}.character_id",
                    f"{character_def.name} is disabled until EX-card rules are implemented",
                )
            )

    selected_character_ids = {setup.character_id for setup in script.characters}
    seen_incident_days: set[int] = set()
    seen_incident_perpetrators: set[str] = set()
    for idx, incident in enumerate(script.incidents):
        path = f"script.incidents[{idx}]"
        if incident.incident_id not in context.incident_defs:
            issues.append(ValidationIssue(f"{path}.incident_id", f"unknown incident: {incident.incident_id!r}"))
        if incident.day < 1 or incident.day > script.days_per_loop:
            issues.append(
                ValidationIssue(
                    f"{path}.day",
                    f"incident day must be in 1..{script.days_per_loop}, got {incident.day}",
                )
            )
        if incident.perpetrator_id not in selected_character_ids:
            issues.append(
                ValidationIssue(
                    f"{path}.perpetrator_id",
                    f"unknown incident perpetrator: {incident.perpetrator_id!r}",
                )
            )
        for target_index, target_id in enumerate(incident.target_character_ids):
            if target_id not in selected_character_ids:
                issues.append(
                    ValidationIssue(
                        f"{path}.target_character_ids[{target_index}]",
                        f"unknown incident target character: {target_id!r}",
                    )
                )
        for area_index, area_id in enumerate(incident.target_area_ids):
            try:
                AreaId(area_id)
            except ValueError:
                issues.append(
                    ValidationIssue(
                        f"{path}.target_area_ids[{area_index}]",
                        f"unknown incident target area: {area_id!r}",
                    )
                )
        for token_index, token_name in enumerate(incident.chosen_token_types):
            try:
                TokenType(token_name)
            except ValueError:
                issues.append(
                    ValidationIssue(
                        f"{path}.chosen_token_types[{token_index}]",
                        f"unknown incident token type: {token_name!r}",
                    )
                )
        if incident.day in seen_incident_days:
            issues.append(ValidationIssue(path, f"multiple incidents scheduled on day: {incident.day}"))
        seen_incident_days.add(incident.day)
        if incident.perpetrator_id in seen_incident_perpetrators:
            issues.append(
                ValidationIssue(
                    f"{path}.perpetrator_id",
                    f"duplicated incident perpetrator across days: {incident.perpetrator_id!r}",
                )
            )
        seen_incident_perpetrators.add(incident.perpetrator_id)

    if script.rule_y is not None:
        issues.extend(_validate_identity_slots(script, [script.rule_y, *script.rules_x], context))

    return issues


def validate_script_creation_constraints(
    script: PrivateScriptInfo,
    context: ScriptValidationContext,
) -> list[ValidationIssue]:
    """SCRIPT_CREATION / 剧本制作时约束。"""
    if context.module_def.module_id not in {"first_steps", "basic_tragedy_x"}:
        return []

    issues: list[ValidationIssue] = []
    character_by_identity = _characters_by_identity(script)
    rule_pool_identity_ids = _selected_rule_identity_ids([script.rule_y, *script.rules_x])

    if script.rule_y and script.rule_y.rule_id == "btx_cursed_contract":
        for character_id in character_by_identity.get("key_person", []):
            char_def = context.character_defs[character_id]
            if Attribute.GIRL not in char_def.attributes:
                issues.append(
                    ValidationIssue(
                        f"script.rule_y.{script.rule_y.rule_id}",
                        "key_person must be assigned to a girl character",
                    )
                )

    for idx, setup in enumerate(script.characters):
        char_def = context.character_defs[setup.character_id]
        identity_id = normalize_identity_id(setup.identity_id)
        identity_def = context.identity_defs.get(identity_id)
        path = f"script.characters[{idx}]"

        if _has_script_constraint(char_def, "cannot_be_commoner") and identity_id == "平民":
            issues.append(
                ValidationIssue(
                    f"{path}.identity_id",
                    f"{char_def.name} cannot be assigned commoner at script creation",
                )
            )

        if _has_script_constraint(char_def, "cannot_ignore_goodwill_identity"):
            traits = identity_def.traits if identity_def is not None else set()
            if traits & _IGNORE_GOODWILL_TRAITS:
                issues.append(
                    ValidationIssue(
                        f"{path}.identity_id",
                        f"{char_def.name} cannot be assigned an identity with ignore-goodwill trait",
                    )
                )

        if char_def.character_id == "outsider":
            if identity_id == "平民":
                issues.append(
                    ValidationIssue(
                        f"{path}.identity_id",
                        f"{char_def.name} cannot be assigned commoner at script creation",
                    )
                )
            elif identity_id in rule_pool_identity_ids:
                issues.append(
                    ValidationIssue(
                        f"{path}.identity_id",
                        f"{char_def.name} must use an identity outside the selected rule pool",
                    )
                )

        if char_def.character_id == "copycat":
            if identity_id == "平民":
                issues.append(
                    ValidationIssue(
                        f"{path}.identity_id",
                        f"{char_def.name} cannot be assigned commoner at script creation",
                    )
                )
            else:
                same_identity_characters = [
                    character_id
                    for character_id in character_by_identity.get(identity_id, [])
                    if character_id != char_def.character_id
                ]
                if not same_identity_characters:
                    issues.append(
                        ValidationIssue(
                            f"{path}.identity_id",
                            f"{char_def.name} requires another character with the same identity",
                        )
                    )

    return issues


def _validate_identity_slots(
    script: PrivateScriptInfo,
    rules: list[RuleDef],
    context: ScriptValidationContext,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    required: dict[str, int] = {}
    ranges: dict[str, tuple[int, int]] = {}
    for rule in rules:
        for identity_id, count in rule.identity_slots.items():
            required[identity_id] = required.get(identity_id, 0) + count
        for identity_id, range_def in rule.identity_slot_ranges.items():
            min_count = int(range_def.get("min", 0))
            max_count = int(range_def.get("max", min_count))
            previous = ranges.get(identity_id)
            if previous is None:
                ranges[identity_id] = (min_count, max_count)
            else:
                ranges[identity_id] = (
                    previous[0] + min_count,
                    previous[1] + max_count,
                )

    actual: dict[str, int] = {}
    for setup in script.characters:
        if setup.character_id in _SPECIAL_SCRIPT_CREATION_IDENTITY_CHARACTER_IDS:
            continue
        identity_id = normalize_identity_id(setup.identity_id)
        if identity_id == "平民":
            continue
        actual[identity_id] = actual.get(identity_id, 0) + 1

    for identity_id, expected in required.items():
        got = actual.get(identity_id, 0)
        if got != expected:
            issues.append(
                ValidationIssue(
                    f"script.identity_slots.{identity_id}",
                    f"expected {expected}, got {got}",
                )
            )

    for identity_id, (min_count, max_count) in ranges.items():
        got = actual.get(identity_id, 0)
        if got < min_count or got > max_count:
            issues.append(
                ValidationIssue(
                    f"script.identity_slots.{identity_id}",
                    f"expected {min_count}..{max_count}, got {got}",
                )
            )

    for identity_id, got in actual.items():
        if identity_id not in required and identity_id not in ranges:
            identity_def = context.identity_defs.get(identity_id)
            max_count = identity_def.max_count if identity_def else None
            if max_count is None:
                issues.append(
                    ValidationIssue(
                        f"script.identity_slots.{identity_id}",
                        "identity is not required by selected rules",
                    )
                )
            elif got > max_count:
                issues.append(
                    ValidationIssue(
                        f"script.identity_slots.{identity_id}",
                        f"exceeds max_count {max_count}, got {got}",
                    )
                )

    return issues


def _selected_rule_identity_ids(rules: list[RuleDef]) -> set[str]:
    selected: set[str] = set()
    for rule in rules:
        for identity_id in rule.identity_slots:
            selected.add(identity_id)
        for identity_id in rule.identity_slot_ranges:
            selected.add(identity_id)
    return selected


def _characters_by_identity(script: Script) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for setup in script.characters:
        identity_id = normalize_identity_id(setup.identity_id)
        result.setdefault(identity_id, []).append(setup.character_id)
    return result


def _has_script_constraint(character_def: CharacterDef, constraint: str) -> bool:
    if constraint in character_def.script_constraints:
        return True
    text = character_def.trait_rule
    if constraint == "cannot_be_commoner":
        return "不能為「平民」" in text or "不能为「平民」" in text or "不能为平民" in text
    if constraint == "cannot_ignore_goodwill_identity":
        return "无视友好特性的身份" in text or "無視友好特性的身份" in text
    if constraint == "disabled_until_ex_rules":
        return constraint in character_def.script_constraints
    return False


def _validate_character_initial_area(
    path: str,
    setup: CharacterSetup,
    character_def: CharacterDef,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    selected_area = str(setup.initial_area or "")
    mode = getattr(character_def, "initial_area_mode", "fixed")
    candidate_values = {area.value for area in character_def.initial_area_candidates}

    if mode == "script_choice":
        if not selected_area:
            issues.append(ValidationIssue(f"{path}.initial_area", "initial_area is required for this character"))
            return issues
        if selected_area not in candidate_values:
            issues.append(
                ValidationIssue(
                    f"{path}.initial_area",
                    f"invalid initial_area {selected_area!r}, expected one of {sorted(candidate_values)}",
                )
            )
        return issues

    if mode == "mastermind_each_loop":
        if selected_area:
            issues.append(
                ValidationIssue(
                    f"{path}.initial_area",
                    "initial_area must be decided at loop_start for this character",
                )
            )
        return issues

    if selected_area:
        issues.append(
            ValidationIssue(
                f"{path}.initial_area",
                "initial_area override is not allowed for this character",
            )
        )
    return issues


def _validate_character_territory_area(
    path: str,
    setup: CharacterSetup,
    character_def: CharacterDef,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    territory_area = str(setup.territory_area or "")

    if setup.character_id != "vip":
        if territory_area:
            issues.append(
                ValidationIssue(
                    f"{path}.territory_area",
                    "territory_area is only allowed for vip",
                )
            )
        return issues

    if not territory_area:
        issues.append(
            ValidationIssue(
                f"{path}.territory_area",
                "territory_area is required for vip",
            )
        )
        return issues

    try:
        selected_area = AreaId(territory_area)
    except ValueError:
        issues.append(
            ValidationIssue(
                f"{path}.territory_area",
                f"unknown territory area: {territory_area!r}",
            )
        )
        return issues

    if selected_area == AreaId.FARAWAY:
        issues.append(
            ValidationIssue(
                f"{path}.territory_area",
                "faraway is not a valid territory area",
            )
        )

    return issues

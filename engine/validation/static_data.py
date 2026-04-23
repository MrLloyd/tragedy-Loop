"""board.json / cards.json / characters.json 校验。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.models.enums import AbilityTiming, AbilityType, AreaId, Attribute, CardType, EffectType, TokenType
from engine.validation.common import ValidationIssue, enum_values

_AREA_VALUES = enum_values(AreaId)
_CARD_VALUES = enum_values(CardType)
_ATTR_VALUES = enum_values(Attribute)
_ABILITY_TIMING_VALUES = enum_values(AbilityTiming)
_ABILITY_TYPE_VALUES = enum_values(AbilityType)
_EFFECT_VALUES = enum_values(EffectType)
_TOKEN_VALUES = enum_values(TokenType)
# 2x2 版图格，不含远方
_BOARD_CELL_AREAS = _AREA_VALUES - {AreaId.FARAWAY.value}


def validate_board(path: Path, file_rel: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return [ValidationIssue(file_rel, f"invalid JSON: {e}")]

    if not isinstance(data, dict):
        return [ValidationIssue(file_rel, "root must be an object")]

    layout = data.get("layout")
    if layout is None:
        issues.append(ValidationIssue(f"{file_rel}:layout", "missing key 'layout'"))
        return issues
    if not isinstance(layout, dict):
        issues.append(ValidationIssue(f"{file_rel}:layout", "must be an object"))
        return issues

    for key, pos in layout.items():
        if key not in _BOARD_CELL_AREAS:
            issues.append(
                ValidationIssue(
                    f"{file_rel}:layout.{key}",
                    f"unknown or invalid board cell area (must be 2x2 id, not faraway): {key!r}",
                )
            )
        if not isinstance(pos, dict):
            issues.append(ValidationIssue(f"{file_rel}:layout.{key}", "position must be an object"))
            continue
        for rk in ("row", "col"):
            if rk not in pos:
                issues.append(ValidationIssue(f"{file_rel}:layout.{key}", f"missing '{rk}'"))
            else:
                v = pos[rk]
                if not isinstance(v, int) or v not in (0, 1):
                    issues.append(
                        ValidationIssue(
                            f"{file_rel}:layout.{key}.{rk}",
                            f"expected 0 or 1, got {v!r}",
                        )
                    )

    sa = data.get("special_areas")
    if sa is None:
        issues.append(ValidationIssue(f"{file_rel}:special_areas", "missing key 'special_areas'"))
    elif not isinstance(sa, list):
        issues.append(ValidationIssue(f"{file_rel}:special_areas", "must be an array"))
    else:
        for i, a in enumerate(sa):
            if a not in _AREA_VALUES:
                issues.append(
                    ValidationIssue(
                        f"{file_rel}:special_areas[{i}]",
                        f"invalid AreaId: {a!r}",
                    )
                )

    return issues


def _validate_card_entries(
    items: Any,
    file_rel: str,
    path_prefix: str,
    issues: list[ValidationIssue],
) -> None:
    if not isinstance(items, list):
        issues.append(ValidationIssue(path_prefix, "must be an array"))
        return
    for i, entry in enumerate(items):
        p = f"{path_prefix}[{i}]"
        if not isinstance(entry, dict):
            issues.append(ValidationIssue(p, "entry must be an object"))
            continue
        ct = entry.get("card_type")
        if ct not in _CARD_VALUES:
            issues.append(
                ValidationIssue(
                    f"{p}.card_type",
                    f"invalid CardType: {ct!r}",
                )
            )
        c = entry.get("count")
        if not isinstance(c, int) or c < 1:
            issues.append(ValidationIssue(f"{p}.count", f"expected positive int, got {c!r}"))
        opl = entry.get("once_per_loop")
        if not isinstance(opl, bool):
            issues.append(ValidationIssue(f"{p}.once_per_loop", f"expected bool, got {opl!r}"))


def validate_cards(path: Path, file_rel: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [ValidationIssue(file_rel, f"invalid JSON: {e}")]

    if not isinstance(data, dict):
        return [ValidationIssue(file_rel, "root must be an object")]

    for key in ("mastermind_base", "protagonist_base"):
        if key not in data:
            issues.append(ValidationIssue(f"{file_rel}:{key}", f"missing key {key!r}"))
        else:
            _validate_card_entries(data[key], file_rel, f"{file_rel}:{key}", issues)

    ext = data.get("extensions")
    if ext is None:
        issues.append(ValidationIssue(f"{file_rel}:extensions", "missing key 'extensions'"))
    elif not isinstance(ext, dict):
        issues.append(ValidationIssue(f"{file_rel}:extensions", "must be an object"))
    else:
        for sub in ("mastermind", "protagonist"):
            if sub not in ext:
                issues.append(ValidationIssue(f"{file_rel}:extensions", f"missing key {sub!r}"))
            else:
                _validate_card_entries(
                    ext[sub], file_rel, f"{file_rel}:extensions.{sub}", issues
                )

    return issues


def validate_characters(
    path: Path,
    file_rel: str,
    board_layout_keys: frozenset[str],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [ValidationIssue(file_rel, f"invalid JSON: {e}")]

    chars = data.get("characters")
    if chars is None:
        return [ValidationIssue(f"{file_rel}:characters", "missing key 'characters'")]
    if not isinstance(chars, list):
        return [ValidationIssue(f"{file_rel}:characters", "must be an array")]

    seen_ids: set[str] = set()
    for i, ch in enumerate(chars):
        p = f"{file_rel}:characters[{i}]"
        if not isinstance(ch, dict):
            issues.append(ValidationIssue(p, "entry must be an object"))
            continue

        cid = ch.get("character_id")
        if not isinstance(cid, str) or not cid.strip():
            issues.append(ValidationIssue(f"{p}.character_id", "must be non-empty string"))
        else:
            if cid in seen_ids:
                issues.append(ValidationIssue(f"{p}.character_id", f"duplicate character_id: {cid!r}"))
            seen_ids.add(cid)

        ia = ch.get("initial_area")
        if ia not in _AREA_VALUES:
            issues.append(ValidationIssue(f"{p}.initial_area", f"invalid AreaId: {ia!r}"))
        else:
            if ia != AreaId.FARAWAY.value and ia not in board_layout_keys:
                issues.append(
                    ValidationIssue(
                        f"{p}.initial_area",
                        f"initial_area {ia!r} not present in board.json layout",
                    )
                )

        fa = ch.get("forbidden_areas")
        if not isinstance(fa, list):
            issues.append(ValidationIssue(f"{p}.forbidden_areas", "must be an array"))
        else:
            for j, area in enumerate(fa):
                if area not in _AREA_VALUES:
                    issues.append(
                        ValidationIssue(
                            f"{p}.forbidden_areas[{j}]",
                            f"invalid AreaId: {area!r}",
                        )
                    )

        attrs = ch.get("attributes")
        if not isinstance(attrs, list):
            issues.append(ValidationIssue(f"{p}.attributes", "must be an array"))
        else:
            for j, at in enumerate(attrs):
                if at not in _ATTR_VALUES:
                    issues.append(
                        ValidationIssue(
                            f"{p}.attributes[{j}]",
                            f"invalid Attribute: {at!r}",
                        )
                    )

        pl = ch.get("paranoia_limit")
        # 附录 C 允许 0（如黑猫）；引擎按规则在判定时覆盖
        if not isinstance(pl, int) or pl < 0:
            issues.append(
                ValidationIssue(f"{p}.paranoia_limit", f"expected int >= 0, got {pl!r}")
            )

        gtexts = ch.get("goodwill_ability_texts")
        if gtexts is not None:
            if not isinstance(gtexts, list) or len(gtexts) != 4:
                issues.append(
                    ValidationIssue(
                        f"{p}.goodwill_ability_texts",
                        "must be an array of length 4 (slots 1–4, empty string if unused)",
                    )
                )
            else:
                for j, t in enumerate(gtexts):
                    if not isinstance(t, str):
                        issues.append(
                            ValidationIssue(
                                f"{p}.goodwill_ability_texts[{j}]",
                                f"expected string, got {t!r}",
                            )
                        )

        grequirements = ch.get("goodwill_ability_goodwill_requirements")
        if grequirements is not None:
            if not isinstance(grequirements, list) or len(grequirements) != 4:
                issues.append(
                    ValidationIssue(
                        f"{p}.goodwill_ability_goodwill_requirements",
                        "must be an array of length 4 (友好能力1–4 所需友好度)",
                    )
                )
            else:
                for j, requirement in enumerate(grequirements):
                    if not isinstance(requirement, int) or requirement < 0:
                        issues.append(
                            ValidationIssue(
                                f"{p}.goodwill_ability_goodwill_requirements[{j}]",
                                f"expected int >= 0, got {requirement!r}",
                            )
                        )

        gopl = ch.get("goodwill_ability_once_per_loop")
        if gopl is not None:
            if not isinstance(gopl, list) or len(gopl) != 2:
                issues.append(
                    ValidationIssue(
                        f"{p}.goodwill_ability_once_per_loop",
                        "must be an array of length 2 (能力1/2 是否每轮回限一次)",
                    )
                )
            else:
                for j, b in enumerate(gopl):
                    if not isinstance(b, bool):
                        issues.append(
                            ValidationIssue(
                                f"{p}.goodwill_ability_once_per_loop[{j}]",
                                f"expected bool, got {b!r}",
                            )
                        )

        gabilities = ch.get("goodwill_abilities")
        if gabilities is not None:
            if not isinstance(gabilities, list):
                issues.append(ValidationIssue(f"{p}.goodwill_abilities", "must be an array"))
            else:
                for j, ability in enumerate(gabilities):
                    _validate_goodwill_ability(ability, f"{p}.goodwill_abilities[{j}]", issues)

    return issues


def _validate_goodwill_ability(
    ability: Any,
    path_prefix: str,
    issues: list[ValidationIssue],
) -> None:
    if not isinstance(ability, dict):
        issues.append(ValidationIssue(path_prefix, "ability must be an object"))
        return

    ability_id = ability.get("ability_id")
    if not isinstance(ability_id, str) or not ability_id.strip():
        issues.append(ValidationIssue(f"{path_prefix}.ability_id", "must be non-empty string"))

    ability_type = ability.get("ability_type", AbilityType.OPTIONAL.value)
    if ability_type not in _ABILITY_TYPE_VALUES:
        issues.append(ValidationIssue(f"{path_prefix}.ability_type", f"invalid AbilityType: {ability_type!r}"))

    timing = ability.get("timing", AbilityTiming.PROTAGONIST_ABILITY.value)
    if timing not in _ABILITY_TIMING_VALUES:
        issues.append(ValidationIssue(f"{path_prefix}.timing", f"invalid AbilityTiming: {timing!r}"))

    requirement = ability.get("goodwill_requirement", 0)
    if not isinstance(requirement, int) or requirement < 0:
        issues.append(ValidationIssue(f"{path_prefix}.goodwill_requirement", "expected int >= 0"))

    for key in ("sequential", "once_per_loop", "once_per_day", "can_be_refused"):
        value = ability.get(key)
        if value is not None and not isinstance(value, bool):
            issues.append(ValidationIssue(f"{path_prefix}.{key}", f"expected bool, got {value!r}"))

    effects = ability.get("effects", [])
    if not isinstance(effects, list):
        issues.append(ValidationIssue(f"{path_prefix}.effects", "must be an array"))
        return
    for k, effect in enumerate(effects):
        _validate_goodwill_effect(effect, f"{path_prefix}.effects[{k}]", issues)


def _validate_goodwill_effect(
    effect: Any,
    path_prefix: str,
    issues: list[ValidationIssue],
) -> None:
    if not isinstance(effect, dict):
        issues.append(ValidationIssue(path_prefix, "effect must be an object"))
        return
    effect_type = effect.get("effect_type")
    if effect_type not in _EFFECT_VALUES:
        issues.append(ValidationIssue(f"{path_prefix}.effect_type", f"invalid EffectType: {effect_type!r}"))
    token_type = effect.get("token_type")
    if token_type is not None and token_type not in _TOKEN_VALUES:
        issues.append(ValidationIssue(f"{path_prefix}.token_type", f"invalid TokenType: {token_type!r}"))
    amount = effect.get("amount", 0)
    if not isinstance(amount, int):
        issues.append(ValidationIssue(f"{path_prefix}.amount", f"expected int, got {amount!r}"))


def load_board_layout_keys(path: Path) -> frozenset[str] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        layout = data.get("layout")
        if isinstance(layout, dict):
            return frozenset(layout.keys())
    except (json.JSONDecodeError, OSError):
        pass
    return None

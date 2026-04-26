"""目标选择器：范围层 + 对象层 + 属性过滤层。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

KNOWN_SELECTOR_SCOPES = frozenset(
    {
        "same_area",
        "any_area",
        "adjacent_area",
        "diagonal_area",
        "initial_area",
        "fixed_area",
    }
)
KNOWN_SELECTOR_SUBJECTS = frozenset(
    {
        "character",
        "other_character",
        "dead_character",
        "board",
        "character_or_board",
    }
)
KNOWN_SELECTOR_MODES = frozenset({"single", "all"})
KNOWN_SELECTOR_REFS = frozenset(
    {
        "self",
        "other",
        "condition_target",
        "last_loop_goodwill_characters",
        "another_character",
        "literal",
        "none",
    }
)


@dataclass(frozen=True)
class SelectorFilters:
    identity_id: str | None = None
    attribute: str | None = None
    limit_reached: bool = False
    exclude_previous_target: bool = False


@dataclass(frozen=True)
class TargetSelector:
    scope: str | None = None
    subject: str | None = None
    mode: str = "single"
    filters: SelectorFilters = field(default_factory=SelectorFilters)
    ref: str | None = None
    value: str | None = None
    area: str | None = None


def is_selector_mapping(value: Any) -> bool:
    return isinstance(value, dict) and any(
        key in value
        for key in ("scope", "subject", "mode", "filters", "ref", "area")
    )


def parse_target_selector(raw: Any) -> TargetSelector:
    if isinstance(raw, TargetSelector):
        return raw
    if is_selector_mapping(raw):
        return _parse_selector_mapping(raw)
    if not isinstance(raw, str):
        return TargetSelector(ref="literal", value=str(raw))
    return _parse_selector_string(raw)


def selector_requires_choice(raw: Any) -> bool:
    selector = parse_target_selector(raw)
    if selector.ref == "another_character":
        return True
    if selector.ref is not None:
        return False
    return selector.mode == "single"


def selector_is_character_choice(raw: Any) -> bool:
    selector = parse_target_selector(raw)
    if selector.ref == "another_character":
        return True
    return selector.ref is None and selector.mode == "single" and selector.subject in {
        "character",
        "other_character",
        "dead_character",
    }


def selector_is_self_ref(raw: Any) -> bool:
    return parse_target_selector(raw).ref == "self"


def selector_literal_value(raw: Any) -> str | None:
    selector = parse_target_selector(raw)
    if selector.ref == "literal":
        return selector.value
    return None


def character_choice_selector(character_id: str) -> dict[str, str]:
    return {"ref": "literal", "value": str(character_id)}


def area_choice_selector(area_id: str) -> dict[str, str]:
    return {
        "scope": "fixed_area",
        "subject": "board",
        "area": str(area_id),
    }


def selector_character_id(raw: Any) -> str | None:
    selector = parse_target_selector(raw)
    if selector.ref == "literal" and selector.value:
        return selector.value
    return None


def selector_area_id(raw: Any) -> str | None:
    selector = parse_target_selector(raw)
    if selector.ref == "literal" and selector.value:
        return selector.value
    if (
        selector.ref is None
        and selector.scope == "fixed_area"
        and selector.subject == "board"
        and selector.area
    ):
        return selector.area
    return None


def selector_is_board_query(raw: Any) -> bool:
    selector = parse_target_selector(raw)
    return selector.ref is None and selector.subject == "board"


def _parse_selector_mapping(data: dict[str, Any]) -> TargetSelector:
    raw_filters = data.get("filters", {})
    filters = SelectorFilters(
        identity_id=str(raw_filters.get("identity_id")) if isinstance(raw_filters, dict) and raw_filters.get("identity_id") is not None else None,
        attribute=str(raw_filters.get("attribute")) if isinstance(raw_filters, dict) and raw_filters.get("attribute") is not None else None,
        limit_reached=bool(raw_filters.get("limit_reached", False)) if isinstance(raw_filters, dict) else False,
        exclude_previous_target=bool(raw_filters.get("exclude_previous_target", False))
        if isinstance(raw_filters, dict)
        else False,
    )
    return TargetSelector(
        scope=str(data.get("scope")) if data.get("scope") is not None else None,
        subject=str(data.get("subject")) if data.get("subject") is not None else None,
        mode=str(data.get("mode", "single")),
        filters=filters,
        ref=str(data.get("ref")) if data.get("ref") is not None else None,
        value=str(data.get("value")) if data.get("value") is not None else None,
        area=str(data.get("area")) if data.get("area") is not None else None,
    )


def _parse_selector_string(raw: str) -> TargetSelector:
    if raw == "self":
        return TargetSelector(ref="self")
    if raw == "other":
        return TargetSelector(ref="other")
    if raw == "condition_target":
        return TargetSelector(ref="condition_target")
    if raw == "last_loop_goodwill_characters":
        return TargetSelector(ref="last_loop_goodwill_characters")
    if raw == "another_character":
        return TargetSelector(ref="another_character")
    return TargetSelector(ref="literal", value=raw)

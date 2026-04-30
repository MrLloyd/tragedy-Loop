"""selector 结构校验。"""

from __future__ import annotations

from typing import Any

from engine.models.enums import AreaId, Attribute
from engine.models.selectors import (
    KNOWN_SELECTOR_MODES,
    KNOWN_SELECTOR_REFS,
    KNOWN_SELECTOR_SCOPES,
    KNOWN_SELECTOR_SUBJECTS,
    is_selector_mapping,
)
from engine.validation.common import ValidationIssue

_AREA_VALUES = frozenset(area.value for area in AreaId)
_ATTRIBUTE_VALUES = frozenset(attribute.value for attribute in Attribute)


def validate_selector(
    selector: Any,
    path: str,
    issues: list[ValidationIssue],
) -> None:
    if isinstance(selector, str):
        if not selector.strip():
            issues.append(ValidationIssue(path, "target selector must be a non-empty string or selector object"))
        return
    if not is_selector_mapping(selector):
        issues.append(ValidationIssue(path, "target selector must be a string or selector object"))
        return

    ref = selector.get("ref")
    scope = selector.get("scope")
    subject = selector.get("subject")
    mode = selector.get("mode", "single")

    if ref is None:
        if scope not in KNOWN_SELECTOR_SCOPES:
            issues.append(ValidationIssue(f"{path}.scope", f"unknown selector scope: {scope!r}"))
        if subject not in KNOWN_SELECTOR_SUBJECTS:
            issues.append(ValidationIssue(f"{path}.subject", f"unknown selector subject: {subject!r}"))
        if mode not in KNOWN_SELECTOR_MODES:
            issues.append(ValidationIssue(f"{path}.mode", f"unknown selector mode: {mode!r}"))
        if scope == "fixed_area":
            area = selector.get("area")
            if area not in _AREA_VALUES:
                issues.append(ValidationIssue(f"{path}.area", f"invalid AreaId: {area!r}"))
    else:
        if ref not in KNOWN_SELECTOR_REFS:
            issues.append(ValidationIssue(f"{path}.ref", f"unknown selector ref: {ref!r}"))
        if ref == "literal":
            value = selector.get("value")
            if not isinstance(value, str) or not value.strip():
                issues.append(ValidationIssue(f"{path}.value", "literal selector requires non-empty value"))

    filters = selector.get("filters")
    if filters is not None and not isinstance(filters, dict):
        issues.append(ValidationIssue(f"{path}.filters", "filters must be an object"))
        return
    if not isinstance(filters, dict):
        return

    identity_id = filters.get("identity_id")
    if identity_id is not None and (not isinstance(identity_id, str) or not identity_id.strip()):
        issues.append(ValidationIssue(f"{path}.filters.identity_id", "must be non-empty string"))
    attribute = filters.get("attribute")
    if attribute is not None and attribute not in _ATTRIBUTE_VALUES:
        issues.append(ValidationIssue(f"{path}.filters.attribute", f"invalid Attribute: {attribute!r}"))
    for flag_key in ("limit_reached", "exclude_previous_target"):
        value = filters.get(flag_key)
        if value is not None and not isinstance(value, bool):
            issues.append(ValidationIssue(f"{path}.filters.{flag_key}", f"expected bool, got {value!r}"))

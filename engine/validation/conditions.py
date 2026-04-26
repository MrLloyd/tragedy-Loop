"""condition 结构校验。"""

from __future__ import annotations

from typing import Any

from engine.models.enums import TokenType
from engine.validation.common import KNOWN_CONDITION_TYPES, ValidationIssue, enum_values
from engine.validation.selectors import validate_selector

_TOKEN_TYPE = enum_values(TokenType)


def validate_condition(
    cond: Any,
    path: str,
    issues: list[ValidationIssue],
) -> None:
    if not isinstance(cond, dict):
        issues.append(ValidationIssue(path, "condition must be an object"))
        return

    condition_type = cond.get("condition_type")
    if condition_type not in KNOWN_CONDITION_TYPES:
        issues.append(
            ValidationIssue(
                f"{path}.condition_type",
                f"unknown condition_type: {condition_type!r}",
            )
        )

    params = cond.get("params")
    if params is not None and not isinstance(params, dict):
        issues.append(ValidationIssue(f"{path}.params", "must be an object"))
        return
    if not isinstance(params, dict):
        return

    if condition_type in {"all_of", "any_of"}:
        nested = params.get("conditions")
        if not isinstance(nested, list):
            issues.append(ValidationIssue(f"{path}.params.conditions", "must be an array"))
        else:
            for idx, item in enumerate(nested):
                validate_condition(item, f"{path}.params.conditions[{idx}]", issues)

    if "target" in params:
        validate_selector(params.get("target"), f"{path}.params.target", issues)

    if condition_type == "token_check":
        token = params.get("token")
        if isinstance(token, str) and token not in _TOKEN_TYPE:
            issues.append(
                ValidationIssue(
                    f"{path}.params.token",
                    f"invalid TokenType: {token!r}",
                )
            )

    if condition_type in {
        "identity_token_check",
        "identity_initial_area_board_token_check",
        "same_area_identity_token_check",
    }:
        identity_id = params.get("identity_id")
        if not isinstance(identity_id, str) or not identity_id.strip():
            issues.append(
                ValidationIssue(
                    f"{path}.params.identity_id",
                    "must be non-empty string",
                )
            )
        token = params.get("token")
        if isinstance(token, str) and token not in _TOKEN_TYPE:
            issues.append(
                ValidationIssue(
                    f"{path}.params.token",
                    f"invalid TokenType: {token!r}",
                )
            )

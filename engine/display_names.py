from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from engine.models.enums import AreaId
from engine.rules.character_loader import load_character_defs, normalize_identity_id

_REPO_ROOT = Path(__file__).parent.parent
_MODULE_DIR = _REPO_ROOT / "data" / "modules"

_PHASE_NAMES = {
    "game_prepare": "游戏准备阶段",
    "loop_start": "轮回开始阶段",
    "turn_start": "回合开始阶段",
    "mastermind_action": "剧作家行动阶段",
    "protagonist_action": "主人公行动阶段",
    "action_resolve": "行动结算阶段",
    "playwright_ability": "剧作家能力阶段",
    "protagonist_ability": "主人公能力阶段",
    "incident": "事件阶段",
    "leader_rotate": "队长轮换阶段",
    "turn_end": "回合结束阶段",
    "loop_end": "轮回结束阶段",
    "next_loop": "进入下一轮回",
    "final_guess": "最终决战",
    "game_end": "对局结束",
}

_AREA_NAMES = {
    AreaId.HOSPITAL.value: "医院",
    AreaId.SCHOOL.value: "学校",
    AreaId.SHRINE.value: "神社",
    AreaId.CITY.value: "都市",
    AreaId.FARAWAY.value: "远方",
}

_TOKEN_NAMES = {
    "paranoia": "不安",
    "intrigue": "密谋",
    "goodwill": "友好",
    "hope": "希望",
    "despair": "绝望",
    "guard": "护卫",
}

_CARD_NAMES = {
    "intrigue_plus_2": "密谋 +2",
    "intrigue_plus_1": "密谋 +1",
    "paranoia_plus_1": "不安 +1",
    "paranoia_minus_1": "不安 -1",
    "move_horizontal": "横向移动",
    "move_vertical": "纵向移动",
    "move_diagonal": "斜向移动",
    "forbid_goodwill": "禁止友好",
    "forbid_paranoia": "禁止不安",
    "despair_plus_1": "绝望 +1",
    "goodwill_plus_1_mm": "友好 +1（剧作家）",
    "goodwill_plus_1": "友好 +1",
    "goodwill_plus_2": "友好 +2",
    "paranoia_plus_1_p": "不安 +1",
    "paranoia_minus_1_p": "不安 -1",
    "move_horizontal_p": "横向移动",
    "move_vertical_p": "纵向移动",
    "forbid_intrigue": "禁止密谋",
    "forbid_movement": "禁止移动",
    "hope_plus_1": "希望 +1",
    "paranoia_plus_2_p": "不安 +2",
}

_OUTCOME_NAMES = {
    "protagonist_death": "主人公死亡",
    "protagonist_failure": "主人公失败",
    "protagonist_win": "主人公胜利",
    "mastermind_win": "剧作家胜利",
    "none": "未结束",
}

_WAIT_TYPE_NAMES = {
    "script_setup": "填写非公开信息表",
    "choose_initial_area": "选择初始区域",
    "place_action_cards": "放置 3 张行动牌",
    "place_action_card": "放置 1 张行动牌",
    "choose_ability_target": "选择能力目标",
    "choose_incident_character": "选择事件角色目标",
    "choose_incident_area": "选择事件版图目标",
    "choose_incident_token_type": "选择事件指示物类型",
    "choose_playwright_ability": "选择剧作家能力",
    "choose_goodwill_ability": "选择友好能力",
    "respond_goodwill_ability": "回应友好能力",
    "choose_turn_end_ability": "选择回合结束能力",
    "final_guess": "最终决战选择",
}

_PLAYER_NAMES = {
    "mastermind": "剧作家",
    "protagonists": "主人公阵营",
    "protagonist_0": "主人公 1",
    "protagonist_1": "主人公 2",
    "protagonist_2": "主人公 3",
}


@lru_cache(maxsize=1)
def _character_names() -> dict[str, str]:
    return {
        character_id: character.name
        for character_id, character in load_character_defs().items()
    }


@lru_cache(maxsize=1)
def _character_initial_areas() -> dict[str, str]:
    return {
        character_id: area_name(character.initial_area.value)
        for character_id, character in load_character_defs().items()
    }


@lru_cache(maxsize=1)
def _module_catalog() -> dict[str, dict[str, str]]:
    modules: dict[str, str] = {}
    rules: dict[str, str] = {}
    identities: dict[str, str] = {"平民": "平民", "commoner": "平民"}
    incidents: dict[str, str] = {}

    for path in sorted(_MODULE_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as handle:
            raw = json.load(handle)
        module = raw.get("module", {})
        module_id = str(module.get("module_id", path.stem))
        modules[module_id] = str(module.get("name", module_id))

        for item in raw.get("rules_y", []):
            rules[str(item["rule_id"])] = str(item.get("name", item["rule_id"]))
        for item in raw.get("rules_x", []):
            rules[str(item["rule_id"])] = str(item.get("name", item["rule_id"]))
        for item in raw.get("identities", []):
            identities[str(item["identity_id"])] = str(item.get("name", item["identity_id"]))
        for item in raw.get("incidents", []):
            incidents[str(item["incident_id"])] = str(item.get("name", item["incident_id"]))

    return {
        "modules": modules,
        "rules": rules,
        "identities": identities,
        "incidents": incidents,
    }


def phase_name(value: str) -> str:
    return _PHASE_NAMES.get(value, value)


def area_name(value: str) -> str:
    return _AREA_NAMES.get(value, value)


def token_name(value: str) -> str:
    return _TOKEN_NAMES.get(value, value)


def card_name(value: str) -> str:
    return _CARD_NAMES.get(value, value)


def outcome_name(value: str) -> str:
    return _OUTCOME_NAMES.get(value, value)


def wait_type_name(value: str) -> str:
    return _WAIT_TYPE_NAMES.get(value, value)


def player_name(value: str) -> str:
    return _PLAYER_NAMES.get(value, value)


def character_name(character_id: str) -> str:
    return _character_names().get(character_id, character_id)


def module_name(module_id: str) -> str:
    return _module_catalog()["modules"].get(module_id, module_id)


def rule_name(rule_id: str) -> str:
    return _module_catalog()["rules"].get(rule_id, rule_id)


def identity_name(identity_id: str) -> str:
    if identity_id == "???":
        return "未公开"
    normalized = normalize_identity_id(identity_id)
    return _module_catalog()["identities"].get(normalized, normalized)


def revealed_identity_message(character_id: str, identity_id: str) -> str:
    return f"{character_name(character_id)}的身份是{identity_name(identity_id)}"


def incident_name(incident_id: str) -> str:
    return _module_catalog()["incidents"].get(incident_id, incident_id)


def option_label(name: str, value: str) -> str:
    if not name or name == value:
        return value
    return f"{name}（{value}）"


def module_option_label(module_id: str) -> str:
    return option_label(module_name(module_id), module_id)


def rule_option_label(rule_id: str) -> str:
    return option_label(rule_name(rule_id), rule_id)


def identity_option_label(identity_id: str) -> str:
    normalized = normalize_identity_id(identity_id)
    return option_label(identity_name(normalized), normalized)


def incident_option_label(incident_id: str) -> str:
    return option_label(incident_name(incident_id), incident_id)


def character_option_label(character_id: str) -> str:
    name = character_name(character_id)
    initial_area = _character_initial_areas().get(character_id)
    if initial_area:
        return f"{name}（{initial_area}｜{character_id}）"
    return option_label(name, character_id)


def format_tokens(tokens: dict[str, int]) -> str:
    if not tokens:
        return "无"
    parts = [
        f"{token_name(token_type)}×{amount}"
        for token_type, amount in tokens.items()
        if amount > 0
    ]
    return "、".join(parts) if parts else "无"


def display_target_name(value: str) -> str:
    if value in _AREA_NAMES:
        return area_name(value)
    if value in _character_names():
        return character_name(value)
    if value in _module_catalog()["identities"]:
        return identity_name(value)
    if value in _module_catalog()["incidents"]:
        return incident_name(value)
    return value


def format_public_info(public_info: dict[str, Any]) -> str:
    if not public_info:
        return ""

    lines: list[str] = []
    module_id = str(public_info.get("module_id", ""))
    if module_id:
        lines.append(f"模组：{module_option_label(module_id)}")

    loop_count = public_info.get("loop_count")
    if loop_count is not None:
        lines.append(f"轮回数：{loop_count}")

    days_per_loop = public_info.get("days_per_loop")
    if days_per_loop is not None:
        lines.append(f"每轮天数：{days_per_loop}")

    incidents = public_info.get("incidents", [])
    if isinstance(incidents, list):
        if incidents:
            incident_text = "；".join(
                f"第 {item.get('day', '?')} 天：{item.get('name', item.get('incident_id', '?'))}"
                for item in incidents
                if isinstance(item, dict)
            )
            lines.append(f"事件：{incident_text}")
        else:
            lines.append("事件：无")

    special_rules = public_info.get("special_rules", [])
    if isinstance(special_rules, list):
        lines.append(
            "特殊规则：" + ("；".join(str(item) for item in special_rules) if special_rules else "无")
        )

    return "\n".join(lines)


def format_public_incidents(public_info: dict[str, Any]) -> str:
    incidents = public_info.get("incidents", [])
    if not isinstance(incidents, list) or not incidents:
        return "无"
    return "；".join(
        f"第 {item.get('day', '?')} 天：{item.get('name', item.get('incident_id', '?'))}"
        for item in incidents
        if isinstance(item, dict)
    ) or "无"

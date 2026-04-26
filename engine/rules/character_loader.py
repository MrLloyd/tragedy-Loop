"""惨剧轮回 — 角色数据加载器

读取 data/characters.json，提供：
- CharacterDef 角色模板
- CharacterSetup -> CharacterState 的实例化
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from engine.models.ability import Ability
from engine.models.effects import Condition, Effect
from engine.models.character import CharacterState
from engine.models.enums import AbilityTiming, AbilityType, AreaId, Attribute, EffectType, TokenType, Trait
from engine.models.script import CharacterSetup

_CHARACTER_DATA_FILE = Path(__file__).parent.parent.parent / "data" / "characters.json"

# 兼容历史脚本中的平民写法。
_COMMONER_ALIASES = {"平民", "commoner"}


@dataclass(frozen=True)
class CharacterDef:
    character_id: str
    name: str
    initial_area: AreaId
    initial_area_mode: str = "fixed"
    forbidden_areas: list[AreaId] = field(default_factory=list)
    attributes: set[Attribute] = field(default_factory=set)
    paranoia_limit: int = 2
    base_traits: set[Trait] = field(default_factory=set)
    trait_rule: str = ""
    script_constraints: list[str] = field(default_factory=list)
    goodwill_abilities: list[Ability] = field(default_factory=list)
    goodwill_ability_texts: list[str] = field(default_factory=list)
    goodwill_ability_goodwill_requirements: list[int] = field(default_factory=list)
    goodwill_ability_once_per_loop: list[bool] = field(default_factory=list)
    initial_area_candidates: list[AreaId] = field(default_factory=list)


def normalize_identity_id(identity_id: str) -> str:
    """统一平民身份的兼容输入。"""
    if identity_id in _COMMONER_ALIASES:
        return "平民"
    return identity_id


def load_character_defs(path: Path | None = None) -> dict[str, CharacterDef]:
    """
    加载角色模板定义。

    Args:
        path: characters.json 路径，默认使用仓库 data/characters.json

    Returns:
        以 character_id 为键的 CharacterDef 字典
    """
    target = path or _CHARACTER_DATA_FILE
    if not target.exists():
        raise FileNotFoundError(f"Character file not found: {target}")

    with target.open(encoding="utf-8") as f:
        raw = json.load(f)

    items = raw.get("characters")
    if not isinstance(items, list):
        raise ValueError(f"Invalid characters payload in {target}: missing 'characters' array")

    defs: dict[str, CharacterDef] = {}
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"Invalid characters[{idx}] in {target}: expected object")
        char_def = _parse_character_def(item)
        defs[char_def.character_id] = char_def
    return defs


def instantiate_character_state(
    setup: CharacterSetup,
    defs: dict[str, CharacterDef],
) -> CharacterState:
    """
    将 CharacterSetup 实例化为 CharacterState。

    仅负责角色基础状态；事件当事人等信息仍由 Script/IncidentSchedule 表达。
    """
    char_def = defs.get(setup.character_id)
    if char_def is None:
        raise ValueError(f"Unknown character_id in setup: {setup.character_id}")

    identity_id = normalize_identity_id(setup.identity_id)
    initial_area = char_def.initial_area
    if setup.initial_area:
        initial_area = AreaId(setup.initial_area)
    return CharacterState(
        character_id=char_def.character_id,
        name=char_def.name,
        area=initial_area,
        initial_area=initial_area,
        identity_id=identity_id,
        original_identity_id=identity_id,
        base_traits=set(char_def.base_traits),
        attributes=set(char_def.attributes),
        paranoia_limit=char_def.paranoia_limit,
        base_forbidden_areas=list(char_def.forbidden_areas),
        forbidden_areas=list(char_def.forbidden_areas),
        goodwill_abilities=list(char_def.goodwill_abilities),
        goodwill_ability_texts=list(char_def.goodwill_ability_texts),
        goodwill_ability_goodwill_requirements=list(char_def.goodwill_ability_goodwill_requirements),
        goodwill_ability_once_per_loop=list(char_def.goodwill_ability_once_per_loop),
    )


def _parse_character_def(data: dict[str, object]) -> CharacterDef:
    character_id = str(data["character_id"])
    name = str(data["name"])
    initial_area = AreaId(str(data["initial_area"]))
    initial_area_mode = str(data.get("initial_area_mode", "fixed"))

    forbidden_areas = [
        AreaId(str(v))
        for v in data.get("forbidden_areas", [])
    ]
    attributes = {
        Attribute(str(v))
        for v in data.get("attributes", [])
    }
    base_traits = {
        Trait(str(v))
        for v in data.get("base_traits", [])
    }
    initial_area_candidates = [
        AreaId(str(v))
        for v in data.get("initial_area_candidates", [])
    ]

    paranoia_limit = int(data.get("paranoia_limit", 2))
    trait_rule = str(data.get("trait_rule", ""))
    script_constraints = [str(v) for v in data.get("script_constraints", [])]

    goodwill_abilities = _parse_goodwill_abilities(data, character_id)
    goodwill_texts = [str(v) for v in data.get("goodwill_ability_texts", [])]
    raw_goodwill_requirements = data.get("goodwill_ability_goodwill_requirements", [])
    goodwill_requirements = [int(v) for v in raw_goodwill_requirements]
    goodwill_once = [bool(v) for v in data.get("goodwill_ability_once_per_loop", [])]

    return CharacterDef(
        character_id=character_id,
        name=name,
        initial_area=initial_area,
        initial_area_mode=initial_area_mode,
        forbidden_areas=forbidden_areas,
        attributes=attributes,
        paranoia_limit=paranoia_limit,
        base_traits=base_traits,
        trait_rule=trait_rule,
        script_constraints=script_constraints,
        goodwill_abilities=goodwill_abilities,
        goodwill_ability_texts=goodwill_texts,
        goodwill_ability_goodwill_requirements=goodwill_requirements,
        goodwill_ability_once_per_loop=goodwill_once,
        initial_area_candidates=initial_area_candidates,
    )


def _parse_goodwill_abilities(data: dict[str, object], character_id: str) -> list[Ability]:
    raw_structured = data.get("goodwill_abilities")
    if isinstance(raw_structured, list):
        return [_parse_goodwill_ability(item, character_id) for item in raw_structured if isinstance(item, dict)]
    return _build_legacy_goodwill_abilities(data, character_id)


def _build_legacy_goodwill_abilities(data: dict[str, object], character_id: str) -> list[Ability]:
    texts = [str(v) for v in data.get("goodwill_ability_texts", [])]
    requirements = [int(v) for v in data.get("goodwill_ability_goodwill_requirements", [])]
    once_per_loop = [bool(v) for v in data.get("goodwill_ability_once_per_loop", [])]

    abilities: list[Ability] = []
    for slot in range(min(len(texts), len(requirements))):
        text = texts[slot].strip()
        if not text:
            continue
        abilities.append(
            Ability(
                ability_id=f"goodwill:{character_id}:{slot + 1}",
                name=f"{character_id} 友好能力{slot + 1}",
                ability_type=AbilityType.OPTIONAL,
                timing=AbilityTiming.PROTAGONIST_ABILITY,
                description=text,
                condition=_legacy_goodwill_condition(character_id, slot),
                effects=_legacy_goodwill_effects(character_id, slot),
                goodwill_requirement=requirements[slot],
                once_per_loop=once_per_loop[slot] if slot < len(once_per_loop) else False,
                can_be_refused=True,
            )
        )
    return abilities


def _parse_goodwill_ability(data: dict[str, object], character_id: str) -> Ability:
    return Ability(
        ability_id=str(data.get("ability_id", "")) or f"goodwill:{character_id}:structured",
        name=str(data.get("name", f"{character_id} 友好能力")),
        ability_type=AbilityType(str(data.get("ability_type", AbilityType.OPTIONAL.value))),
        timing=AbilityTiming(str(data.get("timing", AbilityTiming.PROTAGONIST_ABILITY.value))),
        description=str(data.get("description", "")),
        condition=_parse_condition(data["condition"]) if data.get("condition") else None,
        effects=[_parse_effect(item) for item in data.get("effects", []) if isinstance(item, dict)],
        sequential=bool(data.get("sequential", False)),
        goodwill_requirement=int(data.get("goodwill_requirement", 0)),
        once_per_loop=bool(data.get("once_per_loop", False)),
        once_per_day=bool(data.get("once_per_day", False)),
        can_be_refused=bool(data.get("can_be_refused", True)),
    )


def _parse_condition(data: dict[str, object]) -> Condition:
    return Condition(
        condition_type=str(data["condition_type"]),
        params=dict(data.get("params", {})),
    )


def _parse_effect(data: dict[str, object]) -> Effect:
    token_type = TokenType(str(data["token_type"])) if data.get("token_type") else None
    condition = _parse_condition(data["condition"]) if data.get("condition") else None
    return Effect(
        effect_type=EffectType(str(data["effect_type"])),
        target=data.get("target", "self"),
        token_type=token_type,
        amount=int(data.get("amount", 0)),
        value=data.get("value"),
        condition=condition,
    )


def _legacy_goodwill_condition(character_id: str, slot: int) -> Condition | None:
    if character_id == "shrine_maiden" and slot == 0:
        return Condition(
            condition_type="area_is",
            params={"target": {"ref": "self"}, "value": AreaId.SHRINE.value},
        )
    return None


def _legacy_goodwill_effects(character_id: str, slot: int) -> list[Effect]:
    goodwill_map: dict[tuple[str, int], list[Effect]] = {
        ("female_student", 0): [
            Effect(
                effect_type=EffectType.REMOVE_TOKEN,
                target={
                    "scope": "same_area",
                    "subject": "other_character",
                },
                token_type=TokenType.PARANOIA,
                amount=1,
            )
        ],
        ("male_student", 0): [
            Effect(
                effect_type=EffectType.REMOVE_TOKEN,
                target={
                    "scope": "same_area",
                    "subject": "other_character",
                },
                token_type=TokenType.PARANOIA,
                amount=1,
            )
        ],
        ("idol", 0): [
            Effect(
                effect_type=EffectType.REMOVE_TOKEN,
                target={
                    "scope": "same_area",
                    "subject": "other_character",
                },
                token_type=TokenType.PARANOIA,
                amount=1,
            )
        ],
        ("idol", 1): [
            Effect(
                effect_type=EffectType.PLACE_TOKEN,
                target={
                    "scope": "same_area",
                    "subject": "other_character",
                },
                token_type=TokenType.GOODWILL,
                amount=1,
            )
        ],
        ("office_worker", 0): [
            Effect(
                effect_type=EffectType.REVEAL_IDENTITY,
                target={"ref": "self"},
            )
        ],
        ("shrine_maiden", 0): [
            Effect(
                effect_type=EffectType.REMOVE_TOKEN,
                target={
                    "scope": "same_area",
                    "subject": "board",
                },
                token_type=TokenType.INTRIGUE,
                amount=1,
            )
        ],
        ("shrine_maiden", 1): [
            Effect(
                effect_type=EffectType.REVEAL_IDENTITY,
                target={
                    "scope": "same_area",
                    "subject": "character",
                },
            )
        ],
    }
    return list(goodwill_map.get((character_id, slot), []))

"""惨剧轮回 — 剧本数据模型"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from engine.models.ability import Ability
from engine.models.incident import IncidentSchedule


# ---------------------------------------------------------------------------
# RuleDef — 规则 Y / 规则 X 定义
# ---------------------------------------------------------------------------
@dataclass
class RuleDef:
    rule_id: str                 # 如 "谋杀计划", "好友圈"
    name: str
    rule_type: str               # "Y" or "X"
    module: str                  # 所属模组

    # 该规则要求的身份及数量 {"关键人物": 1, "杀手": 1}
    identity_slots: dict[str, int] = field(default_factory=dict)

    # 该规则允许的身份数量范围 {"暴徒": {"min": 0, "max": 2}}
    identity_slot_ranges: dict[str, dict[str, int]] = field(default_factory=dict)

    # 追加规则带来的能力（失败条件、额外能力等）
    abilities: list[Ability] = field(default_factory=list)

    # 特殊胜利条件（LL 背叛者用）
    special_victory: Optional[dict[str, Any]] = None

    description: str = ""


# ---------------------------------------------------------------------------
# ModuleDef — 模组定义
# ---------------------------------------------------------------------------
@dataclass
class ModuleDef:
    module_id: str               # 如 "first_steps", "basic_tragedy_x"
    name: str                    # 显示名

    # 特殊规则文本
    special_rules: list[str] = field(default_factory=list)

    # 模组规定的规则 X 条数（First Steps=1, 其他一般=2）
    rule_x_count: int = 2

    # 是否有最终决战（First Steps 无）
    has_final_guess: bool = True

    # EX 槽配置
    has_ex_gauge: bool = False
    ex_gauge_resets_per_loop: bool = True

    # 可用规则
    rules_y: list[RuleDef] = field(default_factory=list)
    rules_x: list[RuleDef] = field(default_factory=list)

    # 模组身份池（identity_id 列表）
    identity_pool: list[str] = field(default_factory=list)

    # 模组事件池（incident_id 列表）
    incident_pool: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CharacterSetup — 剧本中单个角色的配置
# ---------------------------------------------------------------------------
@dataclass
class CharacterSetup:
    character_id: str            # 角色标识（引用 characters.json）
    identity_id: str = "平民"   # 分配的身份（非公开）
    is_incident_perpetrator: bool = False  # 是否为某事件当事人
    initial_area: str = ""       # 剧本指定的初始区域（特例角色用）
    territory_area: str = ""     # 大人物领地（后续扩展共用）
    entry_loop: int = 0          # 第几轮登场（神灵）
    entry_day: int = 0           # 第几天登场（转校生）
    hermit_x: int = 0            # 仙人 X（剧本非公开输入）


# ---------------------------------------------------------------------------
# PublicScriptInfo — 公开信息表（只读展示）
# ---------------------------------------------------------------------------
@dataclass
class PublicScriptInfo:
    module_id: str = ""
    loop_count: int = 4
    days_per_loop: int = 4
    incidents: list[dict[str, Any]] = field(default_factory=list)
    special_rules: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "loop_count": self.loop_count,
            "days_per_loop": self.days_per_loop,
            "incidents": list(self.incidents),
            "special_rules": list(self.special_rules),
        }


# ---------------------------------------------------------------------------
# PrivateScriptInfo — 非公开信息表（运行时真值）
# ---------------------------------------------------------------------------
@dataclass
class PrivateScriptInfo:
    module_id: str = ""
    loop_count: int = 4
    days_per_loop: int = 4
    special_rules: list[str] = field(default_factory=list)
    rule_y: Optional[RuleDef] = None
    rules_x: list[RuleDef] = field(default_factory=list)
    characters: list[CharacterSetup] = field(default_factory=list)
    incidents: list[IncidentSchedule] = field(default_factory=list)
    # 与公开信息表中的 incidents 按索引一一对应；默认指向同名真实事件。
    public_incident_refs: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Script — 完整剧本（公开 + 非公开信息）
# ---------------------------------------------------------------------------
@dataclass
class Script:
    public_table: PublicScriptInfo = field(default_factory=PublicScriptInfo)
    private_table: PrivateScriptInfo = field(default_factory=PrivateScriptInfo)

    def get_public_info(self) -> dict:
        """返回主人公可见的公开信息"""
        return self.public_table.to_dict()

    def public_incident_count(self) -> int:
        return len(self.public_table.incidents)

    def public_incident_entry(self, index: int) -> dict[str, Any] | None:
        if 0 <= index < len(self.public_table.incidents):
            return self.public_table.incidents[index]
        return None

    def private_incident_ref_for_public_index(self, index: int) -> str | None:
        refs = self.private_table.public_incident_refs
        if 0 <= index < len(refs) and refs[index]:
            return refs[index]
        incidents = self.private_table.incidents
        if 0 <= index < len(incidents):
            return incidents[index].incident_id
        return None

    # ------------------------------------------------------------------
    # 兼容层：旧代码默认按非公开信息表读取剧本真值
    # ------------------------------------------------------------------
    @property
    def module_id(self) -> str:
        return self.private_table.module_id

    @module_id.setter
    def module_id(self, value: str) -> None:
        self.private_table.module_id = value

    @property
    def loop_count(self) -> int:
        return self.private_table.loop_count

    @loop_count.setter
    def loop_count(self, value: int) -> None:
        self.private_table.loop_count = value

    @property
    def days_per_loop(self) -> int:
        return self.private_table.days_per_loop

    @days_per_loop.setter
    def days_per_loop(self, value: int) -> None:
        self.private_table.days_per_loop = value

    @property
    def special_rules_text(self) -> list[str]:
        return self.private_table.special_rules

    @special_rules_text.setter
    def special_rules_text(self, value: list[str]) -> None:
        self.private_table.special_rules = value

    @property
    def rule_y(self) -> Optional[RuleDef]:
        return self.private_table.rule_y

    @rule_y.setter
    def rule_y(self, value: Optional[RuleDef]) -> None:
        self.private_table.rule_y = value

    @property
    def rules_x(self) -> list[RuleDef]:
        return self.private_table.rules_x

    @rules_x.setter
    def rules_x(self, value: list[RuleDef]) -> None:
        self.private_table.rules_x = value

    @property
    def characters(self) -> list[CharacterSetup]:
        return self.private_table.characters

    @characters.setter
    def characters(self, value: list[CharacterSetup]) -> None:
        self.private_table.characters = value

    @property
    def incidents(self) -> list[IncidentSchedule]:
        return self.private_table.incidents

    @incidents.setter
    def incidents(self, value: list[IncidentSchedule]) -> None:
        self.private_table.incidents = value

    @property
    def incident_public(self) -> list[dict[str, Any]]:
        return self.public_table.incidents

    @incident_public.setter
    def incident_public(self, value: list[dict[str, Any]]) -> None:
        self.public_table.incidents = value

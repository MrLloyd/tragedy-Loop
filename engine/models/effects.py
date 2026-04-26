"""惨剧轮回 — 通用声明式条件与效果模型"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from engine.models.enums import EffectType, TokenType


# ---------------------------------------------------------------------------
# Condition — 效果触发条件
# ---------------------------------------------------------------------------
@dataclass
class Condition:
    """声明式条件，由规则引擎在运行时求值"""

    condition_type: str
    # 常用条件类型：
    #   "token_check"           — 某角色/版图指示物数量 >= / <= value
    #   "same_area_count"       — 同区域角色数量 == / >= value
    #   "character_alive"       — 角色是否存活
    #   "is_final_day"          — 是否最终日
    #   "identity_is"           — 角色身份 == value
    #   "ex_gauge_check"        — EX 槽 >= / <= value
    #   "has_trait"             — 角色是否拥有某特性
    #   "area_is"               — 角色所在区域 == value
    #   "world_line_check"      — 表/里世界（AHR）
    #   "loop_number_check"     — 轮回编号
    #   "incident_occurred"     — 某事件是否发生过

    params: dict[str, Any] = field(default_factory=dict)
    # 例：{"target": {"ref": "self"}, "token": "intrigue", "operator": ">=", "value": 2}


# ---------------------------------------------------------------------------
# Effect — 单个效果原语
# ---------------------------------------------------------------------------
@dataclass
class Effect:
    """声明式效果，由 AtomicResolver 在运行时执行"""

    effect_type: EffectType

    # 目标选择
    target: Any = "self"
    # 常用 target：
    #   {"ref": "self"}                                  — 持有该能力的角色
    #   {"scope": "same_area", "subject": "character"}   — 同区域任意存活角色（需选择）
    #   {"scope": "same_area", "subject": "other_character"} — 同区域其他存活角色
    #   {"scope": "same_area", "subject": "dead_character"}  — 同区域尸体
    #   {"scope": "same_area", "subject": "board"}       — 所在版图
    #   {"scope": "any_area", "subject": "board"}        — 任意版图（需选择）
    #   {"ref": "condition_target"}                      — 条件判定中确定的目标
    #   也允许直接写具体 character_id / area_id

    # 效果参数
    token_type: Optional[TokenType] = None
    amount: int = 0
    chooser: str = "mastermind"  # 谁做选择："mastermind" / "leader" / "owner"
    value: Any = None            # 通用值字段

    # 条件（可选，效果自身的额外条件）
    condition: Optional[Condition] = None

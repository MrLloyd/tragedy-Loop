"""惨剧轮回 — 信息边界过滤

热座模式核心：根据玩家角色裁剪可见状态。

规则（rules.md:177, 221 更新）：
  必须告知：指示物增减结果、移动、死亡（区分死亡/失败）、
           事件是否发生+现象、拒绝时告知"技能发动失败"
  不告知：身份、当事人、能力触发原因、拒绝的具体特性
  亲友死亡：轮回结束时若死亡 → 此时告知身份
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from engine.display_names import (
    area_name,
    character_name,
    display_target_name,
    identity_name,
    incident_name,
    outcome_name,
    rule_name,
    token_name,
)
from engine.models.enums import AreaId, CharacterLifeState, PlayerRole, TokenType
from engine.game_state import GameState
from engine.models.character import CharacterState


# ---------------------------------------------------------------------------
# 可见角色状态（过滤后）
# ---------------------------------------------------------------------------
@dataclass
class VisibleCharacter:
    character_id: str
    name: str
    area: AreaId
    life_state: CharacterLifeState
    tokens: dict[str, int]       # token_type -> count（全部可见）
    identity: str                # "???" 或已公开的身份名
    attributes: list[str]        # 属性标签（公开）
    paranoia_limit: int          # 不安限度（公开）


# ---------------------------------------------------------------------------
# 可见游戏状态（过滤后）
# ---------------------------------------------------------------------------
@dataclass
class VisibleGameState:
    current_loop: int
    max_loops: int
    current_day: int
    max_days: int
    phase: str
    leader_index: int
    characters: list[VisibleCharacter]
    board_tokens: dict[str, dict[str, int]]  # area_id -> {token_type: count}
    public_info: dict[str, Any]              # 公开信息表
    placed_cards_count: int                  # 已放置牌数（不暴露内容）
    announcements: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Visibility — 信息边界过滤器
# ---------------------------------------------------------------------------
class Visibility:

    @staticmethod
    def filter_for_role(state: GameState, role: PlayerRole) -> VisibleGameState:
        """根据玩家角色返回过滤后的可见状态"""
        if role == PlayerRole.MASTERMIND:
            return Visibility._mastermind_view(state)
        return Visibility._protagonist_view(state)

    # ---- 剧作家视角：完整信息 ----

    @staticmethod
    def _mastermind_view(state: GameState) -> VisibleGameState:
        characters = []
        for ch in state.characters.values():
            characters.append(VisibleCharacter(
                character_id=ch.character_id,
                name=ch.name,
                area=ch.area,
                life_state=ch.life_state,
                tokens=Visibility._tokens_to_dict(ch.tokens),
                identity=ch.identity_id,  # 剧作家可见全部身份
                attributes=[a.value for a in ch.attributes],
                paranoia_limit=ch.paranoia_limit,
            ))

        return VisibleGameState(
            current_loop=state.current_loop,
            max_loops=state.max_loops,
            current_day=state.current_day,
            max_days=state.max_days,
            phase=state.current_phase.value,
            leader_index=state.leader_index,
            characters=characters,
            board_tokens=Visibility._board_tokens(state),
            public_info=state.script.public_table.to_dict(),
            placed_cards_count=len(state.placed_cards),
        )

    # ---- 主人公视角：过滤非公开信息 ----

    @staticmethod
    def _protagonist_view(state: GameState) -> VisibleGameState:
        characters = []
        for ch in state.characters.values():
            # 身份：已公开则显示，否则 "???"
            identity = ch.identity_id if ch.revealed else "???"

            characters.append(VisibleCharacter(
                character_id=ch.character_id,
                name=ch.name,
                area=ch.area,
                life_state=ch.life_state,
                tokens=Visibility._tokens_to_dict(ch.tokens),
                identity=identity,
                attributes=[a.value for a in ch.attributes],
                paranoia_limit=ch.paranoia_limit,
            ))

        return VisibleGameState(
            current_loop=state.current_loop,
            max_loops=state.max_loops,
            current_day=state.current_day,
            max_days=state.max_days,
            phase=state.current_phase.value,
            leader_index=state.leader_index,
            characters=characters,
            board_tokens=Visibility._board_tokens(state),
            public_info=state.script.public_table.to_dict(),
            placed_cards_count=len(state.placed_cards),
        )

    # ---- 公告生成 ----

    @staticmethod
    def create_announcement(mutation_type: str, details: dict) -> str:
        """将结算结果转为主人公可见的公告文本"""
        match mutation_type:
            case "token_change":
                target = display_target_name(str(details.get("target_id", "?")))
                token = token_name(str(details.get("token_type", "?")))
                delta = details.get("delta", 0)
                if delta > 0:
                    return f"{target} 获得了 {delta} 枚{token}"
                elif delta < 0:
                    return f"{target} 失去了 {-delta} 枚{token}"
                return ""

            case "character_death":
                target = character_name(
                    str(details.get("target_id") or details.get("character_id") or "?")
                )
                return f"{target} 死亡了"

            case "character_move":
                target = character_name(
                    str(details.get("target_id") or details.get("character_id") or "?")
                )
                destination = area_name(str(details.get("destination", "?")))
                return f"{target} 移动到了 {destination}"

            case "protagonist_death":
                return "主人公死亡"

            case "protagonist_failure":
                return "主人公失败"

            case "reveal_identity":
                cid = character_name(
                    str(details.get("target_id") or details.get("character_id") or "?")
                )
                identity = identity_name(str(details.get("identity_id", "?")))
                return f"{cid} 的身份是 {identity}"

            case "reveal_incident":
                incident_id = incident_name(str(details.get("incident_id", "?")))
                perpetrator = character_name(str(details.get("perpetrator_id", "?")))
                return f"{incident_id}事件的当事人是{perpetrator}"

            case "incident_occurred":
                incident_id = incident_name(str(details.get("incident_id", "?")))
                day = details.get("day", "?")
                return f"第 {day} 天发生事件：{incident_id}"

            case "reveal_rule_x":
                return f"公开规则 X：{rule_name(str(details.get('rule_x_id', '?')))}"

            case "loop_ended":
                return f"轮回 {details.get('loop', '?')} 结束"

            case "game_ended":
                outcome = outcome_name(str(details.get("outcome", "?")))
                return f"对局结束：{outcome}"

            case "ability_refused":
                return "技能发动失败"

            case _:
                return ""

    # ---- 辅助 ----

    @staticmethod
    def _tokens_to_dict(tokens) -> dict[str, int]:
        result = {}
        for t in TokenType:
            val = tokens.get(t)
            if val > 0:
                result[t.value] = val
        return result

    @staticmethod
    def _board_tokens(state: GameState) -> dict[str, dict[str, int]]:
        result = {}
        for area_id, area in state.board.areas.items():
            tokens = Visibility._tokens_to_dict(area.tokens)
            if tokens:
                result[area_id.value] = tokens
        return result

    @staticmethod
    def _token_display_name(token_value: str) -> str:
        return token_name(token_value)

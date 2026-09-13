"""Deterministic, synchronous game rules for the Yuki Kun game plugin.

Derived from UBC2008/astrbot_plugin_kun_game under the MIT License.
This module deliberately has no Host, AstrBot, network, filesystem, or async I/O.
"""

from __future__ import annotations

import json
import math
import random
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, NoReturn
from zoneinfo import ZoneInfo

SCHEMA_VERSION = 1
DISPLAY_PREFIX = "*"
SHANGHAI = ZoneInfo("Asia/Shanghai")
RESOURCE_LIMIT = 10**15
INPUT_COUNT_LIMIT = 100
PRICE_LIMIT = 10**9
WEIGHT_LIMIT = 10**15
DEFAULT_WEIGHT_MIN = 50
DEFAULT_WEIGHT_MAX = 200
CRITICAL_MULTIPLIER = 1.5
DEATH_LIST_LIMIT = 20

KUN_NAMES = (
    "菜虚鲲",
    "将鲲",
    "犷鲲",
    "尘鲲",
    "土鲲",
    "岩鲲",
    "石鲲",
    "沙鲲",
    "雷鲲",
    "雪鲲",
    "虹鲲",
    "碧鲲",
    "蓝鲲",
    "橙鲲",
    "黑鲲",
    "暗鲲",
    "铁头鲲",
    "钢背鲲",
    "彩鲲",
    "炎鲲",
    "冰鲲",
    "凶鲲",
    "恶鲲",
    "幻鲲",
    "诡鲲",
    "炬目鲲",
    "柯温鲲",
    "胖头鲲",
    "阳鲲",
    "靓鲲",
    "尸鲲",
    "血鲲",
    "骨鲲",
    "腐鲲",
    "毒鲲",
    "妖鲲",
    "魔鲲",
    "鬼鲲",
    "圣鲲",
    "灵鲲",
    "冥鲲",
    "玄鲲",
    "炫鲲",
    "帝鲲",
    "齿鲲",
    "剑鲲",
    "铠鲲",
    "阴鲲",
    "烈鲲",
)

BOSS_NAMES = ("鲲霸", "鲲皇", "鲲帝", "鲲神", "上古鲲鹏", "混沌鲲", "灭世鲲")

KUN_ATTRIBUTES = {
    "无": "无属性",
    "魑": "♂魑：免疫强袭",
    "魅": "♂魅：免疫吞噬",
    "魍": "♂魍：免疫攻击",
    "魉": "♂魉：体重低于666千克时恢复至1000千克",
    "淫": "淫：被吞噬后对方75%几率狗带；攻击/被攻击25%几率恢复大量体重",
    "馋": "馋：吞噬失败不损体重；幻化不耗体重；不能攻击；体重>1000kg暴死",
    "贪": "贪：吞噬/攻击30%得蛋；磨炼70%不耗节操；放生得2-10蛋",
    "惰": "惰：极强防御不易被吞噬；免疫强袭",
    "怒": "怒：极强攻击易吞噬；开始25%致命一击",
    "妒": "妒：比其体重大的鲲无法对其吞噬或攻击",
    "傲": "傲：无视对方属性",
    "悲": "悲：初始体重=榜一体重+1000kg；不可幻化；孵化率0.7%",
}

PLAY_COMMANDS = (
    "签到",
    "当前游戏",
    "命令菜单",
    "绑定群",
    "查阅属性",
    "今日运势",
    "阵亡名单",
    "拍卖行",
    "孵化",
    "买蛋",
    "砸蛋",
    "喂食",
    "磨炼",
    "幻化",
    "吞噬",
    "攻击",
    "强袭",
    "扔蛋",
    "喝鸡汤",
    "渡劫",
    "放生",
    "复活",
    "查询BOSS",
    "攻击BOSS",
    "吞噬BOSS",
    "强袭BOSS",
    "出售",
    "出价",
    "成交",
    "免疫强袭",
    "免疫吞噬",
    "免疫攻击",
    "查骰子",
    "奥数比赛",
    "数星星",
    "抄作业",
    "查看群主指令",
    "抽群主一个大嘴巴",
    "单挑群主",
)

ADMIN_COMMANDS = (
    "鲲开",
    "鲲关",
    "小游戏开",
    "小游戏关",
    "刷新BOSS",
    "重置局状态",
    "清除全群数据",
    "强制下架",
    "修改",
    "配置",
)
ADMIN_ONLY_PLAY_COMMANDS = frozenset((*ADMIN_COMMANDS, "数据清除"))

PRIVATE_PLAY_COMMANDS = frozenset(
    {
        "签到",
        "孵化",
        "砸蛋",
        "磨炼",
        "幻化",
        "查阅属性",
        "今日运势",
        "命令菜单",
        "喝鸡汤",
        "当前游戏",
    }
)

BASIC_COMMANDS = frozenset(
    {"签到", "当前游戏", "命令菜单", "绑定群", "查阅属性", "今日运势", "阵亡名单", "拍卖行"}
)
PVP_COMMANDS = frozenset({"吞噬", "攻击", "强袭", "扔蛋"})

JsonObject = dict[str, Any]
ScopeType = Literal["group", "private"]


class StateValidationError(ValueError):
    """Raised when persisted state is unsafe to execute or commit."""


class _Rejected(Exception):
    def __init__(self, message: str) -> None:
        self.message = message


@dataclass(frozen=True, slots=True)
class GameConfig:
    default_jie_cao: int = 50
    default_luck: int = 50
    egg_price: int = 5
    tribulation_cost: int = 10
    train_daily_max: int = 30
    hatch_misfortune_rate: float = 0.007

    @classmethod
    def from_mapping(cls, values: Mapping[str, object] | None) -> GameConfig:
        if values is None:
            return cls()
        known = {name: values[name] for name in cls.__dataclass_fields__ if name in values}
        return cls(**known)  # type: ignore[arg-type]

    def __post_init__(self) -> None:
        for name in (
            "default_jie_cao",
            "default_luck",
            "egg_price",
            "tribulation_cost",
            "train_daily_max",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
        if not 0 <= self.default_jie_cao <= PRICE_LIMIT:
            raise ValueError("default_jie_cao is out of range")
        if not 0 <= self.default_luck <= 100:
            raise ValueError("default_luck is out of range")
        if not 1 <= self.egg_price <= PRICE_LIMIT:
            raise ValueError("egg_price is out of range")
        if not 1 <= self.tribulation_cost <= PRICE_LIMIT:
            raise ValueError("tribulation_cost is out of range")
        if not 1 <= self.train_daily_max <= 1000:
            raise ValueError("train_daily_max is out of range")
        if (
            isinstance(self.hatch_misfortune_rate, bool)
            or not isinstance(self.hatch_misfortune_rate, (int, float))
            or not math.isfinite(self.hatch_misfortune_rate)
            or not 0 <= self.hatch_misfortune_rate <= 1
        ):
            raise ValueError("hatch_misfortune_rate must be finite and between 0 and 1")


@dataclass(frozen=True, slots=True)
class GameResult:
    text: str
    envelope: JsonObject | None
    changed: bool


def default_player(qq: str, *, game_date: str, config: GameConfig) -> JsonObject:
    return {
        "qq": qq,
        "kun": None,
        "jie_cao": config.default_jie_cao,
        "eggs": 0,
        "divine_weapon": 0,
        "phantom_pills": 0,
        "chicken_soup": 0,
        "resurrection_pills": 0,
        "luck": config.default_luck,
        "today_train": 0,
        "signed_today": False,
        "last_sign_date": game_date,
    }


def default_state(scope_id: str) -> JsonObject:
    return {
        "gid": scope_id,
        "kun_enabled": True,
        "game_enabled": True,
        "players": {},
        "boss": None,
        "auction": None,
        "death_list": [],
        "last_boss_date": "",
        "anti_assault": [],
        "anti_devour": [],
        "anti_attack": [],
        "mini_game": None,
        "duel_champion": None,
    }


def default_envelope(scope_type: ScopeType, scope_id: str, now: datetime) -> JsonObject:
    _validate_invocation(scope_type, scope_id, now)
    return {
        "schema_version": SCHEMA_VERSION,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "revision": 0,
        "updated_at": now.astimezone(UTC).isoformat(),
        "state": default_state(scope_id),
    }


def execute_play(
    envelope: Mapping[str, object] | None,
    *,
    text: str,
    user_id: str,
    display_name: str,
    scope_type: ScopeType,
    scope_id: str,
    mentioned_user_ids: tuple[str, ...] = (),
    rng: random.Random,
    now: datetime,
    config: GameConfig | None = None,
) -> GameResult:
    """Execute one ordinary command against a deep copy of one scope envelope."""

    _validate_invocation(scope_type, scope_id, now)
    cfg = config or GameConfig()
    original = _load_envelope(envelope, scope_type, scope_id)
    working = (
        deepcopy(original) if original is not None else default_envelope(scope_type, scope_id, now)
    )
    engine = _Engine(working["state"], cfg, rng, now, scope_type)
    try:
        command, arguments = _parse_command(text)
        engine.new_day_reset()
        result_text = engine.play(
            command,
            arguments,
            user_id=user_id,
            display_name=display_name or user_id,
            mentioned_user_ids=mentioned_user_ids,
        )
    except _Rejected as exc:
        return GameResult(exc.message, deepcopy(original), False)
    return _finish(original, working, result_text, now, scope_type, scope_id)


def execute_admin(
    envelope: Mapping[str, object] | None,
    *,
    text: str,
    user_id: str,
    display_name: str,
    scope_type: ScopeType,
    scope_id: str,
    rng: random.Random,
    now: datetime,
    config: GameConfig | None = None,
) -> GameResult:
    """Execute one SUPERUSER-only action; the adapter owns the authority check."""

    _validate_invocation(scope_type, scope_id, now)
    if scope_type != "group":
        return GameResult(
            "管理命令仅支持群聊。", deepcopy(dict(envelope)) if envelope else None, False
        )
    cfg = config or GameConfig()
    original = _load_envelope(envelope, scope_type, scope_id)
    working = (
        deepcopy(original) if original is not None else default_envelope(scope_type, scope_id, now)
    )
    engine = _Engine(working["state"], cfg, rng, now, scope_type)
    try:
        command, arguments = _parse_command(text)
        engine.new_day_reset()
        result_text = engine.admin(
            command,
            arguments,
            user_id=user_id,
            display_name=display_name or user_id,
        )
    except _Rejected as exc:
        return GameResult(exc.message, deepcopy(original), False)
    return _finish(original, working, result_text, now, scope_type, scope_id)


def validate_envelope(
    envelope: Mapping[str, object], *, scope_type: ScopeType, scope_id: str
) -> None:
    _validate_envelope(dict(envelope), scope_type, scope_id)


def format_weight(weight: float) -> str:
    return f"{weight / 1000:.1f}吨" if weight >= 1000 else f"{weight:.0f}千克"


def _parse_command(text: str) -> tuple[str, str]:
    stripped = text.strip()
    if stripped.startswith(DISPLAY_PREFIX):
        stripped = stripped[len(DISPLAY_PREFIX) :].strip()
    if not stripped:
        _reject(_short_help())
    parts = stripped.split(maxsplit=1)
    return parts[0], parts[1].strip() if len(parts) == 2 else ""


def _load_envelope(
    envelope: Mapping[str, object] | None, scope_type: ScopeType, scope_id: str
) -> JsonObject | None:
    if envelope is None:
        return None
    loaded = deepcopy(dict(envelope))
    _validate_envelope(loaded, scope_type, scope_id)
    return loaded


def _finish(
    original: JsonObject | None,
    working: JsonObject,
    text: str,
    now: datetime,
    scope_type: ScopeType,
    scope_id: str,
) -> GameResult:
    state_changed = original is None or working["state"] != original["state"]
    if not state_changed:
        return GameResult(text, deepcopy(original), False)
    working["revision"] = (int(original["revision"]) if original else 0) + 1
    working["updated_at"] = now.astimezone(UTC).isoformat()
    _validate_envelope(working, scope_type, scope_id)
    return GameResult(text, working, True)


def _validate_invocation(scope_type: ScopeType, scope_id: str, now: datetime) -> None:
    if scope_type not in ("group", "private"):
        raise ValueError("invalid scope_type")
    if not scope_id or len(scope_id) > 128:
        raise ValueError("invalid scope_id")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")


def _reject(message: str) -> NoReturn:
    raise _Rejected(message)


def _positive_int(raw: str, *, default: int = 1, maximum: int = INPUT_COUNT_LIMIT) -> int:
    try:
        value = int(raw) if raw else default
    except ValueError:
        _reject("请输入正确的正整数！")
    if value <= 0 or value > maximum:
        _reject(f"数量必须在 1 到 {maximum} 之间！")
    return value


def _finite_float(raw: str, *, maximum: float = WEIGHT_LIMIT) -> float:
    try:
        value = float(raw)
    except ValueError:
        _reject("请输入正确数值！")
    if not math.isfinite(value) or value <= 0 or value > maximum:
        _reject("数值必须是范围内的有限正数！")
    return value


def _short_help() -> str:
    return "未知养鲲命令。发送 *命令菜单 查看可用命令。"


class _Engine:
    def __init__(
        self,
        state: JsonObject,
        config: GameConfig,
        rng: random.Random,
        now: datetime,
        scope_type: ScopeType,
    ) -> None:
        self.state = state
        self.config = config
        self.rng = rng
        self.now = now
        self.scope_type = scope_type
        self.game_date = now.astimezone(SHANGHAI).date().isoformat()

    def player(self, user_id: str) -> JsonObject:
        players = _mapping(self.state["players"], "players")
        if user_id not in players:
            players[user_id] = default_player(user_id, game_date=self.game_date, config=self.config)
        return _mapping(players[user_id], f"player {user_id}")

    def existing_player(self, user_id: str) -> JsonObject:
        player = _mapping(self.state["players"], "players").get(user_id)
        if player is None:
            _reject("目标还不是本作用域中的玩家。")
        return _mapping(player, f"player {user_id}")

    def new_day_reset(self) -> None:
        self.trim_death_list()
        if self.state.get("last_boss_date") != self.game_date:
            self.state["boss"] = None
            self.state["last_boss_date"] = self.game_date
        for player in self.state["players"].values():
            if player.get("last_sign_date") != self.game_date:
                player["signed_today"] = False
                player["today_train"] = 0
                player["last_sign_date"] = self.game_date

    def play(
        self,
        command: str,
        arguments: str,
        *,
        user_id: str,
        display_name: str,
        mentioned_user_ids: tuple[str, ...],
    ) -> str:
        if command in ADMIN_ONLY_PLAY_COMMANDS:
            _reject("该动作只能通过 Yuki 的 SUPERUSER 管理入口执行。")
        if command not in PLAY_COMMANDS and not command.startswith("="):
            _reject(_short_help())
        if self.scope_type == "private" and command not in PRIVATE_PLAY_COMMANDS:
            _reject("此命令仅支持群聊使用！")
        if command not in BASIC_COMMANDS and not self.state.get("kun_enabled", True):
            _reject("未开启养鲲小游戏！")

        player = self.player(user_id)
        if command == "签到":
            return self.sign_in(player, display_name)
        if command == "当前游戏":
            return self.current_game()
        if command == "命令菜单":
            return self.command_menu()
        if command == "绑定群":
            _reject("绑定群首版暂不支持；私聊与群聊状态彼此独立。")
        if command == "查阅属性":
            return self.check_attributes(player, display_name)
        if command == "今日运势":
            return (
                f"@{display_name} 今日运势：{player['luck']}\n"
                f"砸蛋出道具概率={player['luck'] / 2:.1f}%"
            )
        if command == "阵亡名单":
            return self.death_list()
        if command == "拍卖行":
            return self.auction_list()
        if command == "孵化":
            return self.hatch(player, display_name)
        if command == "买蛋":
            return self.buy_eggs(player, display_name, arguments)
        if command == "砸蛋":
            return self.smash_eggs(player, display_name, arguments)
        if command == "喂食":
            return self.feed(player, display_name, arguments)
        if command == "磨炼":
            return self.train(player, display_name, arguments)
        if command == "幻化":
            return self.evolve(player, display_name)
        if command in PVP_COMMANDS:
            return self.pvp(
                command,
                player,
                user_id,
                display_name,
                mentioned_user_ids,
            )
        if command == "喝鸡汤":
            return self.drink_soup(player, display_name, arguments)
        if command == "渡劫":
            return self.tribulation(player, display_name)
        if command == "放生":
            return self.release(player, display_name)
        if command == "复活":
            return self.resurrect(player, display_name)
        if command == "查询BOSS":
            return self.query_boss()
        if command in {"攻击BOSS", "吞噬BOSS", "强袭BOSS"}:
            return self.boss_action(command.removesuffix("BOSS"), player, user_id, display_name)
        if command == "出售":
            return self.auction_sell(player, user_id, display_name, arguments)
        if command == "出价":
            return self.auction_bid(player, user_id, display_name, arguments)
        if command == "成交":
            return self.auction_deal(player, user_id, display_name)
        if command.startswith("免疫"):
            return self.immunity(player, display_name, command)
        if command == "查骰子":
            return self.roll_dice(display_name, arguments)
        if command in {"奥数比赛", "数星星", "抄作业"}:
            return self.start_mini_game(command)
        if command == "查看群主指令":
            return self.owner_commands()
        if command == "抽群主一个大嘴巴":
            return self.mini_game_slap(player, user_id, display_name)
        if command == "单挑群主":
            return self.mini_game_duel(player, user_id, display_name)
        if command.startswith("=") and len(command) > 1:
            return self.mini_game_answer(command[1:], user_id, display_name)
        _reject(_short_help())

    def admin(self, command: str, arguments: str, *, user_id: str, display_name: str) -> str:
        if command not in ADMIN_COMMANDS:
            _reject(
                "未知管理动作。可用：鲲开、鲲关、小游戏开、小游戏关、刷新BOSS、重置局状态、清除全群数据、强制下架、修改、配置。"
            )
        if command == "鲲开":
            self.state["kun_enabled"] = True
            return "养鲲小游戏已开启！"
        if command == "鲲关":
            self.state["kun_enabled"] = False
            return "养鲲小游戏已关闭！"
        if command == "小游戏开":
            self.state["game_enabled"] = True
            return "小游戏已开启！"
        if command == "小游戏关":
            self.state["game_enabled"] = False
            return "小游戏已关闭！"
        if command == "刷新BOSS":
            self.state["boss"] = self.generate_boss()
            return f"今日BOSS已刷新！\n发送【{DISPLAY_PREFIX}查询BOSS】查看详情"
        if command == "重置局状态":
            self.reset_round()
            return "本群本局状态已重置；玩家养成资源已保留。"
        if command == "清除全群数据":
            if arguments != self.state["gid"]:
                _reject(f"危险操作未确认。请把当前群号 {self.state['gid']} 作为参数重试。")
            self.state.clear()
            self.state.update(default_state(arguments))
            self.new_day_reset()
            return "本群全部养鲲数据已清除。"
        if command == "强制下架":
            return self.auction_force_delist()
        if command == "修改":
            return self.admin_edit(arguments)
        if command == "配置":
            _reject("经济参数配置由 Yuki 适配层处理。")
        _reject("未知管理动作。")

    def sign_in(self, player: JsonObject, name: str) -> str:
        if player["signed_today"]:
            player["jie_cao"] = max(0, player["jie_cao"] - 10)
            return f"@{name} 请勿重复签到！获得惩罚：节操-10\n剩余节操 {player['jie_cao']}"
        player["signed_today"] = True
        player["last_sign_date"] = self.game_date
        player["jie_cao"] += 10
        player["today_train"] = 0
        player["luck"] = min(100, player["luck"] + 5)
        bonus_eggs = self.rng.randint(1, 3)
        player["eggs"] += bonus_eggs
        return (
            f"@{name} 签到成功！\n获得奖励：节操+10，蛋+{bonus_eggs}\n"
            f"磨炼次数恢复至{self.config.train_daily_max}\n运势+5 (当前{player['luck']})\n"
            f"当前节操：{player['jie_cao']}，蛋：{player['eggs']}"
        )

    def current_game(self) -> str:
        if not self.state.get("game_enabled", True):
            _reject("小游戏未开启！")
        game = self.state.get("mini_game")
        if game:
            remaining = game["max_slots"] - game["slots_used"]
            return (
                "====当前小游戏====\n"
                f"进行中：{game['type']}\n问题：{game.get('question', '敲击群主')}\n"
                f"剩余名额：{remaining}\n回复*=答案参与"
            )
        champion = self.state.get("duel_champion")
        if champion:
            return (
                "====当前小游戏====\n"
                f"单挑群主进行中！当前群主：{champion['name']}"
                f"（{champion.get('consecutive', 0)}连胜）\n"
                f"回复【{DISPLAY_PREFIX}单挑群主】开始挑战"
            )
        return (
            "====当前小游戏====\n【奥数比赛】名额5\n【数星星】名额2\n"
            "【群殴群主】名额5\n【抄作业】名额5\n【单挑群主】名额1\n节操至少为1才能参与游戏"
        )

    def command_menu(self) -> str:
        commands = " / ".join(PLAY_COMMANDS)
        return (
            f"====养鲲游戏====\n开局一只鲲，进化全靠吞！\n可用命令：{commands}\n小游戏答案：*=答案"
        )

    def owner_commands(self) -> str:
        return (
            "====SUPERUSER 管理入口====\n"
            "/ai plugin run io.github.yuanyeyoutao.kun-game admin <动作> [参数]\n"
            "动作：鲲开/鲲关/小游戏开/小游戏关/刷新BOSS/重置局状态/清除全群数据/强制下架/修改/配置"
        )

    def check_attributes(self, player: JsonObject, name: str) -> str:
        kun = player.get("kun")
        if not kun:
            _reject(f"@{name} 你还没有鲲！\n发送【{DISPLAY_PREFIX}孵化】获取鲲")
        recovery = self.check_kun_recovery(kun)
        lines = [
            f"@{name} 的鲲：{kun.get('name', '无名鲲')}",
            f"体重：{format_weight(kun['weight'])}",
            f"属性：{kun['attribute']} - {KUN_ATTRIBUTES.get(kun['attribute'], '未知')}",
            f"状态：{'存活' if kun.get('alive', True) else '已阵亡'}",
            f"节操：{player['jie_cao']}",
            f"蛋：{player['eggs']}",
            f"神器：{player['divine_weapon']}",
            f"幻化丹：{player['phantom_pills']}",
            f"鸡汤：{player['chicken_soup']}",
            f"复活药：{player['resurrection_pills']}",
            f"运势：{player['luck']}",
        ]
        if recovery:
            lines.append(recovery)
        return "\n".join(lines)

    def death_list(self) -> str:
        entries = self.state.get("death_list", [])
        if not entries:
            return "阵亡名单：暂无阵亡者"
        return "\n".join(
            ["阵亡名单："]
            + [
                f"  {entry.get('qq', '?')} - {entry.get('reason', '未知')}"
                for entry in entries[-DEATH_LIST_LIMIT:]
            ]
            + ["缅怀以上各位勇士！"]
        )

    def hatch(self, player: JsonObject, name: str) -> str:
        self.ensure_not_auction_seller(player["qq"], "孵化")
        if player.get("kun") and player["kun"].get("alive", True):
            _reject(f"@{name} 你已经拥有一只鲲了，开始吞吧！")
        if player["eggs"] <= 0:
            _reject(
                f"@{name} 你并没有蛋！\n"
                f"通过每日【{DISPLAY_PREFIX}签到】或【{DISPLAY_PREFIX}买蛋】可以获取蛋"
            )
        player["eggs"] -= 1
        player["today_train"] = 0
        if self.rng.random() <= self.config.hatch_misfortune_rate:
            attribute = "悲"
            weight = self.top_weight() + 1000
        else:
            attribute = self.rng.choice(
                ("无", "魑", "魅", "魍", "魉", "淫", "馋", "贪", "惰", "怒", "妒", "傲")
            )
            weight = self.rng.randint(DEFAULT_WEIGHT_MIN, DEFAULT_WEIGHT_MAX)
        player["kun"] = {
            "name": self.rng.choice(KUN_NAMES),
            "weight": weight,
            "attribute": attribute,
            "alive": True,
            "killer": None,
        }
        return (
            f"@{name} 恭喜你获得一只{player['kun']['name']}\n"
            f"体重：{format_weight(weight)}\n{KUN_ATTRIBUTES[attribute]}"
        )

    def buy_eggs(self, player: JsonObject, name: str, arguments: str) -> str:
        count = _positive_int(arguments)
        cost = count * self.config.egg_price
        if player["jie_cao"] < cost:
            _reject(f"@{name} 节操不足！需要{cost}节操，当前节操{player['jie_cao']}")
        player["jie_cao"] -= cost
        player["eggs"] += count
        quip = self.rng.choice(
            (
                "节操去渡劫，运气不好鲲永别！",
                "你不如来买蛋，节操换蛋真划算！",
                "买一个孵只鲲，要是太轻会被吞！",
                "你不如买一对，一个孵化一个喂！",
                "要是喂完还被吞，这个仇人记在心！",
                "回头再来买一斤，砸出神器袭他鲲!",
                "不行还要买一打，直接往他头上砸！",
                "瞧一瞧，看一看，5节操一颗蛋！",
                "走一走，转一转，节操不够靠边站！",
            )
        )
        return (
            f"@{name} 购买了{count}颗蛋！消耗{cost}节操。\n{quip}\n"
            f"剩余节操：{player['jie_cao']}，现有蛋：{player['eggs']}"
        )

    def smash_eggs(self, player: JsonObject, name: str, arguments: str) -> str:
        count = _positive_int(arguments)
        if player["eggs"] < count:
            _reject(f"@{name} 你没有足够的蛋！现有{player['eggs']}颗")
        player["eggs"] -= count
        drops = {"divine_weapon": 0, "phantom_pills": 0, "chicken_soup": 0, "resurrection_pills": 0}
        for _ in range(count):
            if self.rng.random() >= player["luck"] / 200:
                continue
            roll = self.rng.random()
            key = (
                "divine_weapon"
                if roll < 0.15
                else "phantom_pills"
                if roll < 0.35
                else "chicken_soup"
                if roll < 0.65
                else "resurrection_pills"
            )
            drops[key] += 1
        for key, amount in drops.items():
            player[key] += amount
        total = sum(drops.values())
        player["luck"] = min(100, player["luck"] + total) if total else max(0, player["luck"] - 2)
        lines = [f"@{name} 狠心砸开了{count}颗蛋！"]
        labels = {
            "divine_weapon": "上古神器+夨￥宀♂牮√",
            "phantom_pills": "幻化丹",
            "chicken_soup": "鸡汤",
            "resurrection_pills": "复活药",
        }
        lines.extend(f"砸出了{labels[key]} x{amount}！" for key, amount in drops.items() if amount)
        if not total:
            lines.append("里面并没有奖品，只有尚未成型的鲲宝宝……运势-2。")
        lines.append(
            f"现有神器：{player['divine_weapon']}，幻化丹：{player['phantom_pills']}，"
            f"鸡汤：{player['chicken_soup']}，复活药：{player['resurrection_pills']}"
        )
        return "\n".join(lines)

    def feed(self, player: JsonObject, name: str, arguments: str) -> str:
        kun = self.require_live_kun(player, name)
        self.ensure_not_auction_seller(player["qq"], "喂食")
        count = _positive_int(arguments)
        if player["eggs"] < count:
            _reject(f"@{name} 你没有足够的蛋！现有{player['eggs']}颗")
        player["eggs"] -= count
        gain = count * self.rng.randint(5, 15)
        kun["weight"] += gain
        if kun["attribute"] == "馋" and kun["weight"] > 1000:
            self.kill(player, "馋属性暴食而死")
            return f"@{name} 因暴食而死！\n人为鸟死，鲲为食亡！"
        return (
            f"@{name} 喂食了{count}颗蛋！体重增加了{format_weight(gain)}\n"
            f"现体重为{format_weight(kun['weight'])}"
        )

    def train(self, player: JsonObject, name: str, arguments: str) -> str:
        kun = self.require_live_kun(player, name)
        self.ensure_not_auction_seller(player["qq"], "磨炼")
        value = _finite_float(arguments)
        if value >= kun["weight"]:
            _reject("不行不行，这么练会死的！\n磨炼数值必须小于体重！")
        if player["today_train"] >= self.config.train_daily_max:
            _reject(f"今日磨炼次数已用完！上限为{self.config.train_daily_max}次。")
        if player["jie_cao"] < 2:
            _reject(f"@{name} 节操不足2！当前节操{player['jie_cao']}")
        cost = 0 if kun["attribute"] == "贪" and self.rng.random() < 0.7 else 2
        player["jie_cao"] -= cost
        player["today_train"] += 1
        if self.rng.random() < value / kun["weight"]:
            kun["weight"] -= value
            return (
                f"@{name} 磨炼成功！【{kun['attribute']}】体重减少{format_weight(value)}，"
                f"剩余体重{format_weight(kun['weight'])}"
            )
        gain = kun["weight"] - value
        kun["weight"] += gain
        if kun["attribute"] == "馋" and kun["weight"] > 1000:
            self.kill(player, "馋属性磨炼暴食而死")
            return f"@{name} 因暴食而死！人为鸟死，鲲为食亡！"
        return (
            f"@{name} 磨炼失败！【{kun['attribute']}】体重增加{format_weight(gain)}，"
            f"现体重{format_weight(kun['weight'])}"
        )

    def evolve(self, player: JsonObject, name: str) -> str:
        kun = self.require_live_kun(player, name)
        self.ensure_not_auction_seller(player["qq"], "幻化")
        if kun["attribute"] == "悲":
            _reject("悲属性的鲲无法幻化！")
        if player["phantom_pills"] <= 0:
            _reject(f"@{name} 你没有幻化丹！\n【{DISPLAY_PREFIX}砸蛋】可以获取幻化丹")
        player["phantom_pills"] -= 1
        available = [
            attr
            for attr in ("无", "魑", "魅", "魍", "魉", "淫", "馋", "贪", "惰", "怒", "妒", "傲")
            if attr != kun["attribute"]
        ]
        new_attribute = self.rng.choice(available)
        if self.rng.random() >= 0.6:
            return f"@{name} 幻化失败！就这么没了！\n剩余幻化丹：{player['phantom_pills']}"
        old_attribute = kun["attribute"]
        kun["attribute"] = new_attribute
        cost = 0 if old_attribute == "馋" else 10
        kun["weight"] = max(1, kun["weight"] - cost)
        return (
            f"@{name} 幻化成功！\n【{old_attribute}】→【{new_attribute}】\n"
            f"{KUN_ATTRIBUTES[new_attribute]}\n"
            f"{'未消耗体重' if not cost else '消耗' + format_weight(cost) + '体重'}\n"
            f"剩余幻化丹：{player['phantom_pills']}"
        )

    def pvp(
        self,
        command: str,
        player: JsonObject,
        user_id: str,
        name: str,
        mentioned_user_ids: tuple[str, ...],
    ) -> str:
        self.require_live_kun(player, name)
        self.ensure_not_auction_seller(user_id, command)
        targets = tuple(dict.fromkeys(uid for uid in mentioned_user_ids if uid != user_id))
        if len(targets) != 1:
            _reject(f"@{name} 请在当前群消息中恰好提及一个其他玩家；纯文本 QQ 号不作为目标。")
        target_id = targets[0]
        target = self.existing_player(target_id)
        if command == "扔蛋":
            return self.throw_egg(player, target, name, target_id)
        target_kun = target.get("kun")
        if not target_kun or not target_kun.get("alive", True):
            _reject(f"@{name} 对方还没有存活的鲲，快邀请他一起玩吧。")
        if self.auction_seller() == target_id:
            _reject(f"@{name} 对方的鲲正在拍卖，无法{command}！")
        if command == "吞噬":
            return self.devour(player, target, name, target_id)
        if command == "攻击":
            return self.attack(player, target, name, target_id)
        return self.assault(player, target, name, target_id)

    def devour(self, player: JsonObject, target: JsonObject, name: str, target_id: str) -> str:
        attacker = player["kun"]
        defender = target["kun"]
        if defender["attribute"] == "魅":
            _reject(f"@{name} 魅免疫吞噬！吞噬失败！")
        if attacker["attribute"] == "馋":
            _reject(f"@{name} 馋属性无法发起吞噬！")
        if attacker["weight"] < defender["weight"] * 0.3:
            _reject(f"@{name} 你的鲲太小了！养肥了再吞吧")
        critical = attacker["attribute"] == "怒" and self.rng.random() < 0.25
        if self.rng.random() >= self.effective_devour_rate(player, target):
            loss = attacker["weight"] * 0.2
            if attacker["attribute"] != "馋":
                attacker["weight"] -= loss
            if attacker["weight"] <= 0:
                self.kill(player, "吞噬失败反噬而死")
                return f"@{name} 吞噬失败！为食而死！"
            return (
                f"@{name} 吞噬失败！体重减少{format_weight(loss)}\n"
                f"剩余体重{format_weight(attacker['weight'])}"
            )
        damage = attacker["weight"] * (
            CRITICAL_MULTIPLIER if critical else self.rng.uniform(0.3, 0.6)
        )
        defender["weight"] -= damage
        if defender["weight"] <= 0 or critical:
            defender["weight"] = max(0, defender["weight"])
            attacker["weight"] += defender["weight"]
            self.kill(target, f"被{name}吞噬", killer=player["qq"])
            if defender["attribute"] == "淫" and self.rng.random() < 0.75:
                self.kill(player, "被淫属性反噬")
                return f"@{name} 吞噬了{target_id}的鲲，但被淫属性反噬！双方同归于尽！"
            return (
                f"@{name} 吞噬了{target_id}的鲲！\n"
                + ("发动了致命一击！\n" if critical else "")
                + f"现体重：{format_weight(attacker['weight'])}"
            )
        attacker["weight"] += damage
        if defender["attribute"] == "淫" and self.rng.random() < 0.75:
            self.kill(player, "被淫属性反噬")
            return f"@{name} 吞噬成功但{target_id}的淫属性反噬了你！你狗带了！"
        egg_message = ""
        if attacker["attribute"] == "贪" and self.rng.random() < 0.3:
            player["eggs"] += 1
            egg_message = "\n下了一颗蛋！"
        return (
            f"@{name} 发起吞噬！\n吞噬成功！体重增加{format_weight(damage)}\n"
            f"现体重：{format_weight(attacker['weight'])}\n"
            f"对方{target_id}体重减少{format_weight(damage)}，剩余{format_weight(defender['weight'])}"
            + egg_message
        )

    def effective_devour_rate(self, attacker: JsonObject, defender: JsonObject) -> float:
        attacker_weight = attacker["kun"]["weight"]
        defender_weight = defender["kun"]["weight"]
        rate = 0.5
        if defender_weight > attacker_weight * 2:
            rate -= 0.3
        elif defender_weight > attacker_weight:
            rate -= 0.1
        elif attacker_weight > defender_weight * 2:
            rate += 0.3
        elif attacker_weight > defender_weight:
            rate += 0.1
        if defender["kun"]["attribute"] == "惰":
            rate = 0.05
        if attacker["kun"]["attribute"] == "怒":
            rate += 0.2
        if defender["kun"]["attribute"] == "妒" and defender_weight > attacker_weight:
            return 0
        return max(0, min(1, rate))

    def attack(self, player: JsonObject, target: JsonObject, name: str, target_id: str) -> str:
        attacker = player["kun"]
        defender = target["kun"]
        if defender["attribute"] == "魍":
            _reject(f"@{name} 魍免疫攻击！攻击无效！")
        if attacker["attribute"] == "馋":
            _reject("馋属性鲲无法发起攻击！")
        if attacker["weight"] < defender["weight"] * 0.3:
            _reject(f"@{name} 太小了！以大欺小，胜之不武！")
        if defender["attribute"] == "妒" and defender["weight"] > attacker["weight"]:
            _reject(f"@{name} 妒属性的鲲比你重，无法攻击！")
        critical = attacker["attribute"] == "怒" and self.rng.random() < 0.25
        damage = (
            attacker["weight"]
            * self.rng.uniform(0.1, 0.3)
            * (CRITICAL_MULTIPLIER if critical else 1)
        )
        defender["weight"] -= damage
        if defender["weight"] <= 0:
            defender["weight"] = 0
            self.kill(target, f"被{name}攻击致死", killer=player["qq"])
            return (
                f"@{name} 发起攻击！\n"
                + ("发动了致命一击！\n" if critical else "")
                + f"干死了{target_id}的鲲！"
            )
        if attacker["attribute"] == "淫" and self.rng.random() < 0.25:
            heal = attacker["weight"] * 0.5
            attacker["weight"] += heal
            return (
                f"@{name} 发起攻击！\n{target_id}体重减少{format_weight(damage)}\n"
                f"淫属性触发大恢复术！体重+{format_weight(heal)}"
            )
        egg_message = ""
        if attacker["attribute"] == "贪" and self.rng.random() < 0.3:
            player["eggs"] += 1
            egg_message = "\n下了一颗蛋！"
        return (
            f"@{name} 发起攻击！\n{target_id}体重减少{format_weight(damage)}\n"
            f"剩余体重{format_weight(defender['weight'])}" + egg_message
        )

    def assault(self, player: JsonObject, target: JsonObject, name: str, target_id: str) -> str:
        if player["divine_weapon"] <= 0:
            _reject(f"@{name} 你没有神器+夨￥宀♂牮√，无法发动强袭")
        if target["kun"]["attribute"] == "魑":
            _reject(f"@{name} 魑免疫强袭！强袭无效！")
        player["divine_weapon"] -= 1
        player["jie_cao"] = max(0, player["jie_cao"] - 2)
        if self.rng.random() >= 0.7:
            return f"@{name} 向{target_id}发动强袭，但被躲开了！\n强袭失败！节操-2"
        damage = self.rng.randint(50, 300)
        target["kun"]["weight"] -= damage
        if target["kun"]["weight"] <= 0:
            target["kun"]["weight"] = 0
            self.kill(target, f"被{name}强袭致死", killer=player["qq"])
            return f"@{name} 强袭打死了{target_id}的鲲！\n神器余量：{player['divine_weapon']}"
        return (
            f"@{name} 向{target_id}发动强袭！对方受伤：{format_weight(damage)}\n"
            f"节操-2，神器余量：{player['divine_weapon']}"
        )

    def throw_egg(self, player: JsonObject, target: JsonObject, name: str, target_id: str) -> str:
        if player["eggs"] <= 0:
            _reject(f"@{name} 你没有蛋！")
        player["eggs"] -= 1
        if self.rng.random() < 0.5:
            target["luck"] = max(0, target["luck"] - 2)
            return f"@{name} 向{target_id}扔了一颗蛋！命中！\n对方运势-2"
        return f"@{name} 向{target_id}扔了一颗蛋！\n对方闪转腾挪，躲开了！"

    def query_boss(self) -> str:
        boss = self.state.get("boss")
        if not boss:
            _reject("今日BOSS尚未刷新！请联系 SUPERUSER 刷新。")
        if not boss.get("alive", True):
            return f"今日BOSS已经被击杀！\n击杀者：{boss.get('killer', '?')}"
        lines = [
            "====今日BOSS====",
            f"名称：{boss['name']}",
            f"体重：{format_weight(boss['weight'])}",
            f"属性：{', '.join(boss['attributes'])}",
        ]
        ranking = sorted(boss["damage_rank"].items(), key=lambda row: row[1], reverse=True)
        if ranking:
            lines.append("----输出排行----")
            lines.extend(
                f"  {index}. {qq}: {format_weight(damage)}"
                for index, (qq, damage) in enumerate(ranking[:5], 1)
            )
        return "\n".join(lines)

    def generate_boss(self) -> JsonObject:
        return {
            "name": self.rng.choice(BOSS_NAMES),
            "weight": self.rng.randint(2000, 5000),
            "attributes": self.rng.choice(
                (["魅", "魍"], ["魑", "惰"], ["怒", "傲"], ["魅", "魉"], ["淫"], ["妒"])
            ),
            "alive": True,
            "killer": None,
            "damage_rank": {},
            "anti_assault": [],
            "anti_devour": [],
            "anti_attack": [],
        }

    def boss_action(self, action: str, player: JsonObject, user_id: str, name: str) -> str:
        boss = self.state.get("boss")
        if not boss:
            _reject("今日BOSS尚未刷新！请联系 SUPERUSER 刷新。")
        if not boss.get("alive", True):
            _reject(f"今日BOSS已经被击杀！击杀者：{boss.get('killer', '?')}")
        kun = self.require_live_kun(player, name)
        self.ensure_not_auction_seller(user_id, f"{action}BOSS")
        immunity = {"强袭": "魑", "吞噬": "魅", "攻击": "魍"}
        if immunity[action] in boss["attributes"]:
            _reject(f"BOSS免疫{action}！")
        assault_hit = True
        critical = False
        if action == "强袭":
            if player["divine_weapon"] <= 0:
                _reject(f"@{name} 你没有神器+夨￥宀♂牮√，无法强袭BOSS")
            player["divine_weapon"] -= 1
            player["jie_cao"] = max(0, player["jie_cao"] - 2)
            assault_hit = self.rng.random() < 0.7
            damage = float(self.rng.randint(50, 300)) if assault_hit else 0.0
        elif action == "吞噬":
            critical = kun["attribute"] == "怒" and self.rng.random() < 0.25
            multiplier = CRITICAL_MULTIPLIER if critical else self.rng.uniform(0.3, 0.6)
            damage = kun["weight"] * multiplier
        else:
            critical = kun["attribute"] == "怒" and self.rng.random() < 0.25
            damage = kun["weight"] * self.rng.uniform(0.1, 0.3)
            if critical:
                damage *= CRITICAL_MULTIPLIER
        if kun["attribute"] == "傲":
            damage *= 1.5
        boss["weight"] -= damage
        if damage > 0:
            boss["damage_rank"][user_id] = boss["damage_rank"].get(user_id, 0) + damage
        reflect = max(0, boss["weight"]) * 0.1
        reflected = min(reflect, kun["weight"] * 0.3)
        kun["weight"] -= reflected
        action_detail = f"{action}BOSS造成了{format_weight(damage)}伤害"
        if critical:
            action_detail += "（致命一击）"
        if action == "强袭":
            action_detail = (
                f"强袭BOSS造成了{format_weight(damage)}伤害" if assault_hit else "强袭BOSS未命中"
            )
            action_detail += f"，神器余量：{player['divine_weapon']}，节操：{player['jie_cao']}"
        if boss["weight"] <= 0:
            boss["weight"] = 0
            boss["alive"] = False
            boss["killer"] = user_id
            player["eggs"] += 20
            player["jie_cao"] += 100
            ranking = sorted(boss["damage_rank"].items(), key=lambda row: row[1], reverse=True)[:5]
            for ranked_user_id, _ in ranking:
                self.existing_player(ranked_user_id)["jie_cao"] += 300
            return (
                f"@{name} 成功击杀了BOSS {boss['name']}！\n"
                "获得击杀奖励：蛋*20，节操*100\n输出排行前五名每人获得300节操奖励！"
            )
        if kun["weight"] <= 0:
            kun["weight"] = 0
            self.kill(player, "讨伐BOSS阵亡", killer="BOSS")
            return f"@{name} {action_detail}，但被BOSS反击致死！"
        return (
            f"@{name} {action_detail}！\n"
            f"BOSS剩余体重：{format_weight(boss['weight'])}\n"
            f"你的鲲受到{format_weight(reflected)}反伤"
        )

    def check_kun_recovery(self, kun: JsonObject | None) -> str:
        if kun and kun.get("alive", True) and kun["attribute"] == "魉" and kun["weight"] < 666:
            kun["weight"] = 1000
            return "魉属性触发大恢复术！体重恢复至1000千克！"
        return ""

    def tribulation(self, player: JsonObject, name: str) -> str:
        kun = self.require_live_kun(player, name)
        self.ensure_not_auction_seller(player["qq"], "渡劫")
        if kun["attribute"] == "无":
            _reject(f"无属性的鲲无法渡劫！通过【{DISPLAY_PREFIX}幻化】可以获得属性")
        if player["jie_cao"] < self.config.tribulation_cost:
            _reject(f"节操不足{self.config.tribulation_cost}！当前节操：{player['jie_cao']}")
        player["jie_cao"] -= self.config.tribulation_cost
        if self.rng.random() < 0.5:
            kun["weight"] *= self.rng.uniform(1.5, 3.0)
            return (
                f"@{name} 渡劫成功！\n体重暴涨至{format_weight(kun['weight'])}\n"
                f"剩余节操：{player['jie_cao']}"
            )
        self.kill(player, "渡劫失败")
        return f"@{name} 粉身碎骨灰飞烟灭！\n渡劫失败！\n剩余节操：{player['jie_cao']}"

    def release(self, player: JsonObject, name: str) -> str:
        kun = self.require_live_kun(player, name)
        self.ensure_not_auction_seller(player["qq"], "放生")
        bonus = self.rng.randint(2, 10) if kun["attribute"] == "贪" else 0
        player["jie_cao"] += 2
        player["eggs"] += bonus
        player["kun"] = None
        extra = f"\n意外获得了{bonus}颗蛋！" if bonus else ""
        return f"@{name} 功德无量！节操+2！{extra}\n现有节操：{player['jie_cao']}"

    def resurrect(self, player: JsonObject, name: str) -> str:
        self.ensure_not_auction_seller(player["qq"], "复活")
        kun = player.get("kun")
        if not kun:
            _reject(f"@{name} 你并没有鲲！")
        if kun.get("alive", True):
            _reject(f"@{name} 你的鲲还活着！")
        if player["resurrection_pills"] <= 0:
            _reject(f"@{name} 你没有复活药！")
        if kun["attribute"] != "无":
            _reject(f"@{name} 复活失败！属性鲲无法复活。")
        player["resurrection_pills"] -= 1
        kun["alive"] = True
        kun["killer"] = None
        kun["weight"] = self.rng.randint(DEFAULT_WEIGHT_MIN, DEFAULT_WEIGHT_MAX)
        return (
            f"@{name} 已经复活！\n新体重：{format_weight(kun['weight'])}\n"
            f"剩余复活药：{player['resurrection_pills']}"
        )

    def drink_soup(self, player: JsonObject, name: str, arguments: str) -> str:
        count = _positive_int(arguments)
        if player["chicken_soup"] < count:
            _reject(f"@{name} 你没有足够的鸡汤！现有鸡汤：{player['chicken_soup']}")
        player["chicken_soup"] -= count
        player["jie_cao"] += count
        return (
            f"@{name} 喝了{count}碗鸡汤，节操+{count}\n当前节操：{player['jie_cao']}，"
            f"剩余鸡汤：{player['chicken_soup']}"
        )

    def auction_sell(self, player: JsonObject, user_id: str, name: str, arguments: str) -> str:
        if self.state.get("auction"):
            _reject("拍卖行消息：目前已经有鲲在售了！")
        kun = self.require_live_kun(player, name)
        if kun["attribute"] == "无":
            _reject("拍卖行消息：无属性的鲲无法出售！")
        if not arguments:
            _reject(f"请输入正确的起拍价！\n格式：{DISPLAY_PREFIX}出售 价格")
        price = _positive_int(arguments, maximum=PRICE_LIMIT)
        player["kun"] = None
        self.state["auction"] = {
            "seller": user_id,
            "seller_name": name,
            "kun": deepcopy(kun),
            "start_price": price,
            "current_bid": price,
            "bidder": None,
            "start_time": self.now.astimezone(UTC).isoformat(),
        }
        return (
            "拍卖行消息：\n上架成功！\n"
            f"属性：{kun['attribute']}，体重：{format_weight(kun['weight'])}\n"
            f"起拍价：{price}节操\n发送【{DISPLAY_PREFIX}出价 数值】参与竞拍"
        )

    def auction_bid(self, player: JsonObject, user_id: str, name: str, arguments: str) -> str:
        auction = self.state.get("auction")
        if not auction:
            _reject("拍卖行消息：目前没有在售的鲲！")
        if auction["seller"] == user_id:
            _reject("拍卖行消息：无法为自己的鲲出价！")
        if player.get("kun") is not None:
            _reject(f"@{name} 已经拥有鲲，不能竞拍另一只鲲。")
        bid = _positive_int(arguments, maximum=PRICE_LIMIT)
        if bid <= auction["current_bid"]:
            _reject(f"出价必须大于当前竞价：{auction['current_bid']}")
        if player["jie_cao"] < bid:
            _reject(f"节操不足！当前节操：{player['jie_cao']}")
        auction["current_bid"] = bid
        auction["bidder"] = user_id
        return f"拍卖行消息：\n出价成功！\n当前竞价：{bid}"

    def auction_deal(self, player: JsonObject, user_id: str, name: str) -> str:
        auction = self.state.get("auction")
        if not auction:
            _reject("拍卖行消息：你没有在售的鲲！")
        if auction["seller"] != user_id:
            _reject("拍卖行消息：你不是卖家！")
        bidder = auction.get("bidder")
        if not bidder:
            _reject("拍卖行消息：没有买主！")
        buyer = self.existing_player(bidder)
        if buyer.get("kun") is not None:
            _reject("拍卖行消息：买方已经拥有鲲，交易取消且资产未变化。")
        price = auction["current_bid"]
        if buyer["jie_cao"] < price:
            _reject("拍卖行消息：买主节操不足！")
        if player.get("kun") is not None:
            _reject("拍卖托管状态冲突，交易已关闭。")
        buyer["jie_cao"] -= price
        player["jie_cao"] += price
        buyer["kun"] = auction["kun"]
        self.state["auction"] = None
        return f"拍卖行消息：\n交易成功！\n{name}的鲲以{price}节操卖给了{bidder}！"

    def auction_force_delist(self) -> str:
        auction = self.state.get("auction")
        if not auction:
            _reject("拍卖行消息：没有在售的鲲！")
        started = datetime.fromisoformat(auction["start_time"])
        if (self.now.astimezone(UTC) - started.astimezone(UTC)).total_seconds() < 300:
            _reject("拍卖行消息：上架时间不足5分钟，不可强制下架！")
        self.restore_auction()
        return "拍卖行消息：已经强制下架！"

    def auction_list(self) -> str:
        auction = self.state.get("auction")
        if not auction:
            return f"拍卖行消息：目前没有鲲上架！\n发送【{DISPLAY_PREFIX}出售 起拍价】上架"
        kun = auction["kun"]
        return (
            "拍卖行消息：\n"
            f"卖家：{auction['seller_name']}\n鲲名：{kun['name']}\n"
            f"属性：{kun['attribute']}，体重：{format_weight(kun['weight'])}\n"
            f"当前竞价：{auction['current_bid']}\n出价者：{auction.get('bidder') or '无'}"
        )

    def immunity(self, player: JsonObject, name: str, command: str) -> str:
        kun = player.get("kun")
        if not kun:
            _reject(f"@{name} 你还没有鲲！")
        expected = {"魑": "免疫强袭", "魅": "免疫吞噬", "魍": "免疫攻击", "惰": "免疫强袭"}.get(
            kun["attribute"]
        )
        if expected == command:
            return f"@{name} 你的鲲({kun['attribute']})已免疫！"
        return f"@{name} 你的鲲属性不提供此免疫"

    def roll_dice(self, name: str, arguments: str) -> str:
        try:
            sides = int(arguments) if arguments else 6
        except ValueError:
            sides = 6
        sides = max(2, min(100, sides))
        return f"@{name} 掷出了 {self.rng.randint(1, sides)} 点 (D{sides})"

    def start_mini_game(self, command: str) -> str:
        if not self.state.get("game_enabled", True):
            _reject("小游戏未开启！")
        if self.state.get("mini_game"):
            _reject(f"当前已有游戏在进行中：{self.state['mini_game']['type']}")
        if command == "奥数比赛":
            first, second = self.rng.randint(1, 99), self.rng.randint(1, 99)
            operator = self.rng.choice(("+", "-", "*"))
            answer = {"+": first + second, "-": first - second, "*": first * second}[operator]
            game = self.new_mini_game("奥数比赛", 5)
            game.update(question=f"{first} {operator} {second} = ?", answer=str(answer))
            message = f"奥数比赛【总名额5】\n问：{game['question']}"
        elif command == "数星星":
            count = self.rng.randint(5, 20)
            stars = ["★"] * self.rng.randint(1, min(5, count)) + ["☆"] * count
            self.rng.shuffle(stars)
            game = self.new_mini_game("数星星", 2)
            game.update(question="".join(stars), answer=str(stars.count("★")))
            message = f"数星星【总名额2】\n问：{game['question']} 中有多少黑色星星"
        else:
            characters = "ABCDEFGHJKLMN0123456789"
            question = "".join(self.rng.choice(characters) for _ in range(self.rng.randint(4, 8)))
            game = self.new_mini_game("抄作业", 5)
            game.update(question=question, answer=question[::-1])
            message = f"抄作业【总名额5】\n原文：{question}\n答案：倒序抄写问题"
        self.state["mini_game"] = game
        return f"{message}\n回复【{DISPLAY_PREFIX}=答案】来抢答"

    def new_mini_game(self, game_type: str, slots: int) -> JsonObject:
        return {
            "type": game_type,
            "slots_used": 0,
            "max_slots": slots,
            "participants": [],
            "rewards": {},
        }

    def mini_game_answer(self, answer: str, user_id: str, name: str) -> str:
        game = self.state.get("mini_game")
        if not game or game.get("type") == "群殴群主":
            _reject("当前没有可抢答的小游戏。")
        if user_id in game["participants"]:
            _reject(f"@{name} 你已经参与过此轮游戏了！")
        if game["slots_used"] >= game["max_slots"]:
            _reject("本轮游戏名额已满！")
        game["slots_used"] += 1
        game["participants"].append(user_id)
        player = self.player(user_id)
        if answer.strip().upper() == game["answer"].strip().upper():
            reward = self.rng.randint(2, 8)
            player["jie_cao"] += reward
            self.state["mini_game"] = None
            return f"@{name} 回答正确！节操+{reward}\n当前节操：{player['jie_cao']}"
        player["jie_cao"] = max(0, player["jie_cao"] - 1)
        if game["slots_used"] >= game["max_slots"]:
            correct = game["answer"]
            self.state["mini_game"] = None
            return f"@{name} 回答错误！节操-1\n游戏结束，正确答案是：{correct}"
        return f"@{name} 回答错误！节操-1\n剩余名额：{game['max_slots'] - game['slots_used']}"

    def mini_game_slap(self, player: JsonObject, user_id: str, name: str) -> str:
        if not self.state.get("game_enabled", True):
            _reject("小游戏未开启！")
        game = self.state.get("mini_game")
        if not game:
            game = self.new_mini_game("群殴群主", 5)
            self.state["mini_game"] = game
            return f"群殴群主【总名额5】\n回复【{DISPLAY_PREFIX}抽群主一个大嘴巴】参与"
        if game.get("type") != "群殴群主":
            _reject(f"当前已有游戏在进行中：{game['type']}")
        if user_id in game["participants"]:
            player["jie_cao"] = max(0, player["jie_cao"] - 10)
            return f"@{name} 你已经抽过了！节操-10\n当前节操：{player['jie_cao']}"
        game["slots_used"] += 1
        game["participants"].append(user_id)
        reward = self.rng.randint(1, 5)
        player["jie_cao"] += reward
        remaining = game["max_slots"] - game["slots_used"]
        if remaining == 0:
            self.state["mini_game"] = None
            return f"@{name} 抽了群主一个大嘴巴！节操+{reward}\n群主已被抽肿！游戏结束！"
        return f"@{name} 抽了群主一个大嘴巴！节操+{reward}\n剩余名额：{remaining}"

    def mini_game_duel(self, player: JsonObject, user_id: str, name: str) -> str:
        if not self.state.get("game_enabled", True):
            _reject("小游戏未开启！")
        if player["jie_cao"] <= 0:
            _reject("节操至少为1才能参与游戏")
        champion = self.state.get("duel_champion")
        if champion and champion["uid"] == user_id:
            _reject(f"@{name} 你就是群主！还有谁！！！")
        if not champion:
            self.state["duel_champion"] = {"uid": user_id, "name": name, "consecutive": 0}
            return f"@{name} 开始单挑群主！\n回复【{DISPLAY_PREFIX}单挑群主】继续挑战"
        consecutive = champion["consecutive"]
        if self.rng.random() < 0.3 + consecutive * 0.05:
            reward = 5 + consecutive * 2
            player["jie_cao"] += reward
            player["luck"] = min(100, player["luck"] + 5)
            self.state["duel_champion"] = None
            return f"@{name} 打趴了群主！节操+{reward}\n单挑群主游戏结束"
        player["jie_cao"] = max(0, player["jie_cao"] - 5)
        champion["consecutive"] = consecutive + 1
        return f"@{name} 被群主打趴了！节操-5，当前节操：{player['jie_cao']}"

    def admin_edit(self, arguments: str) -> str:
        parts = arguments.split(maxsplit=2)
        if len(parts) != 3:
            _reject("格式：修改 QQ号 项目 数值")
        target_id, project, raw_value = parts
        if not target_id.isdigit():
            _reject("QQ号必须是纯数字。")
        player = self.existing_player(target_id)
        auction = self.state.get("auction")
        if auction and auction["seller"] == target_id and project in {"鲲", "体重", "属性"}:
            _reject("该玩家的鲲正在拍卖，不能修改鲲、体重或属性。")
        resource_fields = {
            "节操": "jie_cao",
            "蛋": "eggs",
            "神器": "divine_weapon",
            "幻化丹": "phantom_pills",
            "鸡汤": "chicken_soup",
            "复活药": "resurrection_pills",
            "运势": "luck",
        }
        if project == "鲲":
            if raw_value not in {"无", "删除", "remove", "null"}:
                _reject("鲲只支持设为“无”以删除。")
            player["kun"] = None
            return f"已删除玩家{target_id}的鲲"
        if project == "属性":
            kun = self.require_any_kun(player, target_id)
            if raw_value not in KUN_ATTRIBUTES:
                _reject(f"无效属性。可选：{', '.join(KUN_ATTRIBUTES)}")
            kun["attribute"] = raw_value
            return f"已将玩家{target_id}的鲲属性改为[{raw_value}]"
        if project == "体重":
            kun = self.require_any_kun(player, target_id)
            kun["weight"] = self.apply_numeric(kun["weight"], raw_value, float_value=True)
            if not math.isfinite(kun["weight"]) or not 0 < kun["weight"] <= WEIGHT_LIMIT:
                _reject("体重必须是范围内的有限正数。")
            return f"玩家{target_id}鲲体重→{format_weight(kun['weight'])}"
        key = resource_fields.get(project)
        if key is None:
            _reject("项目必须是鲲/体重/属性/节操/蛋/神器/幻化丹/鸡汤/复活药/运势。")
        value = self.apply_numeric(player[key], raw_value, float_value=False)
        maximum = 100 if key == "luck" else RESOURCE_LIMIT
        if not 0 <= value <= maximum:
            _reject(f"{project}超出允许范围。")
        player[key] = value
        return f"玩家{target_id} {project}→{value}"

    def apply_numeric(self, current: int | float, raw: str, *, float_value: bool) -> int | float:
        parser = float if float_value else int
        operator = raw[:1] if raw[:1] in "+-" else ""
        payload = raw[1:] if operator else raw
        try:
            parsed = parser(payload)
        except ValueError:
            _reject("请输入正确数值！")
        if isinstance(parsed, float) and not math.isfinite(parsed):
            _reject("数值必须是有限数。")
        if parsed < 0:
            _reject("数值本身不能为负；减少请使用前导减号。")
        if operator == "+":
            return current + parsed
        if operator == "-":
            return current - parsed
        return parsed

    def reset_round(self) -> None:
        self.restore_auction()
        self.state.update(
            boss=None,
            auction=None,
            death_list=[],
            anti_assault=[],
            anti_devour=[],
            anti_attack=[],
            mini_game=None,
            duel_champion=None,
        )

    def restore_auction(self) -> None:
        auction = self.state.get("auction")
        if not auction:
            return
        seller = self.existing_player(auction["seller"])
        if seller.get("kun") is not None:
            _reject("拍卖托管状态冲突，无法安全下架。")
        seller["kun"] = auction["kun"]
        self.state["auction"] = None

    def require_live_kun(self, player: JsonObject, name: str) -> JsonObject:
        kun = player.get("kun")
        if not kun or not kun.get("alive", True):
            _reject(f"@{name} 你还没有存活的鲲！\n发送【{DISPLAY_PREFIX}孵化】获取鲲")
        return _mapping(kun, "kun")

    def require_any_kun(self, player: JsonObject, label: str) -> JsonObject:
        kun = player.get("kun")
        if not kun:
            _reject(f"玩家{label}还没有鲲！")
        return _mapping(kun, "kun")

    def ensure_not_auction_seller(self, user_id: str, action: str) -> None:
        if self.auction_seller() == user_id:
            _reject(f"正在拍卖的鲲由系统托管，无法{action}！")

    def auction_seller(self) -> str | None:
        auction = self.state.get("auction")
        return auction["seller"] if auction else None

    def top_weight(self) -> float:
        weights = [
            player["kun"]["weight"]
            for player in self.state["players"].values()
            if player.get("kun") and player["kun"].get("alive", True)
        ]
        return max(weights, default=1000)

    def kill(self, player: JsonObject, reason: str, *, killer: str | None = None) -> None:
        kun = player["kun"]
        kun["alive"] = False
        kun["weight"] = max(0, kun["weight"])
        kun["killer"] = killer
        self.state["death_list"].append({"qq": player["qq"], "reason": reason})
        self.trim_death_list()

    def trim_death_list(self) -> None:
        entries = self.state["death_list"]
        if len(entries) > DEATH_LIST_LIMIT:
            del entries[:-DEATH_LIST_LIMIT]


def _validate_envelope(envelope: JsonObject, scope_type: ScopeType, scope_id: str) -> None:
    if envelope.get("schema_version") != SCHEMA_VERSION:
        raise StateValidationError("unsupported schema_version")
    if envelope.get("scope_type") != scope_type or envelope.get("scope_id") != scope_id:
        raise StateValidationError("persisted scope does not match requested scope")
    revision = envelope.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise StateValidationError("revision must be a non-negative integer")
    updated_at = envelope.get("updated_at")
    if not isinstance(updated_at, str):
        raise StateValidationError("updated_at must be an ISO timestamp")
    try:
        parsed_updated_at = datetime.fromisoformat(updated_at)
    except ValueError as exc:
        raise StateValidationError("updated_at must be an ISO timestamp") from exc
    if parsed_updated_at.tzinfo is None or parsed_updated_at.utcoffset() is None:
        raise StateValidationError("updated_at must include a timezone")

    state = _mapping(envelope.get("state"), "state")
    required = {
        "gid",
        "kun_enabled",
        "game_enabled",
        "players",
        "boss",
        "auction",
        "death_list",
        "last_boss_date",
        "anti_assault",
        "anti_devour",
        "anti_attack",
        "mini_game",
        "duel_champion",
    }
    if not required.issubset(state):
        raise StateValidationError("state is missing required fields")
    if state["gid"] != scope_id:
        raise StateValidationError("state gid does not match scope_id")
    if not isinstance(state["kun_enabled"], bool) or not isinstance(state["game_enabled"], bool):
        raise StateValidationError("game switches must be booleans")
    if not isinstance(state["last_boss_date"], str):
        raise StateValidationError("last_boss_date must be a string")

    players = _mapping(state["players"], "players")
    for player_id, raw_player in players.items():
        if not isinstance(player_id, str) or not player_id:
            raise StateValidationError("player keys must be non-empty strings")
        player = _mapping(raw_player, f"player {player_id}")
        if player.get("qq") != player_id:
            raise StateValidationError("player key and qq differ")
        for field in (
            "jie_cao",
            "eggs",
            "divine_weapon",
            "phantom_pills",
            "chicken_soup",
            "resurrection_pills",
            "today_train",
        ):
            _nonnegative_int(player.get(field), f"player.{field}")
        luck = _nonnegative_int(player.get("luck"), "player.luck")
        if luck > 100:
            raise StateValidationError("player luck exceeds 100")
        if not isinstance(player.get("signed_today"), bool):
            raise StateValidationError("signed_today must be boolean")
        if not isinstance(player.get("last_sign_date"), str):
            raise StateValidationError("last_sign_date must be a string")
        kun = player.get("kun")
        if kun is not None:
            _validate_kun(_mapping(kun, f"player {player_id} kun"))

    for field in ("anti_assault", "anti_devour", "anti_attack"):
        values = state[field]
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise StateValidationError(f"{field} must be a string list")

    death_list = state["death_list"]
    if not isinstance(death_list, list):
        raise StateValidationError("death_list must be a list")
    for entry in death_list:
        row = _mapping(entry, "death_list entry")
        if not isinstance(row.get("qq"), str) or not isinstance(row.get("reason"), str):
            raise StateValidationError("invalid death_list entry")

    auction = state["auction"]
    if auction is not None:
        _validate_auction(_mapping(auction, "auction"), players)
    boss = state["boss"]
    if boss is not None:
        _validate_boss(_mapping(boss, "boss"), players)
    mini_game = state["mini_game"]
    if mini_game is not None:
        _validate_mini_game(_mapping(mini_game, "mini_game"), players)
    champion = state["duel_champion"]
    if champion is not None:
        champion_row = _mapping(champion, "duel_champion")
        if champion_row.get("uid") not in players or not isinstance(champion_row.get("name"), str):
            raise StateValidationError("invalid duel champion")
        _nonnegative_int(champion_row.get("consecutive"), "duel_champion.consecutive")

    try:
        json.dumps(envelope, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise StateValidationError("state is not strict JSON") from exc


def _validate_kun(kun: JsonObject) -> None:
    if not isinstance(kun.get("name"), str) or not kun["name"]:
        raise StateValidationError("kun name must be non-empty")
    attribute = kun.get("attribute")
    if attribute not in KUN_ATTRIBUTES:
        raise StateValidationError("unknown kun attribute")
    alive = kun.get("alive")
    if not isinstance(alive, bool):
        raise StateValidationError("kun alive must be boolean")
    weight = kun.get("weight")
    if (
        isinstance(weight, bool)
        or not isinstance(weight, (int, float))
        or not math.isfinite(weight)
    ):
        raise StateValidationError("kun weight must be finite")
    if weight < 0 or weight > WEIGHT_LIMIT or (alive and weight <= 0):
        raise StateValidationError("kun weight is out of range")
    killer = kun.get("killer")
    if killer is not None and not isinstance(killer, str):
        raise StateValidationError("kun killer must be a string or null")


def _validate_auction(auction: JsonObject, players: JsonObject) -> None:
    seller = auction.get("seller")
    if not isinstance(seller, str) or seller not in players:
        raise StateValidationError("auction seller is missing")
    seller_player = _mapping(players[seller], "auction seller player")
    if seller_player.get("kun") is not None:
        raise StateValidationError("auctioned kun must be held in escrow")
    _validate_kun(_mapping(auction.get("kun"), "auction kun"))
    start_price = _positive_state_int(
        auction.get("start_price"), "auction.start_price", PRICE_LIMIT
    )
    current_bid = _positive_state_int(
        auction.get("current_bid"), "auction.current_bid", PRICE_LIMIT
    )
    if current_bid < start_price:
        raise StateValidationError("auction bid is below start price")
    bidder = auction.get("bidder")
    if bidder is not None and (
        not isinstance(bidder, str) or bidder not in players or bidder == seller
    ):
        raise StateValidationError("invalid auction bidder")
    if not isinstance(auction.get("seller_name"), str):
        raise StateValidationError("auction seller_name must be a string")
    started = auction.get("start_time")
    if not isinstance(started, str):
        raise StateValidationError("auction start_time must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(started)
    except ValueError as exc:
        raise StateValidationError("auction start_time must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise StateValidationError("auction start_time must include a timezone")


def _validate_boss(boss: JsonObject, players: JsonObject) -> None:
    if not isinstance(boss.get("name"), str) or not boss["name"]:
        raise StateValidationError("boss name must be non-empty")
    alive = boss.get("alive")
    if not isinstance(alive, bool):
        raise StateValidationError("boss alive must be boolean")
    weight = boss.get("weight")
    if (
        isinstance(weight, bool)
        or not isinstance(weight, (int, float))
        or not math.isfinite(weight)
    ):
        raise StateValidationError("boss weight must be finite")
    if weight < 0 or weight > WEIGHT_LIMIT or (alive and weight <= 0):
        raise StateValidationError("boss weight is out of range")
    attributes = boss.get("attributes")
    if not isinstance(attributes, list) or any(
        attribute not in KUN_ATTRIBUTES for attribute in attributes
    ):
        raise StateValidationError("invalid boss attributes")
    killer = boss.get("killer")
    if killer is not None and not isinstance(killer, str):
        raise StateValidationError("boss killer must be string or null")
    ranking = _mapping(boss.get("damage_rank"), "boss.damage_rank")
    for player_id, damage in ranking.items():
        if player_id not in players:
            raise StateValidationError("boss ranking references an unknown player")
        if (
            isinstance(damage, bool)
            or not isinstance(damage, (int, float))
            or not math.isfinite(damage)
            or damage < 0
        ):
            raise StateValidationError("boss damage must be finite and non-negative")
    for field in ("anti_assault", "anti_devour", "anti_attack"):
        values = boss.get(field)
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise StateValidationError(f"boss.{field} must be a string list")


def _validate_mini_game(game: JsonObject, players: JsonObject) -> None:
    if not isinstance(game.get("type"), str):
        raise StateValidationError("mini_game type must be a string")
    slots_used = _nonnegative_int(game.get("slots_used"), "mini_game.slots_used")
    max_slots = _positive_state_int(game.get("max_slots"), "mini_game.max_slots", 100)
    participants = game.get("participants")
    if not isinstance(participants, list) or any(
        not isinstance(value, str) for value in participants
    ):
        raise StateValidationError("mini_game participants must be strings")
    if len(participants) != len(set(participants)) or slots_used != len(participants):
        raise StateValidationError("mini_game participants and slots differ")
    if slots_used > max_slots or any(value not in players for value in participants):
        raise StateValidationError("invalid mini_game participant state")
    if not isinstance(game.get("rewards"), dict):
        raise StateValidationError("mini_game rewards must be an object")
    if game["type"] != "群殴群主":
        if not isinstance(game.get("question"), str) or not isinstance(game.get("answer"), str):
            raise StateValidationError("answer game requires question and answer")


def _mapping(value: object, label: str) -> JsonObject:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise StateValidationError(f"{label} must be an object with string keys")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= RESOURCE_LIMIT:
        raise StateValidationError(f"{label} must be a bounded non-negative integer")
    return value


def _positive_state_int(value: object, label: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise StateValidationError(f"{label} must be a bounded positive integer")
    return value


__all__ = [
    "ADMIN_COMMANDS",
    "PLAY_COMMANDS",
    "PRIVATE_PLAY_COMMANDS",
    "SCHEMA_VERSION",
    "GameConfig",
    "GameResult",
    "StateValidationError",
    "default_envelope",
    "default_player",
    "default_state",
    "execute_admin",
    "execute_play",
    "format_weight",
    "validate_envelope",
]

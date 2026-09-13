"""Deterministic rule and compatibility tests for the pure Kun game engine."""

from __future__ import annotations

import ast
import math
import random
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import engine
import pytest

NOW = datetime(2026, 8, 2, 4, 0, tzinfo=UTC)
SCOPE_ID = "20001"
USER_ID = "10001"
TARGET_ID = "10002"


def _player(
    player_id: str,
    *,
    attribute: str = "怒",
    kun: bool = True,
    alive: bool = True,
) -> dict[str, Any]:
    player = engine.default_player(
        player_id,
        game_date="2026-08-02",
        config=engine.GameConfig(),
    )
    player.update(
        jie_cao=1000,
        eggs=100,
        divine_weapon=10,
        phantom_pills=10,
        chicken_soup=10,
        resurrection_pills=10,
        luck=50,
    )
    if kun:
        player["kun"] = {
            "name": f"测试鲲-{player_id}",
            "weight": 1000.0,
            "attribute": attribute,
            "alive": alive,
            "killer": None if alive else "BOSS",
        }
    return player


def _envelope() -> dict[str, Any]:
    envelope = engine.default_envelope("group", SCOPE_ID, NOW)
    state = envelope["state"]
    state["last_boss_date"] = "2026-08-02"
    state["players"] = {
        USER_ID: _player(USER_ID),
        TARGET_ID: _player(TARGET_ID, attribute="无"),
        "10003": _player("10003", kun=False),
    }
    state["boss"] = {
        "name": "测试BOSS",
        "weight": 3000.0,
        "attributes": ["妒"],
        "alive": True,
        "killer": None,
        "damage_rank": {},
        "anti_assault": [],
        "anti_devour": [],
        "anti_attack": [],
    }
    engine.validate_envelope(envelope, scope_type="group", scope_id=SCOPE_ID)
    return envelope


def _auction(
    envelope: dict[str, Any],
    *,
    seller: str = TARGET_ID,
    bidder: str | None = None,
) -> None:
    state = envelope["state"]
    seller_player = state["players"][seller]
    kun = deepcopy(seller_player["kun"])
    seller_player["kun"] = None
    if bidder is not None:
        state["players"][bidder]["kun"] = None
    state["auction"] = {
        "seller": seller,
        "seller_name": seller,
        "kun": kun,
        "start_price": 10,
        "current_bid": 20 if bidder else 10,
        "bidder": bidder,
        "start_time": (NOW - timedelta(minutes=10)).isoformat(),
    }
    engine.validate_envelope(envelope, scope_type="group", scope_id=SCOPE_ID)


def _play(
    envelope: dict[str, Any] | None,
    text: str,
    *,
    user_id: str = USER_ID,
    mentions: tuple[str, ...] = (),
    seed: int = 7,
    now: datetime = NOW,
    scope_type: engine.ScopeType = "group",
    scope_id: str = SCOPE_ID,
) -> engine.GameResult:
    return engine.execute_play(
        envelope,
        text=text,
        user_id=user_id,
        display_name=f"玩家-{user_id}",
        scope_type=scope_type,
        scope_id=scope_id,
        mentioned_user_ids=mentions,
        rng=random.Random(seed),
        now=now,
    )


def _smoke_case(command: str) -> tuple[dict[str, Any], str, str, tuple[str, ...]]:
    envelope = _envelope()
    state = envelope["state"]
    player = state["players"][USER_ID]
    text = command
    user_id = USER_ID
    mentions: tuple[str, ...] = ()
    arguments = {
        "买蛋": " 2",
        "砸蛋": " 2",
        "喂食": " 2",
        "磨炼": " 10",
        "喝鸡汤": " 2",
        "出售": " 10",
        "查骰子": " 6",
    }
    text += arguments.get(command, "")
    if command == "孵化":
        player["kun"] = None
    elif command == "复活":
        player["kun"]["attribute"] = "无"
        player["kun"]["alive"] = False
        player["kun"]["weight"] = 0
    elif command in engine.PVP_COMMANDS:
        mentions = (TARGET_ID,)
    elif command == "出价":
        player["kun"] = None
        _auction(envelope)
        text += " 20"
    elif command == "成交":
        user_id = TARGET_ID
        _auction(envelope, seller=TARGET_ID, bidder=USER_ID)
    elif command.startswith("免疫"):
        player["kun"]["attribute"] = {"免疫强袭": "魑", "免疫吞噬": "魅", "免疫攻击": "魍"}[command]
    engine.validate_envelope(envelope, scope_type="group", scope_id=SCOPE_ID)
    return envelope, text, user_id, mentions


@pytest.mark.parametrize("command", engine.PLAY_COMMANDS)
def test_every_play_command_has_a_deterministic_smoke(command: str) -> None:
    envelope, text, user_id, mentions = _smoke_case(command)

    first = _play(deepcopy(envelope), text, user_id=user_id, mentions=mentions)
    second = _play(deepcopy(envelope), text, user_id=user_id, mentions=mentions)

    assert first.text
    assert first == second


@pytest.mark.parametrize("command", engine.ADMIN_COMMANDS)
def test_every_admin_command_has_a_deterministic_smoke(command: str) -> None:
    envelope = _envelope()
    text = command
    if command == "强制下架":
        _auction(envelope)
    elif command == "清除全群数据":
        text += f" {SCOPE_ID}"
    elif command == "修改":
        text += f" {TARGET_ID} 节操 +1"

    first = engine.execute_admin(
        deepcopy(envelope),
        text=text,
        user_id=USER_ID,
        display_name="管理员",
        scope_type="group",
        scope_id=SCOPE_ID,
        rng=random.Random(3),
        now=NOW,
    )
    second = engine.execute_admin(
        deepcopy(envelope),
        text=text,
        user_id=USER_ID,
        display_name="管理员",
        scope_type="group",
        scope_id=SCOPE_ID,
        rng=random.Random(3),
        now=NOW,
    )

    assert first.text
    assert first == second


def test_mini_game_answer_is_in_inventory_and_deterministic() -> None:
    started = _play(_envelope(), "数星星")
    assert started.envelope is not None
    game = started.envelope["state"]["mini_game"]
    assert game["answer"] == str(game["question"].count("★"))

    answered = _play(started.envelope, f"={game['answer']}")

    assert "回答正确" in answered.text
    assert answered.envelope is not None
    assert answered.envelope["state"]["mini_game"] is None


def test_prefixed_and_long_entry_text_produce_the_same_transition() -> None:
    envelope = _envelope()

    prefixed = _play(deepcopy(envelope), "*签到")
    long_entry = _play(deepcopy(envelope), "签到")

    assert prefixed == long_entry


@pytest.mark.parametrize(
    "text",
    [
        "买蛋 0",
        "买蛋 -1",
        "买蛋 101",
        "砸蛋 0",
        "喂食 -1",
        "磨炼 nan",
        "磨炼 inf",
        "磨炼 1000",
        "出售 nan",
        "出售 inf",
        f"攻击 {TARGET_ID}",
    ],
)
def test_invalid_input_does_not_change_old_state(text: str) -> None:
    envelope = _envelope()
    before = deepcopy(envelope)

    result = _play(envelope, text)

    assert result.changed is False
    assert result.envelope == before
    assert envelope == before


def test_repeat_sign_in_and_repeat_slap_apply_real_penalties() -> None:
    envelope = _envelope()
    first = _play(envelope, "签到")
    assert first.envelope is not None
    before_repeat = first.envelope["state"]["players"][USER_ID]["jie_cao"]

    repeated = _play(first.envelope, "签到")
    assert repeated.envelope is not None
    assert repeated.envelope["state"]["players"][USER_ID]["jie_cao"] == before_repeat - 10

    started = _play(repeated.envelope, "抽群主一个大嘴巴")
    joined = _play(started.envelope, "抽群主一个大嘴巴")
    assert joined.envelope is not None
    before_slap_repeat = joined.envelope["state"]["players"][USER_ID]["jie_cao"]
    slapped_twice = _play(joined.envelope, "抽群主一个大嘴巴")
    assert slapped_twice.envelope is not None
    assert slapped_twice.envelope["state"]["players"][USER_ID]["jie_cao"] == before_slap_repeat - 10


def test_attribute_output_has_no_duplicate_block_and_persists_recovery() -> None:
    envelope = _envelope()
    kun = envelope["state"]["players"][USER_ID]["kun"]
    kun.update(attribute="魉", weight=100.0)

    result = _play(envelope, "查阅属性")

    assert result.text.count("的鲲：") == 1
    assert result.text.count("体重：") == 1
    assert result.envelope is not None
    assert result.envelope["state"]["players"][USER_ID]["kun"]["weight"] == 1000


def test_pvp_requires_one_trusted_existing_target() -> None:
    envelope = _envelope()
    rejected = _play(envelope, f"攻击 {TARGET_ID}")
    multiple = _play(envelope, "攻击", mentions=(TARGET_ID, "10003"))
    accepted = _play(envelope, "攻击", mentions=(TARGET_ID,))

    assert rejected.changed is False
    assert multiple.changed is False
    assert accepted.changed is True


def test_boss_killer_also_receives_top_five_reward() -> None:
    envelope = _envelope()
    envelope["state"]["boss"]["weight"] = 1.0
    before = envelope["state"]["players"][USER_ID]["jie_cao"]

    result = _play(envelope, "攻击BOSS")

    assert result.envelope is not None
    player = result.envelope["state"]["players"][USER_ID]
    assert player["jie_cao"] == before + 400
    assert player["eggs"] == 120


def test_failed_training_reports_the_actual_weight_gain() -> None:
    envelope = _envelope()
    envelope["state"]["players"][USER_ID]["kun"].update(attribute="无", weight=1000.0)

    result = _play(envelope, "磨炼 100", seed=7)

    assert result.envelope is not None
    assert result.envelope["state"]["players"][USER_ID]["kun"]["weight"] == 1900.0
    assert "体重增加900千克" in result.text
    assert "现体重1.9吨" in result.text


def test_boss_actions_use_distinct_damage_and_assault_consumes_resources() -> None:
    seed = 11
    results: dict[str, engine.GameResult] = {}
    for action in ("攻击", "吞噬", "强袭"):
        envelope = _envelope()
        envelope["state"]["players"][USER_ID]["kun"]["attribute"] = "无"
        results[action] = _play(envelope, f"{action}BOSS", seed=seed)

    attack_rng = random.Random(seed)
    expected_attack = 1000.0 * attack_rng.uniform(0.1, 0.3)
    devour_rng = random.Random(seed)
    expected_devour = 1000.0 * devour_rng.uniform(0.3, 0.6)
    assault_rng = random.Random(seed)
    assert assault_rng.random() < 0.7
    expected_assault = float(assault_rng.randint(50, 300))

    expected = {
        "攻击": expected_attack,
        "吞噬": expected_devour,
        "强袭": expected_assault,
    }
    damages: dict[str, float] = {}
    for action, result in results.items():
        assert result.envelope is not None
        state = result.envelope["state"]
        damages[action] = state["boss"]["damage_rank"][USER_ID]
        assert damages[action] == pytest.approx(expected[action])

    assert len({round(value, 6) for value in damages.values()}) == 3
    assert results["攻击"].envelope["state"]["players"][USER_ID]["divine_weapon"] == 10
    assert results["吞噬"].envelope["state"]["players"][USER_ID]["divine_weapon"] == 10
    assault_player = results["强袭"].envelope["state"]["players"][USER_ID]
    assert assault_player["divine_weapon"] == 9
    assert assault_player["jie_cao"] == 998
    assert "神器余量：9" in results["强袭"].text


def test_boss_assault_without_weapon_is_rejected_without_state_change() -> None:
    envelope = _envelope()
    envelope["state"]["players"][USER_ID]["divine_weapon"] = 0
    before = deepcopy(envelope)

    result = _play(envelope, "强袭BOSS")

    assert result.changed is False
    assert result.envelope == before
    assert "没有神器" in result.text


def test_missed_boss_assault_still_consumes_weapon_without_ranking_damage() -> None:
    envelope = _envelope()
    envelope["state"]["players"][USER_ID]["kun"]["attribute"] = "无"
    boss_weight = envelope["state"]["boss"]["weight"]

    result = _play(envelope, "强袭BOSS", seed=0)

    assert result.envelope is not None
    state = result.envelope["state"]
    player = state["players"][USER_ID]
    assert player["divine_weapon"] == 9
    assert player["jie_cao"] == 998
    assert state["boss"]["weight"] == boss_weight
    assert USER_ID not in state["boss"]["damage_rank"]
    assert "强袭BOSS未命中" in result.text


def test_death_list_is_compacted_in_storage_and_stays_bounded_after_kill() -> None:
    envelope = _envelope()
    envelope["state"]["death_list"] = [
        {"qq": f"death-{index}", "reason": "测试阵亡"} for index in range(25)
    ]

    compacted = _play(envelope, "阵亡名单")

    assert compacted.envelope is not None
    entries = compacted.envelope["state"]["death_list"]
    assert len(entries) == engine.DEATH_LIST_LIMIT
    assert entries[0]["qq"] == "death-5"
    assert "death-0" not in compacted.text
    assert "death-24" in compacted.text

    compacted.envelope["state"]["players"][USER_ID]["kun"]["attribute"] = "无"
    compacted.envelope["state"]["players"][TARGET_ID]["kun"]["weight"] = 1.0
    killed = _play(compacted.envelope, "攻击", mentions=(TARGET_ID,), seed=7)

    assert killed.envelope is not None
    entries_after_kill = killed.envelope["state"]["death_list"]
    assert len(entries_after_kill) == engine.DEATH_LIST_LIMIT
    assert entries_after_kill[0]["qq"] == "death-6"
    assert entries_after_kill[-1]["qq"] == TARGET_ID


def test_auction_escrow_preserves_assets_and_refuses_buyer_with_kun() -> None:
    envelope = _envelope()
    seller_before = deepcopy(envelope["state"]["players"][USER_ID]["kun"])
    sold = _play(envelope, "出售 10")
    assert sold.envelope is not None
    assert sold.envelope["state"]["players"][USER_ID]["kun"] is None
    assert sold.envelope["state"]["auction"]["kun"] == seller_before

    bid = _play(sold.envelope, "出价 20", user_id="10003")
    assert bid.envelope is not None
    bid.envelope["state"]["players"]["10003"]["kun"] = _player("x")["kun"]
    before_deal = deepcopy(bid.envelope)
    rejected = _play(bid.envelope, "成交")

    assert rejected.changed is False
    assert rejected.envelope == before_deal


def test_auction_insufficient_balance_changes_no_asset() -> None:
    envelope = _envelope()
    _auction(envelope, bidder=USER_ID)
    envelope["state"]["players"][USER_ID]["jie_cao"] = 19
    before = deepcopy(envelope)

    rejected = _play(envelope, "成交", user_id=TARGET_ID)

    assert rejected.changed is False
    assert rejected.envelope == before


def test_successful_auction_is_atomic_and_conserves_jie_cao() -> None:
    envelope = _envelope()
    envelope["state"]["players"]["10003"]["jie_cao"] = 100
    total_before = sum(player["jie_cao"] for player in envelope["state"]["players"].values())
    sold = _play(envelope, "出售 10")
    bid = _play(sold.envelope, "出价 20", user_id="10003")
    deal = _play(bid.envelope, "成交")

    assert deal.envelope is not None
    state = deal.envelope["state"]
    assert state["auction"] is None
    assert state["players"][USER_ID]["kun"] is None
    assert state["players"]["10003"]["kun"] is not None
    assert sum(player["jie_cao"] for player in state["players"].values()) == total_before


def test_shanghai_midnight_controls_daily_reset() -> None:
    before_midnight = datetime(2026, 8, 2, 15, 59, 59, tzinfo=UTC)
    envelope = _envelope()
    envelope["state"]["last_boss_date"] = "2026-08-02"
    first = _play(envelope, "签到", now=before_midnight)
    assert first.envelope is not None

    next_day = _play(first.envelope, "签到", now=before_midnight + timedelta(seconds=1))

    assert "签到成功" in next_day.text
    assert next_day.envelope is not None
    assert next_day.envelope["state"]["players"][USER_ID]["last_sign_date"] == "2026-08-03"


def test_private_hatch_is_isolated_and_group_only_commands_fail_closed() -> None:
    private_id = USER_ID
    envelope = engine.default_envelope("private", private_id, NOW)
    envelope["state"]["last_boss_date"] = "2026-08-02"
    envelope["state"]["players"][USER_ID] = _player(USER_ID, kun=False)

    hatched = _play(
        envelope,
        "孵化",
        scope_type="private",
        scope_id=private_id,
    )
    rejected = _play(
        hatched.envelope,
        "攻击",
        mentions=(TARGET_ID,),
        scope_type="private",
        scope_id=private_id,
    )

    assert hatched.changed is True
    assert rejected.changed is False


def test_corrupt_state_fails_closed_instead_of_overwriting() -> None:
    envelope = _envelope()
    envelope["state"]["players"][USER_ID]["jie_cao"] = -1
    with pytest.raises(engine.StateValidationError):
        _play(envelope, "签到")

    envelope = _envelope()
    envelope["state"]["players"][USER_ID]["kun"]["weight"] = math.nan
    with pytest.raises(engine.StateValidationError):
        _play(envelope, "查阅属性")


@pytest.mark.parametrize("动作", ["鲲开", "数据清除", "修改"])
def test_play_never_dispatches_admin_actions(动作: str) -> None:
    envelope = _envelope()
    before = deepcopy(envelope)

    result = _play(envelope, 动作)

    assert result.changed is False
    assert result.envelope == before
    assert "SUPERUSER" in result.text


def test_unknown_command_returns_help_without_creating_state() -> None:
    result = _play(None, "这不是命令")

    assert result.changed is False
    assert result.envelope is None
    assert "命令菜单" in result.text


@pytest.mark.parametrize(("arguments", "expected"), [("1", "D2"), ("6", "D6"), ("101", "D100")])
def test_dice_boundaries(arguments: str, expected: str) -> None:
    result = _play(_envelope(), f"查骰子 {arguments}")

    assert expected in result.text


def test_round_reset_preserves_players_and_full_clear_removes_them() -> None:
    envelope = _envelope()
    _auction(envelope)
    reset = engine.execute_admin(
        envelope,
        text="重置局状态",
        user_id=USER_ID,
        display_name="管理员",
        scope_type="group",
        scope_id=SCOPE_ID,
        rng=random.Random(3),
        now=NOW,
    )

    assert reset.envelope is not None
    assert set(reset.envelope["state"]["players"]) == {USER_ID, TARGET_ID, "10003"}
    assert reset.envelope["state"]["auction"] is None
    assert reset.envelope["state"]["players"][TARGET_ID]["kun"] is not None

    cleared = engine.execute_admin(
        reset.envelope,
        text=f"清除全群数据 {SCOPE_ID}",
        user_id=USER_ID,
        display_name="管理员",
        scope_type="group",
        scope_id=SCOPE_ID,
        rng=random.Random(3),
        now=NOW,
    )

    assert cleared.envelope is not None
    assert cleared.envelope["state"]["players"] == {}


@pytest.mark.parametrize("raw", ["nan", "inf", "-inf"])
def test_admin_rejects_non_finite_weight_without_state_change(raw: str) -> None:
    envelope = _envelope()
    before = deepcopy(envelope)

    result = engine.execute_admin(
        envelope,
        text=f"修改 {USER_ID} 体重 {raw}",
        user_id=USER_ID,
        display_name="管理员",
        scope_type="group",
        scope_id=SCOPE_ID,
        rng=random.Random(3),
        now=NOW,
    )

    assert result.changed is False
    assert result.envelope == before
    assert envelope == before


def test_engine_import_boundary_has_no_host_network_or_filesystem_dependencies() -> None:
    source_path = Path(engine.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    roots = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    roots.update(
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )

    assert not roots & {
        "astrbot",
        "nonebot",
        "qq_ai_bot",
        "yuki_plugin_sdk",
        "httpx",
        "requests",
        "socket",
        "urllib",
        "pathlib",
        "os",
    }

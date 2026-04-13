import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import database as db

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SettingDefinition:
    key: str
    section: str
    attr: str
    label: str
    min_value: int
    max_value: Optional[int]
    prompt_hint: str


SETTING_DEFINITIONS: List[SettingDefinition] = [
    SettingDefinition(
        key="checkin.points",
        section="checkin",
        attr="points",
        label="签到积分",
        min_value=0,
        max_value=100000,
        prompt_hint="请输入新的签到积分，允许 0-100000",
    ),
    SettingDefinition(
        key="chat.text_min_length",
        section="chat",
        attr="text_min_length",
        label="文字最少字数",
        min_value=1,
        max_value=1000,
        prompt_hint="请输入新的文字最少字数，允许 1-1000",
    ),
    SettingDefinition(
        key="chat.text_points",
        section="chat",
        attr="text_points",
        label="文字积分",
        min_value=0,
        max_value=100000,
        prompt_hint="请输入新的文字积分，允许 0-100000",
    ),
    SettingDefinition(
        key="chat.sticker_points",
        section="chat",
        attr="sticker_points",
        label="贴纸积分",
        min_value=0,
        max_value=100000,
        prompt_hint="请输入新的贴纸积分，允许 0-100000",
    ),
    SettingDefinition(
        key="chat.photo_points",
        section="chat",
        attr="photo_points",
        label="图片积分",
        min_value=0,
        max_value=100000,
        prompt_hint="请输入新的图片积分，允许 0-100000",
    ),
    SettingDefinition(
        key="chat.video_points",
        section="chat",
        attr="video_points",
        label="视频积分",
        min_value=0,
        max_value=100000,
        prompt_hint="请输入新的视频积分，允许 0-100000",
    ),
    SettingDefinition(
        key="chat.daily_limit",
        section="chat",
        attr="daily_limit",
        label="每日聊天积分上限",
        min_value=0,
        max_value=100000,
        prompt_hint="请输入新的每日聊天积分上限，允许 0-100000",
    ),
    SettingDefinition(
        key="chat.cooldown_seconds",
        section="chat",
        attr="cooldown_seconds",
        label="聊天积分冷却秒数",
        min_value=0,
        max_value=86400,
        prompt_hint="请输入新的聊天积分冷却秒数，允许 0-86400",
    ),
    SettingDefinition(
        key="rank.top_n",
        section="rank",
        attr="top_n",
        label="排行榜显示人数",
        min_value=1,
        max_value=100,
        prompt_hint="请输入新的排行榜显示人数，允许 1-100",
    ),
    SettingDefinition(
        key="lottery.default_min_participants",
        section="lottery",
        attr="default_min_participants",
        label="抽奖默认最少人数",
        min_value=1,
        max_value=100000,
        prompt_hint="请输入新的抽奖默认最少人数，允许 1-100000",
    ),
]

SETTINGS_BY_KEY: Dict[str, SettingDefinition] = {
    definition.key: definition for definition in SETTING_DEFINITIONS
}

SETTINGS_BUTTON_ROWS: List[List[str]] = [
    ["checkin.points", "chat.text_min_length"],
    ["chat.text_points", "chat.sticker_points"],
    ["chat.photo_points", "chat.video_points"],
    ["chat.daily_limit", "chat.cooldown_seconds"],
    ["rank.top_n", "lottery.default_min_participants"],
]


def get_setting_definition(key: str) -> SettingDefinition:
    definition = SETTINGS_BY_KEY.get(key)
    if definition is None:
        raise KeyError(f"未知配置项: {key}")
    return definition


def get_runtime_setting_value(config, key: str) -> int:
    definition = get_setting_definition(key)
    return int(getattr(getattr(config, definition.section), definition.attr))


def _parse_setting_value(definition: SettingDefinition, raw_value: Any) -> int:
    if isinstance(raw_value, bool):
        raise ValueError(f"{definition.label} 必须是整数")

    try:
        value = int(str(raw_value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{definition.label} 必须是整数") from exc

    if value < definition.min_value:
        raise ValueError(f"{definition.label} 不能小于 {definition.min_value}")
    if definition.max_value is not None and value > definition.max_value:
        raise ValueError(f"{definition.label} 不能大于 {definition.max_value}")
    return value


def _set_config_value(config, definition: SettingDefinition, value: int) -> int:
    setattr(getattr(config, definition.section), definition.attr, value)
    return value


def apply_runtime_settings(config) -> None:
    for definition in SETTING_DEFINITIONS:
        stored_value = db.get_config_value(definition.key)
        if stored_value is None:
            continue
        try:
            value = _parse_setting_value(definition, stored_value)
        except ValueError as exc:
            logger.warning("忽略无效运行时配置 %s=%r: %s", definition.key, stored_value, exc)
            continue
        _set_config_value(config, definition, value)


def update_runtime_setting(config, key: str, raw_value: Any) -> int:
    definition = get_setting_definition(key)
    value = _parse_setting_value(definition, raw_value)
    _set_config_value(config, definition, value)
    db.set_config_value(definition.key, value)
    return value

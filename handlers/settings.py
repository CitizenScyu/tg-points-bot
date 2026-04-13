from dataclasses import dataclass
from typing import Dict, Optional

from aiogram import F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from runtime_settings import (
    SETTINGS_BUTTON_ROWS,
    get_runtime_setting_value,
    get_setting_definition,
    update_runtime_setting,
)
from .common import get_bound_group_id, is_bot_admin, is_bound_group_admin

SETTINGS_CALLBACK_PREFIX = "settings:"
SETTINGS_CANCEL_WORDS = {"取消", "cancel", "Cancel", "CANCEL"}


@dataclass
class PendingSettingUpdate:
    key: str


PENDING_SETTING_UPDATES: Dict[int, PendingSettingUpdate] = {}


def _build_settings_markup(config) -> InlineKeyboardMarkup:
    rows = []
    for key_row in SETTINGS_BUTTON_ROWS:
        button_row = []
        for key in key_row:
            definition = get_setting_definition(key)
            current_value = get_runtime_setting_value(config, key)
            button_row.append(
                InlineKeyboardButton(
                    text=f"{definition.label}：{current_value}",
                    callback_data=f"{SETTINGS_CALLBACK_PREFIX}edit:{key}",
                )
            )
        rows.append(button_row)
    rows.append(
        [
            InlineKeyboardButton(text="刷新", callback_data=f"{SETTINGS_CALLBACK_PREFIX}refresh"),
            InlineKeyboardButton(text="取消输入", callback_data=f"{SETTINGS_CALLBACK_PREFIX}cancel"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_settings_text(config, user_id: Optional[int] = None) -> str:
    bound_group_id = get_bound_group_id(config)
    pending_update = PENDING_SETTING_UPDATES.get(user_id) if user_id is not None else None

    lines = [
        "管理员配置面板",
        "",
        f"当前绑定群组：{bound_group_id if bound_group_id is not None else '未绑定'}",
        "修改结果会写入数据库配置覆盖层，重启后仍生效，不会改写 config.yaml。",
        "",
        "签到：",
        f"- 签到积分：{config.checkin.points}",
        "",
        "聊天积分：",
        f"- 文字最少字数：{config.chat.text_min_length}",
        f"- 文字积分：{config.chat.text_points}",
        f"- 贴纸积分：{config.chat.sticker_points}",
        f"- 图片积分：{config.chat.photo_points}",
        f"- 每日聊天积分上限：{config.chat.daily_limit}",
        f"- 聊天积分冷却秒数：{config.chat.cooldown_seconds}",
        "",
        "排行榜：",
        f"- 显示人数：{config.rank.top_n}",
        "",
        "抽奖：",
        f"- 默认最少人数：{config.lottery.default_min_participants}",
        "",
        "点击下方按钮选择要修改的项目。",
        "发送“取消”可以退出当前输入。",
    ]
    if pending_update is not None:
        lines.extend(
            [
                "",
                f"当前等待输入：{get_setting_definition(pending_update.key).label}",
            ]
        )
    return "\n".join(lines)


async def _has_settings_access(bot, config, user_id: int) -> bool:
    return is_bot_admin(config, user_id) or await is_bound_group_admin(bot, config, user_id)


async def _send_settings_panel(target_message: Message, config) -> None:
    await target_message.reply(
        _build_settings_text(config, target_message.from_user.id),
        reply_markup=_build_settings_markup(config),
    )


async def _refresh_settings_panel(message: Message, config, user_id: int) -> None:
    try:
        await message.edit_text(
            _build_settings_text(config, user_id),
            reply_markup=_build_settings_markup(config),
        )
    except Exception:
        pass


def register_settings_handlers(dp, config):
    @dp.message(Command("settings", "设置"), F.chat.type == "private")
    async def cmd_settings(message: Message):
        if not await _has_settings_access(message.bot, config, message.from_user.id):
            await message.reply("只有 Bot Admin 或已绑定群管理员可以在私聊中修改配置")
            return

        PENDING_SETTING_UPDATES.pop(message.from_user.id, None)
        await _send_settings_panel(message, config)

    @dp.callback_query(F.data.startswith(SETTINGS_CALLBACK_PREFIX))
    async def callback_settings(callback: CallbackQuery):
        if callback.message is None or callback.message.chat.type != "private":
            await callback.answer("请在私聊中使用设置面板", show_alert=True)
            return

        user_id = callback.from_user.id
        if not await _has_settings_access(callback.message.bot, config, user_id):
            await callback.answer("无权修改机器人配置", show_alert=True)
            return

        parts = (callback.data or "").split(":", maxsplit=2)
        if len(parts) < 2:
            await callback.answer("设置指令无效", show_alert=True)
            return

        action = parts[1]
        if action == "refresh":
            await _refresh_settings_panel(callback.message, config, user_id)
            await callback.answer("已刷新")
            return

        if action == "cancel":
            if PENDING_SETTING_UPDATES.pop(user_id, None) is None:
                await callback.answer("当前没有待输入的配置项")
                return
            await _refresh_settings_panel(callback.message, config, user_id)
            await callback.answer("已取消当前输入")
            return

        if action != "edit" or len(parts) < 3:
            await callback.answer("设置指令无效", show_alert=True)
            return

        key = parts[2]
        try:
            definition = get_setting_definition(key)
        except KeyError:
            await callback.answer("未知配置项", show_alert=True)
            return

        PENDING_SETTING_UPDATES[user_id] = PendingSettingUpdate(key=key)
        await _refresh_settings_panel(callback.message, config, user_id)
        await callback.answer("请发送新的数值")
        await callback.message.answer(
            f"正在修改：{definition.label}\n"
            f"{definition.prompt_hint}\n"
            "发送“取消”退出本次输入。"
        )

    @dp.message(F.chat.type == "private", F.text)
    async def handle_private_setting_input(message: Message):
        pending_update = PENDING_SETTING_UPDATES.get(message.from_user.id)
        if pending_update is None or not message.text:
            return
        if message.text.startswith("/"):
            return

        if not await _has_settings_access(message.bot, config, message.from_user.id):
            PENDING_SETTING_UPDATES.pop(message.from_user.id, None)
            await message.reply("你当前无权继续修改配置")
            return

        if message.text.strip() in SETTINGS_CANCEL_WORDS:
            PENDING_SETTING_UPDATES.pop(message.from_user.id, None)
            await message.reply("已取消当前输入")
            await _send_settings_panel(message, config)
            return

        definition = get_setting_definition(pending_update.key)
        try:
            new_value = update_runtime_setting(config, pending_update.key, message.text)
        except ValueError as exc:
            await message.reply(f"{exc}\n{definition.prompt_hint}\n发送“取消”退出本次输入。")
            return

        PENDING_SETTING_UPDATES.pop(message.from_user.id, None)
        await message.reply(f"已更新 {definition.label}：{new_value}")
        await _send_settings_panel(message, config)

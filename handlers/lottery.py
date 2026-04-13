import logging
from datetime import datetime
from html import escape
from typing import Dict, Optional

from aiogram import Bot, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import database as db
from .common import ensure_points_group, has_group_management_rights, is_bot_admin
from .utils import schedule_auto_delete

logger = logging.getLogger(__name__)

JOIN_CALLBACK_PREFIX = "lottery_join:"
TIME_INPUT_FORMATS = (
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%dT%H:%M:%S",
)


def _build_join_markup(lottery_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="参与抽奖", callback_data=f"{JOIN_CALLBACK_PREFIX}{lottery_id}")]
        ]
    )


def _build_lottery_list_markup(lotteries: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for lottery in lotteries:
        button_text = f"参与 #{lottery['lottery_id']} {lottery['title'][:18]}"
        rows.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"{JOIN_CALLBACK_PREFIX}{lottery['lottery_id']}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _parse_datetime_input(raw_value: str) -> datetime:
    value = raw_value.strip()
    for fmt in TIME_INPUT_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError("时间格式错误，请使用 YYYY-MM-DD HH:MM")


def _parse_draw_rule(
    draw_spec: str,
    extra_spec: Optional[str],
    config,
) -> tuple[str, int, Optional[str]]:
    default_min_participants = config.lottery.default_min_participants
    raw_spec = (draw_spec or "").strip()
    extra_value = (extra_spec or "").strip() or None

    if not raw_spec:
        min_participants = int(extra_value) if extra_value else default_min_participants
        return "manual", min_participants, None

    if raw_spec.isdigit():
        if extra_value is not None:
            raise ValueError("旧格式下不需要再额外填写人数")
        return "manual", int(raw_spec), None

    normalized = raw_spec.replace("：", ":")
    mode, _, payload = normalized.partition(":")
    mode = mode.strip()
    payload = payload.strip()

    if mode == "手动":
        min_participants = int(extra_value) if extra_value else int(payload) if payload else default_min_participants
        return "manual", min_participants, None

    if mode == "人数":
        if not payload:
            raise ValueError("按人数开奖请使用 人数:目标人数")
        if extra_value is not None:
            raise ValueError("按人数开奖不需要再额外填写最少人数")
        return "participant_count", int(payload), None

    if mode == "时间":
        if not payload:
            raise ValueError("按时间开奖请使用 时间:YYYY-MM-DD HH:MM")
        draw_time = _parse_datetime_input(payload)
        if draw_time <= datetime.now():
            raise ValueError("开奖时间必须晚于当前时间")
        min_participants = int(extra_value) if extra_value else default_min_participants
        return "time", min_participants, draw_time.isoformat(timespec="seconds")

    raise ValueError("开奖条件格式错误，请使用 手动、人数:10 或 时间:2026-04-13 20:00")


def _format_draw_rule(lottery: dict) -> str:
    draw_mode = lottery.get("draw_mode") or "manual"
    if draw_mode == "participant_count":
        return f"开奖条件：满 {lottery['min_participants']} 人自动开奖"
    if draw_mode == "time":
        end_time = lottery.get("end_time")
        end_display = datetime.fromisoformat(end_time).strftime("%Y-%m-%d %H:%M") if end_time else "未设置"
        if lottery['min_participants'] > 1:
            return f"开奖条件：{end_display} 自动开奖，少于 {lottery['min_participants']} 人则取消并退款"
        return f"开奖条件：{end_display} 自动开奖"
    return f"开奖条件：手动开奖（至少 {lottery['min_participants']} 人）"


def _winner_display_name(lottery: dict, winner_id: Optional[int]) -> str:
    if winner_id is None:
        return ""
    winner = db.get_user(winner_id, lottery['group_id'])
    if not winner:
        return f"用户{winner_id}"
    return winner.get('username') or f"用户{winner_id}"


def _build_active_lottery_announcement_text(lottery: dict, participant_count: int) -> str:
    return (
        f"抽奖进行中\n"
        f"ID: #{lottery['lottery_id']}\n"
        f"标题: {escape(lottery['title'])}\n"
        f"奖品: {escape(lottery['prize'])}\n"
        f"参与费: {lottery['cost']} 积分\n"
        f"{_format_draw_rule(lottery)}\n"
        f"当前参与人数: {participant_count}\n"
        f"点击下方按钮或发送 参与 {lottery['lottery_id']} 参与抽奖"
    )


def _build_closed_lottery_announcement_text(
    lottery: dict,
    participant_count: int,
    *,
    reason: Optional[str] = None,
    winner_id: Optional[int] = None,
) -> str:
    if lottery['status'] == 'finished' and winner_id is not None:
        winner_name = escape(_winner_display_name(lottery, winner_id))
        reason_text = (
            "满人数自动开奖"
            if reason == "participant_count"
            else "到期自动开奖"
            if reason == "time_reached"
            else "管理员手动开奖"
        )
        return (
            f"抽奖已开奖\n"
            f"ID: #{lottery['lottery_id']}\n"
            f"标题: {escape(lottery['title'])}\n"
            f"奖品: {escape(lottery['prize'])}\n"
            f"开奖方式: {reason_text}\n"
            f"参与人数: {participant_count}\n"
            f"中奖者: {winner_name}"
        )

    if reason == "insufficient_participants":
        status_text = f"到期取消，人数不足（{participant_count}/{lottery['min_participants']}）"
    elif reason == "no_participants":
        status_text = "到期取消，无人参与"
    else:
        status_text = "抽奖已取消"
    return (
        f"抽奖已取消\n"
        f"ID: #{lottery['lottery_id']}\n"
        f"标题: {escape(lottery['title'])}\n"
        f"奖品: {escape(lottery['prize'])}\n"
        f"状态: {status_text}"
    )


async def _pin_message_if_possible(bot: Bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.pin_chat_message(chat_id, message_id, disable_notification=True)
    except Exception:
        logger.warning("置顶开奖消息失败: chat_id=%s message_id=%s", chat_id, message_id, exc_info=True)


async def _edit_lottery_announcement_message(
    bot: Bot,
    lottery: dict,
    *,
    participant_count: int,
    reason: Optional[str] = None,
    winner_id: Optional[int] = None,
) -> None:
    chat_id = lottery.get("announcement_chat_id")
    message_id = lottery.get("announcement_message_id")
    if not chat_id or not message_id:
        return

    if lottery['status'] == 'active':
        text = _build_active_lottery_announcement_text(lottery, participant_count)
        reply_markup = _build_join_markup(lottery['lottery_id'])
    else:
        text = _build_closed_lottery_announcement_text(
            lottery,
            participant_count,
            reason=reason,
            winner_id=winner_id,
        )
        reply_markup = None

    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
        )
    except Exception:
        logger.warning(
            "更新抽奖消息失败: lottery_id=%s chat_id=%s message_id=%s",
            lottery['lottery_id'],
            chat_id,
            message_id,
            exc_info=True,
        )


async def _announce_lottery_result(
    bot: Bot,
    lottery: dict,
    *,
    winner_id: Optional[int],
    reason: str,
    participant_count: int,
) -> None:
    if winner_id is not None:
        winner_name = escape(_winner_display_name(lottery, winner_id))

        if reason == "participant_count":
            trigger_text = f"已满 {lottery['min_participants']} 人，自动开奖"
        elif reason == "time_reached":
            end_display = datetime.fromisoformat(lottery['end_time']).strftime("%Y-%m-%d %H:%M")
            trigger_text = f"到达开奖时间 {end_display}，自动开奖"
        else:
            trigger_text = "管理员手动开奖"

        text = (
            f"抽奖开奖\n"
            f"标题：{escape(lottery['title'])}\n"
            f"奖品：{escape(lottery['prize'])}\n"
            f"{trigger_text}\n"
            f"参与人数：{participant_count}\n"
            f"恭喜 {winner_name} 获得奖品"
        )
        result_message = await bot.send_message(lottery['group_id'], text)
        await _pin_message_if_possible(bot, lottery['group_id'], result_message.message_id)
        return

    if reason == "insufficient_participants":
        text = (
            f"抽奖结束\n"
            f"标题：{escape(lottery['title'])}\n"
            f"到达开奖时间，但参与人数不足（{participant_count}/{lottery['min_participants']}）\n"
            f"本次抽奖已取消，积分已退还"
        )
    else:
        text = (
            f"抽奖结束\n"
            f"标题：{escape(lottery['title'])}\n"
            f"到达开奖时间，无人参与，本次抽奖已取消"
        )
    await bot.send_message(lottery['group_id'], text)


async def _handle_lottery_join(
    *,
    bot: Bot,
    group_id: int,
    lottery_id: int,
    user_id: int,
    username: Optional[str],
) -> Dict[str, object]:
    db.get_or_create_user(user_id, group_id, username)
    result = db.join_lottery_with_result(lottery_id, group_id, user_id)

    if result.get("success") and result.get("lottery"):
        participant_count = int(result.get("participant_count", 0))
        await _edit_lottery_announcement_message(
            bot,
            result["lottery"],
            participant_count=participant_count,
            reason="participant_count" if result.get("auto_finished") else None,
            winner_id=result.get("winner_id"),
        )

        if result.get("auto_finished"):
            await _announce_lottery_result(
                bot,
                result["lottery"],
                winner_id=result.get("winner_id"),
                reason="participant_count",
                participant_count=participant_count,
            )

    return result


async def process_due_time_lotteries(bot: Bot) -> None:
    for lottery in db.get_due_time_lotteries():
        try:
            result = db.settle_due_time_lottery(lottery['lottery_id'], lottery['group_id'])
            if result.get("status") not in {"finished", "cancelled"}:
                continue
            await _edit_lottery_announcement_message(
                bot,
                result["lottery"],
                participant_count=int(result.get("participant_count", 0)),
                reason=result.get("reason"),
                winner_id=result.get("winner_id"),
            )
            await _announce_lottery_result(
                bot,
                result["lottery"],
                winner_id=result.get("winner_id"),
                reason=result.get("reason", "time_reached"),
                participant_count=int(result.get("participant_count", 0)),
            )
        except Exception:
            logger.exception("处理到期抽奖失败: lottery_id=%s", lottery['lottery_id'])


def register_lottery_handlers(dp, config):
    async def handle_lottery_list(message: Message):
        group_id = await ensure_points_group(message, config)
        if group_id is None:
            return

        lotteries = db.get_active_lotteries(group_id)
        if not lotteries:
            reply_msg = await message.reply("当前没有进行中的抽奖")
            schedule_auto_delete(message, reply_msg, delay=30)
            return

        text_lines = ["当前进行中的抽奖：", ""]
        for lottery in lotteries:
            participant_count = db.get_lottery_participant_count(lottery['lottery_id'])
            text_lines.append(f"#{lottery['lottery_id']} {escape(lottery['title'])}")
            text_lines.append(f"奖品：{escape(lottery['prize'])}")
            text_lines.append(f"参与费：{lottery['cost']} 积分")
            text_lines.append(_format_draw_rule(lottery))
            text_lines.append(f"当前参与人数：{participant_count}")
            text_lines.append("")

        text_lines.append("发送 参与 <抽奖ID> 参与抽奖")
        reply_msg = await message.reply(
            "\n".join(text_lines),
            reply_markup=_build_lottery_list_markup(lotteries),
        )
        schedule_auto_delete(message, reply_msg, delay=30)

    @dp.message(F.text == "抽奖")
    async def cmd_lottery_list_text(message: Message):
        await handle_lottery_list(message)

    @dp.message(Command("lotteries"))
    async def cmd_lottery_list_slash(message: Message):
        await handle_lottery_list(message)

    @dp.message(F.text.regexp(r"^参与\s+\d+$"))
    async def cmd_join_lottery(message: Message):
        group_id = await ensure_points_group(message, config)
        if group_id is None:
            return

        args = message.text.split()
        try:
            lottery_id = int(args[1])
        except (ValueError, IndexError):
            reply_msg = await message.reply("格式: 参与 <抽奖ID>")
            schedule_auto_delete(message, reply_msg, delay=30)
            return

        result = await _handle_lottery_join(
            bot=message.bot,
            group_id=group_id,
            lottery_id=lottery_id,
            user_id=message.from_user.id,
            username=message.from_user.username or message.from_user.full_name,
        )

        if result.get("success"):
            participant_count = int(result.get("participant_count", 0))
            if result.get("auto_finished"):
                reply_msg = await message.reply("参与成功！已满足开奖条件，正在自动开奖")
            else:
                reply_msg = await message.reply(
                    f"参与成功！已扣除 {result['lottery']['cost']} 积分\n"
                    f"当前参与人数：{participant_count}"
                )
        else:
            reply_msg = await message.reply(str(result.get("message")))
        schedule_auto_delete(message, reply_msg, delay=30)

    @dp.callback_query(F.data.startswith(JOIN_CALLBACK_PREFIX))
    async def callback_join_lottery(callback: CallbackQuery):
        if callback.message is None:
            await callback.answer("无法识别抽奖消息", show_alert=True)
            return

        group_id = await ensure_points_group(
            callback.message,
            config,
            reply_on_private=False,
            reply_on_mismatch=False,
            reply_on_unbound=False,
        )
        if group_id is None:
            await callback.answer("当前群组不可使用该抽奖按钮", show_alert=True)
            return

        try:
            lottery_id = int(callback.data.split(":", maxsplit=1)[1])
        except (IndexError, ValueError):
            await callback.answer("抽奖按钮数据无效", show_alert=True)
            return

        result = await _handle_lottery_join(
            bot=callback.bot,
            group_id=group_id,
            lottery_id=lottery_id,
            user_id=callback.from_user.id,
            username=callback.from_user.username or callback.from_user.full_name,
        )

        if not result.get("success"):
            await callback.answer(str(result.get("message")), show_alert=True)
            return

        participant_count = int(result.get("participant_count", 0))
        if result.get("auto_finished"):
            await callback.answer("参与成功，已满足开奖条件", show_alert=False)
        else:
            await callback.answer(f"参与成功，当前参与人数：{participant_count}", show_alert=False)

    @dp.message(Command("lottery", "抽奖"))
    async def cmd_new_lottery(message: Message):
        group_id = await ensure_points_group(message, config)
        if group_id is None:
            return

        if not await has_group_management_rights(message, config):
            await message.reply("只有管理员才能创建抽奖")
            return

        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply(
                "格式:\n"
                "/抽奖 标题|奖品|积分|最少人数\n"
                "/抽奖 标题|奖品|积分|手动[:最少人数]\n"
                "/抽奖 标题|奖品|积分|人数:目标人数\n"
                "/抽奖 标题|奖品|积分|时间:2026-04-13 20:00|最少人数"
            )
            return

        try:
            parts = [part.strip() for part in args[1].split('|')]
            if len(parts) < 3:
                raise ValueError("格式错误，请使用 标题|奖品|积分|开奖条件")

            title = parts[0]
            prize = parts[1]
            cost = int(parts[2])
            draw_spec = parts[3] if len(parts) > 3 else ""
            extra_spec = parts[4] if len(parts) > 4 else None
            draw_mode, min_participants, end_time = _parse_draw_rule(draw_spec, extra_spec, config)

            if not title:
                raise ValueError("标题不能为空")
            if not prize:
                raise ValueError("奖品不能为空")

            lottery_id = db.create_lottery(
                group_id=group_id,
                title=title,
                prize=prize,
                cost=cost,
                creator_id=message.from_user.id,
                min_participants=min_participants,
                end_time=end_time,
                draw_mode=draw_mode,
            )
            lottery = db.get_lottery(lottery_id, group_id)

            announcement_message = await message.reply(
                _build_active_lottery_announcement_text(lottery, participant_count=0),
                reply_markup=_build_join_markup(lottery_id),
            )
            db.set_lottery_announcement_message(
                lottery_id,
                group_id,
                announcement_message.chat.id,
                announcement_message.message_id,
            )
        except Exception as exc:
            await message.reply(f"创建失败：{exc}")

    @dp.message(Command("draw", "开奖"))
    async def cmd_draw(message: Message):
        group_id = await ensure_points_group(message, config)
        if group_id is None:
            return

        args = message.text.split()
        if len(args) < 2:
            await message.reply("格式: /开奖 <抽奖ID>")
            return

        try:
            lottery_id = int(args[1])
        except ValueError:
            await message.reply("请输入有效的抽奖ID")
            return

        user_id = message.from_user.id
        lottery = db.get_lottery(lottery_id, group_id)

        if not lottery:
            await message.reply("当前群组中不存在该抽奖")
            return
        if lottery['draw_mode'] != 'manual':
            await message.reply("该抽奖不是手动开奖模式，会按设定条件自动开奖")
            return

        is_admin = is_bot_admin(config, user_id)
        is_creator = lottery['creator_id'] == user_id
        if not (is_admin or is_creator or await has_group_management_rights(message, config)):
            await message.reply("只有管理员或抽奖创建者才能开奖")
            return

        participant_count = db.get_lottery_participant_count(lottery_id)
        if participant_count < lottery['min_participants']:
            await message.reply(f"参与人数不足，需要至少 {lottery['min_participants']} 人")
            return

        winner_id = db.finish_lottery(lottery_id, group_id)
        if winner_id:
            updated_lottery = db.get_lottery(lottery_id, group_id)
            await _edit_lottery_announcement_message(
                message.bot,
                updated_lottery,
                participant_count=participant_count,
                reason="manual",
                winner_id=winner_id,
            )
            await _announce_lottery_result(
                message.bot,
                updated_lottery,
                winner_id=winner_id,
                reason="manual",
                participant_count=participant_count,
            )
        else:
            await message.reply("抽奖已取消（无人参与）")

    @dp.message(Command("cancel_lottery", "取消抽奖"))
    async def cmd_cancel_lottery(message: Message):
        group_id = await ensure_points_group(message, config)
        if group_id is None:
            return

        args = message.text.split()
        if len(args) < 2:
            await message.reply("格式: /取消抽奖 <抽奖ID>")
            return

        try:
            lottery_id = int(args[1])
        except ValueError:
            await message.reply("请输入有效的抽奖ID")
            return

        user_id = message.from_user.id
        lottery = db.get_lottery(lottery_id, group_id)

        if not lottery:
            await message.reply("当前群组中不存在该抽奖")
            return

        is_admin = is_bot_admin(config, user_id)
        is_creator = lottery['creator_id'] == user_id
        if not (is_admin or is_creator or await has_group_management_rights(message, config)):
            await message.reply("只有管理员或抽奖创建者才能取消抽奖")
            return

        participant_count = db.get_lottery_participant_count(lottery_id)
        if db.cancel_lottery(lottery_id, group_id):
            updated_lottery = db.get_lottery(lottery_id, group_id)
            await _edit_lottery_announcement_message(
                message.bot,
                updated_lottery,
                participant_count=participant_count,
                reason="cancelled",
            )
            await message.reply("抽奖已取消，积分已退还给参与者")
        else:
            await message.reply("取消失败")

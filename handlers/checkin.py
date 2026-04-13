from aiogram import F
from aiogram.filters import Command
from aiogram.types import Message
from datetime import date
import database as db
import logging
from .common import ensure_points_group
from .utils import schedule_auto_delete

logger = logging.getLogger(__name__)

def register_checkin_handlers(dp, config):
    async def handle_checkin(message: Message):
        logger.info(f"签到触发: user={message.from_user.id}, text={message.text}")
        group_id = await ensure_points_group(message, config)
        if group_id is None:
            return

        user_id = message.from_user.id
        username = message.from_user.username or message.from_user.full_name

        db.get_or_create_user(user_id, group_id, username)

        if db.do_checkin(user_id, group_id, config.checkin.points):
            points = db.get_user_points(user_id, group_id)
            reply_msg = await message.reply(
                f"签到成功！获得 {config.checkin.points} 积分\n"
                f"当前积分：{points}"
            )
        else:
            reply_msg = await message.reply("今天已经签到过了，明天再来吧~")

        schedule_auto_delete(message, reply_msg, delay=30)

    @dp.message(F.text == "签到")
    async def cmd_checkin_text(message: Message):
        await handle_checkin(message)

    @dp.message(Command("checkin"))
    async def cmd_checkin_slash(message: Message):
        await handle_checkin(message)

    async def handle_my_checkin(message: Message):
        group_id = await ensure_points_group(message, config)
        if group_id is None:
            return

        user_id = message.from_user.id
        username = message.from_user.username or message.from_user.full_name

        user = db.get_or_create_user(user_id, group_id, username)

        if user['last_checkin']:
            last = user['last_checkin']
            today = date.today().isoformat()
            if last == today:
                status = "今日已签到"
            else:
                status = f"上次签到：{last}"
        else:
            status = "从未签到"

        reply_msg = await message.reply(
            f"积分：{user['points']}\n{status}"
        )

        schedule_auto_delete(message, reply_msg, delay=30)

    @dp.message(F.text == "我的签到")
    async def cmd_my_checkin_text(message: Message):
        await handle_my_checkin(message)

    @dp.message(Command("my_checkin"))
    async def cmd_my_checkin_slash(message: Message):
        await handle_my_checkin(message)

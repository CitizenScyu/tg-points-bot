from aiogram import F
from aiogram.types import Message
from datetime import date
import database as db
import logging
import asyncio
from .common import ensure_points_group

logger = logging.getLogger(__name__)

async def auto_delete(message: Message, reply_msg: Message, delay: int = 30):
    """自动删除触发消息和机器人回复"""
    await asyncio.sleep(delay)
    try:
        await message.delete()
        await reply_msg.delete()
    except:
        pass  # 忽略删除失败（权限不足或消息已删除）

def register_checkin_handlers(dp, config):
    # 签到 - 直接汉字触发
    @dp.message(F.text == "签到")
    async def cmd_checkin(message: Message):
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

        # 30秒后自动删除用户消息和机器人回复
        asyncio.create_task(auto_delete(message, reply_msg, delay=30))

    # 我的签到 - 直接汉字触发
    @dp.message(F.text == "我的签到")
    async def cmd_my_checkin(message: Message):
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

        # 30秒后自动删除用户消息和机器人回复
        asyncio.create_task(auto_delete(message, reply_msg, delay=30))

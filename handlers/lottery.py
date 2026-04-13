from aiogram import F
from aiogram.filters import Command
from aiogram.types import Message
from html import escape
import database as db
import asyncio
from .common import ensure_points_group

async def auto_delete(message: Message, reply_msg: Message, delay: int = 30):
    """自动删除触发消息和机器人回复"""
    await asyncio.sleep(delay)
    try:
        await message.delete()
        await reply_msg.delete()
    except:
        pass

def register_lottery_handlers(dp, config):
    # 抽奖 - 直接汉字触发，查看抽奖列表
    @dp.message(F.text == "抽奖")
    async def cmd_lottery_list(message: Message):
        group_id = await ensure_points_group(message, config)
        if group_id is None:
            return

        lotteries = db.get_active_lotteries(group_id)

        if not lotteries:
            reply_msg = await message.reply("当前没有进行中的抽奖")
            asyncio.create_task(auto_delete(message, reply_msg, delay=30))
            return

        text = "当前进行中的抽奖：\n\n"
        for l in lotteries:
            participants = db.get_lottery_participants(l['lottery_id'])
            text += f"#{l['lottery_id']} {escape(l['title'])}\n"
            text += f"  奖品：{escape(l['prize'])}\n"
            text += f"  参与费：{l['cost']} 积分\n"
            text += f"  参与人数：{len(participants)}/{l['min_participants']}\n\n"

        text += "发送 参与 <抽奖ID> 参与抽奖"
        reply_msg = await message.reply(text)
        asyncio.create_task(auto_delete(message, reply_msg, delay=30))

    # 参与 - 直接汉字触发
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
            asyncio.create_task(auto_delete(message, reply_msg, delay=30))
            return

        user_id = message.from_user.id
        username = message.from_user.username or message.from_user.full_name

        db.get_or_create_user(user_id, group_id, username)

        lottery = db.get_lottery(lottery_id)
        if not lottery:
            reply_msg = await message.reply("抽奖不存在")
            asyncio.create_task(auto_delete(message, reply_msg, delay=30))
            return

        success, msg = db.join_lottery(lottery_id, group_id, user_id)
        if success:
            participants = db.get_lottery_participants(lottery_id)
            reply_msg = await message.reply(
                f"参与成功！已扣除 {lottery['cost']} 积分\n"
                f"当前参与人数：{len(participants)}"
            )
        else:
            reply_msg = await message.reply(f"{msg}")
        asyncio.create_task(auto_delete(message, reply_msg, delay=30))

    # /抽奖 - 管理员创建抽奖
    @dp.message(Command("抽奖"))
    async def cmd_new_lottery(message: Message):
        group_id = await ensure_points_group(message, config)
        if group_id is None:
            return

        user_id = message.from_user.id

        if user_id not in config.bot.admin_ids:
            try:
                member = await message.bot.get_chat_member(group_id, user_id)
                if member.status not in ('administrator', 'creator'):
                    await message.reply("只有管理员才能创建抽奖")
                    return
            except:
                await message.reply("只有管理员才能创建抽奖")
                return

        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply(
                "格式: /抽奖 标题|奖品|积分|最少人数\n"
                "示例: /抽奖 周末抽奖|奶茶一杯|50|3"
            )
            return

        try:
            parts = args[1].split('|')
            if len(parts) < 3:
                raise ValueError("格式错误，请使用 标题|奖品|积分|最少人数")
            title = parts[0].strip()
            prize = parts[1].strip()
            cost = int(parts[2])
            min_participants = int(parts[3]) if len(parts) > 3 else 1

            if not title:
                raise ValueError("标题不能为空")
            if not prize:
                raise ValueError("奖品不能为空")

            lottery_id = db.create_lottery(
                group_id, title, prize, cost, user_id, min_participants
            )

            await message.reply(
                f"抽奖创建成功！\n"
                f"ID: #{lottery_id}\n"
                f"标题: {escape(title)}\n"
                f"奖品: {escape(prize)}\n"
                f"参与费: {cost} 积分\n"
                f"最少人数: {min_participants}\n"
                f"发送 参与 {lottery_id} 参与抽奖"
            )
        except Exception as e:
            await message.reply(f"创建失败：{str(e)}")

    # /开奖 - 管理员开奖
    @dp.message(Command("开奖"))
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

        is_admin = user_id in config.bot.admin_ids
        is_creator = lottery['creator_id'] == user_id

        if not (is_admin or is_creator):
            try:
                member = await message.bot.get_chat_member(message.chat.id, user_id)
                if member.status not in ('administrator', 'creator'):
                    await message.reply("只有管理员或抽奖创建者才能开奖")
                    return
            except:
                await message.reply("只有管理员或抽奖创建者才能开奖")
                return

        participants = db.get_lottery_participants(lottery_id)
        if len(participants) < lottery['min_participants']:
            await message.reply(f"参与人数不足，需要至少 {lottery['min_participants']} 人")
            return

        winner_id = db.finish_lottery(lottery_id, group_id)
        if winner_id:
            winner = db.get_or_create_user(winner_id, lottery['group_id'], None)
            winner_name = escape(winner.get('username') or f"用户{winner_id}")
            await message.reply(
                f"抽奖结束！\n"
                f"恭喜 {winner_name} 获得：{escape(lottery['prize'])}"
            )
        else:
            await message.reply("抽奖已取消（无人参与）")

    # /取消抽奖 - 管理员取消抽奖
    @dp.message(Command("取消抽奖"))
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

        is_admin = user_id in config.bot.admin_ids
        is_creator = lottery['creator_id'] == user_id

        if not (is_admin or is_creator):
            try:
                member = await message.bot.get_chat_member(message.chat.id, user_id)
                if member.status not in ('administrator', 'creator'):
                    await message.reply("只有管理员或抽奖创建者才能取消抽奖")
                    return
            except Exception:
                await message.reply("只有管理员或抽奖创建者才能取消抽奖")
                return

        if db.cancel_lottery(lottery_id, group_id):
            await message.reply("抽奖已取消，积分已退还给参与者")
        else:
            await message.reply("取消失败")

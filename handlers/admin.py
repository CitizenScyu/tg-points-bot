import asyncio
import logging

from aiogram import F
from aiogram.filters import Command
from aiogram.types import Message
import database as db
from telegram_commands import sync_bot_commands
from .common import (
    bind_group,
    clear_group_binding,
    ensure_points_group,
    get_bound_group_id,
    has_fixed_group_binding,
    has_group_management_rights,
    is_bot_admin,
)

logger = logging.getLogger(__name__)

def register_admin_handlers(dp, config):
    @dp.message(F.text.regexp(r"^/(bind_group|绑定群组)(?:@\w+)?$"))
    async def cmd_bind_group(message: Message):
        if message.chat.type not in {"group", "supergroup"}:
            await message.reply("请在目标群组中使用此命令")
            return

        if has_fixed_group_binding(config):
            await message.reply("当前使用固定群组配置，不能在运行时重新绑定")
            return

        current_bound_group_id = get_bound_group_id(config)
        if current_bound_group_id == message.chat.id:
            await message.reply("当前群组已经绑定")
            return

        user_id = message.from_user.id
        if current_bound_group_id is not None and not is_bot_admin(config, user_id):
            await message.reply("机器人已绑定其他群组，只有 Bot Admin 可以重新绑定")
            return

        if not await has_group_management_rights(message, config):
            await message.reply("只有 Bot Admin 或当前群管理员才能绑定")
            return

        previous_group_id = current_bound_group_id
        bind_group(config, message.chat.id)
        await sync_bot_commands(message.bot, config, previous_bound_group_id=previous_group_id)
        logger.info("群组绑定: admin=%d group=%d previous=%s", user_id, message.chat.id, previous_group_id)
        await message.reply("群组绑定成功")

    @dp.message(F.text.regexp(r"^/(unbind_group|解绑群组)(?:@\w+)?$"))
    async def cmd_unbind_group(message: Message):
        if message.chat.type not in {"group", "supergroup"}:
            await message.reply("请在已绑定群组中使用此命令")
            return

        if has_fixed_group_binding(config):
            await message.reply("当前使用固定群组配置，不能在运行时解绑")
            return

        current_bound_group_id = get_bound_group_id(config)
        if current_bound_group_id is None:
            await message.reply("当前没有已绑定的群组")
            return

        user_id = message.from_user.id
        if current_bound_group_id != message.chat.id and not is_bot_admin(config, user_id):
            await message.reply("请在已绑定群组中解绑，或使用 Bot Admin 账号处理")
            return

        if not await has_group_management_rights(message, config):
            await message.reply("只有 Bot Admin 或当前群管理员才能解绑")
            return

        previous_group_id = current_bound_group_id
        clear_group_binding(config)
        await sync_bot_commands(message.bot, config, previous_bound_group_id=previous_group_id)
        await message.reply("群组绑定已解除")

    @dp.message(Command("add_points", "加积分"))
    async def cmd_add_points(message: Message):
        group_id = await ensure_points_group(message, config)
        if group_id is None:
            return

        user_id = message.from_user.id
        if not is_bot_admin(config, user_id):
            await message.reply("只有 Bot Admin 才能使用此命令")
            return

        args = message.text.split()
        if len(args) < 3:
            await message.reply("格式: /加积分 <用户ID> <积分>")
            return

        try:
            target_id = int(args[1])
            points = int(args[2])
        except ValueError:
            await message.reply("请输入有效的数字")
            return

        if points <= 0:
            await message.reply("积分必须大于 0")
            return

        success, new_points, code = db.adjust_user_points(target_id, group_id, points)
        if not success:
            await message.reply("目标用户还没有在当前群组建立积分记录")
            return
        logger.info("增加积分: admin=%d target=%d group=%d points=%d new_total=%d",
                    user_id, target_id, group_id, points, new_points)
        await message.reply(f"已为用户 {target_id} 增加 {points} 积分，当前积分：{new_points}")

    @dp.message(Command("sub_points", "扣积分"))
    async def cmd_subtract_points(message: Message):
        group_id = await ensure_points_group(message, config)
        if group_id is None:
            return

        user_id = message.from_user.id
        if not is_bot_admin(config, user_id):
            await message.reply("只有 Bot Admin 才能使用此命令")
            return

        args = message.text.split()
        if len(args) < 3:
            await message.reply("格式: /扣积分 <用户ID> <积分>")
            return

        try:
            target_id = int(args[1])
            points = int(args[2])
        except ValueError:
            await message.reply("请输入有效的数字")
            return

        if points <= 0:
            await message.reply("积分必须大于 0")
            return

        success, new_points, code = db.adjust_user_points(target_id, group_id, -points)
        if not success and code == "user_not_found":
            await message.reply("目标用户还没有在当前群组建立积分记录")
            return
        if not success and code == "insufficient_points":
            await message.reply(f"目标用户积分不足，当前仅有 {new_points} 积分")
            return
        logger.info("扣除积分: admin=%d target=%d group=%d points=%d new_total=%d",
                    user_id, target_id, group_id, points, new_points)
        await message.reply(f"已为用户 {target_id} 扣除 {points} 积分，当前积分：{new_points}")

    @dp.message(Command("set_points", "设积分"))
    async def cmd_set_points(message: Message):
        group_id = await ensure_points_group(message, config)
        if group_id is None:
            return

        user_id = message.from_user.id
        if not is_bot_admin(config, user_id):
            await message.reply("只有 Bot Admin 才能使用此命令")
            return

        args = message.text.split()
        if len(args) < 3:
            await message.reply("格式: /设积分 <用户ID> <积分>")
            return

        try:
            target_id = int(args[1])
            points = int(args[2])
        except ValueError:
            await message.reply("请输入有效的数字")
            return

        if points < 0:
            await message.reply("积分不能小于 0")
            return

        new_points = db.set_user_points(target_id, group_id, points)
        if new_points is None:
            await message.reply("目标用户还没有在当前群组建立积分记录")
            return
        logger.info("设置积分: admin=%d target=%d group=%d points=%d", user_id, target_id, group_id, new_points)
        await message.reply(f"已将用户 {target_id} 在当前群组的积分设置为 {new_points}")

    @dp.message(Command("backup", "备份"))
    async def cmd_backup(message: Message):
        user_id = message.from_user.id
        if not is_bot_admin(config, user_id):
            await message.reply("只有 Bot Admin 才能使用此命令")
            return

        try:
            from backup import backup_to_webdav
            logger.info("手动备份: admin=%d", user_id)
            if await asyncio.to_thread(backup_to_webdav, config):
                await message.reply("备份成功")
            else:
                await message.reply("备份失败")
        except Exception as e:
            logger.exception("备份失败: admin=%d", user_id)
            await message.reply(f"备份出错：{str(e)}")

    @dp.message(Command("restore", "恢复"))
    async def cmd_restore(message: Message):
        user_id = message.from_user.id
        if not is_bot_admin(config, user_id):
            await message.reply("只有 Bot Admin 才能使用此命令")
            return

        try:
            from backup import restore_from_webdav
            logger.info("手动恢复: admin=%d", user_id)
            if await asyncio.to_thread(restore_from_webdav, config):
                await message.reply("恢复成功")
            else:
                await message.reply("恢复失败")
        except Exception as e:
            logger.exception("恢复失败: admin=%d", user_id)
            await message.reply(f"恢复出错：{str(e)}")

    @dp.message(Command("help", "帮助"))
    async def cmd_help(message: Message):
        text = """积分机器人帮助

用户命令（直接发送）：
签到 - 每日签到
积分 - 查看我的积分
排行榜 - 查看积分排行
抽奖 - 查看进行中的抽奖
参与 <ID> - 参与抽奖

用户斜杠命令：
/checkin - 每日签到
/points - 查看我的积分
/rank - 查看积分排行
/lotteries - 查看进行中的抽奖

管理员命令（/开头）：
/bind_group 或 /绑定群组 - 绑定当前群组
/unbind_group 或 /解绑群组 - 解绑当前群组
/settings - 私聊打开管理员配置面板
/抽奖 标题|奖品|积分|人数 - 创建手动开奖抽奖
/抽奖 标题|奖品|积分|人数:目标人数 - 创建满人数自动开奖抽奖
/抽奖 标题|奖品|积分|时间:YYYY-MM-DD HH:MM|最少人数 - 创建到点自动开奖抽奖
/开奖 <ID> - 开奖
/取消抽奖 <ID> - 取消抽奖
/加积分 <用户ID> <积分> - 给当前群组用户增加积分
/扣积分 <用户ID> <积分> - 给当前群组用户扣除积分
/设积分 <用户ID> <积分> - 设置当前群组用户积分
/备份 - 手动备份
/恢复 - 从备份恢复

抽奖说明：
- 创建抽奖后会附带参与按钮
- 自动开奖和手动开奖都会在群内发送结果，并尝试置顶
- /settings 需在私聊中使用，可修改常用积分和抽奖配置
- 已补英文别名，便于 Telegram 命令菜单接入，例如 /lottery /draw /cancel_lottery /add_points
- 已启用 Telegram 命令作用域：普通群成员、群管理员、Bot Admin 私聊看到的菜单会不同

聊天可自动获得积分：
- 文字 5字以上 +1积分
- 贴纸 +1积分
- 图片 +2积分
- 每日上限 150 积分
"""
        await message.reply(text)

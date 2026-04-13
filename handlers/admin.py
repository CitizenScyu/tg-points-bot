from aiogram.filters import Command
from aiogram.types import Message
import database as db
from .common import ensure_points_group

def register_admin_handlers(dp, config):
    @dp.message(Command("加积分"))
    async def cmd_add_points(message: Message):
        group_id = await ensure_points_group(message, config)
        if group_id is None:
            return

        user_id = message.from_user.id
        if user_id not in config.bot.admin_ids:
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

        new_points = db.update_user_points(target_id, group_id, points)
        if new_points is None:
            await message.reply("目标用户还没有在当前群组建立积分记录")
            return
        await message.reply(f"已为用户 {target_id} 增加 {points} 积分，当前积分：{new_points}")

    @dp.message(Command("扣积分"))
    async def cmd_subtract_points(message: Message):
        group_id = await ensure_points_group(message, config)
        if group_id is None:
            return

        user_id = message.from_user.id
        if user_id not in config.bot.admin_ids:
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

        new_points = db.update_user_points(target_id, group_id, -points)
        if new_points is None:
            await message.reply("目标用户还没有在当前群组建立积分记录")
            return
        await message.reply(f"已为用户 {target_id} 扣除 {points} 积分，当前积分：{new_points}")

    @dp.message(Command("设积分"))
    async def cmd_set_points(message: Message):
        group_id = await ensure_points_group(message, config)
        if group_id is None:
            return

        user_id = message.from_user.id
        if user_id not in config.bot.admin_ids:
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
        await message.reply(f"已将用户 {target_id} 在当前群组的积分设置为 {new_points}")

    @dp.message(Command("备份"))
    async def cmd_backup(message: Message):
        user_id = message.from_user.id
        if user_id not in config.bot.admin_ids:
            await message.reply("只有 Bot Admin 才能使用此命令")
            return

        try:
            from backup import backup_to_webdav
            if backup_to_webdav():
                await message.reply("备份成功")
            else:
                await message.reply("备份失败")
        except Exception as e:
            await message.reply(f"备份出错：{str(e)}")

    @dp.message(Command("恢复"))
    async def cmd_restore(message: Message):
        user_id = message.from_user.id
        if user_id not in config.bot.admin_ids:
            await message.reply("只有 Bot Admin 才能使用此命令")
            return

        try:
            from backup import restore_from_webdav
            if restore_from_webdav():
                await message.reply("恢复成功")
            else:
                await message.reply("恢复失败")
        except Exception as e:
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

管理员命令（/开头）：
/抽奖 标题|奖品|积分|人数 - 创建抽奖
/开奖 <ID> - 开奖
/取消抽奖 <ID> - 取消抽奖
/加积分 <用户ID> <积分> - 给当前群组用户增加积分
/扣积分 <用户ID> <积分> - 给当前群组用户扣除积分
/设积分 <用户ID> <积分> - 设置当前群组用户积分
/备份 - 手动备份
/恢复 - 从备份恢复

聊天可自动获得积分：
- 文字 5字以上 +1积分
- 贴纸 +1积分
- 图片 +2积分
- 每日上限 150 积分
"""
        await message.reply(text)

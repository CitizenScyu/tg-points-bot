from aiogram import F
from aiogram.types import Message
import database as db
from .common import ensure_points_group

# 排除的关键词，这些由其他 handler 处理
EXCLUDED_KEYWORDS = {"签到", "我的签到", "积分", "排行榜", "抽奖"}

def register_chat_handlers(dp, config):
    @dp.message(F.text, F.chat.type.in_({"group", "supergroup"}))
    async def handle_text(message: Message):
        group_id = await ensure_points_group(
            message,
            config,
            reply_on_private=False,
            reply_on_mismatch=False,
        )
        if group_id is None:
            return

        if not message.text or message.text.startswith('/'):
            return

        # 排除特定关键词
        if message.text in EXCLUDED_KEYWORDS:
            return

        # 排除"参与 xxx"格式
        if message.text.startswith("参与 "):
            return

        user_id = message.from_user.id
        username = message.from_user.username or message.from_user.full_name

        # 确保用户存在
        db.get_or_create_user(user_id, group_id, username)

        # 检查是否可以获得积分
        can_earn, reason = db.can_earn_chat_points(
            user_id,
            group_id,
            config.chat.cooldown_seconds,
            config.chat.daily_limit
        )

        if not can_earn:
            return  # 冷却中或已达上限，不提示

        # 检查文字长度
        if len(message.text) >= config.chat.text_min_length:
            actual = db.add_chat_points(user_id, group_id, config.chat.text_points, config.chat.daily_limit)
            if actual > 0:
                # 获得积分，但不提示（避免刷屏）
                pass

    @dp.message(F.sticker, F.chat.type.in_({"group", "supergroup"}))
    async def handle_sticker(message: Message):
        group_id = await ensure_points_group(
            message,
            config,
            reply_on_private=False,
            reply_on_mismatch=False,
        )
        if group_id is None:
            return

        user_id = message.from_user.id
        username = message.from_user.username or message.from_user.full_name

        db.get_or_create_user(user_id, group_id, username)

        can_earn, reason = db.can_earn_chat_points(
            user_id,
            group_id,
            config.chat.cooldown_seconds,
            config.chat.daily_limit
        )

        if can_earn:
            db.add_chat_points(user_id, group_id, config.chat.sticker_points, config.chat.daily_limit)

    @dp.message(F.photo, F.chat.type.in_({"group", "supergroup"}))
    async def handle_photo(message: Message):
        group_id = await ensure_points_group(
            message,
            config,
            reply_on_private=False,
            reply_on_mismatch=False,
        )
        if group_id is None:
            return

        user_id = message.from_user.id
        username = message.from_user.username or message.from_user.full_name

        db.get_or_create_user(user_id, group_id, username)

        can_earn, reason = db.can_earn_chat_points(
            user_id,
            group_id,
            config.chat.cooldown_seconds,
            config.chat.daily_limit
        )

        if can_earn:
            db.add_chat_points(user_id, group_id, config.chat.photo_points, config.chat.daily_limit)

#!/usr/bin/env python3
"""TG 积分机器人主程序"""
import asyncio
import logging
import sys
from pathlib import Path

# 添加当前目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import config
import database as db
from handlers import register_all_handlers
from backup import backup_to_webdav

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    # 初始化数据库
    db.init_db()
    logger.info("数据库初始化完成")

    if config.bot.group_id is not None:
        db.set_bound_group_id(config.bot.group_id)
        logger.info(f"已绑定群组: {config.bot.group_id}")
    else:
        bound_group_id = db.get_bound_group_id()
        if bound_group_id is not None:
            config.bot.group_id = bound_group_id
            logger.info(f"读取已绑定群组: {bound_group_id}")
        else:
            logger.info("未配置固定群组，将在首个使用的群组自动绑定")

    # 配置 Bot
    bot_kwargs = {
        'default': DefaultBotProperties(parse_mode=ParseMode.HTML)
    }

    # 配置代理
    if config.proxy.enabled:
        session = AiohttpSession(proxy=config.proxy.url)
        bot_kwargs['session'] = session
        logger.info(f"使用代理: {config.proxy.url}")

    bot = Bot(token=config.bot.token, **bot_kwargs)
    dp = Dispatcher()

    # 注册处理器
    register_all_handlers(dp, config)
    logger.info("处理器注册完成")

    # 配置定时备份
    if config.backup.enabled:
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            backup_to_webdav,
            'interval',
            hours=config.backup.interval_hours
        )
        scheduler.start()
        logger.info(f"定时备份已启动，间隔 {config.backup.interval_hours} 小时")

    # 启动 Bot
    logger.info("Bot 启动中...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())

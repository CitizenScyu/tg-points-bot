from .checkin import register_checkin_handlers
from .chat import register_chat_handlers
from .lottery import register_lottery_handlers
from .rank import register_rank_handlers
from .admin import register_admin_handlers
from .settings import register_settings_handlers

def register_all_handlers(dp, config):
    """注册所有处理器 - 顺序很重要，特定handler先于通用handler"""
    # 先注册特定文本匹配的 handler
    register_checkin_handlers(dp, config)
    register_rank_handlers(dp, config)
    register_lottery_handlers(dp, config)
    register_settings_handlers(dp, config)
    register_admin_handlers(dp, config)
    # 最后注册通用的聊天积分 handler
    register_chat_handlers(dp, config)

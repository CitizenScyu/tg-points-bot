import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional

CONFIG_PATH = Path(__file__).parent / "config.yaml"


class ConfigError(Exception):
    """Raised when the bot configuration is missing or invalid."""


@dataclass
class BotConfig:
    token: str
    admin_ids: List[int]
    group_id: Optional[int] = None
    configured_group_id: Optional[int] = None

@dataclass
class ProxyConfig:
    enabled: bool = False
    url: str = ""

@dataclass
class CheckinConfig:
    points: int = 10

@dataclass
class ChatConfig:
    text_min_length: int = 5
    text_points: int = 1
    sticker_points: int = 1
    photo_points: int = 2
    daily_limit: int = 150
    cooldown_seconds: int = 10

@dataclass
class RankConfig:
    top_n: int = 10

@dataclass
class LotteryConfig:
    default_min_participants: int = 1

@dataclass
class BackupConfig:
    enabled: bool = True
    webdav_url: str = ""
    username: str = ""
    password: str = ""
    interval_hours: int = 6
    filename: str = "points_bot.db"

@dataclass
class Config:
    bot: BotConfig
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    checkin: CheckinConfig = field(default_factory=CheckinConfig)
    chat: ChatConfig = field(default_factory=ChatConfig)
    rank: RankConfig = field(default_factory=RankConfig)
    lottery: LotteryConfig = field(default_factory=LotteryConfig)
    backup: BackupConfig = field(default_factory=BackupConfig)


def load_config(path: Path = CONFIG_PATH) -> Config:
    if not path.exists():
        raise ConfigError(f"配置文件不存在: {path}")

    with path.open('r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}

    if not isinstance(data, dict):
        raise ConfigError("配置文件格式无效，顶层必须是 YAML 对象")
    if not isinstance(data.get('bot'), dict):
        raise ConfigError("缺少 bot 配置段")
    if not data['bot'].get('token'):
        raise ConfigError("缺少 bot.token 配置")
    raw_group_id = data['bot'].get('group_id')

    return Config(
        bot=BotConfig(
            token=data['bot']['token'],
            admin_ids=data['bot'].get('admin_ids', []),
            group_id=raw_group_id,
            configured_group_id=raw_group_id,
        ),
        proxy=ProxyConfig(
            enabled=data.get('proxy', {}).get('enabled', False),
            url=data.get('proxy', {}).get('url', '')
        ),
        checkin=CheckinConfig(
            points=data.get('checkin', {}).get('points', 10)
        ),
        chat=ChatConfig(
            text_min_length=data.get('chat', {}).get('text_min_length', 5),
            text_points=data.get('chat', {}).get('text_points', 1),
            sticker_points=data.get('chat', {}).get('sticker_points', 1),
            photo_points=data.get('chat', {}).get('photo_points', 2),
            daily_limit=data.get('chat', {}).get('daily_limit', 150),
            cooldown_seconds=data.get('chat', {}).get('cooldown_seconds', 10)
        ),
        rank=RankConfig(
            top_n=data.get('rank', {}).get('top_n', 10)
        ),
        lottery=LotteryConfig(
            default_min_participants=data.get('lottery', {}).get('default_min_participants', 1)
        ),
        backup=BackupConfig(
            enabled=data.get('backup', {}).get('enabled', True),
            webdav_url=data.get('backup', {}).get('webdav_url', ''),
            username=data.get('backup', {}).get('username', ''),
            password=data.get('backup', {}).get('password', ''),
            interval_hours=data.get('backup', {}).get('interval_hours', 6),
            filename=data.get('backup', {}).get('filename', 'points_bot.db')
        )
    )

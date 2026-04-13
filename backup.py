"""WebDAV 备份模块"""
import logging
import tempfile
from datetime import datetime
from pathlib import Path

import database as db
from webdav3.client import Client

logger = logging.getLogger(__name__)


def get_webdav_client(config) -> Client:
    """获取 WebDAV 客户端。"""
    options = {
        'webdav_hostname': config.backup.webdav_url,
        'webdav_login': config.backup.username,
        'webdav_password': config.backup.password
    }
    return Client(options)


def _new_temp_db_path() -> Path:
    temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp_file.close()
    return Path(temp_file.name)


def backup_to_webdav(config) -> bool:
    """备份数据库到 WebDAV。"""
    if not config.backup.enabled:
        return False
    if not db.DB_PATH.exists():
        return False

    snapshot_path = _new_temp_db_path()
    try:
        client = get_webdav_client(config)
        db.create_database_snapshot(snapshot_path)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        remote_path = f"points_bot_{timestamp}.db"

        client.upload(remote_path=remote_path, local_path=str(snapshot_path))
        client.upload(remote_path=config.backup.filename, local_path=str(snapshot_path))
        cleanup_old_backups(client)
        return True
    except Exception as exc:
        logger.exception("备份失败: %s", exc)
        return False
    finally:
        if snapshot_path.exists():
            snapshot_path.unlink(missing_ok=True)


def restore_from_webdav(config) -> bool:
    """从 WebDAV 恢复数据库。"""
    if not config.backup.enabled:
        return False

    restore_path = _new_temp_db_path()
    try:
        client = get_webdav_client(config)
        client.download(local_path=str(restore_path), remote_path=config.backup.filename)
        db.restore_database_from_file(restore_path)
        return True
    except Exception as exc:
        logger.exception("恢复失败: %s", exc)
        return False
    finally:
        if restore_path.exists():
            restore_path.unlink(missing_ok=True)


def cleanup_old_backups(client: Client, keep: int = 10) -> None:
    """清理旧备份，保留最近的 N 个。"""
    try:
        files = client.list()
        backups = [name for name in files if name.startswith('points_bot_') and name.endswith('.db')]
        backups.sort(reverse=True)
        for old_file in backups[keep:]:
            try:
                client.clean(old_file)
            except Exception:
                logger.warning("删除旧备份失败: %s", old_file)
    except Exception:
        logger.warning("列出 WebDAV 备份失败", exc_info=True)


if __name__ == "__main__":
    from config import ConfigError, load_config

    try:
        config = load_config()
    except ConfigError as exc:
        print(f"配置加载失败: {exc}")
    else:
        if backup_to_webdav(config):
            print("备份成功")
        else:
            print("备份失败")

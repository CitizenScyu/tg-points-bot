import json
import random
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).parent / "data" / "points_bot.db"
DB_LOCK = threading.RLock()
BOUND_GROUP_KEY = "bot.group_id"
LOTTERY_DRAW_MODES = {"manual", "participant_count", "time"}


def _today_iso() -> str:
    return date.today().isoformat()


def _now_iso() -> str:
    return datetime.now().isoformat()


def _create_users_table(conn: sqlite3.Connection, table_name: str = "users") -> None:
    conn.execute(
        f'''
        CREATE TABLE {table_name} (
            group_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT,
            points INTEGER DEFAULT 0,
            last_checkin TEXT,
            daily_chat_points INTEGER DEFAULT 0,
            last_chat_date TEXT,
            last_chat_time TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (group_id, user_id)
        )
        '''
    )


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _migrate_users_table(conn: sqlite3.Connection) -> None:
    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "users" not in tables:
        return

    columns = conn.execute("PRAGMA table_info(users)").fetchall()
    pk_columns = [
        row["name"]
        for row in sorted(
            (row for row in columns if row["pk"]),
            key=lambda row: row["pk"],
        )
    ]
    if pk_columns == ["group_id", "user_id"]:
        return

    legacy_columns = {row["name"] for row in columns}
    conn.execute("DROP TABLE IF EXISTS users_legacy")
    conn.execute("ALTER TABLE users RENAME TO users_legacy")
    _create_users_table(conn)

    insert_columns = [
        "group_id",
        "user_id",
        "username",
        "points",
        "last_checkin",
        "daily_chat_points",
        "last_chat_date",
        "last_chat_time",
        "created_at",
    ]
    default_values = {
        "group_id": "0",
        "user_id": "NULL",
        "username": "NULL",
        "points": "0",
        "last_checkin": "NULL",
        "daily_chat_points": "0",
        "last_chat_date": "NULL",
        "last_chat_time": "NULL",
        "created_at": "CURRENT_TIMESTAMP",
    }
    select_parts = []
    for column in insert_columns:
        if column in legacy_columns:
            expression = "COALESCE(group_id, 0)" if column == "group_id" else column
        else:
            expression = default_values[column]
        select_parts.append(f"{expression} AS {column}")

    conn.execute(
        f'''
        INSERT OR REPLACE INTO users ({", ".join(insert_columns)})
        SELECT {", ".join(select_parts)}
        FROM users_legacy
        WHERE user_id IS NOT NULL
        '''
    )
    conn.execute("DROP TABLE users_legacy")


def _ensure_lotteries_schema(conn: sqlite3.Connection) -> None:
    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "lotteries" not in tables:
        return

    columns = _table_columns(conn, "lotteries")
    if "draw_mode" not in columns:
        conn.execute("ALTER TABLE lotteries ADD COLUMN draw_mode TEXT DEFAULT 'manual'")
        conn.execute(
            """
            UPDATE lotteries
            SET draw_mode = CASE
                WHEN end_time IS NOT NULL THEN 'time'
                ELSE 'manual'
            END
            WHERE draw_mode IS NULL OR draw_mode = ''
            """
        )
    else:
        conn.execute(
            "UPDATE lotteries SET draw_mode = 'manual' WHERE draw_mode IS NULL OR draw_mode = ''"
        )
    if "announcement_chat_id" not in columns:
        conn.execute("ALTER TABLE lotteries ADD COLUMN announcement_chat_id INTEGER")
    if "announcement_message_id" not in columns:
        conn.execute("ALTER TABLE lotteries ADD COLUMN announcement_message_id INTEGER")

def init_db():
    """初始化数据库"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        _migrate_users_table(conn)
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS lotteries (
                lottery_id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                prize TEXT NOT NULL,
                cost INTEGER NOT NULL,
                creator_id INTEGER NOT NULL,
                status TEXT DEFAULT 'active',
                min_participants INTEGER DEFAULT 1,
                end_time TEXT,
                draw_mode TEXT DEFAULT 'manual',
                announcement_chat_id INTEGER,
                announcement_message_id INTEGER,
                winner_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT
            );

            CREATE TABLE IF NOT EXISTS lottery_participants (
                lottery_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (lottery_id, user_id)
            );
        ''')
        if conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'users'"
        ).fetchone() is None:
            _create_users_table(conn)
        _ensure_lotteries_schema(conn)

        conn.executescript('''
            CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id);
            CREATE INDEX IF NOT EXISTS idx_users_group_points ON users(group_id, points DESC);
            CREATE INDEX IF NOT EXISTS idx_lotteries_group ON lotteries(group_id);
            CREATE INDEX IF NOT EXISTS idx_lotteries_status ON lotteries(status);
            CREATE INDEX IF NOT EXISTS idx_lotteries_due_time ON lotteries(status, draw_mode, end_time);
            CREATE INDEX IF NOT EXISTS idx_lottery_participants_user ON lottery_participants(user_id);
        ''')

@contextmanager
def get_connection():
    """获取数据库连接"""
    DB_LOCK.acquire()
    try:
        conn = sqlite3.connect(str(DB_PATH))
    except Exception:
        DB_LOCK.release()
        raise
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
        DB_LOCK.release()


def _serialize_user(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    user = dict(row)
    if user.get("last_chat_date") != _today_iso():
        user["daily_chat_points"] = 0
    return user


def get_user(user_id: int, group_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
            'SELECT * FROM users WHERE group_id = ? AND user_id = ?',
            (group_id, user_id)
        ).fetchone()
        return _serialize_user(row)

# ============ 用户相关 ============

def get_or_create_user(user_id: int, group_id: int, username: str = None) -> Dict[str, Any]:
    """获取或创建群内用户。"""
    today = _today_iso()
    with get_connection() as conn:
        row = conn.execute(
            'SELECT * FROM users WHERE group_id = ? AND user_id = ?',
            (group_id, user_id)
        ).fetchone()

        if row:
            updates = []
            params: List[Any] = []
            if username and row['username'] != username:
                updates.append('username = ?')
                params.append(username)
            if row['last_chat_date'] not in (None, today) and row['daily_chat_points']:
                updates.append('daily_chat_points = 0')
                updates.append('last_chat_date = ?')
                params.append(today)

            if updates:
                conn.execute(
                    f"UPDATE users SET {', '.join(updates)} WHERE group_id = ? AND user_id = ?",
                    (*params, group_id, user_id)
                )
                row = conn.execute(
                    'SELECT * FROM users WHERE group_id = ? AND user_id = ?',
                    (group_id, user_id)
                ).fetchone()
            return _serialize_user(row)

        conn.execute(
            'INSERT INTO users (group_id, user_id, username) VALUES (?, ?, ?)',
            (group_id, user_id, username)
        )
        return {
            'group_id': group_id,
            'user_id': user_id,
            'username': username,
            'points': 0,
            'last_checkin': None,
            'daily_chat_points': 0,
            'last_chat_date': None,
            'last_chat_time': None,
        }


def update_user_points(user_id: int, group_id: int, delta: int) -> Optional[int]:
    """更新群内用户积分，返回新积分。"""
    success, new_points, _ = adjust_user_points(user_id, group_id, delta)
    return new_points if success else None


def adjust_user_points(user_id: int, group_id: int, delta: int) -> tuple[bool, Optional[int], str]:
    """安全更新群内用户积分，返回 (是否成功, 当前/新积分, 结果码)。"""
    with get_connection() as conn:
        row = conn.execute(
            'SELECT points FROM users WHERE group_id = ? AND user_id = ?',
            (group_id, user_id)
        ).fetchone()
        if row is None:
            return False, None, "user_not_found"

        new_points = row['points'] + delta
        if new_points < 0:
            return False, row['points'], "insufficient_points"

        conn.execute(
            'UPDATE users SET points = ? WHERE group_id = ? AND user_id = ?',
            (new_points, group_id, user_id)
        )
        return True, new_points, "ok"


def set_user_points(user_id: int, group_id: int, points: int) -> Optional[int]:
    """设置群内用户积分，返回新积分。"""
    if points < 0:
        raise ValueError("积分不能小于 0")

    with get_connection() as conn:
        result = conn.execute(
            'UPDATE users SET points = ? WHERE group_id = ? AND user_id = ?',
            (points, group_id, user_id)
        )
        if result.rowcount == 0:
            return None

        row = conn.execute(
            'SELECT points FROM users WHERE group_id = ? AND user_id = ?',
            (group_id, user_id)
        ).fetchone()
        return row['points']


def get_user_points(user_id: int, group_id: int) -> int:
    """获取群内用户积分。"""
    with get_connection() as conn:
        row = conn.execute(
            'SELECT points FROM users WHERE group_id = ? AND user_id = ?',
            (group_id, user_id)
        ).fetchone()
        return row['points'] if row else 0


def get_ranking(group_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """获取群组排行榜。"""
    with get_connection() as conn:
        rows = conn.execute(
            '''
            SELECT user_id, username, points
            FROM users
            WHERE group_id = ?
            ORDER BY points DESC, created_at ASC
            LIMIT ?
            ''',
            (group_id, limit)
        ).fetchall()
        return [dict(row) for row in rows]

# ============ 签到相关 ============

def can_checkin(user_id: int, group_id: int) -> bool:
    """检查是否可以签到。"""
    with get_connection() as conn:
        row = conn.execute(
            'SELECT last_checkin FROM users WHERE group_id = ? AND user_id = ?',
            (group_id, user_id)
        ).fetchone()
        if not row or not row['last_checkin']:
            return True
        return row['last_checkin'] != _today_iso()


def do_checkin(user_id: int, group_id: int, points: int) -> bool:
    """执行签到。"""
    today = _today_iso()
    with get_connection() as conn:
        result = conn.execute(
            '''
            UPDATE users
            SET points = points + ?, last_checkin = ?
            WHERE group_id = ? AND user_id = ?
              AND (last_checkin IS NULL OR last_checkin != ?)
            ''',
            (points, today, group_id, user_id, today)
        )
        return result.rowcount > 0

# ============ 聊天积分相关 ============

def can_earn_chat_points(
    user_id: int,
    group_id: int,
    cooldown: int,
    daily_limit: int
) -> tuple[bool, str]:
    """检查是否可以获得聊天积分，返回 (是否可以, 原因)。"""
    with get_connection() as conn:
        row = conn.execute(
            '''
            SELECT last_chat_time, last_chat_date, daily_chat_points
            FROM users
            WHERE group_id = ? AND user_id = ?
            ''',
            (group_id, user_id)
        ).fetchone()

        if not row:
            return True, "ok"

        now = datetime.now()
        today = _today_iso()
        daily_used = row['daily_chat_points'] if row['last_chat_date'] == today else 0

        if daily_used >= daily_limit:
            return False, "daily_limit"

        if row['last_chat_time']:
            try:
                last_chat = datetime.fromisoformat(row['last_chat_time'])
            except ValueError:
                last_chat = None
            if last_chat is not None:
                elapsed = (now - last_chat).total_seconds()
                if elapsed < cooldown:
                    return False, f"cooldown:{int(cooldown - elapsed)}s"

        return True, "ok"


def add_chat_points(user_id: int, group_id: int, points: int, daily_limit: int) -> int:
    """添加聊天积分，返回实际添加的积分。"""
    today = _today_iso()
    now = _now_iso()

    with get_connection() as conn:
        row = conn.execute(
            '''
            SELECT daily_chat_points, last_chat_date
            FROM users
            WHERE group_id = ? AND user_id = ?
            ''',
            (group_id, user_id)
        ).fetchone()

        if not row:
            return 0

        daily_used = row['daily_chat_points'] if row['last_chat_date'] == today else 0
        remaining = max(0, daily_limit - daily_used)
        actual_points = max(0, min(points, remaining))

        if actual_points == 0:
            if row['last_chat_date'] not in (None, today) and row['daily_chat_points']:
                conn.execute(
                    '''
                    UPDATE users
                    SET daily_chat_points = 0, last_chat_date = ?
                    WHERE group_id = ? AND user_id = ?
                    ''',
                    (today, group_id, user_id)
                )
            return 0

        conn.execute(
            '''
            UPDATE users
            SET points = points + ?,
                daily_chat_points = ?,
                last_chat_date = ?,
                last_chat_time = ?
            WHERE group_id = ? AND user_id = ?
            ''',
            (actual_points, daily_used + actual_points, today, now, group_id, user_id)
        )
        return actual_points

# ============ 抽奖相关 ============

def _serialize_lottery(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    lottery = dict(row)
    lottery["draw_mode"] = lottery.get("draw_mode") or "manual"
    return lottery


def _get_lottery_locked(
    conn: sqlite3.Connection,
    lottery_id: int,
    group_id: Optional[int] = None,
) -> Optional[sqlite3.Row]:
    if group_id is None:
        return conn.execute(
            'SELECT * FROM lotteries WHERE lottery_id = ?',
            (lottery_id,)
        ).fetchone()
    return conn.execute(
        'SELECT * FROM lotteries WHERE lottery_id = ? AND group_id = ?',
        (lottery_id, group_id)
    ).fetchone()


def _get_lottery_participants_locked(conn: sqlite3.Connection, lottery_id: int) -> List[int]:
    return [
        row['user_id']
        for row in conn.execute(
            'SELECT user_id FROM lottery_participants WHERE lottery_id = ?',
            (lottery_id,)
        ).fetchall()
    ]


def _get_lottery_participant_count_locked(conn: sqlite3.Connection, lottery_id: int) -> int:
    row = conn.execute(
        'SELECT COUNT(*) AS count FROM lottery_participants WHERE lottery_id = ?',
        (lottery_id,)
    ).fetchone()
    return int(row['count']) if row else 0


def _refund_lottery_participants_locked(
    conn: sqlite3.Connection,
    lottery: sqlite3.Row,
    participant_ids: List[int],
) -> None:
    for participant_id in participant_ids:
        conn.execute(
            'UPDATE users SET points = points + ? WHERE group_id = ? AND user_id = ?',
            (lottery['cost'], lottery['group_id'], participant_id)
        )


def _cancel_lottery_locked(
    conn: sqlite3.Connection,
    lottery: sqlite3.Row,
    *,
    refund: bool = False,
    participant_ids: Optional[List[int]] = None,
) -> None:
    participants = participant_ids if participant_ids is not None else _get_lottery_participants_locked(
        conn, lottery['lottery_id']
    )
    if refund and participants:
        _refund_lottery_participants_locked(conn, lottery, participants)
    conn.execute(
        "UPDATE lotteries SET status = 'cancelled', finished_at = ? WHERE lottery_id = ?",
        (_now_iso(), lottery['lottery_id'])
    )


def _finish_lottery_locked(
    conn: sqlite3.Connection,
    lottery: sqlite3.Row,
    winner_id: Optional[int] = None,
) -> tuple[Optional[int], str, List[int]]:
    participants = _get_lottery_participants_locked(conn, lottery['lottery_id'])

    if not participants:
        _cancel_lottery_locked(conn, lottery, refund=False, participant_ids=participants)
        return None, "cancelled", participants

    if winner_id is not None and winner_id not in participants:
        raise ValueError("指定中奖者未参与本次抽奖")
    if winner_id is None:
        winner_id = random.choice(participants)

    conn.execute(
        '''
        UPDATE lotteries
        SET status = 'finished', winner_id = ?, finished_at = ?
        WHERE lottery_id = ?
        ''',
        (winner_id, _now_iso(), lottery['lottery_id'])
    )
    return winner_id, "finished", participants


def create_lottery(group_id: int, title: str, prize: str, cost: int,
                   creator_id: int, min_participants: int = 1,
                   end_time: str = None, draw_mode: str = "manual") -> int:
    """创建抽奖，返回抽奖ID。"""
    if cost <= 0:
        raise ValueError("参与费必须大于 0")
    if min_participants < 1:
        raise ValueError("最少人数不能小于 1")
    if draw_mode not in LOTTERY_DRAW_MODES:
        raise ValueError("不支持的开奖模式")
    if draw_mode == "time" and not end_time:
        raise ValueError("按时间开奖必须设置开奖时间")
    if draw_mode != "time":
        end_time = None

    with get_connection() as conn:
        cursor = conn.execute(
            '''
            INSERT INTO lotteries
                (group_id, title, prize, cost, creator_id, min_participants, end_time, draw_mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (group_id, title, prize, cost, creator_id, min_participants, end_time, draw_mode)
        )
        return cursor.lastrowid


def get_active_lotteries(group_id: int) -> List[Dict[str, Any]]:
    """获取群组内活跃的抽奖。"""
    with get_connection() as conn:
        rows = conn.execute(
            '''
            SELECT *
            FROM lotteries
            WHERE group_id = ? AND status = 'active'
            ORDER BY created_at DESC
            ''',
            (group_id,)
        ).fetchall()
        return [_serialize_lottery(row) for row in rows]


def get_lottery(lottery_id: int, group_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """获取抽奖详情。"""
    with get_connection() as conn:
        row = _get_lottery_locked(conn, lottery_id, group_id)
        return _serialize_lottery(row)


def set_lottery_announcement_message(
    lottery_id: int,
    group_id: int,
    chat_id: int,
    message_id: int,
) -> bool:
    with get_connection() as conn:
        result = conn.execute(
            '''
            UPDATE lotteries
            SET announcement_chat_id = ?, announcement_message_id = ?
            WHERE lottery_id = ? AND group_id = ?
            ''',
            (chat_id, message_id, lottery_id, group_id)
        )
        return result.rowcount > 0


def join_lottery(lottery_id: int, group_id: int, user_id: int) -> tuple[bool, str]:
    """参与抽奖，返回 (成功, 消息)。"""
    result = join_lottery_with_result(lottery_id, group_id, user_id)
    return result["success"], result["message"]


def join_lottery_with_result(lottery_id: int, group_id: int, user_id: int) -> Dict[str, Any]:
    """参与抽奖并返回详细结果。"""
    with get_connection() as conn:
        lottery = _get_lottery_locked(conn, lottery_id)
        if not lottery:
            return {"success": False, "message": "抽奖不存在"}
        if lottery['group_id'] != group_id:
            return {"success": False, "message": "请在创建抽奖的群组中参与"}
        if lottery['status'] != 'active':
            return {"success": False, "message": "抽奖已结束"}
        if lottery['cost'] <= 0:
            return {"success": False, "message": "抽奖配置无效，请联系管理员"}

        existing = conn.execute(
            'SELECT 1 FROM lottery_participants WHERE lottery_id = ? AND user_id = ?',
            (lottery_id, user_id)
        ).fetchone()
        if existing:
            return {"success": False, "message": "已参与此抽奖"}

        user = conn.execute(
            'SELECT points FROM users WHERE group_id = ? AND user_id = ?',
            (group_id, user_id)
        ).fetchone()
        if not user:
            return {"success": False, "message": "用户不存在"}
        if user['points'] < lottery['cost']:
            return {"success": False, "message": f"积分不足，需要 {lottery['cost']} 积分"}

        conn.execute(
            'UPDATE users SET points = points - ? WHERE group_id = ? AND user_id = ?',
            (lottery['cost'], group_id, user_id)
        )
        conn.execute(
            'INSERT INTO lottery_participants (lottery_id, user_id) VALUES (?, ?)',
            (lottery_id, user_id)
        )

        participant_count = _get_lottery_participant_count_locked(conn, lottery_id)
        winner_id = None
        auto_finished = False
        settlement = "active"

        if (lottery['draw_mode'] or "manual") == "participant_count" and participant_count >= lottery['min_participants']:
            winner_id, settlement, _ = _finish_lottery_locked(conn, lottery)
            auto_finished = settlement == "finished"

        updated_lottery = _serialize_lottery(_get_lottery_locked(conn, lottery_id))
        return {
            "success": True,
            "message": "参与成功",
            "participant_count": participant_count,
            "lottery": updated_lottery,
            "winner_id": winner_id,
            "auto_finished": auto_finished,
            "settlement": settlement,
        }

def get_lottery_participants(lottery_id: int) -> List[int]:
    """获取抽奖参与者列表"""
    with get_connection() as conn:
        return _get_lottery_participants_locked(conn, lottery_id)


def get_lottery_participant_count(lottery_id: int) -> int:
    with get_connection() as conn:
        return _get_lottery_participant_count_locked(conn, lottery_id)


def get_due_time_lotteries(now_iso: Optional[str] = None) -> List[Dict[str, Any]]:
    """获取已到期开奖时间的抽奖。"""
    current_time = now_iso or _now_iso()
    with get_connection() as conn:
        rows = conn.execute(
            '''
            SELECT *
            FROM lotteries
            WHERE status = 'active'
              AND draw_mode = 'time'
              AND end_time IS NOT NULL
              AND end_time <= ?
            ORDER BY end_time ASC, created_at ASC
            ''',
            (current_time,)
        ).fetchall()
        return [_serialize_lottery(row) for row in rows]

def finish_lottery(lottery_id: int, group_id: int, winner_id: int = None) -> Optional[int]:
    """结束抽奖，返回中奖者ID。"""
    with get_connection() as conn:
        lottery = _get_lottery_locked(conn, lottery_id, group_id)
        if not lottery or lottery['status'] != 'active':
            return None

        winner_id, _, _ = _finish_lottery_locked(conn, lottery, winner_id)
        return winner_id


def settle_due_time_lottery(lottery_id: int, group_id: int) -> Dict[str, Any]:
    """结算到期的按时间开奖抽奖。"""
    with get_connection() as conn:
        lottery = _get_lottery_locked(conn, lottery_id, group_id)
        if not lottery or lottery['status'] != 'active' or (lottery['draw_mode'] or "manual") != 'time':
            return {"status": "ignored"}

        participants = _get_lottery_participants_locked(conn, lottery_id)
        participant_count = len(participants)

        if participant_count < lottery['min_participants']:
            _cancel_lottery_locked(
                conn,
                lottery,
                refund=participant_count > 0,
                participant_ids=participants,
            )
            updated_lottery = _serialize_lottery(_get_lottery_locked(conn, lottery_id, group_id))
            return {
                "status": "cancelled",
                "reason": "insufficient_participants" if participant_count else "no_participants",
                "participant_count": participant_count,
                "winner_id": None,
                "lottery": updated_lottery,
            }

        winner_id, status, _ = _finish_lottery_locked(conn, lottery)
        updated_lottery = _serialize_lottery(_get_lottery_locked(conn, lottery_id, group_id))
        return {
            "status": status,
            "reason": "time_reached",
            "participant_count": participant_count,
            "winner_id": winner_id,
            "lottery": updated_lottery,
        }


def cancel_lottery(lottery_id: int, group_id: int) -> bool:
    """取消抽奖并退还积分。"""
    with get_connection() as conn:
        lottery = _get_lottery_locked(conn, lottery_id, group_id)
        if not lottery or lottery['status'] != 'active':
            return False

        _cancel_lottery_locked(conn, lottery, refund=True)
        return True

# ============ 配置相关 ============

def get_config_value(key: str, default: Any = None) -> Any:
    """获取配置值。"""
    with get_connection() as conn:
        row = conn.execute(
            'SELECT value FROM config WHERE key = ?', (key,)
        ).fetchone()
        if row:
            return json.loads(row['value'])
        return default

def set_config_value(key: str, value: Any) -> None:
    """设置配置值。"""
    with get_connection() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)',
            (key, json.dumps(value))
        )


def get_bound_group_id() -> Optional[int]:
    value = get_config_value(BOUND_GROUP_KEY)
    return int(value) if value is not None else None


def set_bound_group_id(group_id: Optional[int]) -> None:
    set_config_value(BOUND_GROUP_KEY, int(group_id) if group_id is not None else None)


def clear_bound_group_id() -> None:
    set_bound_group_id(None)


def create_database_snapshot(target_path: Path) -> Path:
    """创建 SQLite 一致性快照。"""
    snapshot_path = Path(target_path)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    if not DB_PATH.exists():
        raise FileNotFoundError(DB_PATH)

    with DB_LOCK:
        source = sqlite3.connect(str(DB_PATH))
        try:
            destination = sqlite3.connect(str(snapshot_path))
            try:
                source.backup(destination)
            finally:
                destination.close()
        finally:
            source.close()
    return snapshot_path


def restore_database_from_file(source_path: Path) -> None:
    """从 SQLite 文件恢复数据库。"""
    restore_path = Path(source_path)
    if not restore_path.exists():
        raise FileNotFoundError(restore_path)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DB_LOCK:
        source = sqlite3.connect(str(restore_path))
        try:
            integrity_row = source.execute('PRAGMA integrity_check').fetchone()
            integrity = integrity_row[0] if integrity_row else 'failed'
            if integrity != 'ok':
                raise ValueError(f"恢复文件校验失败: {integrity}")

            destination = sqlite3.connect(str(DB_PATH))
            try:
                source.backup(destination)
            finally:
                destination.close()
        finally:
            source.close()

    init_db()

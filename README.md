# TG 积分机器人

Telegram 群组积分系统，支持签到、聊天积分、排行榜、抽奖功能，部署于 Phoenix VPS。

首次部署时，请基于 `config.example.yaml` 准备本地 `config.yaml`。

## 功能特性

- **每日签到**：发送"签到"获得积分
- **聊天积分**：群内发消息自动获得积分（文字/贴纸/图片）
- **排行榜**：发送"排行榜"查看积分排名
- **抽奖系统**：管理员创建抽奖，用户消耗积分参与
- **WebDAV 备份**：定时备份数据库到坚果云

## 文件结构

```
tg-points-bot/
├── bot.py              # 主程序入口
├── config.py           # 配置加载模块
├── config.yaml         # 本地运行配置（建议仅本地保存）
├── config.example.yaml # 脱敏示例配置
├── database.py         # SQLite 数据库操作
├── backup.py           # WebDAV 备份模块
├── Dockerfile          # Docker 镜像构建
├── docker-compose.yml  # Docker Compose 配置
├── requirements.txt    # Python 依赖
├── data/
│   └── points_bot.db   # SQLite 数据库（运行时生成）
└── handlers/
    ├── __init__.py     # 处理器注册（顺序关键）
    ├── common.py       # 群组绑定和访问控制
    ├── checkin.py      # 签到处理
    ├── chat.py         # 聊天积分处理
    ├── rank.py         # 排行榜处理
    ├── lottery.py      # 抽奖处理
    └── admin.py        # 管理员命令处理
```

## 命令说明

### 用户命令（直接发送文字）
| 命令 | 说明 |
|------|------|
| 签到 | 每日签到获得积分 |
| 积分 | 查看我的积分 |
| 排行榜 | 查看积分排名 |
| 抽奖 | 查看进行中的抽奖 |
| 参与 <ID> | 参与抽奖 |

### 管理员命令（/开头）
| 命令 | 说明 |
|------|------|
| /抽奖 标题\|奖品\|积分\|人数 | 创建抽奖 |
| /开奖 <ID> | 开奖 |
| /取消抽奖 <ID> | 取消抽奖并退还积分 |
| /加积分 <用户ID> <积分> | 给当前群组内用户增加积分 |
| /扣积分 <用户ID> <积分> | 给当前群组内用户扣除积分 |
| /设积分 <用户ID> <积分> | 设置当前群组内用户积分 |
| /备份 | 手动备份 |
| /恢复 | 从备份恢复 |

## 关键部署细节

### 1. 处理器注册顺序（最重要）

`handlers/__init__.py` 中的注册顺序决定了消息匹配优先级：

```python
def register_all_handlers(dp, config):
    # 先注册特定文本匹配的 handler
    register_checkin_handlers(dp, config)   # "签到", "我的签到"
    register_rank_handlers(dp, config)       # "积分", "排行榜"
    register_lottery_handlers(dp, config)    # "抽奖", "参与 xxx"
    register_admin_handlers(dp, config)      # /命令
    # 最后注册通用的聊天积分 handler
    register_chat_handlers(dp, config)       # 所有其他群消息
```

**原因**：aiogram 按注册顺序匹配消息。如果 `chat.py` 先注册，它会捕获所有群消息（包括"签到"），导致特定命令失效。

### 2. chat.py 的关键词排除

通用聊天处理器必须排除被其他 handler 处理的关键词：

```python
EXCLUDED_KEYWORDS = {"签到", "我的签到", "积分", "排行榜", "抽奖"}

@dp.message(F.text, F.chat.type.in_({"group", "supergroup"}))
async def handle_text(message: Message):
    if message.text in EXCLUDED_KEYWORDS:
        return
    if message.text.startswith("参与 "):
        return
    # ... 聊天积分逻辑
```

这是双重保险，即使注册顺序错误也不会错误捕获。

### 3. 群组绑定与隔离

- `bot.group_id` 填了值时，只响应这个群
- `bot.group_id: null` 时，会在首个使用的群自动绑定，并写入数据库
- 积分、签到、排行榜、抽奖全部按 `group_id + user_id` 隔离，不再串群
- 私聊和其他群不能再操作已绑定群的抽奖或积分

### 4. 代理配置

本地无法直连 Telegram，需配置代理：

```yaml
proxy:
  enabled: true
  url: "http://127.0.0.1:7891"
```

bot.py 使用 `AiohttpSession` 配置代理：

```python
if config.proxy.enabled:
    session = AiohttpSession(proxy=config.proxy.url)
    bot_kwargs['session'] = session
```

**注意**：需要 `aiohttp-socks` 依赖支持 SOCKS 代理。

### 5. Docker 部署

代码更新后需要 rebuild，不能只 restart：

```bash
docker compose build --no-cache
docker compose up -d
```

挂载配置文件和数据目录：

```yaml
volumes:
  - ./config.yaml:/app/config.yaml:ro
  - ./data:/app/data
```

`.dockerignore` 已排除 `config.yaml` 和 `data/`，避免把密钥和数据库打进镜像。

### 6. 数据库设计

SQLite 单文件设计，便于备份迁移：

- `users` 表：按 `(group_id, user_id)` 存储用户积分、签到日期、每日聊天积分
- `lotteries` 表：抽奖信息、状态、中奖者
- `lottery_participants` 表：抽奖参与记录
- `config` 表：键值对配置

### 7. WebDAV 备份

使用坚果云 WebDAV，每 6 小时自动备份：

- 备份文件：`points_bot_<timestamp>.db`（带时间戳）
- 最新版本：`points_bot.db`（覆盖）
- 保留策略：最近 10 个备份
- 备份前会先生成 SQLite 一致性快照，避免直接上传正在写入的数据库文件
- 恢复时会先校验下载文件完整性，再覆盖本地数据库

## 常见问题排查

### Bot 不响应文字命令

1. 检查 Bot 的 Privacy Mode 是否关闭（@BotFather 设置）
2. 检查 handler 注册顺序（`handlers/__init__.py`）
3. 检查 `chat.py` 的 `EXCLUDED_KEYWORDS` 是否包含该命令

### 代码更新后不生效

```bash
docker compose build --no-cache
docker compose up -d
```

### 代理连接失败

检查代理地址和端口，确保代理服务运行中。

### 备份失败

检查 WebDAV 配置（url、username、password），坚果云需使用应用密码。

## 配置参数说明

```yaml
bot:
  token: "Bot Token"
  admin_ids: [123456789]       # 管理员 Telegram ID
  group_id: -1001234567890     # 固定群ID；留空则首个使用的群自动绑定

checkin:
  points: 10                   # 签到获得积分

chat:
  text_min_length: 5           # 文字最少字数
  text_points: 1               # 文字积分
  sticker_points: 1            # 贴纸积分
  photo_points: 2              # 图片积分
  daily_limit: 150             # 每日聊天积分上限
  cooldown_seconds: 10         # 聊天积分冷却时间

rank:
  top_n: 10                    # 排行榜显示人数

backup:
  enabled: true
  webdav_url: "https://dav.jianguoyun.com/dav/目录名"
  username: "坚果云邮箱"
  password: "应用密码"
  interval_hours: 6
```

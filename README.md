# TG 积分机器人

面向 Telegram 群组的积分机器人，提供签到、聊天积分、排行榜、抽奖、私聊配置、WebDAV 备份等能力，支持本地运行和 Docker 部署。

首次部署前，请先基于 [config.example.yaml](config.example.yaml) 创建本地 `config.yaml`。

## 项目概览

### 功能特性

- 每日签到：用户发送 `签到` 或 `/checkin` 获取每日积分
- 聊天积分：按文字、贴纸、图片发言自动发放积分，并带冷却与每日上限
- 积分查询：支持查看个人积分和群内排行榜
- 抽奖系统：支持手动开奖、满人数自动开奖、到点自动开奖
- 交互优化：抽奖消息支持内联“参与抽奖”按钮，开奖结果会在群内播报并尝试置顶
- 管理配置：管理员可在私聊使用 `/settings` 修改常用运行时参数
- 群组隔离：积分、签到、排行榜、抽奖均按 `group_id + user_id` 隔离
- 数据安全：SQLite 一致性快照备份，支持 WebDAV 上传与恢复
- 命令菜单：自动同步 Telegram 命令菜单，并按用户身份展示不同命令

### 技术栈

- Python 3.11+
- aiogram 3.x
- SQLite
- APScheduler
- aiohttp / aiohttp-socks
- WebDAV

## 目录结构

```text
tg-points-bot/
├── bot.py                 # 主程序入口
├── config.py              # YAML 配置加载
├── runtime_settings.py    # 运行时配置覆盖与校验
├── telegram_commands.py   # Telegram 命令菜单同步
├── database.py            # SQLite 数据库与迁移逻辑
├── backup.py              # WebDAV 备份与恢复
├── config.example.yaml    # 示例配置
├── config.yaml            # 本地实际配置，不建议提交
├── Dockerfile             # Docker 镜像构建
├── docker-compose.yml     # Docker Compose 编排
├── requirements.txt       # Python 依赖
├── data/
│   └── points_bot.db      # 运行时数据库
├── docs/
│   └── OPERATIONS.md      # 管理员运维手册
├── handlers/
│   ├── __init__.py        # Handler 注册入口
│   ├── common.py          # 群组绑定、权限与公共校验
│   ├── checkin.py         # 签到
│   ├── chat.py            # 聊天积分
│   ├── rank.py            # 排行榜与积分查询
│   ├── lottery.py         # 抽奖
│   ├── admin.py           # 管理命令
│   ├── settings.py        # 私聊配置面板
│   └── utils.py           # 通用工具
└── tests/
    ├── test_database.py
    ├── test_common.py
    ├── test_runtime_settings.py
    └── test_telegram_commands.py
```

## 运行要求

### 基础要求

- Python 3.11 或更高版本
- 可访问 Telegram Bot API 的网络环境
- 机器人已由 `@BotFather` 创建，并获取 `bot token`

### 建议的 BotFather 设置

- 关闭 `Privacy Mode`
  原因：机器人需要接收群内普通文字消息，才能处理 `签到`、`积分`、`排行榜`、`抽奖` 以及聊天积分
- 设置机器人为群管理员
  建议至少具备以下权限：
  - 删除消息
    用于自动删除部分提示消息，未授权时会自动降级为忽略
  - 置顶消息
    用于抽奖开奖结果置顶，未授权时只发送结果，不会报错中断

## 快速开始

### 1. 准备配置文件

复制示例配置：

```powershell
Copy-Item config.example.yaml config.yaml
```

编辑 `config.yaml`，至少填写：

- `bot.token`
- `bot.admin_ids`
- `proxy`，如果当前网络环境无法直接访问 Telegram

### 2. 本地运行

安装依赖：

```powershell
py -m pip install -r requirements.txt
```

启动：

```powershell
py bot.py
```

### 3. Docker 运行

构建并启动：

```powershell
docker compose build --no-cache
docker compose up -d
```

查看日志：

```powershell
docker compose logs -f
```

## 配置说明

完整示例见 [config.example.yaml](config.example.yaml)。

### `bot`

| 字段 | 类型 | 说明 |
|------|------|------|
| `token` | string | Telegram Bot Token |
| `admin_ids` | int[] | Bot 超级管理员 Telegram ID 列表 |
| `group_id` | int \| null | 固定服务群组 ID；为 `null` 时需手动绑定 |

说明：

- 当 `group_id` 已填写时，机器人只服务该群
- 当 `group_id: null` 时，需管理员在目标群使用 `/bind_group`
- `admin_ids` 中的用户拥有最高管理权限，不依赖群管理员身份

### `proxy`

| 字段 | 类型 | 说明 |
|------|------|------|
| `enabled` | bool | 是否启用代理 |
| `url` | string | 代理地址，例如 `http://127.0.0.1:7891` |

### `checkin`

| 字段 | 类型 | 说明 |
|------|------|------|
| `points` | int | 每日签到奖励积分 |

### `chat`

| 字段 | 类型 | 说明 |
|------|------|------|
| `text_min_length` | int | 文字消息最少长度 |
| `text_points` | int | 文字消息积分 |
| `sticker_points` | int | 贴纸消息积分 |
| `photo_points` | int | 图片消息积分 |
| `video_points` | int | 视频消息积分 |
| `daily_limit` | int | 每日聊天积分总上限 |
| `cooldown_seconds` | int | 聊天积分冷却秒数 |

### `rank`

| 字段 | 类型 | 说明 |
|------|------|------|
| `top_n` | int | 排行榜显示人数 |

### `lottery`

| 字段 | 类型 | 说明 |
|------|------|------|
| `default_min_participants` | int | 抽奖默认最少参与人数 |

### `backup`

| 字段 | 类型 | 说明 |
|------|------|------|
| `enabled` | bool | 是否启用自动备份 |
| `webdav_url` | string | WebDAV 目标目录 |
| `username` | string | WebDAV 用户名 |
| `password` | string | WebDAV 密码或应用密码 |
| `interval_hours` | int | 自动备份间隔小时数 |
| `filename` | string | 最新备份文件名 |

## 群组绑定与权限模型

### 群组绑定规则

- 固定群模式：`bot.group_id` 已配置，启动后直接绑定该群
- 动态群模式：`bot.group_id: null`，需管理员在目标群执行 `/bind_group`
- 已绑定其他群时，只有 `Bot Admin` 可以重新绑定到新群
- 动态模式下可通过 `/unbind_group` 解除绑定
- 固定群模式下不允许运行时解绑

### 权限规则

- 普通用户：
  - 可签到、查询积分、查看排行榜、参与抽奖
- 已绑定群管理员：
  - 可创建抽奖、开奖、取消抽奖
  - 可在私聊使用 `/settings`
- Bot Admin：
  - 拥有所有管理能力
  - 可跨群重新绑定
  - 可使用 `/add_points`、`/sub_points`、`/set_points`、`/backup`、`/restore`

## 命令说明

### 用户文本命令

| 命令 | 说明 |
|------|------|
| `签到` | 每日签到 |
| `我的签到` | 查看签到状态 |
| `积分` | 查看个人积分 |
| `排行榜` | 查看积分排行 |
| `抽奖` | 查看进行中的抽奖 |
| `参与 <抽奖ID>` | 参与指定抽奖 |

### 用户斜杠命令

| 命令 | 说明 |
|------|------|
| `/checkin` | 每日签到 |
| `/my_checkin` | 查看签到状态 |
| `/points` | 查看个人积分 |
| `/rank` | 查看积分排行 |
| `/lotteries` | 查看进行中的抽奖 |
| `/help` | 查看帮助 |

### 管理员命令

| 中文命令 | 英文别名 | 说明 |
|------|------|------|
| `/bind_group` 或 `/绑定群组` | `/bind_group` | 绑定当前群组 |
| `/unbind_group` 或 `/解绑群组` | `/unbind_group` | 解绑当前群组 |
| `/抽奖 标题\|奖品\|积分\|人数` | `/lottery ...` | 创建手动开奖抽奖 |
| `/抽奖 标题\|奖品\|积分\|人数:目标人数` | `/lottery ...` | 创建满人数自动开奖抽奖 |
| `/抽奖 标题\|奖品\|积分\|时间:YYYY-MM-DD HH:MM\|最少人数` | `/lottery ...` | 创建定时开奖抽奖 |
| `/开奖 <ID>` | `/draw <ID>` | 手动开奖 |
| `/取消抽奖 <ID>` | `/cancel_lottery <ID>` | 取消抽奖并退回参与积分 |
| `/加积分 <用户ID> <积分>` | `/add_points <用户ID> <积分>` | 增加用户积分 |
| `/扣积分 <用户ID> <积分>` | `/sub_points <用户ID> <积分>` | 扣减用户积分 |
| `/设积分 <用户ID> <积分>` | `/set_points <用户ID> <积分>` | 直接设置用户积分 |
| `/settings` | `/settings` | 在私聊打开管理员配置面板 |
| `/备份` | `/backup` | 手动备份数据库 |
| `/恢复` | `/restore` | 从远端备份恢复数据库 |

说明：

- 中文命令和英文别名可以并存
- Telegram 命令菜单优先展示英文斜杠命令
- 文本命令与斜杠命令共用同一套业务逻辑

## 抽奖说明

### 开奖模式

- 手动开奖：
  - 示例：`/抽奖 周末抽奖|红包|10|3`
  - 含义：至少 3 人参与后，由管理员手动执行 `/开奖 <ID>`
- 满人数自动开奖：
  - 示例：`/抽奖 周末抽奖|红包|10|人数:10`
  - 含义：满 10 人后自动开奖
- 定时自动开奖：
  - 示例：`/抽奖 周末抽奖|红包|10|时间:2026-04-13 20:00|3`
  - 含义：在 `2026-04-13 20:00` 自动开奖，若参与人数少于 3 人则取消并退款

### 抽奖行为说明

- 创建抽奖后会发送抽奖公告消息
- 抽奖公告带“参与抽奖”内联按钮
- 用户可通过按钮或 `参与 <ID>` 加入抽奖
- 满足开奖条件后会自动或手动结算
- 开奖结果会在群内发送，并尝试置顶
- 原抽奖公告会同步更新为“已开奖”或“已取消”状态

### 抽奖限制

- 参与抽奖需要足够积分
- 参与积分会在加入时扣除
- 取消抽奖或定时抽奖人数不足时，会自动退款
- 手动开奖模式仅允许管理员或创建者执行 `/开奖`

## 私聊配置面板

管理员可在私聊发送 `/settings` 进入配置面板。

当前支持修改：

- 签到积分
- 文字最少字数
- 文字积分
- 贴纸积分
- 图片积分
- 每日聊天积分上限
- 聊天积分冷却秒数
- 排行榜显示人数
- 抽奖默认最少人数

说明：

- `/settings` 写入的是数据库配置覆盖层，不会直接改写 `config.yaml`
- 一旦某项被私聊配置修改，后续重启仍优先使用数据库中的覆盖值
- 若需恢复为 YAML 默认值，可将该项重新改回相同数值，或谨慎清理数据库 `config` 表中的对应键

## Telegram 命令菜单作用域

机器人启动时会自动调用 Telegram `setMyCommands` 同步命令菜单，绑定或解绑群组后也会重新同步。

当前命令菜单作用域如下：

- 所有私聊：
  - `/help`
  - `/settings`
- Bot Admin 私聊：
  - 额外显示 `/backup`
  - 额外显示 `/restore`
- 已绑定群普通成员：
  - `/checkin`
  - `/points`
  - `/rank`
  - `/lotteries`
- 已绑定群管理员：
  - 额外显示 `/lottery`
  - 额外显示 `/draw`
  - 额外显示 `/cancel_lottery`
- 未绑定状态下的群管理员：
  - `/bind_group`

说明：

- 命令菜单只是展示层，不代替权限校验
- 即使某命令未展示，只要用户手动输入，仍会走服务端权限判断
- Telegram 客户端可能存在短暂缓存，命令菜单刷新通常会有几秒延迟

## 备份与恢复

### 自动备份

- 当 `backup.enabled: true` 时，机器人会按 `interval_hours` 定时备份
- 备份前先创建 SQLite 一致性快照，再上传到 WebDAV
- 远端会同时保留带时间戳版本和最新覆盖版本

### 手动备份

- 命令：`/backup`
- 权限：仅 `Bot Admin`

### 手动恢复

- 命令：`/restore`
- 权限：仅 `Bot Admin`
- 恢复前会校验备份数据库完整性

建议：

- WebDAV 建议使用应用密码，不要使用主账号登录密码
- 恢复前最好先做一次现状备份

## 数据存储与运行时覆盖

### 数据库表

| 表名 | 用途 |
|------|------|
| `users` | 用户积分、签到、聊天积分状态 |
| `lotteries` | 抽奖主体、开奖模式、状态、公告消息引用 |
| `lottery_participants` | 抽奖参与记录 |
| `config` | 运行时配置覆盖值和绑定群信息 |

### 运行时配置覆盖规则

- YAML 配置是启动默认值
- 数据库 `config` 表中的覆盖值会在启动时合并到内存配置
- `/settings` 修改的内容会写入 `config` 表
- 数据库覆盖值优先级高于 YAML 同名默认值

## 开发说明

### 处理器注册顺序

[handlers/__init__.py](handlers/__init__.py) 的注册顺序决定消息匹配优先级，不能随意调整：

```python
def register_all_handlers(dp, config):
    register_checkin_handlers(dp, config)
    register_rank_handlers(dp, config)
    register_lottery_handlers(dp, config)
    register_settings_handlers(dp, config)
    register_admin_handlers(dp, config)
    register_chat_handlers(dp, config)
```

原因：

- aiogram 按注册顺序匹配消息
- 如果通用聊天积分 handler 提前注册，会吞掉本该由签到、排行榜、抽奖处理的消息

### 聊天积分排除规则

[handlers/chat.py](handlers/chat.py) 会显式排除以下关键词，避免命令误计分：

```python
EXCLUDED_KEYWORDS = {"签到", "我的签到", "积分", "排行榜", "抽奖"}
```

### 测试

运行全部单元测试：

```powershell
py -m unittest -q
```

当前测试覆盖：

- 数据库迁移与抽奖结算
- 群组绑定与权限判断
- 运行时配置覆盖
- Telegram 命令作用域同步

## 部署与升级建议

### Docker 升级

代码更新后需要重新构建镜像，不建议只重启容器：

```powershell
docker compose build --no-cache
docker compose up -d
```

### 本地升级

```powershell
py -m pip install -r requirements.txt
py -m unittest -q
py bot.py
```

### 升级前检查

- 备份 `data/points_bot.db`
- 备份当前 `config.yaml`
- 若启用了 `/settings`，注意数据库 `config` 表中的覆盖值仍会生效

## 常见问题

### 机器人不响应群内文字命令

检查项：

1. 是否关闭了 `Privacy Mode`
2. 机器人是否已加入目标群
3. 群组是否已经绑定
4. 是否发在已绑定群中

### 抽奖结果没有置顶

通常是因为机器人缺少群管理员置顶权限。功能会自动降级为“只发送结果，不置顶”。

### 自动删除消息没有生效

通常是因为机器人缺少删除消息权限。功能会自动降级，不影响主流程。

### 修改 `config.yaml` 后配置没有变化

如果该配置项之前已经通过 `/settings` 修改过，那么数据库覆盖值优先。此时应：

- 使用 `/settings` 改回目标值
- 或谨慎清理数据库 `config` 表中的对应键

### 备份失败

优先检查：

- `webdav_url`
- `username`
- `password`
- 网络连通性
- WebDAV 是否要求使用应用密码

## 相关文档

- 管理员运维手册：[docs/OPERATIONS.md](docs/OPERATIONS.md)
- 示例配置：[config.example.yaml](config.example.yaml)

# 飞书代理服务（杨维斯）

一个基于 Python 的智能对话代理系统，通过飞书机器人提供 AI 助手服务。该项目集成了 iFlow CLI 作为核心 AI 引擎，支持语音消息识别和智能对话。

## 核心特性

- **飞书集成**：通过飞书开放平台 API 接收和发送消息
- **AI 对话**：使用 iFlow CLI 提供智能对话能力
- **语音识别**：支持语音消息识别，使用 OpenAI Whisper 进行语音转文字
- **扩展系统**：支持动态加载和热重载的自定义扩展
- **对话上下文管理**：基于 SQLite 的对话历史持久化
- **事件去重**：防止重复处理相同事件
- **自动清理**：定期清理过期的事件和对话上下文

## 技术栈

- **后端框架**：FastAPI 0.109.0
- **Web 服务器**：Uvicorn
- **数据库**：SQLite（支持 WAL 模式和连接池）
- **HTTP 客户端**：requests + requests-toolbelt
- **语音识别**：OpenAI Whisper
- **音频处理**：ffmpeg
- **文件监听**：watchdog（用于扩展热重载）
- **配置管理**：python-dotenv
- **Python 版本**：3.12+

## 项目结构

```
/root/feishu_proxy/
├── app.py                      # FastAPI 应用主入口
├── main.py                     # 服务启动脚本
├── config.py                   # 配置管理（环境变量）
├── feishu_client.py            # 飞书 API 客户端
├── llm_client.py               # iFlow CLI 客户端（核心 AI 引擎）
├── database.py                 # SQLite 数据库管理（连接池）
├── extension_loader.py         # 扩展加载器（支持热重载）
├── requirements.txt            # Python 依赖
├── .env                        # 环境变量配置（需自行创建）
├── .env.example                # 环境变量示例
├── extensions/                 # 扩展目录
│   ├── __init__.py
│   ├── README.md               # 扩展开发指南
│   ├── example_extension.py    # 示例扩展（天气查询）
│   ├── weather_extension.py    # 天气查询扩展
│   ├── tea_recommendation_extension.py  # 茶叶推荐扩展
│   ├── paper_recommendation_extension.py # 论文推荐扩展
│   └── message_forward_extension.py     # 消息转发扩展
├── temp/                       # 临时文件目录
└── feishu_proxy.db             # SQLite 数据库文件
```

## 快速开始

### 环境要求

- Python 3.12+
- pip
- ffmpeg（用于音频处理）
- iFlow CLI（需已安装并可用）

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置环境变量

1. 复制 `.env.example` 为 `.env`
2. 编辑 `.env` 文件，填写飞书应用配置：

```bash
cp .env.example .env
vi .env  # 或使用其他编辑器
```

必需配置项：
- `FEISHU_APP_ID`：飞书应用的 App ID
- `FEISHU_APP_SECRET`：飞书应用的 App Secret

可选配置项：
- `FEISHU_VERIFICATION_TOKEN`：URL 验证令牌
- `FEISHU_ENCRYPT_KEY`：加密密钥
- `PROXY_HOST`：服务监听地址（默认：0.0.0.0）
- `PROXY_PORT`：服务监听端口（默认：8000）

### 启动服务

#### 方式一：使用启动脚本（推荐）

```bash
python main.py
```

启动脚本会自动：
- 检查并安装依赖
- 验证配置
- 启动服务

#### 方式二：直接运行

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

#### 方式三：开发模式（支持热重载）

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

### 健康检查

服务启动后，访问 `http://localhost:8000/` 进行健康检查：

```bash
curl http://localhost:8000/
```

预期返回：
```json
{"status": "ok", "service": "feishu-proxy"}
```

## 功能说明

### 文本消息

用户直接发送文本消息，机器人会：
1. 接收消息
2. 调用 iFlow CLI 处理
3. 返回 AI 回复

### 语音消息

用户发送语音消息，机器人会：
1. 接收语音消息
2. 下载音频文件
3. 使用 ffmpeg 转换格式
4. 使用 Whisper 转录为文字
5. 调用 iFlow CLI 处理
6. 返回 AI 回复

**注意**：首次启动时需要下载 Whisper 模型（base 模型约 74MB），可能需要几秒钟。

## 扩展开发

所有自定义功能必须通过扩展系统实现，**禁止修改核心代码文件**。

### 核心代码文件包括：
- `llm_client.py`
- `app.py`
- `feishu_client.py`
- `database.py`
- `config.py`
- `extension_loader.py`

### 扩展开发步骤

1. 在 `extensions/` 目录下创建新的 Python 文件
2. 继承 `ExtensionBase` 类
3. 实现必需方法：
   - `name`：扩展名称（必须唯一）
   - `version`：扩展版本号
   - `description`：扩展描述
   - `can_handle(user_message)`：判断是否可以处理该消息
   - `handle(user_message, conversation_id)`：处理消息并返回结果
4. 可选方法：
   - `on_load()`：扩展加载时调用
   - `on_unload()`：扩展卸载时调用

### 扩展示例

```python
from extension_loader import ExtensionBase

class MyExtension(ExtensionBase):
    @property
    def name(self) -> str:
        return "my_extension"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "我的扩展功能"

    def can_handle(self, user_message: str) -> bool:
        return "关键词" in user_message

    def handle(self, user_message: str, conversation_id: str):
        return "这是扩展的回复"
```

扩展文件修改后会自动热重载，无需重启服务。

详细开发指南请参考 `extensions/README.md`。

## API 接口

### POST /webhook

飞书事件回调接口，接收飞书推送的消息事件。

**请求头**：
- `X-Lark-Request-Timestamp`：请求时间戳
- `X-Lark-Request-Nonce`：随机数
- `X-Lark-Signature`：签名（如果配置了加密密钥）

**请求体**：
```json
{
  "type": "url_verification" | "im.message.receive_v1",
  "header": {
    "event_id": "事件ID",
    "event_type": "事件类型"
  },
  "event": {
    "message": {
      "message_id": "消息ID",
      "chat_id": "对话ID",
      "content": "{\"text\":\"消息内容\"}"
    },
    "sender": {
      "sender_id": {
        "open_id": "发送者ID"
      },
      "sender_type": "user" | "app"
    }
  }
}
```

**响应**：
```json
{
  "code": 0,
  "msg": "success"
}
```

### GET /

健康检查接口。

**响应**：
```json
{
  "status": "ok",
  "service": "feishu-proxy"
}
```

## 数据库表结构

### processed_events

已处理事件表，用于事件去重。

| 字段 | 类型 | 说明 |
|------|------|------|
| event_id | TEXT | 事件 ID（主键） |
| processed_at | TIMESTAMP | 处理时间 |

### conversation_contexts

对话上下文表，用于持久化对话 ID。

| 字段 | 类型 | 说明 |
|------|------|------|
| chat_id | TEXT | 对话 ID（主键） |
| conversation_id | TEXT | iFlow CLI 的对话 ID |
| last_used | TIMESTAMP | 最后使用时间 |

## 自动任务

### 定期清理任务

服务启动后自动执行以下定期任务：

1. **清理旧事件**：每小时清理一次 24 小时前的事件记录
2. **清理过期对话**：每 30 分钟清理一次 2 小时前的对话上下文

## 工具脚本

### get_my_openid.py

获取当前用户的 OpenID。

```bash
python get_my_openid.py
```

### check_db.py

检查数据库状态。

```bash
python check_db.py
```

### send_*.py

各种消息发送测试脚本：
- `send_ai_dialogue.py`：发送 AI 对话
- `send_file_reply.py`：发送文件回复
- `send_markdown.py`：发送 Markdown 消息
- `send_md_file.py`：发送 Markdown 文件
- `send_ppt.py`：发送 PPT

## 常见问题

### 服务无法启动

1. 检查依赖是否安装：`pip install -r requirements.txt`
2. 检查 `.env` 文件是否存在且配置正确
3. 检查端口是否被占用：`lsof -i :8000`
4. 检查 ffmpeg 是否安装：`which ffmpeg`
5. 检查 iFlow CLI 是否可用：`which iflow`

### 飞书消息无法接收

1. 检查飞书应用配置是否正确
2. 检查 webhook URL 是否正确配置在飞书管理后台
3. 检查服务日志：`tail -f feishu_proxy.log`

### 扩展未加载

1. 检查扩展文件是否在 `extensions/` 目录下
2. 检查扩展是否继承 `ExtensionBase` 类
3. 检查扩展名称是否唯一
4. 查看服务日志中的错误信息

### 语音识别失败

1. 检查 ffmpeg 是否安装：`which ffmpeg`
2. 检查 Whisper 是否安装：`pip list | grep whisper`
3. 检查临时目录权限：`ls -la temp/`
4. 查看服务日志中的错误信息

## 扩展示例

项目内置了多个扩展示例，可供参考：

- **weather_extension.py**：天气查询扩展
- **tea_recommendation_extension.py**：茶叶推荐扩展
- **paper_recommendation_extension.py**：论文推荐扩展
- **message_forward_extension.py**：消息转发扩展

详细代码请参考 `extensions/` 目录。

## 安全规范

**禁止操作**（必须严格遵守）：
- 禁止执行任何重启系统（reboot、shutdown、poweroff 等）的操作
- 禁止执行任何重启代理服务（proxy）的操作
- 禁止修改任何核心代码文件
- 禁止在代码中记录或提交敏感信息（API 密钥、密码等）

## 许可证

本项目为内部项目，仅供授权用户使用。

## 联系方式

如有问题，请联系项目维护者。
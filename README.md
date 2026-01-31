# Feishu Proxy

一个基于 FastAPI 和 LLM 的飞书智能代理服务，支持多扩展集成和智能消息路由。

## 🎯 功能特点

### 核心功能
- **智能消息路由**：自动将用户消息路由到合适的扩展处理
- **飞书消息处理**：支持文本、Markdown、文件等多种消息类型
- **多扩展系统**：支持热重载的扩展机制
- **数据库管理**：SQLite 数据库存储对话上下文和事件记录
- **环境配置**：基于 `.env` 文件的配置管理

### 内置扩展
- **天气查询**：使用 wttr.in 免费服务，支持中文城市
- **AI 论文推荐**：从 arXiv 获取最新的 AI Agent 论文并生成中文摘要
- **茶饮推荐**：基于时间、天气和用户需求智能推荐合适的茶饮

## 🚀 快速开始

### 环境要求
- Python 3.8+
- 飞书企业自建应用
- iFlow CLI（用于智能路由判断）

### 安装步骤

1. **克隆代码库**
   ```bash
   git clone <repository-url>
   cd feishu_proxy_release
   ```

2. **创建虚拟环境**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS/Linux
   source venv/bin/activate
   ```

3. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

4. **配置环境变量**
   ```bash
   cp .env.example .env
   # 编辑 .env 文件，填写飞书应用配置
   ```

5. **启动服务**
   ```bash
   python main.py
   ```

### 飞书应用配置

1. **创建飞书企业自建应用**
   - 访问 [飞书开放平台](https://open.feishu.cn)
   - 创建企业自建应用
   - 启用机器人能力

2. **配置应用权限**
   - 消息权限：`im:message:send_as_bot`
   - 事件订阅：`im.message.receive_v1`

3. **设置事件回调**
   - 回调地址：`http://your-server:8000/webhook`
   - 验证令牌：与 `.env` 文件中的 `FEISHU_VERIFICATION_TOKEN` 一致

## 📁 项目结构

```
feishu_proxy_release/
├── extensions/          # 扩展目录
│   ├── README.md        # 扩展说明
│   ├── __init__.py      # 扩展初始化
│   ├── example_extension.py     # 示例扩展
│   ├── paper_recommendation_extension.py  # 论文推荐扩展
│   ├── tea_recommendation_extension.py    # 茶饮推荐扩展
│   └── weather_extension.py      # 天气查询扩展
├── .env.example         # 环境变量模板
├── .gitignore           # Git 忽略规则
├── LICENSE              # MIT 许可证
├── README.md            # 项目说明
├── __init__.py          # 包初始化
├── app.py               # FastAPI 应用
├── config.py            # 配置管理
├── database.py          # 数据库管理
├── extension_loader.py  # 扩展加载器
├── feishu_client.py     # 飞书客户端
├── llm_client.py        # LLM 客户端
├── main.py              # 启动脚本
└── requirements.txt     # 依赖列表
```

## 📖 使用指南

### 发送消息

在飞书中向机器人发送消息，系统会根据消息内容自动路由到合适的扩展处理：

- **天气查询**："北京今天天气怎么样？"
- **论文推荐**："推荐最近的 AI Agent 论文"
- **茶饮推荐**："现在适合喝什么茶？"

### 扩展开发

1. **创建扩展文件**：在 `extensions/` 目录创建新的扩展文件
2. **继承基类**：继承 `ExtensionBase` 类
3. **实现方法**：实现 `name`、`description`、`handle` 等方法
4. **热重载**：修改扩展后会自动热重载，无需重启服务

### 示例扩展

```python
from extension_loader import ExtensionBase

class ExampleExtension(ExtensionBase):
    @property
    def name(self) -> str:
        return "example"

    @property
    def description(self) -> str:
        return "示例扩展，用于演示扩展开发"

    def handle(self, user_message: str, conversation_id: str) -> str:
        return f"你好！这是示例扩展的回复：{user_message}"
```

## 🔧 配置说明

### 环境变量配置

编辑 `.env` 文件，填写以下配置：

```dotenv
# 飞书应用配置
FEISHU_APP_ID=your_app_id_here
FEISHU_APP_SECRET=your_app_secret_here
FEISHU_VERIFICATION_TOKEN=your_verification_token_here
FEISHU_ENCRYPT_KEY=your_encrypt_key_here

# 代理服务配置
PROXY_HOST=0.0.0.0
PROXY_PORT=8000

# 日志配置
LOG_FILE=feishu_proxy.log

# iFlow CLI 配置
IFLOW_API_URL=http://localhost:8080
```

### 扩展配置

- **天气扩展**：无需额外配置，使用 wttr.in 免费服务
- **论文推荐扩展**：无需额外配置，使用 arXiv 免费 API
- **茶饮推荐扩展**：纯本地逻辑，无需外部服务

## 📈 性能优化

- **SQLite WAL 模式**：启用 Write-Ahead Logging 提升并发性能
- **连接池**：使用连接池管理数据库连接
- **热重载**：扩展支持热重载，无需重启服务
- **事件去重**：避免重复处理相同事件

## 🐛 常见问题

### 服务启动失败
- 检查飞书应用配置是否正确
- 检查环境变量是否配置完整
- 检查依赖是否安装成功

### 消息不响应
- 检查飞书应用权限是否正确
- 检查事件回调是否配置成功
- 检查网络连接是否正常

### 扩展不工作
- 检查扩展文件是否正确放置在 `extensions/` 目录
- 检查扩展类是否正确继承 `ExtensionBase`
- 检查扩展方法是否正确实现

## 🤝 贡献

欢迎贡献代码、报告问题或提出建议！

### 开发流程
1. Fork 代码库
2. 创建分支
3. 提交更改
4. 发起 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 📞 联系我们

- 如有问题，请在 GitHub Issues 中提出
- 欢迎加入我们的开发讨论

---

**享受智能飞书代理服务！** 🎉
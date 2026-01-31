# 杨维斯扩展开发指南

## 简介

扩展系统允许你为杨维斯添加自定义功能，而无需修改核心代码。所有扩展都会自动加载，修改后自动热重载，无需重启服务。

## 快速开始

1. 在 `extensions/` 目录下创建一个新的 Python 文件（例如 `my_extension.py`）
2. 继承 `ExtensionBase` 类
3. 实现必需的方法
4. 保存文件，扩展会自动加载

## 扩展模板

```python
from extension_loader import ExtensionBase

class MyExtension(ExtensionBase):
    """我的自定义扩展"""

    @property
    def name(self) -> str:
        """扩展名称（必须唯一）"""
        return "my_extension"

    @property
    def version(self) -> str:
        """扩展版本号"""
        return "1.0.0"

    @property
    def description(self) -> str:
        """扩展描述"""
        return "我的扩展功能描述"

    def can_handle(self, user_message: str) -> bool:
        """
        判断是否可以处理该消息

        Args:
            user_message: 用户消息内容

        Returns:
            bool: 返回 True 表示可以处理该消息
        """
        # 在这里编写你的判断逻辑
        return "关键词" in user_message

    def handle(self, user_message: str, conversation_id: str):
        """
        处理用户消息

        Args:
            user_message: 用户消息内容
            conversation_id: 对话ID

        Returns:
            str: 返回处理结果
        """
        # 在这里编写你的处理逻辑
        return "这是扩展的回复"

    def on_load(self):
        """扩展加载时调用（可选）"""
        print(f"{self.name} 加载成功")

    def on_unload(self):
        """扩展卸载时调用（可选）"""
        print(f"{self.name} 卸载")
```

## 方法说明

### 必需实现的方法

| 方法 | 说明 |
|------|------|
| `name` | 扩展名称，必须唯一 |
| `version` | 扩展版本号 |
| `description` | 扩展描述 |
| `can_handle(user_message)` | 判断是否可以处理该消息 |
| `handle(user_message, conversation_id)` | 处理消息并返回结果 |

### 可选实现的方法

| 方法 | 说明 |
|------|------|
| `on_load()` | 扩展加载时调用 |
| `on_unload()` | 扩展卸载时调用 |

## 扩展执行流程

1. 用户发送消息
2. 系统依次调用每个扩展的 `can_handle()` 方法
3. 找到第一个返回 `True` 的扩展
4. 调用该扩展的 `handle()` 方法
5. 返回处理结果给用户
6. 如果所有扩展都不处理，则使用默认的 iFlow CLI 处理

## 注意事项

1. **扩展名称必须唯一**：如果名称重复，后加载的扩展会替换先加载的
2. **避免耗时操作**：`handle()` 方法会阻塞消息处理，请避免长时间运行的操作
3. **错误处理**：在 `handle()` 中使用 try-except 捕获异常
4. **热重载**：修改扩展文件后会自动重载，无需重启服务
5. **删除扩展**：删除扩展文件后会自动卸载

## 示例扩展

查看 `example_extension.py` 获取完整示例。

## 常见使用场景

- 特定领域的问答（如天气、股票、新闻）
- 自定义命令处理
- 外部 API 集成
- 数据库查询
- 文件操作

## 扩展管理

### 查看已加载的扩展

在 Python 代码中：
```python
from llm_client import llm_client
extensions = llm_client.extension_loader.list_extensions()
print(extensions)
```

### 手动重载扩展

扩展会自动热重载，但如果需要手动重载：
```python
llm_client.extension_loader.load_all()
```

## 技术细节

- 扩展文件使用 Python 的 `importlib` 动态加载
- 文件监听使用 `watchdog` 库实现热重载
- 扩展按文件名顺序加载，第一个匹配的扩展优先处理
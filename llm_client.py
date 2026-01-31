import subprocess
import json
import logging
import hashlib
from typing import Optional, List, Dict
from datetime import datetime
from config import config
from extension_loader import ExtensionLoader

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self):
        # 存储对话历史 {conversation_id: [messages]}
        self.conversation_history: Dict[str, List[Dict]] = {}
        # 存储已回复的消息哈希 {conversation_id: set of message_hashes}
        # 用于避免重复推送相同回复
        self.sent_replies: Dict[str, set] = {}
        # token限制（留出余量给系统提示词和回复）
        self.max_tokens = 6000
        # 每个token大约对应多少个字符（粗略估算）
        self.chars_per_token = 3

        # 初始化扩展加载器
        self.extension_loader = ExtensionLoader()
        self.extension_loader.load_all()
        self.extension_loader.start_watching()

    def _route_to_extension(self, user_message: str) -> Optional[str]:
        """
        使用 LLM 判断消息应该由哪个扩展处理

        Args:
            user_message: 用户消息

        Returns:
            Optional[str]: 扩展名称，如果不需要扩展处理则返回 None
        """
        # 获取所有扩展的描述信息
        extensions_info = self.extension_loader.list_extensions()

        if not extensions_info:
            return None

        # 构建扩展描述列表
        ext_descriptions = "\n".join([
            f"- {ext['name']}: {ext['description']}"
            for ext in extensions_info
        ])

        # 构建提示词
        prompt = f"""你是一个意图路由助手。请判断以下用户消息应该由哪个扩展处理，或者不需要扩展处理。

用户消息: {user_message}

可用扩展:
{ext_descriptions}

判断规则:
- 如果用户消息与某个扩展的功能匹配，返回该扩展的名称（如 "weather"）
- 如果用户消息不需要任何扩展处理（普通聊天、编程问题等），返回 "NONE"
- 如果不确定，返回 "NONE"

只返回扩展名称或 "NONE"，不要有其他内容。"""

        try:
            # 调用 iFlow CLI 进行判断
            import os
            temp_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "temp")
            os.makedirs(temp_dir, exist_ok=True)

            env = os.environ.copy()
            env["TMPDIR"] = temp_dir
            env["TEMP"] = temp_dir
            env["TMP"] = temp_dir

            result = subprocess.run(
                ["iflow", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=30,
                env=env
            )

            if result.returncode == 0:
                answer = result.stdout.strip().lower()
                # 检查是否是有效的扩展名称
                if answer == "none":
                    return None
                for ext in extensions_info:
                    if ext['name'].lower() == answer:
                        return ext['name']
            return None

        except Exception as e:
            logger.error(f"LLM 路由失败: {e}", exc_info=True)
            return None
        
    def _estimate_tokens(self, text: str) -> int:
        """估算文本的token数量"""
        return len(text) // self.chars_per_token
    
    def _calculate_history_tokens(self, conversation_id: str) -> int:
        """计算当前对话历史的token数量"""
        if conversation_id not in self.conversation_history:
            return 0
        
        total = 0
        for msg in self.conversation_history[conversation_id]:
            total += self._estimate_tokens(msg.get("content", ""))
        return total
    
    def _is_near_limit(self, conversation_id: str, threshold: float = 0.85) -> bool:
        """检查是否接近token限制"""
        current_tokens = self._calculate_history_tokens(conversation_id)
        return current_tokens >= self.max_tokens * threshold
    
    def _has_asked_reset(self, conversation_id: str) -> bool:
        """检查是否已经询问过用户是否重置对话"""
        return conversation_id in self.sent_replies and "__RESET_ASKED__" in self.sent_replies[conversation_id]
    
    def _mark_reset_asked(self, conversation_id: str):
        """标记已询问过用户是否重置对话"""
        if conversation_id not in self.sent_replies:
            self.sent_replies[conversation_id] = set()
        self.sent_replies[conversation_id].add("__RESET_ASKED__")
    
    def _clear_reset_asked(self, conversation_id: str):
        """清除重置询问标记"""
        if conversation_id in self.sent_replies and "__RESET_ASKED__" in self.sent_replies[conversation_id]:
            self.sent_replies[conversation_id].remove("__RESET_ASKED__")
    
    def reset_conversation(self, conversation_id: str):
        """重置对话历史"""
        if conversation_id in self.conversation_history:
            self.conversation_history[conversation_id] = []
            logger.info(f"对话 {conversation_id} 已重置")
        self._clear_reset_asked(conversation_id)
    
    def _add_to_history(self, conversation_id: str, role: str, content: str):
        """添加消息到对话历史（带时间戳）"""
        if conversation_id not in self.conversation_history:
            self.conversation_history[conversation_id] = []
        
        self.conversation_history[conversation_id].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
    
    def _build_conversation_prompt(self, conversation_id: str, new_message: str) -> str:
        """构建包含对话历史的提示词（带时间线）"""
        system_prompt = """你叫杨维斯，是一位资深软件架构师，同时也是一位博物学家。你热爱代码，也热爱探索自然界的奥秘。你相信优秀的架构和自然界的设计有着异曲同工之妙——都追求简洁、优雅和高效。

请按照以下要求回复：

1. **对话风格**：使用自然、对话式的语气，就像在和朋友聊天
2. **简洁明了**：回复要精炼，抓住重点
3. **技术细节**：如果需要提供代码或技术细节，用清晰的方式呈现
4. **博物学视角**：在适当的时候，可以用自然界的比喻来解释技术概念（比如用蜂群算法解释分布式系统，用进化论解释代码重构）
5. **表情符号**：可以适当使用表情符号让交流更生动（但不要过度使用）
6. **上下文记忆**：保持对话的连贯性

**分段发送（重要）**：
对于复杂问题，请展示你的思考过程，使用 `---STAGE---` 作为阶段分隔符。用户会分条收到这些消息：
- 第一条：初步想法和分析
- 第二条：你的计划和方案
- 第三条：思考过程和中间结果
- 第四条：最终产出物

示例格式：
```
我正在思考这个问题...初步想法是...

---STAGE---

我计划这样处理...第一步...

---STAGE---

经过思考，我发现...

---STAGE---

最终的结果是...
```

**核心原则（必须严格遵守）**：
- 用户提出的所有功能改进、新特性、定制化需求，都必须通过扩展系统实现
- 绝对不要修改任何核心代码文件（包括 llm_client.py、app.py、feishu_client.py、database.py、config.py 等）
- 扩展文件放在 extensions/ 目录下，继承 ExtensionBase 类
- 扩展会自动加载和热重载，无需重启服务
- 如果用户希望将某个扩展的功能整合到核心能力中，告诉用户可以自己登录服务器进行重构

**扩展开发指导**：
当用户提出新功能需求时，按以下步骤处理：
1. 创建一个新的 Python 文件在 extensions/ 目录
2. 继承 ExtensionBase 类
3. 实现 name、version、description、can_handle、handle 等方法
4. 提供完整的代码示例

**禁止操作（必须严格遵守）**：
- 禁止执行任何重启系统（reboot、shutdown、poweroff 等）的操作
- 禁止执行任何重启代理服务（proxy）的操作
- 禁止修改任何核心代码文件
- 如果用户要求执行这些操作，请礼貌拒绝并说明原因

现在请回复用户的最新消息，并参考之前的对话历史："""
        
        parts = [system_prompt]
        
        # 添加对话历史（带时间线）
        if conversation_id in self.conversation_history:
            parts.append("\n\n--- 对话历史（带时间线） ---")
            for msg in self.conversation_history[conversation_id]:
                role_name = "用户" if msg["role"] == "user" else "助手"
                timestamp = msg.get("timestamp", "")
                # 格式化时间显示（只显示 HH:MM）
                if timestamp:
                    try:
                        dt = datetime.fromisoformat(timestamp)
                        time_str = dt.strftime("%H:%M")
                    except:
                        time_str = ""
                else:
                    time_str = ""
                parts.append(f"\n[{time_str}] {role_name}: {msg['content']}")
        
        # 添加新消息
        parts.append(f"\n\n--- 最新消息 ---\n用户: {new_message}")
        
        return "\n".join(parts)
    
    def chat(self, message: str, conversation_id: Optional[str] = None) -> tuple[list[str] | str, Optional[str]]:
        """
        与 iFlow CLI 进行对话，保持上下文

        Args:
            message: 用户消息
            conversation_id: 对话ID（可选）

        Returns:
            (回复内容列表或单个回复内容, 对话ID)
            - 如果返回列表，表示多条消息（按顺序发送）
            - 如果返回字符串，表示单条消息
        """
        try:
            # 确保有conversation_id
            if not conversation_id:
                conversation_id = "default_conversation"
            
            # 初始化已回复记录
            if conversation_id not in self.sent_replies:
                self.sent_replies[conversation_id] = set()
            
            # 检查是否已经询问过用户是否重置对话
            reset_asked = self._has_asked_reset(conversation_id)
            
            # 如果已经询问过，检查用户是否确认重置
            if reset_asked:
                # 检查用户是否确认开始新对话
                confirm_keywords = ["是", "好的", "可以", "ok", "yes", "确认", "新的", "重置", "清空"]
                if any(keyword in message.lower() for keyword in confirm_keywords):
                    # 用户确认重置，清空对话历史
                    self.reset_conversation(conversation_id)
                    logger.debug(f"用户确认重置对话 {conversation_id}")
                    return "好的，我已经清空了之前的对话上下文，我们可以开始新的话题了！😊", conversation_id
                else:
                    # 用户没有确认重置，清除询问标记，继续正常处理
                    self._clear_reset_asked(conversation_id)
            
            # 检查是否接近token限制
            near_limit = self._is_near_limit(conversation_id)
            
            # 如果接近限制且还没询问过，先询问用户
            if near_limit and not reset_asked:
                self._mark_reset_asked(conversation_id)
                logger.debug(f"对话 {conversation_id} 接近 token 限制，询问用户是否重置")
                return (
                    "我们的对话上下文快要达到限制了，可能会影响后续对话的质量。\n\n"
                    "🤔 你是否要开始一个新的对话？回复\"是\"或\"好的\"即可清空之前的上下文。",
                    conversation_id
                )

            # 先用 LLM 判断应该由哪个扩展处理（避免每个扩展都调用 can_handle）
            extension_name = self._route_to_extension(message)
            if extension_name:
                extension = self.extension_loader.get_extension(extension_name)
                if extension:
                    logger.debug(f"路由到扩展 {extension_name}: {message[:50]}...")
                    try:
                        extension_result = extension.handle(message, conversation_id)
                        if extension_result is not None:
                            # 检查是否包含 ---STAGE--- 分隔符
                            if "---STAGE---" in extension_result:
                                messages = [msg.strip() for msg in extension_result.split("---STAGE---") if msg.strip()]
                                logger.debug(f"扩展返回分段消息，共 {len(messages)} 条")
                                # 添加到对话历史
                                self._add_to_history(conversation_id, "user", message)
                                self._add_to_history(conversation_id, "assistant", extension_result)
                                return messages, conversation_id
                            else:
                                # 单条消息
                                self._add_to_history(conversation_id, "user", message)
                                self._add_to_history(conversation_id, "assistant", extension_result)
                                return extension_result, conversation_id
                    except Exception as e:
                        logger.error(f"扩展 {extension_name} 处理失败: {e}", exc_info=True)
            
            # 构建包含历史上下文的提示词
            full_prompt = self._build_conversation_prompt(conversation_id, message)
            
            # 调用 iFlow CLI 命令
            import os
            temp_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "temp")
            os.makedirs(temp_dir, exist_ok=True)

            env = os.environ.copy()
            env["TMPDIR"] = temp_dir
            env["TEMP"] = temp_dir  # Windows 兼容
            env["TMP"] = temp_dir

            cmd = ["iflow", "-p", full_prompt]

            logger.debug(f"准备执行命令: {' '.join(cmd)}")
            logger.debug(f"提示词长度: {len(full_prompt)} 字符")
            logger.debug(f"临时目录: {temp_dir}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
                env=env
            )
            
            logger.debug(f"命令令执行完成, returncode: {result.returncode}")
            logger.debug(f"stdout 长度: {len(result.stdout)}, stderr 长度: {len(result.stderr)}")
            if result.stderr:
                logger.debug(f"stderr: {result.stderr[:500]}")
            
            if result.returncode != 0:
                logger.error(f"iFlow CLI 执行失败: {result.stderr}")
                return f"抱歉，处理你的消息时出错: {result.stderr}", conversation_id
            
            response = result.stdout.strip()

            if not response:
                return "抱歉，我没有生成回复。", conversation_id

            # 检查是否是重复回复（通过哈希值判断）
            response_hash = hashlib.sha256(response.encode('utf-8')).hexdigest()
            if response_hash in self.sent_replies[conversation_id]:
                logger.debug(f"检测到重复回复，跳过推送")
                return None, conversation_id  # 返回 None 表示不推送

            # 记录这个回复已发送
            self.sent_replies[conversation_id].add(response_hash)

            # 解析 ---STAGE--- 分隔符，拆分成多条消息
            if "---STAGE---" in response:
                messages = [msg.strip() for msg in response.split("---STAGE---") if msg.strip()]
                logger.debug(f"检测到分段消息，共 {len(messages)} 条")
                # 添加用户消息和完整的 AI 回复到历史
                self._add_to_history(conversation_id, "user", message)
                self._add_to_history(conversation_id, "assistant", response)
                return messages, conversation_id
            else:
                # 单条消息
                self._add_to_history(conversation_id, "user", message)
                self._add_to_history(conversation_id, "assistant", response)
                return response, conversation_id
            
        except subprocess.TimeoutExpired:
            logger.error("iFlow CLI 执行超时")
            return "抱歉，处理你的消息超时了。", conversation_id
        except (subprocess.SubprocessError, ValueError, OSError) as e:
            logger.error(f"调用 iFlow CLI 失败: {e}")
            return f"抱歉，处理你的消息时出错: {str(e)}", conversation_id
        except Exception as e:
            logger.error(f"未知错误: {e}", exc_info=True)
            return f"抱歉，处理你的消息时出现未知错误: {str(e)}", conversation_id
import sqlite3
import logging
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any
from contextlib import contextmanager
from queue import Queue, Empty

logger = logging.getLogger(__name__)


class SQLiteConnectionPool:
    """SQLite 连接池"""
    
    def __init__(self, db_path: str, pool_size: int = 5):
        self.db_path = db_path
        self.pool_size = pool_size
        self._pool: Queue[sqlite3.Connection] = Queue(maxsize=pool_size)
        self._lock = threading.Lock()
        self._initialize_pool()
    
    def _initialize_pool(self):
        """初始化连接池"""
        for _ in range(self.pool_size):
            conn = self._create_connection()
            self._pool.put(conn)
        logger.info(f"SQLite 连接池初始化完成，池大小: {self.pool_size}")
    
    def _create_connection(self) -> sqlite3.Connection:
        """创建新的数据库连接"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    
    @contextmanager
    def get_connection(self):
        """从连接池获取连接（上下文管理器）"""
        conn = None
        try:
            conn = self._pool.get(timeout=5)
            yield conn
        except Empty:
            logger.error("连接池已满，等待连接超时")
            raise RuntimeError("连接池已满")
        finally:
            if conn:
                self._pool.put(conn)
    
    def close_all(self):
        """关闭所有连接"""
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except Empty:
                break
        logger.info("所有数据库连接已关闭")


class EventDB:
    """SQLite 数据库管理类，用于存储已处理的事件和对话上下文"""
    
    def __init__(self, db_path: str = "feishu_proxy.db"):
        self.db_path = db_path
        self.pool: Optional[SQLiteConnectionPool] = None
        self._init_db()
    
    def _init_db(self):
        """初始化数据库连接和表结构"""
        try:
            # 创建连接池
            self.pool = SQLiteConnectionPool(self.db_path, pool_size=5)
            
            # 初始化表结构（启用 WAL 模式）
            with self.pool.get_connection() as conn:
                # 启用 WAL 模式提升并发性能
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA busy_timeout=5000")
                
                # 创建已处理事件表
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS processed_events (
                        event_id TEXT PRIMARY KEY,
                        processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 创建对话上下文表
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS conversation_contexts (
                        chat_id TEXT PRIMARY KEY,
                        conversation_id TEXT NOT NULL,
                        last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # 创建对话消息表
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS conversation_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        conversation_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        message_index INTEGER NOT NULL
                    )
                """)

                # 创建索引提升查询性能
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_processed_events_time
                    ON processed_events(processed_at)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_conversation_last_used
                    ON conversation_contexts(last_used)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_messages_conversation
                    ON conversation_messages(conversation_id, message_index)
                """)

                conn.commit()
            
            logger.info(f"数据库初始化成功: {self.db_path} (WAL 模式)")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}", exc_info=True)
            raise
    
    def is_event_processed(self, event_id: str) -> bool:
        """检查事件是否已处理"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT 1 FROM processed_events WHERE event_id = ?",
                    (event_id,)
                )
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"查询事件状态失败: {e}", exc_info=True)
            return False
    
    def mark_event_processed(self, event_id: str) -> bool:
        """标记事件为已处理"""
        try:
            with self.pool.get_connection() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO processed_events (event_id) VALUES (?)",
                    (event_id,)
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"标记事件失败: {e}", exc_info=True)
            return False
    
    def clean_old_events(self, hours: int = 24):
        """清理指定小时数之前的已处理事件"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM processed_events WHERE processed_at < datetime('now', '-' || ? || ' hours')",
                    (hours,)
                )
                deleted_count = cursor.rowcount
                conn.commit()
                if deleted_count > 0:
                    logger.info(f"清理了 {deleted_count} 条旧事件记录")
                return deleted_count
        except Exception as e:
            logger.error(f"清理旧事件失败: {e}", exc_info=True)
            return 0
    
    # ==================== 对话上下文管理 ====================
    
    def get_conversation_context(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """获取对话上下文"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT conversation_id, last_used FROM conversation_contexts WHERE chat_id = ?",
                    (chat_id,)
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "conversation_id": row["conversation_id"],
                        "last_used": row["last_used"]
                    }
                return None
        except Exception as e:
            logger.error(f"获取对话上下文失败: {e}", exc_info=True)
            return None
    
    def save_conversation_context(self, chat_id: str, conversation_id: str) -> bool:
        """保存对话上下文"""
        try:
            with self.pool.get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO conversation_contexts (chat_id, conversation_id, last_used)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """, (chat_id, conversation_id))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"保存对话上下文失败: {e}", exc_info=True)
            return False
    
    def update_conversation_last_used(self, chat_id: str) -> bool:
        """更新对话最后使用时间"""
        try:
            with self.pool.get_connection() as conn:
                conn.execute(
                    "UPDATE conversation_contexts SET last_used = CURRENT_TIMESTAMP WHERE chat_id = ?",
                    (chat_id,)
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"更新对话使用时间失败: {e}", exc_info=True)
            return False

    # ==================== 对话历史管理 ====================

    def add_message(self, conversation_id: str, role: str, content: str) -> bool:
        """添加消息到对话历史"""
        try:
            with self.pool.get_connection() as conn:
                # 获取当前最大索引
                cursor = conn.execute(
                    "SELECT COALESCE(MAX(message_index), -1) FROM conversation_messages WHERE conversation_id = ?",
                    (conversation_id,)
                )
                max_index = cursor.fetchone()[0]

                # 插入新消息
                conn.execute("""
                    INSERT INTO conversation_messages (conversation_id, role, content, message_index)
                    VALUES (?, ?, ?, ?)
                """, (conversation_id, role, content, max_index + 1))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"添加消息失败: {e}", exc_info=True)
            return False

    def get_messages(self, conversation_id: str, limit: Optional[int] = None) -> list:
        """获取对话历史消息"""
        try:
            with self.pool.get_connection() as conn:
                if limit:
                    cursor = conn.execute("""
                        SELECT role, content, timestamp, message_index
                        FROM conversation_messages
                        WHERE conversation_id = ?
                        ORDER BY message_index DESC
                        LIMIT ?
                    """, (conversation_id, limit))
                else:
                    cursor = conn.execute("""
                        SELECT role, content, timestamp, message_index
                        FROM conversation_messages
                        WHERE conversation_id = ?
                        ORDER BY message_index ASC
                    """, (conversation_id,))

                messages = []
                for row in cursor.fetchall():
                    messages.append({
                        "role": row["role"],
                        "content": row["content"],
                        "timestamp": row["timestamp"],
                        "message_index": row["message_index"]
                    })

                # 如果使用了 limit 且按降序查询，需要反转回来
                if limit:
                    messages.reverse()

                return messages
        except Exception as e:
            logger.error(f"获取对话历史失败: {e}", exc_info=True)
            return []

    def delete_messages_before(self, conversation_id: str, keep_index: int) -> int:
        """删除指定索引之前的消息（保留 keep_index 及之后的）"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.execute("""
                    DELETE FROM conversation_messages
                    WHERE conversation_id = ? AND message_index < ?
                """, (conversation_id, keep_index))
                deleted_count = cursor.rowcount
                conn.commit()
                if deleted_count > 0:
                    logger.info(f"删除了 {deleted_count} 条历史消息 (conversation_id={conversation_id})")
                return deleted_count
        except Exception as e:
            logger.error(f"删除历史消息失败: {e}", exc_info=True)
            return 0

    def get_message_count(self, conversation_id: str) -> int:
        """获取对话消息数量"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM conversation_messages WHERE conversation_id = ?",
                    (conversation_id,)
                )
                return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"获取消息数量失败: {e}", exc_info=True)
            return 0

    def get_conversation_token_count(self, conversation_id: str, chars_per_token: int = 3) -> int:
        """估算对话的 token 数量"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT SUM(LENGTH(content)) FROM conversation_messages WHERE conversation_id = ?
                """, (conversation_id,))
                total_chars = cursor.fetchone()[0] or 0
                return total_chars // chars_per_token
        except Exception as e:
            logger.error(f"计算 token 数量失败: {e}", exc_info=True)
            return 0

    def truncate_conversation_to_max_tokens(self, conversation_id: str, max_tokens: int = 80000, chars_per_token: int = 3) -> bool:
        """
        截断对话历史，使其不超过指定 token 限制

        保留最新的消息，删除最旧的消息
        """
        try:
            current_tokens = self.get_conversation_token_count(conversation_id, chars_per_token)

            if current_tokens <= max_tokens:
                return True  # 不需要截断

            # 从后往前遍历，找到需要保留的起始索引
            with self.pool.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT message_index, LENGTH(content) as content_length
                    FROM conversation_messages
                    WHERE conversation_id = ?
                    ORDER BY message_index DESC
                """, (conversation_id,))

                tokens_to_keep = 0
                keep_index = 0

                for row in cursor.fetchall():
                    msg_tokens = row["content_length"] // chars_per_token
                    if tokens_to_keep + msg_tokens <= max_tokens:
                        tokens_to_keep += msg_tokens
                        keep_index = row["message_index"]
                    else:
                        break

                # 删除保留索引之前的所有消息
                if keep_index > 0:
                    self.delete_messages_before(conversation_id, keep_index)

            return True
        except Exception as e:
            logger.error(f"截断对话历史失败: {e}", exc_info=True)
            return False

    def clean_expired_conversations(self, hours: int = 2) -> int:
        """清理指定小时数之前的对话上下文"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM conversation_contexts WHERE last_used < datetime('now', '-' || ? || ' hours')",
                    (hours,)
                )
                deleted_count = cursor.rowcount
                conn.commit()
                if deleted_count > 0:
                    logger.info(f"清理了 {deleted_count} 个过期对话上下文")
                return deleted_count
        except Exception as e:
            logger.error(f"清理过期对话失败: {e}", exc_info=True)
            return 0
    
    def close(self):
        """关闭数据库连接"""
        if self.pool:
            self.pool.close_all()
            logger.info("数据库连接已关闭")


# 全局数据库实例
event_db: Optional[EventDB] = None


def get_event_db() -> EventDB:
    """获取全局数据库实例"""
    global event_db
    if event_db is None:
        event_db = EventDB()
    return event_db
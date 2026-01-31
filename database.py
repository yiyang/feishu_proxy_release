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
                
                # 创建索引提升查询性能
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_processed_events_time 
                    ON processed_events(processed_at)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_conversation_last_used 
                    ON conversation_contexts(last_used)
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
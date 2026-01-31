import os
import importlib
import importlib.util
import logging
from typing import Dict, List, Optional, Callable, Any
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class ExtensionBase(ABC):
    """扩展基类，所有用户扩展必须继承此类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """扩展名称"""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """扩展版本"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """扩展描述"""
        pass

    @abstractmethod
    def can_handle(self, user_message: str) -> bool:
        """
        判断是否可以处理该消息

        Args:
            user_message: 用户消息

        Returns:
            bool: 是否可以处理
        """
        pass

    @abstractmethod
    def handle(self, user_message: str, conversation_id: str) -> Optional[str]:
        """
        处理用户消息

        Args:
            user_message: 用户消息
            conversation_id: 对话ID

        Returns:
            Optional[str]: 处理结果，如果返回 None 则表示不处理
        """
        pass

    def on_load(self):
        """扩展加载时调用"""
        logger.info(f"扩展 {self.name} (v{self.version}) 加载成功")

    def on_unload(self):
        """扩展卸载时调用"""
        logger.info(f"扩展 {self.name} (v{self.version}) 卸载")


class ExtensionFileHandler(FileSystemEventHandler):
    """文件系统事件处理器，用于监听扩展文件变化"""

    def __init__(self, loader: 'ExtensionLoader'):
        self.loader = loader

    def on_created(self, event: FileCreatedEvent):
        if not event.is_directory and event.src_path.endswith('.py'):
            logger.info(f"检测到新扩展文件: {event.src_path}")
            self.loader.load_extension(event.src_path)

    def on_modified(self, event: FileModifiedEvent):
        if not event.is_directory and event.src_path.endswith('.py'):
            logger.info(f"检测到扩展文件修改: {event.src_path}")
            self.loader.reload_extension(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory and event.src_path.endswith('.py'):
            logger.info(f"检测到扩展文件删除: {event.src_path}")
            self.loader.unload_extension(event.src_path)


class ExtensionLoader:
    """扩展加载器，支持动态加载和热重载"""

    def __init__(self, extensions_dir: str = "extensions"):
        self.extensions_dir = Path(extensions_dir)
        self.extensions: Dict[str, ExtensionBase] = {}
        self.extension_modules: Dict[str, Any] = {}
        self.observer: Optional[Observer] = None

        # 确保扩展目录存在
        self.extensions_dir.mkdir(exist_ok=True)

    def load_all(self):
        """加载所有扩展"""
        if not self.extensions_dir.exists():
            logger.warning(f"扩展目录不存在: {self.extensions_dir}")
            return

        for file_path in self.extensions_dir.glob("*.py"):
            if file_path.name.startswith("_"):
                continue
            self.load_extension(str(file_path))

        logger.info(f"已加载 {len(self.extensions)} 个扩展")

    def load_extension(self, file_path: str) -> bool:
        """
        加载单个扩展

        Args:
            file_path: 扩展文件路径

        Returns:
            bool: 是否加载成功
        """
        try:
            module_name = Path(file_path).stem
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                logger.error(f"无法加载扩展模块: {file_path}")
                return False

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # 查找扩展类
            extension_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and
                    issubclass(attr, ExtensionBase) and
                    attr != ExtensionBase):
                    extension_class = attr
                    break

            if extension_class is None:
                logger.warning(f"未找到扩展类: {file_path}")
                return False

            # 实例化扩展
            extension = extension_class()

            # 检查是否已存在同名扩展
            if extension.name in self.extensions:
                logger.warning(f"扩展 {extension.name} 已存在，将被替换")
                self.unload_extension_by_name(extension.name)

            # 加载扩展
            extension.on_load()
            self.extensions[extension.name] = extension
            self.extension_modules[file_path] = module

            logger.info(f"成功加载扩展: {extension.name} (v{extension.version})")
            return True

        except Exception as e:
            logger.error(f"加载扩展失败: {file_path}, 错误: {e}", exc_info=True)
            return False

    def reload_extension(self, file_path: str) -> bool:
        """
        重新加载扩展

        Args:
            file_path: 扩展文件路径

        Returns:
            bool: 是否重新加载成功
        """
        if file_path not in self.extension_modules:
            return self.load_extension(file_path)

        try:
            # 卸载旧扩展
            module = self.extension_modules[file_path]
            for attr_name in dir(module):
                extension = getattr(module, attr_name)
                if isinstance(extension, ExtensionBase):
                    extension.on_unload()
                    if extension.name in self.extensions:
                        del self.extensions[extension.name]

            # 重新加载模块
            module_name = Path(file_path).stem
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                return False

            # 重新执行模块
            spec.loader.exec_module(module)

            # 查找扩展类
            extension_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and
                    issubclass(attr, ExtensionBase) and
                    attr != ExtensionBase):
                    extension_class = attr
                    break

            if extension_class is None:
                return False

            # 实例化扩展
            extension = extension_class()
            extension.on_load()
            self.extensions[extension.name] = extension

            logger.info(f"成功重新加载扩展: {extension.name} (v{extension.version})")
            return True

        except Exception as e:
            logger.error(f"重新加载扩展失败: {file_path}, 错误: {e}", exc_info=True)
            return False

    def unload_extension(self, file_path: str):
        """
        卸载扩展

        Args:
            file_path: 扩展文件路径
        """
        if file_path not in self.extension_modules:
            return

        try:
            module = self.extension_modules[file_path]
            for attr_name in dir(module):
                extension = getattr(module, attr_name)
                if isinstance(extension, ExtensionBase):
                    extension.on_unload()
                    if extension.name in self.extensions:
                        del self.extensions[extension.name]

            del self.extension_modules[file_path]
            logger.info(f"已卸载扩展: {file_path}")

        except Exception as e:
            logger.error(f"卸载扩展失败: {file_path}, 错误: {e}", exc_info=True)

    def unload_extension_by_name(self, name: str):
        """
        按名称卸载扩展

        Args:
            name: 扩展名称
        """
        if name not in self.extensions:
            return

        extension = self.extensions[name]
        extension.on_unload()
        del self.extensions[name]

        # 找到对应的模块并删除
        for file_path, module in list(self.extension_modules.items()):
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, ExtensionBase) and attr.name == name:
                    del self.extension_modules[file_path]
                    break

        logger.info(f"已卸载扩展: {name}")

    def get_extension(self, name: str) -> Optional[ExtensionBase]:
        """
        获取扩展

        Args:
            name: 扩展名称

        Returns:
            Optional[ExtensionBase]: 扩展实例
        """
        return self.extensions.get(name)

    def list_extensions(self) -> List[Dict[str, str]]:
        """
        列出所有扩展

        Returns:
            List[Dict]: 扩展列表
        """
        return [
            {
                "name": ext.name,
                "version": ext.version,
                "description": ext.description
            }
            for ext in self.extensions.values()
        ]

    def process_message(self, user_message: str, conversation_id: str) -> Optional[str]:
        """
        处理用户消息，返回第一个匹配的扩展处理结果

        Args:
            user_message: 用户消息
            conversation_id: 对话ID

        Returns:
            Optional[str]: 处理结果
        """
        for extension in self.extensions.values():
            if extension.can_handle(user_message):
                logger.debug(f"扩展 {extension.name} 处理消息: {user_message[:50]}...")
                try:
                    result = extension.handle(user_message, conversation_id)
                    if result is not None:
                        return result
                except Exception as e:
                    logger.error(f"扩展 {extension.name} 处理失败: {e}", exc_info=True)

        return None

    def start_watching(self):
        """启动文件监听，实现热重载"""
        if self.observer is not None:
            return

        try:
            from watchdog.observers import Observer
            event_handler = ExtensionFileHandler(self)
            self.observer = Observer()
            self.observer.schedule(event_handler, str(self.extensions_dir), recursive=False)
            self.observer.start()
            logger.info(f"已启动扩展目录监听: {self.extensions_dir}")
        except ImportError:
            logger.warning("未安装 watchdog，无法启用热重载功能。请运行: pip install watchdog")
        except Exception as e:
            logger.error(f"启动文件监听失败: {e}", exc_info=True)

    def stop_watching(self):
        """停止文件监听"""
        if self.observer is not None:
            self.observer.stop()
            self.observer.join()
            self.observer = None
            logger.info("已停止扩展目录监听")

    def __del__(self):
        """析构函数，确保停止监听"""
        self.stop_watching()
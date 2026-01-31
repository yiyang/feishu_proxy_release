import os
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class Config:
    # 飞书应用配置
    FEISHU_APP_ID: str = os.getenv("FEISHU_APP_ID", "")
    FEISHU_APP_SECRET: str = os.getenv("FEISHU_APP_SECRET", "")
    FEISHU_VERIFICATION_TOKEN: str = os.getenv("FEISHU_VERIFICATION_TOKEN", "")
    FEISHU_ENCRYPT_KEY: str = os.getenv("FEISHU_ENCRYPT_KEY", "")
    
    # 代理服务配置
    PROXY_HOST: str = os.getenv("PROXY_HOST", "0.0.0.0")
    PROXY_PORT: int = int(os.getenv("PROXY_PORT", "8000"))
    
    # 日志配置
    LOG_FILE: str = os.getenv("LOG_FILE", "feishu_proxy.log")
    
    # iFlow CLI 配置
    IFLOW_API_URL: str = os.getenv("IFLOW_API_URL", "http://localhost:8080")
    
    def validate(self):
        """验证必要配置是否存在"""
        required_fields = [
            "FEISHU_APP_ID",
            "FEISHU_APP_SECRET"
        ]
        
        missing_fields = []
        for field in required_fields:
            if not getattr(self, field):
                missing_fields.append(field)
        
        if missing_fields:
            raise ValueError(f"缺少必要配置: {', '.join(missing_fields)}")
        
        # 提示可选配置
        optional_fields = []
        if not self.FEISHU_VERIFICATION_TOKEN:
            optional_fields.append("FEISHU_VERIFICATION_TOKEN")
        
        if optional_fields:
            logger.warning(f"可选配置未设置 {', '.join(optional_fields)}，某些功能可能受限")

config = Config()
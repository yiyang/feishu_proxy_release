import json
import hmac
import hashlib
import base64
import time
import logging
from typing import Dict, Optional
import requests
from config import config

logger = logging.getLogger(__name__)


class FeishuClient:
    def __init__(self):
        self.app_id = config.FEISHU_APP_ID
        self.app_secret = config.FEISHU_APP_SECRET
        self.verification_token = config.FEISHU_VERIFICATION_TOKEN
        self.encrypt_key = config.FEISHU_ENCRYPT_KEY
        self.tenant_access_token = None
        
        # 重试配置
        self.max_retries = 3
        self.retry_delay = 1  # 秒
        
    def get_tenant_access_token(self) -> str:
        """获取 tenant_access_token（带重试机制）"""
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        headers = {"Content-Type": "application/json; charset=utf-8"}
        data = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }
        
        for attempt in range(self.max_retries):
            try:
                response = requests.post(url, headers=headers, json=data, timeout=10)
                result = response.json()
                
                if result.get("code") != 0:
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay * (attempt + 1))
                        continue
                    raise Exception(f"获取 tenant_access_token 失败: {result.get('msg')}")
                
                self.tenant_access_token = result.get("tenant_access_token")
                return self.tenant_access_token
                
            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise Exception(f"获取 tenant_access_token 请求失败: {e}")
        
        raise Exception("获取 tenant_access_token 失败: 超过最大重试次数")
    
    def send_message(self, receive_id: str, msg_type: str, content: Dict) -> bool:
        """发送消息到飞书（带重试机制）

        Args:
            receive_id: 接收者 ID（open_id、user_id 或 chat_id）
            msg_type: 消息类型
            content: 消息内容（字典格式）

        Returns:
            bool: 发送是否成功
        """
        if not self.tenant_access_token:
            self.get_tenant_access_token()
        
        url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
        headers = {
            "Authorization": f"Bearer {self.tenant_access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        data = {
            "receive_id": receive_id,
            "msg_type": msg_type,
            "content": json.dumps(content)
        }
        
        for attempt in range(self.max_retries):
            try:
                response = requests.post(url, headers=headers, json=data, timeout=10)
                result = response.json()
                
                if result.get("code") != 0:
                    # Token 过期，重新获取并重试
                    if result.get("code") == 99991663 and attempt == 0:
                        self.get_tenant_access_token()
                        headers["Authorization"] = f"Bearer {self.tenant_access_token}"
                        continue
                    
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay * (attempt + 1))
                        continue
                    
                    logger.error(f"发送消息失败: {result.get('msg')}")
                    return False
                
                return True
                
            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                logger.error(f"发送消息请求失败: {e}")
                return False
        
        return False
    
    def send_message_to_chat(self, chat_id: str, msg_type: str, content: Dict) -> bool:
        """发送消息到飞书对话（带重试机制）

        Args:
            chat_id: 对话 ID
            msg_type: 消息类型
            content: 消息内容（字典格式）

        Returns:
            bool: 发送是否成功
        """
        if not self.tenant_access_token:
            self.get_tenant_access_token()
        
        url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
        headers = {
            "Authorization": f"Bearer {self.tenant_access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        data = {
            "receive_id": chat_id,
            "msg_type": msg_type,
            "content": json.dumps(content)
        }
        
        for attempt in range(self.max_retries):
            try:
                response = requests.post(url, headers=headers, json=data, timeout=10)
                result = response.json()
                
                if result.get("code") != 0:
                    # Token 过期，重新获取并重试
                    if result.get("code") == 99991663 and attempt == 0:
                        self.get_tenant_access_token()
                        headers["Authorization"] = f"Bearer {self.tenant_access_token}"
                        continue
                    
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay * (attempt + 1))
                        continue
                    
                    logger.error(f"发送消息到对话失败: {result.get('msg')}")
                    return False
                
                return True
                
            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                logger.error(f"发送消息到对话请求失败: {e}")
                return False
        
        return False
    
    def send_text_message(self, receive_id: str, text: str) -> bool:
        """发送文本消息"""
        content = {"text": text}
        return self.send_message(receive_id, "text", content)
    
    def verify_event(self, timestamp: str, nonce: str, body: str, signature: str) -> bool:
        """验证飞书事件签名"""
        if not self.encrypt_key:
            return True
        
        # 构造签名字符串
        sign_str = f"{timestamp}{nonce}{self.encrypt_key}{body}"
        # 计算签名
        sign_bytes = hmac.new(
            self.encrypt_key.encode('utf-8'),
            sign_str.encode('utf-8'),
            hashlib.sha256
        ).digest()
        sign = base64.b64encode(sign_bytes).decode('utf-8')
        
        return sign == signature
    
    def decrypt_event(self, encrypted_data: str) -> Dict:
        """解密飞书事件数据"""
        if not self.encrypt_key:
            return json.loads(encrypted_data)
        
        # 这里需要实现 AES 解密逻辑
        # 为了简化，暂时返回空字典
        return {}
    
    def upload_file(self, file_path: str, file_type: str = "file") -> Optional[str]:
        """上传文件到飞书，返回 file_key

        Args:
            file_path: 文件的绝对路径
            file_type: 文件类型，支持 "file"（通用文件）、"image"（图片）、"video"（视频）、"audio"（音频）

        Returns:
            file_key: 上传成功后返回的 file_key，失败返回 None
        """
        import os
        from requests_toolbelt import MultipartEncoder

        if not self.tenant_access_token:
            self.get_tenant_access_token()

        url = "https://open.feishu.cn/open-apis/im/v1/files"

        # 获取文件信息
        file_name = os.path.basename(file_path)

        # 构造请求体（参考飞书文档和示例代码）
        form = {
            'file_type': file_type,
            'file_name': file_name,
            'file': (file_name, open(file_path, 'rb'), 'text/plain')
        }

        multi_form = MultipartEncoder(form)
        headers = {
            'Authorization': f'Bearer {self.tenant_access_token}',
            'Content-Type': multi_form.content_type
        }

        try:
            response = requests.post(url, headers=headers, data=multi_form, timeout=30)
            result = response.json()

            logger.debug(f"上传文件响应: 状态码={response.status_code}, 响应内容={result}")

            if result.get("code") != 0:
                logger.error(f"上传文件失败: {result.get('msg')}")
                return None

            # 返回 file_key
            return result.get("data", {}).get("file_key")

        except requests.exceptions.RequestException as e:
            logger.error(f"上传文件请求失败: {e}")
            return None
        except FileNotFoundError:
            logger.error(f"文件不存在: {file_path}")
            return None
        except ImportError:
            logger.error("缺少依赖 requests_toolbelt，请安装: pip install requests-toolbelt")
            return None
        finally:
            # 确保关闭文件
            if 'file' in form:
                form['file'][1].close()
    
    def send_file_message(self, receive_id: str, file_key: str, file_name: str = "") -> bool:
        """发送文件消息到飞书

        Args:
            receive_id: 接收者的 open_id
            file_key: 上传文件后获取的 file_key（飞书返回的 file_token）
            file_name: 文件名（已废弃，仅保留兼容性）

        Returns:
            bool: 发送是否成功
        """
        content = {
            "file_key": file_key
        }
        return self.send_message(receive_id, "file", content)
    
    def send_image_message(self, receive_id: str, image_key: str) -> bool:
        """发送图片消息到飞书
        
        Args:
            receive_id: 接收者的 open_id
            image_key: 上传图片后获取的 file_key
        
        Returns:
            bool: 发送是否成功
        """
        content = {
            "image_key": image_key
        }
        return self.send_message(receive_id, "image", content)
    
    def send_markdown_message(self, receive_id: str, markdown_content: str) -> bool:
        """发送 Markdown 格式消息到飞书

        Args:
            receive_id: 接收者的 open_id
            markdown_content: Markdown 格式的文本内容

        Returns:
            bool: 发送是否成功
        """
        # 使用富文本消息类型，通过 md 标签发送 Markdown 内容
        content = {
            "zh_cn": {
                "content": [[
                    {
                        "tag": "md",
                        "text": markdown_content
                    }
                ]]
            }
        }
        return self.send_message(receive_id, "post", content)
    
    def reply_message(self, message_id: str, msg_type: str, content: Dict) -> bool:
        """回复消息到飞书（带重试机制）

        Args:
            message_id: 要回复的消息 ID
            msg_type: 消息类型（text, post, file, image 等）
            content: 消息内容（字典格式）

        Returns:
            bool: 回复是否成功
        """
        if not self.tenant_access_token:
            self.get_tenant_access_token()
        
        # 使用 RESTful 风格的 API，将 message_id 作为路径参数
        url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply"
        headers = {
            "Authorization": f"Bearer {self.tenant_access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        data = {
            "msg_type": msg_type,
            "content": json.dumps(content)
        }
        
        for attempt in range(self.max_retries):
            try:
                response = requests.post(url, headers=headers, json=data, timeout=10)
                
                logger.debug(f"回复消息响应: 状态码={response.status_code}, 响应内容={response.text}")
                
                result = response.json()
                
                if result.get("code") != 0:
                    # Token 过期，重新获取并重试
                    if result.get("code") == 99991663 and attempt == 0:
                        self.get_tenant_access_token()
                        headers["Authorization"] = f"Bearer {self.tenant_access_token}"
                        continue
                    
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay * (attempt + 1))
                        continue
                    
                    logger.error(f"回复消息失败: {result.get('msg')}")
                    return False
                
                return True
                
            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                logger.error(f"回复消息请求失败: {e}")
                return False
        
        return False
    
    def reply_text_message(self, message_id: str, text: str) -> bool:
        """回复文本消息"""
        content = {"text": text}
        return self.reply_message(message_id, "text", content)
    
    def reply_file_message(self, message_id: str, file_key: str) -> bool:
        """回复文件消息"""
        content = {"file_key": file_key}
        return self.reply_message(message_id, "file", content)
    
    def reply_markdown_message(self, message_id: str, markdown_content: str) -> bool:
        """回复 Markdown 格式消息"""
        content = {
            "zh_cn": {
                "content": [[
                    {
                        "tag": "md",
                        "text": markdown_content
                    }
                ]]
            }
        }
        return self.reply_message(message_id, "post", content)
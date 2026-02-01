from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import json
import logging
import time
import requests
import whisper
from config import config
from feishu_client import FeishuClient
from llm_client import LLMClient
from database import get_event_db

# 配置日志（带轮转）
from logging.handlers import RotatingFileHandler
import os

# 确保日志目录存在
log_dir = os.path.dirname(config.LOG_FILE) if hasattr(config, 'LOG_FILE') else '.'
if log_dir:  # Only create directory if it's not empty
    os.makedirs(log_dir, exist_ok=True)

# 创建日志记录器
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 创建轮转文件处理器（每个文件最大 10MB，保留 5 个备份）
log_file = getattr(config, 'LOG_FILE', 'feishu_proxy.log')
file_handler = RotatingFileHandler(
    log_file,
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5,
    encoding='utf-8'
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# 同时输出到控制台
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# 添加处理器
logger.addHandler(file_handler)
logger.addHandler(console_handler)

app = FastAPI(title="飞书代理服务")
feishu_client = FeishuClient()
llm_client = LLMClient()
event_db = get_event_db()

# Whisper 音频识别模型（全局变量，服务启动时加载）
whisper_model = None


@app.get("/")
async def root():
    """健康检查"""
    return {"status": "ok", "service": "feishu-proxy"}


@app.post("/webhook")
async def webhook(request: Request):
    """
    飞书事件回调接口
    """
    try:
        # 记录所有请求
        logger.info("=" * 50)
        logger.info("收到 webhook 请求")
        
        # 获取请求头信息
        timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
        nonce = request.headers.get("X-Lark-Request-Nonce", "")
        signature = request.headers.get("X-Lark-Signature", "")
        
        # 记录请求头信息
        logger.info(f"请求头 - Timestamp: {timestamp}, Nonce: {nonce}, Signature: {signature[:20] if signature else 'None'}...")
        
        # 读取请求体
        body = await request.body()
        body_str = body.decode('utf-8')
        
        logger.info(f"请求体: {body_str}")
        
        # 验证签名
        if not feishu_client.verify_event(timestamp, nonce, body_str, signature):
            logger.warning("签名验证失败")
            raise HTTPException(status_code=403, detail="签名验证失败")
        
        # 解析事件数据
        event_data = json.loads(body_str)
        
        # 检查消息时间戳，忽略早于当前时间30秒以上的消息
        request_timestamp = int(timestamp) if timestamp.isdigit() else None
        current_timestamp = int(time.time())
        if request_timestamp:
            time_diff = current_timestamp - request_timestamp
            if time_diff > 30:
                logger.info(f"消息过期: 时间差 {time_diff} 秒，超过30秒限制，忽略该消息")
                return JSONResponse(content={"code": 0, "msg": "success"})
        
        logger.info(f"事件类型: {event_data.get('type')}, 事件名称: {event_data.get('header', {}).get('event_type', 'N/A')}")
        
        # 处理 URL 验证
        if event_data.get("type") == "url_verification":
            logger.info("处理 URL 验证")
            return JSONResponse(content={
                "challenge": event_data.get("challenge")
            })
        
        # 获取事件ID并去重
        event_id = event_data.get("header", {}).get("event_id", "")
        if event_id:
            if event_db.is_event_processed(event_id):
                logger.info(f"事件 {event_id} 已处理过,跳过")
                return JSONResponse(content={"code": 0, "msg": "success"})
            event_db.mark_event_processed(event_id)
        
        # 处理消息事件
        event_type = event_data.get("header", {}).get("event_type")
        if event_type == "im.message.receive_v1":
            logger.info("处理消息事件")
            await handle_message_event(event_data)
        else:
            logger.info(f"忽略事件类型: {event_type}")
        
        return JSONResponse(content={"code": 0, "msg": "success"})
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理事件失败: {e}", exc_info=True)
        return JSONResponse(content={"code": -1, "msg": str(e)}, status_code=500)


async def handle_message_event(event_data: dict):
    """
    处理消息事件
    """
    import os
    
    try:
        event = event_data.get("event", {})
        message = event.get("message", {})
        
        # 获取消息内容和发送者信息
        message_id = message.get("message_id")
        msg_type = message.get("message_type", "")
        content = json.loads(message.get("content", "{}"))
        text = content.get("text", "").strip()
        
        sender = event.get("sender", {})
        sender_id = sender.get("sender_id", {}).get("open_id", "")
        
        # 获取会话信息
        chat_id = message.get("chat_id", "")
        
        # 忽略机器人自己的消息
        if sender.get("sender_type") == "app":
            logger.info("忽略机器人自己的消息")
            return
        
        logger.info(f"收到消息 - 发送者: {sender_id}, 消息类型: {msg_type}")
        
        # 处理音频消息
        if msg_type == "audio":
            logger.info("检测到音频消息，开始处理...")
            file_key = content.get("file_key")
            
            if not file_key:
                logger.error("音频消息缺少 file_key")
                return
            
            # 直接下载音频文件（使用 "file" 类型）
            audio_file_path = feishu_client.get_message_resource(message_id, file_key, "file")
            if not audio_file_path:
                logger.error("下载音频文件失败")
                return
            
            logger.info(f"音频文件已下载: {audio_file_path}")
            
            # 使用 Whisper 识别音频
            try:
                # 转换为 wav 格式（确保兼容性）
                if audio_file_path.endswith(".bin"):
                    wav_file_path = audio_file_path[:-4] + ".wav"
                else:
                    wav_file_path = audio_file_path.rsplit(".", 1)[0] + ".wav"
                
                import subprocess
                # 转换为标准 wav 格式
                subprocess.run(
                    ["ffmpeg", "-i", audio_file_path, "-ar", "16000", "-ac", "1", wav_file_path],
                    capture_output=True,
                    check=True
                )
                
                logger.info(f"音频转换完成: {wav_file_path}")
                
                # 使用 Whisper 转录音频
                if whisper_model is None:
                    logger.error("Whisper 模型未加载")
                    feishu_client.reply_text_message(message_id, "抱歉，语音识别服务未初始化")
                    return
                
                result = whisper_model.transcribe(wav_file_path, language="zh")
                text = result.get("text", "").strip()
                
                if text:
                    logger.info(f"音频转录成功: {text[:100]}...")
                else:
                    text = "（语音内容未能识别）"
                    logger.warning("Whisper 返回空文本")
                
            except Exception as e:
                logger.error(f"音频转录失败: {e}", exc_info=True)
                feishu_client.reply_text_message(message_id, "抱歉，无法识别语音内容")
                return
            
            # 清理临时文件
            try:
                if os.path.exists(audio_file_path):
                    os.remove(audio_file_path)
                if 'wav_file_path' in locals() and os.path.exists(wav_file_path):
                    os.remove(wav_file_path)
            except Exception as e:
                logger.warning(f"清理临时文件失败: {e}")
        
        logger.info(f"处理后的文本内容: {text}")
        
        # 从数据库获取对话上下文
        conversation_data = event_db.get_conversation_context(chat_id)
        if conversation_data:
            conversation_id = conversation_data.get("conversation_id", chat_id)
        else:
            conversation_id = chat_id
        logger.info(f"对话ID: {conversation_id}, 准备调用 LLM...")
        
        # 调用 LLM 获取回复
        response_text, new_conversation_id = llm_client.chat(text, conversation_id)
        logger.info(f"LLM 返回: {response_text[:50] if response_text else 'None'}...")

        # 更新对话上下文到数据库
        if new_conversation_id:
            event_db.save_conversation_context(chat_id, new_conversation_id)

        # 发送回复（如果 response_text 不为 None）
        # response_text 为 None 表示是重复回复，不推送
        if response_text is not None:
            # 使用 Markdown 格式发送消息，保证用户阅读体验
            # 支持多条消息（列表）或单条消息（字符串）
            messages = response_text if isinstance(response_text, list) else [response_text]

            for idx, msg in enumerate(messages, 1):
                success = feishu_client.send_markdown_message(sender_id, msg)
                if success:
                    logger.info(f"回复发送成功 [{idx}/{len(messages)}]: {msg[:50]}...")
                else:
                    logger.error(f"回复发送失败 [{idx}/{len(messages)}]")
        else:
            logger.info("检测到重复回复，跳过发送")
        
    except Exception as e:
        logger.error(f"处理消息事件失败: {e}", exc_info=True)


@app.on_event("startup")
async def startup_event():
    """服务启动时的初始化"""
    logger.info("飞书代理服务启动")
    try:
        config.validate()
        # 预获取 tenant_access_token
        feishu_client.get_tenant_access_token()
        logger.info("飞书客户端初始化成功")

        # 加载 Whisper 模型
        global whisper_model
        logger.info("正在加载 Whisper 模型...")
        whisper_model = whisper.load_model("base")
        logger.info("Whisper 模型加载成功")

        # 启动定期清理任务
        import asyncio
        asyncio.create_task(cleanup_old_events_task())
        logger.info("定期清理任务已启动")
    except Exception as e:
        logger.error(f"服务启动失败: {e}", exc_info=True)
        raise


async def cleanup_old_events_task():
    """定期清理旧事件的异步任务"""
    import asyncio
    import time
    while True:
        try:
            # 每小时清理一次
            await asyncio.sleep(3600)
            event_db.clean_old_events(hours=24)
        except Exception as e:
            logger.error(f"清理任务执行失败: {e}", exc_info=True)


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app:app",
        host=config.PROXY_HOST,
        port=config.PROXY_PORT,
        reload=True
    )
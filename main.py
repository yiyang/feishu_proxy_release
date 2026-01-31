#!/usr/bin/env python3
"""
飞书代理服务启动脚本
"""
import os
import sys
import subprocess
from pathlib import Path

def install_dependencies():
    """安装依赖"""
    print("正在安装依赖...")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
    ])
    print("依赖安装完成！")

def create_env_file():
    """创建 .env 文件"""
    env_file = Path(__file__).parent / ".env"
    env_example = Path(__file__).parent / ".env.example"
    
    if not env_file.exists() and env_example.exists():
        print(f"\n请创建 .env 文件，参考 .env.example")
        print(f"位置: {env_file}")
        return False
    
    return True

def main():
    """主函数"""
    print("=" * 50)
    print("飞书代理服务启动")
    print("=" * 50)
    
    # 检查是否安装了依赖
    try:
        import fastapi
        import uvicorn
    except ImportError:
        print("\n未检测到依赖包，正在安装...")
        install_dependencies()
    
    # 检查 .env 文件
    if not create_env_file():
        print("\n请先配置 .env 文件后再启动服务")
        return
    
    # 加载环境变量
    from dotenv import load_dotenv
    load_dotenv()
    
    # 验证配置
    from config import config
    try:
        config.validate()
        print("\n配置验证通过！")
    except ValueError as e:
        print(f"\n配置错误: {e}")
        return
    
    # 启动服务
    print(f"\n启动服务在 http://{config.PROXY_HOST}:{config.PROXY_PORT}")
    print("=" * 50)
    
    import uvicorn
    uvicorn.run(
        "app:app",
        host=config.PROXY_HOST,
        port=config.PROXY_PORT,
        reload=False
    )

if __name__ == "__main__":
    main()
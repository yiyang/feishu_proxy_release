"""
示例扩展：天气查询扩展

此扩展演示如何创建一个自定义扩展来处理特定类型的用户请求。
用户可以参考此文件创建自己的扩展。

使用方法：
1. 将此文件放入 extensions/ 目录
2. 修改 can_handle 和 handle 方法实现你的逻辑
3. 无需重启，扩展会自动加载

扩展修改后会自动热重载！
"""
from extension_loader import ExtensionBase
import requests
from datetime import datetime


class WeatherExtension(ExtensionBase):
    """天气查询扩展"""

    @property
    def name(self) -> str:
        return "weather"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "查询天气信息的扩展，支持简单天气查询"

    def can_handle(self, user_message: str) -> bool:
        """判断是否可以处理该消息"""
        # 检查消息中是否包含天气相关关键词
        keywords = ["天气", "weather", "气温", "温度", "下雨", "晴天"]
        message_lower = user_message.lower()
        return any(keyword in message_lower for keyword in keywords)

    def handle(self, user_message: str, conversation_id: str):
        """处理用户消息"""
        try:
            # 这里是一个简单的示例，实际使用时可以接入真实的天气 API
            # 例如：和风天气、OpenWeatherMap 等

            # 解析城市名（简单实现）
            city = "北京"  # 默认城市
            if "上海" in user_message:
                city = "上海"
            elif "广州" in user_message:
                city = "广州"
            elif "深圳" in user_message:
                city = "深圳"

            # 模拟天气查询（实际应该调用真实 API）
            # response = requests.get(f"https://api.weather.com/v1/current?city={city}")

            # 返回模拟的天气信息
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
            weather_info = f"""
🌤️ {city} 天气信息
━━━━━━━━━━━━━━━━━━
📅 时间：{current_time}
🌡️ 温度：18°C
💧 湿度：65%
💨 风向：东南风 3级
☁️ 天气：多云

📍 数据来源：模拟数据（请接入真实天气 API）
"""

            return weather_info.strip()

        except Exception as e:
            return f"查询天气信息时出错：{str(e)}"
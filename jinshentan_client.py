import subprocess
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class JinShentanClient:
    """金圣叹评论客户端"""

    def __init__(self):
        pass

    def generate_comment(self, user_message: str, assistant_reply: str) -> str:
        """
        生成金圣叹的评论

        Args:
            user_message: 用户消息
            assistant_reply: 助手的回复

        Returns:
            评论内容
        """
        try:
            # 构建评论提示词，让 iFlow CLI 自己处理领域识别和时事背景
            prompt = f"""你叫金圣叹，是明末清初的文学批评家，以犀利独到的见解著称。现在你穿越到2026年，化身为一位博学多才的评论大师。你上知天文、下知地理，通晓古今中外，融汇文史哲艺。

用户问题：
{user_message}

助手回复：
{assistant_reply}

请以金圣叹的口吻，从以下角度进行评论：
1. **问题价值**：这个问题是否有深度？是否触及本质？
2. **回答质量**：助手是否抓住了关键？是否有遗漏或可改进之处？
3. **领域洞察**：识别问题所属领域，站在该领域专家的视角，提供更深层的思考
4. **文化视角**：结合古今中外的智慧，用跨学科的思维提供独特见解
5. **时事背景**：如果涉及时事热点，可以结合2026年的相关背景进行评论

评论要求：
- 语气犀利但中肯，有大师风范
- 60-120字，精炼有力
- 不要重复助手已经说过的内容
- 可以适当使用感叹号和反问
- 以"金圣叹曰："开头
- 如果问题领域需要时事背景，iFlow CLI 会自动访问网络获取相关信息

示例：
金圣叹曰：此问甚妙！直指分布式系统之核心。助手所言甚当，然未尽其意。盖分布式之难，不在算法，而在人心。如昔时周公吐哺，今之分布式亦然，各方协调，方成大业！"""

            result = subprocess.run(
                ["iflow", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=90  # 给 iFlow 更长时间处理可能的网络请求
            )

            if result.returncode == 0:
                comment = result.stdout.strip()
                logger.info(f"金圣叹评论: {comment[:50]}...")
                return comment

        except Exception as e:
            logger.error(f"生成金圣叹评论失败: {e}")

        return ""


# 全局实例
jinshentan_client: Optional[JinShentanClient] = None


def get_jinshentan_client() -> JinShentanClient:
    """获取金圣叹客户端实例"""
    global jinshentan_client
    if jinshentan_client is None:
        jinshentan_client = JinShentanClient()
    return jinshentan_client
import re
from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star


# 匹配 "@某人 说内容" 与 "@某人 说～内容" 两种 OneBot CQ 消息.
# - [CQ:at,qq=(\d+)]   捕获被 @ 用户的 QQ
# - \s*                兼容 0..N 个空白 (含 Tab)
# - 说～?               波浪号变为可选, 兼容用户两种格式
MENTION_SAY_PATTERN = r"^\[CQ:at,qq=(\d+)\]\s*说～?(.*)"


class MentionSayPlugin(Star):
    name = "mention_say_plugin"
    version = "1.0.4"
    author = "AI Assistant"
    description = "当检测到@某用户说～时，生成表情包"

    def __init__(self, context: Context):
        super().__init__(context)

    # @filter.regex 不会自动注入匹配对象, 这里自己用 re 模块匹配同一份正则.
    # 必须与下方 MENTION_SAY_PATTERN 保持完全一致, 否则会出现
    # "装饰器能匹配但回调内 match 为 None" 的诡异 bug.
    @filter.regex(MENTION_SAY_PATTERN)
    async def on_mention_say(self, event: AstrMessageEvent):
        """检测 @用户 说～ 或 @用户 说 内容格式并生成表情包"""
        if not self.context.get_config().get("enabled", True):
            return

        match = re.search(MENTION_SAY_PATTERN, event.message_str.strip())
        if not match:
            return

        mentioned_user_id = match.group(1)
        say_content = match.group(2).strip()

        # 调试日志
        print(f"[mention_say] message_str: {event.message_str}")
        print(f"[mention_say] mentioned_user_id: {mentioned_user_id}")
        print(f"[mention_say] say_content: {say_content}")

        if not say_content:
            return

        # 修复点 #3 & #4: 不再使用 self.context.get_group_member_info,
        # AstrBot Context 没有该方法.
        # 头像优先通过 OneBot 适配器 (aiocqhttp) 的 bot.call_action 获取,
        # 若不在 aiocqhttp 平台, 则使用 QQ 公开的头像 CDN 作为后备.
        avatar_bytes: bytes | None = None
        try:
            bot = getattr(event, "bot", None)
            if bot is not None and event.get_group_id():
                try:
                    member_info: dict[str, Any] = await bot.call_action(
                        "get_group_member_info",
                        group_id=int(event.get_group_id()),
                        user_id=int(mentioned_user_id),
                        no_cache=True,
                    )
                    avatar_url = member_info.get("avatar")
                except Exception:
                    avatar_url = None

                if not avatar_url:
                    avatar_url = (
                        f"https://q1.qlogo.cn/g?b=qq&nk={mentioned_user_id}&s=640"
                    )

                # 下载头像
                import urllib.request

                with urllib.request.urlopen(avatar_url, timeout=10) as resp:
                    avatar_bytes = resp.read()
        except Exception as e:
            print(f"[mention_say] 获取头像失败: {e}")

        if avatar_bytes is None:
            # 至少给出一张纯文字表情包, 不要让插件静默失败
            yield event.plain_result(
                f"未找到用户 {mentioned_user_id} 的头像信息，但表情包内容是：{say_content}"
            )
            return

        # 修复点 #5: self.context.llm_generate_image 不存在.
        # 改为使用 PIL 本地渲染, 直接 yield 字节流给 event.image_result.
        try:
            img = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
            img = img.resize((120, 120))
            # 圆形遮罩
            mask = Image.new("L", img.size, 0)
            ImageDraw.Draw(mask).ellipse((0, 0, img.size[0], img.size[1]), fill=255)
            avatar_img = Image.new("RGBA", img.size, (0, 0, 0, 0))
            avatar_img.paste(img, (0, 0), mask)

            canvas_w, canvas_h = 640, 200
            canvas = Image.new("RGB", (canvas_w, canvas_h), (245, 245, 245))
            canvas.paste(avatar_img, (20, 40), avatar_img)

            draw = ImageDraw.Draw(canvas)
            try:
                font = ImageFont.truetype(
                    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 28
                )
            except Exception:
                font = ImageFont.load_default()

            # LV100 标签
            try:
                font_small = ImageFont.truetype(
                    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 18
                )
            except Exception:
                font_small = ImageFont.load_default()
            draw.text((20, 15), "LV100", fill=(150, 150, 150), font=font_small)

            # 消息气泡
            bubble_x0, bubble_y0 = 160, 60
            bubble_x1, bubble_y1 = canvas_w - 20, 140
            draw.rounded_rectangle(
                (bubble_x0, bubble_y0, bubble_x1, bubble_y1),
                radius=12,
                fill=(255, 255, 255),
                outline=(220, 220, 220),
            )
            draw.text(
                (bubble_x0 + 14, bubble_y0 + 14),
                say_content,
                fill=(30, 30, 30),
                font=font,
            )

            buf = BytesIO()
            canvas.save(buf, format="PNG")
            image_bytes = buf.getvalue()
        except Exception as e:
            print(f"[mention_say] 渲染表情包失败: {e}")
            yield event.plain_result(f"表情包生成失败: {e}")
            return

        yield event.image_result(image_bytes)

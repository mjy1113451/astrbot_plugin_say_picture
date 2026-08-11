from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import At, Image as AstrImage, Plain
from astrbot.api.star import Context, Star


class MentionSayPlugin(Star):
    name = "mention_say_plugin"
    version = "1.0.6"
    author = "AI Assistant"
    description = "当检测到@某用户说～时，生成表情包"

    def __init__(self, context: Context):
        super().__init__(context)

    # @filter.regex 仅作粗筛：消息中包含"说"字就触发回调.
    # 真正的"是否含 @某用户 + 是否带说～"判断在回调内通过解析
    # event.message_obj.message (消息链) 完成, 不依赖字符串正则,
    # 因为 aiocqhttp 适配器已经把 [CQ:at,qq=N] 转换成 @昵称(qq) 文字格式,
    # 无法再用正则从 message_str 中精确拿到被 @ 的 QQ.
    @filter.regex(r"说～?")
    async def on_mention_say(self, event: AstrMessageEvent):
        """检测消息链中 \"At 某用户\" 紧跟 \"说[～]内容\" 格式"""
        if not self.context.get_config().get("enabled", True):
            return

        chain = event.message_obj.message or []
        at_qq: str | int | None = None
        plain_parts: list[str] = []

        for comp in chain:
            if isinstance(comp, At):
                # 仅记录第一个被 @ 的用户 (跳过 @全体成员)
                if at_qq is None and str(comp.qq) != "all":
                    at_qq = comp.qq
            elif isinstance(comp, Plain):
                plain_parts.append(comp.text)

        if at_qq is None or not plain_parts:
            return

        # 拼接所有 plain 段, 找出以 "说～?" 开头的部分
        full_text = "".join(plain_parts).strip()
        if not full_text.startswith("说"):
            return

        # "说" 后允许 0..1 个全角波浪号 ～, 然后是真正的内容
        prefix = "说"
        rest = full_text[len(prefix) :].lstrip()
        if rest.startswith("～"):
            rest = rest[1:].lstrip()
        say_content = rest.strip()

        if not say_content:
            return

        mentioned_user_id = str(at_qq)

        # 调试日志
        print(f"[mention_say] message_str: {event.message_str}")
        print(f"[mention_say] mentioned_user_id: {mentioned_user_id}")
        print(f"[mention_say] say_content: {say_content}")

        # 获取被 @ 用户的头像: 优先走 OneBot 适配器, 失败时回退到 QLogo CDN.
        avatar_bytes: bytes | None = None
        try:
            bot = getattr(event, "bot", None)
            avatar_url: str | None = None

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

            import urllib.request

            with urllib.request.urlopen(avatar_url, timeout=10) as resp:
                avatar_bytes = resp.read()
        except Exception as e:
            print(f"[mention_say] 获取头像失败: {e}")

        if avatar_bytes is None:
            yield event.plain_result(
                f"未找到用户 {mentioned_user_id} 的头像信息，但表情包内容是：{say_content}"
            )
            return

        # 用 PIL 本地渲染头像 + 气泡表情包.
        try:
            img = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
            img = img.resize((120, 120))
            mask = Image.new("L", img.size, 0)
            ImageDraw.Draw(mask).ellipse(
                (0, 0, img.size[0], img.size[1]), fill=255
            )
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

            try:
                font = ImageFont.truetype(
                    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 28
                )
            except Exception:
                font_small = ImageFont.load_default()

            draw.text((160, 38), "LV100", fill=(150, 150, 150), font=font_small)

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

        # event.image_result() 仅接受 str (URL 或路径), 传入 bytes 会触发
        # TypeError: startswith first arg must be bytes or a tuple of bytes, not str.
        # 改用 chain_result + AstrImage.fromBytes() 直接传字节流.
        yield event.chain_result([AstrImage.fromBytes(image_bytes)])

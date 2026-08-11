from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw, ImageFont
import urllib.request
import os
import tempfile

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import At, Image as AstrImage, Plain
from astrbot.api.star import Context, Star

# ---------------------------------------------------------------------------
# 中文字体：优先从系统常见路径加载，找不到则从 Noto CJK GitHub Release 下载.
# ---------------------------------------------------------------------------

_CN_FONT_CANDIDATES = [
    # Linux (Debian/Ubuntu)
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    # Linux (RHEL/CentOS/Fedora)
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
    "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    # Windows
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simsun.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
]

# Noto Sans SC — permissive OFL license, ~8 MB
_NOTO_SANS_SC_URL = (
    "https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/"
    "NotoSansSC-Regular.otf"
)
_FONT_CACHE_DIR: str | None = None  # lazy-initialized


def _get_font_cache_dir() -> str:
    global _FONT_CACHE_DIR
    if _FONT_CACHE_DIR is None:
        _FONT_CACHE_DIR = os.path.join(tempfile.gettempdir(), "astrbot_say_font")
        os.makedirs(_FONT_CACHE_DIR, exist_ok=True)
    return _FONT_CACHE_DIR


def _download_cn_font() -> str | None:
    """Download Noto Sans SC if not cached yet. Returns path or None."""
    cache_dir = _get_font_cache_dir()
    cached = os.path.join(cache_dir, "NotoSansSC-Regular.otf")
    if os.path.isfile(cached):
        return cached
    try:
        print("[mention_say] 系统无中文字体，正在下载 Noto Sans SC ...")
        urllib.request.urlretrieve(_NOTO_SANS_SC_URL, cached)
        print(f"[mention_say] 字体已缓存到 {cached}")
        return cached
    except Exception as e:
        print(f"[mention_say] 字体下载失败: {e}")
        return None


def _load_cn_font(size: int = 26) -> ImageFont.FreeTypeFont:
    """Try system Chinese fonts, then download Noto Sans SC as fallback."""
    for path in _CN_FONT_CANDIDATES:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    downloaded = _download_cn_font()
    if downloaded:
        try:
            return ImageFont.truetype(downloaded, size)
        except Exception:
            pass
    # Last resort: PIL bitmap font (no CJK support)
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Plugin
# ---------------------------------------------------------------------------


class MentionSayPlugin(Star):
    name = "mention_say_plugin"
    version = "1.0.6"
    author = "AI Assistant"
    description = "当检测到@某用户说～时，生成表情包"

    def __init__(self, context: Context):
        super().__init__(context)

    @filter.regex(r"说～?")
    async def on_mention_say(self, event: AstrMessageEvent):
        """检测消息链中 "At 某用户" 紧跟 "说[～]内容" 格式"""
        if not self.context.get_config().get("enabled", True):
            return

        chain = event.message_obj.message or []
        at_qq: str | int | None = None
        plain_parts: list[str] = []

        for comp in chain:
            if isinstance(comp, At):
                if at_qq is None and str(comp.qq) != "all":
                    at_qq = comp.qq
            elif isinstance(comp, Plain):
                plain_parts.append(comp.text)

        if at_qq is None or not plain_parts:
            return

        full_text = "".join(plain_parts).strip()
        if not full_text.startswith("说"):
            return

        prefix = "说"
        rest = full_text[len(prefix) :].lstrip()
        if rest.startswith("～"):
            rest = rest[1:].lstrip()
        say_content = rest.strip()

        if not say_content:
            return

        mentioned_user_id = str(at_qq)

        print(f"[mention_say] message_str: {event.message_str}")
        print(f"[mention_say] mentioned_user_id: {mentioned_user_id}")
        print(f"[mention_say] say_content: {say_content}")

        # ---- 获取头像 ----
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

            with urllib.request.urlopen(avatar_url, timeout=10) as resp:
                avatar_bytes = resp.read()
        except Exception as e:
            print(f"[mention_say] 获取头像失败: {e}")

        if avatar_bytes is None:
            yield event.plain_result(
                f"未找到用户 {mentioned_user_id} 的头像信息，"
                f"但表情包内容是：{say_content}"
            )
            return

        # ---- PIL 渲染 ----
        try:
            avatar_size = 80
            canvas_w, canvas_h = 640, 160
            bubble_r = 10  # 气泡圆角
            txt_pad = 10  # 气泡内文字边距
            font_size = 26  # 正文字号
            name_font_size = 14  # "LV100" 字号

            # 字体（只加载一次，正文字体和标签字体各取所需大小）
            font = _load_cn_font(font_size)
            font_small = _load_cn_font(name_font_size)

            # -- 头像（圆形裁剪） --
            avatar_raw = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
            avatar_raw = avatar_raw.resize(
                (avatar_size, avatar_size), Image.LANCZOS
            )
            mask = Image.new("L", (avatar_size, avatar_size), 0)
            ImageDraw.Draw(mask).ellipse(
                (0, 0, avatar_size - 1, avatar_size - 1), fill=255
            )
            avatar_img = Image.new("RGBA", (avatar_size, avatar_size), (0, 0, 0, 0))
            avatar_img.paste(avatar_raw, (0, 0), mask)

            # -- 气泡坐标 --
            margin_x = 14
            avatar_gap = 12
            bubble_x0 = margin_x + avatar_size + avatar_gap  # ~106
            bubble_x1 = canvas_w - margin_x  # 626
            bubble_h = avatar_size  # 80
            bubble_y0 = (canvas_h - bubble_h) // 2  # 40
            bubble_y1 = bubble_y0 + bubble_h  # 120

            # -- 头像垂直居中 --
            avatar_y = (canvas_h - avatar_size) // 2  # 40

            # -- 画布 --
            canvas = Image.new("RGB", (canvas_w, canvas_h), (245, 245, 245))
            canvas.paste(avatar_img, (margin_x, avatar_y), avatar_img)

            draw = ImageDraw.Draw(canvas)

            # -- LV100 标签（气泡上方） --
            draw.text(
                (bubble_x0, bubble_y0 - name_font_size - 4),
                "LV100",
                fill=(150, 150, 150),
                font=font_small,
            )

            # -- 气泡 --
            draw.rounded_rectangle(
                (bubble_x0, bubble_y0, bubble_x1, bubble_y1),
                radius=bubble_r,
                fill=(255, 255, 255),
                outline=(220, 220, 220),
            )
            draw.text(
                (bubble_x0 + txt_pad, bubble_y0 + txt_pad),
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

        yield event.chain_result([AstrImage.fromBytes(image_bytes)])

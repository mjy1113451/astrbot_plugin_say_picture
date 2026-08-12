from io import BytesIO
from typing import Any
import os
import tempfile

from PIL import Image, ImageDraw, ImageFont
import urllib.request

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import At, Image as AstrImage, Plain
from astrbot.api.star import Context, Star

# ---------------------------------------------------------------------------
# 中文字体加载（优先级：插件内置 → 系统路径 → 网络下载）
# ---------------------------------------------------------------------------

# 插件自带的精简中文字体（微软雅黑子集，~6MB）
_BUNDLED_FONT = os.path.join(os.path.dirname(__file__), "fonts", "msyh-subset.ttf")

_SYSTEM_FONT_CANDIDATES = [
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

_NOTO_SANS_SC_URL = (
    "https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/"
    "NotoSansSC-Regular.otf"
)
_font_cache_dir: str | None = None


def _get_font_cache_dir() -> str:
    global _font_cache_dir
    if _font_cache_dir is None:
        _font_cache_dir = os.path.join(tempfile.gettempdir(), "astrbot_say_font")
        os.makedirs(_font_cache_dir, exist_ok=True)
    return _font_cache_dir


def _download_cn_font() -> str | None:
    cache_dir = _get_font_cache_dir()
    cached = os.path.join(cache_dir, "NotoSansSC-Regular.otf")
    if os.path.isfile(cached):
        return cached
    try:
        print("[mention_say] 系统无中文字体，正在下载 Noto Sans SC ...")
        import socket
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(30)
        try:
            urllib.request.urlretrieve(_NOTO_SANS_SC_URL, cached)
        finally:
            socket.setdefaulttimeout(old_timeout)
        print(f"[mention_say] 字体已缓存到 {cached}")
        return cached
    except Exception as e:
        print(f"[mention_say] 字体下载失败: {e}")
        return None


def _load_cn_font(size: int = 26) -> ImageFont.FreeTypeFont:
    """按优先级加载中文字体：内置 → 系统 → 下载 → 默认位图."""
    # 1) 插件内置字体（最可靠）
    if os.path.isfile(_BUNDLED_FONT):
        try:
            return ImageFont.truetype(_BUNDLED_FONT, size)
        except Exception:
            pass
    # 2) 系统字体
    for path in _SYSTEM_FONT_CANDIDATES:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    # 3) 网络下载
    downloaded = _download_cn_font()
    if downloaded:
        try:
            return ImageFont.truetype(downloaded, size)
        except Exception:
            pass
    # 4) 最终兜底
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Plugin
# ---------------------------------------------------------------------------


class MentionSayPlugin(Star):
    name = "mention_say_plugin"
    version = "1.0.7"
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

        rest = full_text[len("说"):].lstrip()
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
            image_bytes = self._render_bubble(avatar_bytes, say_content)
        except Exception as e:
            print(f"[mention_say] 渲染表情包失败: {e}")
            yield event.plain_result(f"表情包生成失败: {e}")
            return

        yield event.chain_result([AstrImage.fromBytes(image_bytes)])

    # ------------------------------------------------------------------
    # 渲染核心
    # ------------------------------------------------------------------

    def _render_bubble(self, avatar_bytes: bytes, text: str) -> bytes:
        """生成聊天气泡表情包，返回 PNG 字节."""
        # ---- 常量 ----
        canvas_w = 520
        bg_color = (232, 234, 237)       # 浅灰蓝背景
        shadow_color = (200, 202, 206)    # 阴影色
        avatar_size = 80
        avatar_border = 3                 # 白色边框宽度
        margin_left = 24                  # 头像左边距
        avatar_gap = 12                   # 头像到三角的间距

        bubble_r = 12                     # 气泡圆角
        bubble_pad_x = 14                 # 气泡内水平边距
        bubble_pad_y = 10                 # 气泡内垂直边距
        font_size = 26                    # 正文字号
        name_font_size = 14               # LV100 字号
        line_h = font_size + 4            # 行高

        font = _load_cn_font(font_size)
        font_small = _load_cn_font(name_font_size)

        # ---- 文字换行 ----
        bubble_x0 = margin_left + avatar_size + avatar_gap + 10  # +10 给三角留位
        bubble_x1 = canvas_w - margin_left
        content_w = bubble_x1 - bubble_x0 - bubble_pad_x * 2

        lines: list[str] = []
        cur = ""
        for ch in text:
            test = cur + ch
            bbox = font.getbbox(test)
            if bbox[2] <= content_w:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = ch
        if cur:
            lines.append(cur)

        text_block_h = len(lines) * line_h
        bubble_h = max(avatar_size, text_block_h + bubble_pad_y * 2)

        # 画布高度（预计算 LV100 标签尺寸）
        _badge_bb = font_small.getbbox("LV100")
        _badge_tw = _badge_bb[2] - _badge_bb[0]
        _badge_th = _badge_bb[3] - _badge_bb[1]
        badge_w = _badge_tw + 14
        badge_h = _badge_th + 8
        badge_gap = 8
        needed_h = bubble_h + badge_h + badge_gap + 24
        canvas_h = max(160, needed_h)

        bubble_y0 = (canvas_h - bubble_h) // 2
        bubble_y1 = bubble_y0 + bubble_h

        # 头像偏上（比气泡顶部高一点）
        avatar_y = bubble_y0 - 10

        # ---- 1. 阴影层（RGBA）----
        shadow_offset = 3
        canvas_rgba = Image.new("RGBA", (canvas_w, canvas_h), bg_color + (255,))
        shadow_draw = ImageDraw.Draw(canvas_rgba)

        # 气泡阴影
        shadow_draw.rounded_rectangle(
            (bubble_x0 + shadow_offset, bubble_y0 + shadow_offset,
             bubble_x1 + shadow_offset, bubble_y1 + shadow_offset),
            radius=bubble_r,
            fill=shadow_color + (90,),
        )

        # LV100 标签（贴气泡左边缘）
        badge_text = "LV100"
        badge_x0 = bubble_x0
        badge_x1 = badge_x0 + badge_w
        badge_y0 = bubble_y0 - badge_h - badge_gap
        badge_y1 = badge_y0 + badge_h
        shadow_draw.rounded_rectangle(
            (badge_x0 + 2, badge_y0 + 2, badge_x1 + 2, badge_y1 + 2),
            rectangle(),
            fill=shadow_color + (70,),
        )

        # ---- 2. 头像（圆形 + 白色边框）----
        avatar_raw = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
        avatar_raw = avatar_raw.resize((avatar_size, avatar_size), Image.LANCZOS)
        mask = Image.new("L", (avatar_size, avatar_size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, avatar_size - 1, avatar_size - 1), fill=255)
        avatar_circle = Image.new("RGBA", (avatar_size, avatar_size), (0, 0, 0, 0))
        avatar_circle.paste(avatar_raw, (0, 0), mask)
        border_size = avatar_size + avatar_border * 2
        border_img = Image.new("RGBA", (border_size, border_size), (0, 0, 0, 0))
        ImageDraw.Draw(border_img).ellipse(
            (0, 0, border_size - 1, border_size - 1), fill=(255, 255, 255, 255)
        )
        border_img.paste(avatar_circle, (avatar_border, avatar_border), avatar_circle)
        canvas_rgba.paste(border_img, (margin_left, avatar_y - avatar_border), border_img)

        draw = ImageDraw.Draw(canvas_rgba)

        # ---- 3. LV100 标签（白字灰底圆角）----
        draw.rounded_rectangle(
            (badge_x0, badge_y0, badge_x1, badge_y1),
            rectangle(),
            fill=(209, 211, 216, 255),
        )
        draw.text(
            (badge_x0 + (badge_w - _badge_tw) // 2, badge_y0 + 2),
            badge_text,
            fill=(255, 255, 255),
            font=font_small,
        )

        # ---- 4. 气泡 + 三角指针 ----
        draw.rounded_rectangle(
            (bubble_x0, bubble_y0, bubble_x1, bubble_y1),
            radius=bubble_r,
            fill=(255, 255, 255, 255),
        )
        # 三角指针（气泡左上角，指向头像方向）
        tri_tip_x = bubble_x0          # 三角尖端（贴气泡左边缘）
        tri_tip_y = bubble_y0 + 18     # 尖端垂直位置（气泡顶部偏下）
        tri_points = [
            (tri_tip_x, tri_tip_y),           # 尖端（指向头像）
            (tri_tip_x - 10, tri_tip_y - 10), # 左上
            (tri_tip_x - 10, tri_tip_y + 10), # 左下
        ]
        draw.polygon(tri_points, fill=(255, 255, 255, 255))
        # 覆盖三角左侧边缘（用背景色画竖线，模拟三角嵌入效果）
        draw.line(
            [(tri_tip_x - 10, tri_tip_y - 9), (tri_tip_x - 10, tri_tip_y + 9)],
            fill=bg_color + (255,),
            width=2,
        )

        # ---- 5. 多行文字 ----
        for i, ln in enumerate(lines):
            draw.text(
                (bubble_x0 + bubble_pad_x, bubble_y0 + bubble_pad_y + i * line_h),
                ln,
                fill=(30, 30, 30),
                font=font,
            )

        # ---- 导出 PNG ----
        buf = BytesIO()
        canvas_rgba.save(buf, format="PNG")
        return buf.getvalue()

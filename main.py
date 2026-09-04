from typing import Any

import urllib.request

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import At, Image as AstrImage, Plain
from astrbot.api.star import Context, Star
from astrbot.api.star.star_tools import StarTools

from .rendering.chat_screenshot import (
    render_chat_screenshot,
    get_bundled_fallback_paths,
    set_font_dir,  # noqa: F401  (仅供测试确认导入路径可用)
    set_font_manager,
)
from .rendering.font_manager import FontManager

# ---------------------------------------------------------------------------
# Plugin
# ---------------------------------------------------------------------------


class MentionSayPlugin(Star):
    name = "mention_say_plugin"
    version = "1.1.0"
    author = "AI Assistant"
    description = "当检测到@某用户说～时，生成表情包"

    def __init__(self, context: Context):
        super().__init__(context)
        # 字体后台下载在 initialize() 中启动

    async def initialize(self) -> None:
        """插件加载完成后异步初始化：字体 CDN 下载（不阻塞消息处理）."""
        try:
            import asyncio

            data_dir = StarTools.get_data_dir(str(self.name))
            self._font_manager = FontManager(data_dir)
            set_font_manager(self._font_manager)
            # 后台下载，避免阻塞 initialize
            asyncio.create_task(self._ensure_fonts_task())
        except Exception as e:
            print(f"[mention_say] 字体后台初始化失败（使用内置字体兜底）: {e}")
            import traceback

            traceback.print_exc()

    async def _ensure_fonts_task(self) -> None:
        """后台异步确保字体可用（CDN 下载 + 校验）."""
        try:
            await self._font_manager.ensure_fonts()
            if self._font_manager.font_dir.exists():
                set_font_dir(self._font_manager.font_dir)
        except Exception as e:
            print(f"[mention_say] 字体后台下载失败（使用内置字体兜底）: {e}")

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

        # ---- 获取头像 + 群成员信息 ----
        avatar_bytes: bytes | None = None
        member_info: dict[str, Any] = {}
        try:
            bot = getattr(event, "bot", None)
            if bot is not None and event.get_group_id():
                try:
                    member_info = await bot.call_action(
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

        # ---- 渲染（方案 A：anti_revoke 聊天截图格式，保留原排版参数）----
        try:
            name = (
                member_info.get("card")
                or member_info.get("nickname")
                or f"用户{mentioned_user_id}"
            )
            role = member_info.get("role", "member")
            level = int(member_info.get("level", 0) or 0)
            title = member_info.get("title", "") or ""

            image_bytes = render_chat_screenshot(
                name=name,
                avatar_bytes=avatar_bytes,
                text=say_content,
                role=role,
                title=title,
                level=level,
                show_title=True,
                # 保持 say_picture 原有排版（issue #47 "图片不变"）
                font_size=26,
                max_text_width=480,
                name_font_size=20,
                label_font_size=18,
                fallback_paths=get_bundled_fallback_paths(),
            )
        except Exception as e:
            print(f"[mention_say] 渲染表情包失败: {e}")
            import traceback

            traceback.print_exc()
            yield event.plain_result(f"表情包生成失败: {e}")
            return

        yield event.chain_result([AstrImage.fromBytes(image_bytes)])
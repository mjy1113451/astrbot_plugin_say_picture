from typing import Any

import urllib.request

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import At, Image as AstrImage, Plain
from astrbot.api.star import Context, Star
from astrbot.api.star import StarTools

from .rendering.chat_screenshot import (
    render_chat_screenshot,
    get_bundled_fallback_paths,
    make_placeholder_avatar,
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

    async def _resolve_member_info(
        self, event: AstrMessageEvent, mentioned_user_id: str
    ) -> dict[str, Any]:
        """群成员信息：OneBot get_group_member_info 优先；非 OneBot 平台/失败回退默认值。

        issue #61：QQ 官方机器人等平台的 id 为 openid（非数字）、client 无 call_action，
        这里统一吞掉异常并返回默认成员信息，保证渲染流程继续。
        """
        info: dict[str, Any] = {}
        bot = getattr(event, "bot", None)
        group_id = event.get_group_id()
        if bot is not None and group_id and hasattr(bot, "call_action"):
            try:
                gid_int = int(group_id)
                uid_int = int(mentioned_user_id)
            except ValueError:
                # review #62：官方机器人 openid 非数字，明确分类日志，不与 call_action 失败混淆
                print(
                    f"[mention_say] group_id/user_id 非数字（官方机器人 openid 形态），"
                    f"跳过 OneBot 成员信息: gid={group_id!r} uid={mentioned_user_id!r}"
                )
                gid_int = uid_int = None
            if gid_int is not None:
                try:
                    info = (
                        await bot.call_action(
                            "get_group_member_info",
                            group_id=gid_int,
                            user_id=uid_int,
                            no_cache=True,
                        )
                        or {}
                    )
                except Exception as e:
                    print(f"[mention_say] 获取群成员信息失败（可能非 OneBot 平台）: {e}")
                    info = {}
        return {
            "role": info.get("role", "member"),
            "level": int(info.get("level", 0) or 0),
            "title": info.get("title", "") or "",
            "nickname": info.get("card") or info.get("nickname") or "",
            "avatar": info.get("avatar") or "",
        }

    @staticmethod
    def _fetch_avatar_sync(urls: list[str]) -> bytes | None:
        """同步顺序拉取头像；经线程池调用避免阻塞事件循环（review #62 sync-in-async）."""
        for url in urls:
            try:
                with urllib.request.urlopen(url, timeout=10) as resp:
                    return resp.read()
            except Exception as e:
                print(f"[mention_say] 获取头像失败 {url}: {e}")
        return None

    async def _fetch_avatar(
        self, mentioned_user_id: str, member_info: dict[str, Any]
    ) -> bytes | None:
        """头像：成员信息 avatar(仅 http(s)) → QLogo CDN(仅数字 QQ) → None(调用方占位)."""
        urls: list[str] = []
        avatar_field = str(member_info.get("avatar") or "")
        if avatar_field:
            if avatar_field.startswith(("http://", "https://")):
                urls.append(avatar_field)
            else:
                # review #62 ssrf：avatar 字段可能为相对路径/base64/非 http(s) 协议，跳过并走兜底
                print(f"[mention_say] 跳过非 http(s) avatar 字段: {avatar_field[:64]!r}")
        if mentioned_user_id.isdigit():
            urls.append(f"https://q1.qlogo.cn/g?b=qq&nk={mentioned_user_id}&s=640")
        if not urls:
            return None
        import asyncio

        return await asyncio.to_thread(self._fetch_avatar_sync, urls)

    @filter.regex(r"说[\s～]")
    async def on_mention_say(self, event: AstrMessageEvent):
        """检测消息链中 "At 某用户" 紧跟 "说[～/空格]内容" 格式。

        issue #54：「说」后必须有分隔符（空格或～），
        避免「说话」「说明天见」等自然词误触发。
        """
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

        rest = full_text[len("说"):]
        if not rest:
            return
        if rest[0] == "～":
            # 兼容：说～内容 / 说～ 内容
            rest = rest[1:].lstrip()
        elif rest[0].isspace():
            # 标准格式：说 + 空格 + 内容（支持全角空格 U+3000）
            rest = rest.lstrip()
        else:
            # 「说话」「说明天见」等无分隔符自然词，不触发
            return
        say_content = rest.strip()

        if not say_content:
            return

        mentioned_user_id = str(at_qq)

        print(f"[mention_say] message_str: {event.message_str}")
        print(f"[mention_say] mentioned_user_id: {mentioned_user_id}")
        print(f"[mention_say] say_content: {say_content}")

        # ---- 获取头像 + 群成员信息（跨平台：OneBot 优先，官方机器人等优雅回退）----
        member_info = await self._resolve_member_info(event, mentioned_user_id)
        avatar_bytes = await self._fetch_avatar(mentioned_user_id, member_info)
        if avatar_bytes is None:
            # issue #61：QQ 官方机器人等平台无 OneBot 头像接口、openid 也无法走 QLogo CDN，
            # 用占位头像继续渲染，而不是放弃出图。
            avatar_bytes = make_placeholder_avatar()

        # ---- 渲染（方案 A：anti_revoke 聊天截图格式，保留原排版参数）----
        try:
            name = member_info.get("nickname") or f"用户{mentioned_user_id}"
            role = member_info.get("role", "member")
            level = member_info.get("level", 0)
            title = member_info.get("title", "")
            # 调试：打印昵称/头衔码点，用于定位渲染 tofu 的确切字符
            print(
                f"[mention_say] name codepoints: "
                f"{[hex(ord(c)) for c in name]!r}"
            )
            print(
                f"[mention_say] title codepoints: "
                f"{[hex(ord(c)) for c in title]!r}"
            )

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
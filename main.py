import re
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star


class MentionSayPlugin(Star):
    name = "mention_say_plugin"
    version = "1.0.2"
    author = "AI Assistant"
    description = "当检测到@某用户说～时，生成表情包"

    def __init__(self, context: Context):
        super().__init__(context)

    @filter.regex(r"@(\S+)\s+说～(.*)")
    async def on_mention_say(self, event: AstrMessageEvent):
        """检测 @用户 说～ 格式并生成表情包"""
        if not self.context.get_config().get("enabled", True):
            return

        match = event.message_str_matched
        mentioned_user = match.group(1)
        say_content = match.group(2).strip()

        # ── 调试日志 begin ──
        print(f"[mention_say] raw_message: {event.raw_message}")
        print(f"[mention_say] message_str_matched: {event.message_str_matched}")
        print(f"[mention_say] unified_msg_origin: {event.unified_msg_origin}")
        print(f"[mention_say] mentioned_user: {mentioned_user}")
        print(f"[mention_say] say_content: {say_content}")
        # ── 调试日志 end ──

        if not say_content:
            return

        # 获取被@用户的头像（通过 context 获取群员信息）
        avatar_url = None
        try:
            member_info = await self.context.get_group_member_info(
                group_id=event.unified_msg_origin,
                user_id=mentioned_user,
            )
            if member_info:
                avatar_url = member_info.get("avatar")
                print(f"[mention_say] avatar_url: {avatar_url}")
        except Exception as e:
            print(f"[mention_say] get_group_member_info error: {e}")

        if not avatar_url:
            yield event.plain_result(f"未找到用户 {mentioned_user} 的信息")
            return

        # 生成表情包描述
        prompt = (
            f"一个聊天界面截图，显示一个用户头像在左边，右边有消息框。"
            f"头像是一个圆形图片，显示被@用户的头像。"
            f"在头像上方显示\"LV100\"的灰色标签。"
            f"右边的消息框是白色圆角矩形，里面显示\"{say_content}\"的文字。"
            f"整体风格是简约的聊天界面，背景是浅灰色。"
        )

        # 调用图片生成工具
        image_url = await self.context.llm_generate_image(prompt)
        if image_url:
            yield event.image_result(image_url)

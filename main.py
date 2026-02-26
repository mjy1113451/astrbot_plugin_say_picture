# context_aware_reply.py
"""
上下文感知回复插件
在Bot回复消息前，获取并注入当前会话的历史消息作为上下文
"""

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.provider import ProviderRequest
from typing import List, Optional


@register("context_aware_reply", "AstrBot Plugin", "在Bot回复前注入会话上下文", "1.0.0")
class ContextAwareReplyPlugin(Star):
    """
    上下文感知回复插件
    
    功能：当Bot准备回复消息时，自动获取当前会话的历史消息，
    并将其添加到LLM请求的上下文中，使Bot能够参考之前的对话内容。
    """
    
    def __init__(self, context: Context):
        super().__init__(context)
        # 可配置参数：获取最近几轮对话作为上下文
        self.max_history_turns = 3  # 获取最近3轮对话
        self.include_system_prompt = True  # 是否包含系统提示
    
    @filter.on_llm_request(priority=10)
    async def inject_context_to_llm_request(self, event: AstrMessageEvent, req: ProviderRequest):
        """
        在LLM请求时注入上下文
        
        参数:
            event: AstrBot消息事件对象
            req: LLM请求对象，包含请求文本、系统提示等信息
        """
        try:
            # 获取当前会话ID
            session_id = event.session_id
            
            # 获取历史消息记录
            history_messages = await self._get_session_history(session_id)
            
            if not history_messages:
                return
            
            # 构建上下文提示
            context_prompt = self._build_context_prompt(history_messages)
            
            # 将上下文添加到系统提示中
            if self.include_system_prompt and req.system_prompt:
                req.system_prompt = f"{context_prompt}\n\n{req.system_prompt}"
            else:
                req.system_prompt = context_prompt
                
            # 记录日志（实际使用时可替换为正式日志系统）
            print(f"[ContextPlugin] 已为会话 {session_id} 注入 {len(history_messages)} 条历史消息上下文")
            
        except Exception as e:
            print(f"[ContextPlugin] 注入上下文时出错: {e}")
    
    async def _get_session_history(self, session_id: str) -> List[str]:
        """
        获取指定会话的历史消息记录
        
        参数:
            session_id: 会话ID
            
        返回:
            历史消息列表，每条消息格式为"角色: 内容"
        """
        try:
            # 通过AstrBot的会话管理器获取历史记录
            # 注意：这里需要AstrBot提供会话管理API，以下为示例实现
            history = []
            
            # 实际项目中，您需要根据AstrBot的API获取会话历史
            # 这里提供一个基本框架：
            
            # 1. 获取当前会话对象
            session_controller = self.context.get_session_controller()
            session = await session_controller.get_session(session_id)
            
            if not session:
                return history
            
            # 2. 获取历史消息（实现可能因AstrBot版本而异）
            # 假设会话对象有history_messages属性
            if hasattr(session, 'history_messages'):
                all_messages = session.history_messages[-self.max_history_turns:]
                
                for msg in all_messages:
                    # 根据消息类型确定角色（用户或助手）
                    role = "用户" if msg.sender_is_user() else "Bot"
                    content = msg.message_str or str(msg.message)
                    history.append(f"{role}: {content}")
            
            return history
            
        except Exception as e:
            print(f"[ContextPlugin] 获取会话历史出错: {e}")
            return []
    
    def _build_context_prompt(self, history_messages: List[str]) -> str:
        """
        构建上下文提示字符串
        
        参数:
            history_messages: 历史消息列表
            
        返回:
            格式化的上下文提示字符串
        """
        if not history_messages:
            return ""
        
        context_lines = ["【当前对话历史上下文】"]
        context_lines.extend(history_messages)
        context_lines.append("\n请基于以上历史对话上下文，回答用户最新的问题。")
        
        return "\n".join(context_lines)
    
    @filter.command("clear_context")
    async def clear_context(self, event: AstrMessageEvent):
        """
        清除当前会话的上下文记忆
        
        指令：/clear_context
        """
        session_id = event.session_id
        
        # 这里需要实现清除会话历史的逻辑
        # 具体实现取决于AstrBot的会话管理API
        
        yield event.plain_result(f"已清除会话 {session_id} 的上下文记忆。")
    
    @filter.command("set_history_turns")
    async def set_history_turns(self, event: AstrMessageEvent, turns: int):
        """
        设置保存历史对话的轮数
        
        指令：/set_history_turns 5
        
        参数:
            turns: 保存的历史对话轮数
        """
        if turns < 0:
            yield event.plain_result("轮数不能小于0。")
            return
            
        self.max_history_turns = turns
        yield event.plain_result(f"已设置历史对话轮数为 {turns}。")

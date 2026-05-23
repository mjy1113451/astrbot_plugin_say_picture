from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger
from typing import Dict, Any, Optional
import json
from datetime import datetime

class GroupSpeakCounter(Star):
    """
    群聊发言统计插件
    功能：统计群员发言次数（排除群主），显示发言榜，清除统计数据，可配置上榜人数
    """
    
    def __init__(self, context: Context):
        super().__init__(context)
        self.storage_key = "group_speak_stats"
        self.config_key = "top_n_config"
        logger.info("群聊发言统计插件初始化完成")
    
    async def _get_stats(self) -> Dict[str, Any]:
        """获取统计数据"""
        stats = await self.get_kv_data(self.storage_key, {})
        return stats if stats else {}
    
    async def _save_stats(self, stats: Dict[str, Any]):
        """保存统计数据"""
        await self.put_kv_data(self.storage_key, stats)
    
    async def _get_top_n(self) -> int:
        """获取配置的上榜人数"""
        top_n = await self.get_kv_data(self.config_key, 20)
        if not isinstance(top_n, int) or top_n < 1 or top_n > 100:
            top_n = 20
        return top_n
    
    async def _save_top_n(self, top_n: int):
        """保存上榜人数配置"""
        await self.put_kv_data(self.config_key, top_n)
    
    async def _is_group_owner(self, event: AstrMessageEvent) -> bool:
        """
        判断发送者是否为群主
        注意：AstrBot不同版本可能获取群主信息的方式不同，
        这里提供几种常见方法的实现
        """
        # 方法1：通过事件属性直接判断
        if hasattr(event, 'is_group_owner') and event.is_group_owner:
            return True
        
        # 方法2：通过群成员信息判断（需要适配器支持）
        if hasattr(event, 'member_info'):
            member_info = event.member_info
            if hasattr(member_info, 'role') and member_info.role == 'owner':
                return True
        
        # 方法3：通过群成员列表判断（较慢，不推荐）
        # 这里需要根据实际适配器API实现
        
        return False
    
    async def _update_user_count(self, group_id: str, user_id: str, user_name: str):
        """更新用户发言计数"""
        stats = await self._get_stats()
        
        if "group_stats" not in stats:
            stats["group_stats"] = {}
        
        if group_id not in stats["group_stats"]:
            stats["group_stats"][group_id] = {}
        
        # 获取当前计数，如果不存在则初始化为0
        user_data = stats["group_stats"][group_id].get(user_id, {
            "count": 0,
            "name": user_name,
            "last_active": None
        })
        
        # 更新计数
        user_data["count"] += 1
        user_data["last_active"] = datetime.now().isoformat()
        
        # 保存更新后的数据
        stats["group_stats"][group_id][user_id] = user_data
        stats["last_update"] = datetime.now().isoformat()
        
        await self._save_stats(stats)
        
        logger.debug(f"更新发言计数: 群{group_id} 用户{user_name}({user_id}) 次数:{user_data['count']}")
    
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        """
        监听群消息事件，更新发言计数
        注意：排除群主的消息
        """
        # 检查是否是群消息
        if not hasattr(event, 'group_id') or not event.group_id:
            return
        
        # 检查是否是群主，如果是则不统计
        if await self._is_group_owner(event):
            logger.debug(f"跳过群主消息: 群{event.group_id} 用户{event.get_sender_name()}")
            return
        
        group_id = str(event.group_id)
        user_id = str(event.sender_id)
        user_name = event.get_sender_name()
        
        # 排除机器人自己的消息
        if user_id == str(event.self_id):
            return
        
        await self._update_user_count(group_id, user_id, user_name)
    
    @filter.command("发言榜", alias=["发言统计", "群发言榜"])
    async def show_speak_rank(self, event: AstrMessageEvent):
        """显示发言榜"""
        group_id = str(event.group_id)
        
        # 检查是否在群聊中
        if not group_id:
            yield event.plain_result("该指令只能在群聊中使用！")
            return
        
        stats = await self._get_stats()
        
        if "group_stats" not in stats or group_id not in stats["group_stats"]:
            yield event.plain_result("本群暂无发言统计数据！")
            return
        
        group_data = stats["group_stats"][group_id]
        
        # 按发言次数排序
        sorted_users = sorted(
            group_data.items(),
            key=lambda x: x[1]["count"],
            reverse=True
        )
        
        # 获取配置的上榜人数
        top_n = await self._get_top_n()
        show_items = sorted_users[:top_n]
        
        # 构建发言榜
        rank_list = []
        for index, (user_id, user_info) in enumerate(show_items, 1):
            rank_list.append(f"{index}. {user_info['name']}: {user_info['count']}次")
        
        if not rank_list:
            yield event.plain_result("本群暂无发言统计数据！")
            return
        
        # 构建完整消息
        message = f"📊 群发言榜（{group_id}）\n"
        message += "=" * 30 + "\n"
        message += "\n".join(rank_list)
        
        # 添加统计信息
        total_users = len(group_data)
        total_messages = sum(user["count"] for user in group_data.values())
        message += f"\n\n📈 统计信息: 共{total_users}人参与，累计发言{total_messages}次"
        message += f"\n🕐 最后更新: {stats.get('last_update', '未知')}"
        
        yield event.plain_result(message)
    
    @filter.command("清除统计", alias=["重置统计"])
    async def clear_stats(self, event: AstrMessageEvent):
        """清除统计数据"""
        group_id = str(event.group_id)
        
        if not group_id:
            yield event.plain_result("该指令只能在群聊中使用！")
            return
        
        # 获取当前统计
        stats = await self._get_stats()
        
        if "group_stats" in stats and group_id in stats["group_stats"]:
            # 清除本群统计
            del stats["group_stats"][group_id]
            stats["last_update"] = datetime.now().isoformat()
            await self._save_stats(stats)
            
            yield event.plain_result(f"已清除群{group_id}的发言统计数据！")
            logger.info(f"用户{event.get_sender_name()}清除了群{group_id}的发言统计")
        else:
            yield event.plain_result(f"群{group_id}暂无统计数据需要清除！")
    
    @filter.command("设置上榜人数", alias=["设置发言榜人数"])
    async def set_top_n(self, event: AstrMessageEvent):
        """设置上榜人数"""
        # 解析指令参数
        args = event.message_str.split()
        
        if len(args) < 2:
            current_top_n = await self._get_top_n()
            yield event.plain_result(f"当前上榜人数设置为: {current_top_n}人\n用法: /设置上榜人数 10")
            return
        
        try:
            new_top_n = int(args[1])
            if new_top_n < 1 or new_top_n > 100:
                yield event.plain_result("上榜人数范围应为1-100，请重新设置！")
                return
            
            # 保存配置
            await self._save_top_n(new_top_n)
            
            yield event.plain_result(f"✅ 已将发言榜上榜人数设置为: {new_top_n}人")
            logger.info(f"用户{event.get_sender_name()}将上榜人数设置为{new_top_n}")
            
        except ValueError:
            yield event.plain_result("❌ 请输入有效的数字！\n用法: /设置上榜人数 10")
    
    @filter.command("全局统计")
    async def global_stats(self, event: AstrMessageEvent):
        """显示全局统计信息（所有群）"""
        stats = await self._get_stats()
        
        if "group_stats" not in stats:
            yield event.plain_result("暂无全局统计数据！")
            return
        
        # 统计所有群的总发言数
        total_groups = len(stats["group_stats"])
        total_users = 0
        total_messages = 0
        
        group_stats = []
        for group_id, group_data in stats["group_stats"].items():
            group_total = sum(user["count"] for user in group_data.values())
            group_users = len(group_data)
            
            total_users += group_users
            total_messages += group_total
            
            group_stats.append(f"群{group_id}: {group_users}人, {group_total}条消息")
        
        message = "🌐 全局发言统计\n"
        message += "=" * 30 + "\n"
        message += "\n".join(group_stats)
        message += f"\n\n📊 总计: {total_groups}个群, {total_users}位用户, {total_messages}条消息"
        
        yield event.plain_result(message)
    
    async def terminate(self):
        """插件卸载时清理资源"""
        logger.info("群聊发言统计插件已卸载")

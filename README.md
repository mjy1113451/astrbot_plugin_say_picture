# astrbot_plugin_say_picture

当检测到群消息中 **@某人 说～xxx**（或 **@某人 说 xxx**）格式时，自动生成聊天气泡表情包并发送。

基于 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 框架开发，兼容 OneBot v11 标准；在 QQ 官方机器人等非 OneBot 平台会优雅降级（见「平台兼容」）。

---

## 效果预览

发送以下任意一条消息：

```
@某人 说～你好呀
@某人 说 今天天气真好
```

机器人将生成一张聊天气泡表情包：

- 🧑 圆形头像 + 白色边框
- 💬 白色聊天气泡 + 三角指向头像
- 🏷️ 等级徽章（取群成员实际等级，缺失时显示 `LV0`）
- ✍️ 气泡内显示「说」后面的文字
- 🏅 群头衔（OneBot 平台可用时显示）

### 触发规则

- 消息中必须 **@到一个用户**（@全体成员不触发）。
- 「说」后面必须紧跟 **分隔符**：半角空格、全角空格（U+3000）或全角波浪号 `～`。
- 因此「说话」「说明天见」这类自然词不会误触发。
- 「说～」后面的空格可有可无：`说～内容` 与 `说～ 内容` 都会触发。

---

## 安装

### 方式一：插件市场（推荐）

在 AstrBot WebUI 插件市场搜索 `astrbot_plugin_say_picture`，一键安装。

### 方式二：手动安装

```bash
git clone https://github.com/mjy1113451/astrbot_plugin_say_picture.git
```

将仓库内容放入 AstrBot 插件目录（通常为 `AstrBot/plugins/`）后重启 AstrBot。

---

## 配置

插件**没有可配置项**：`_conf_schema.json` 为空对象 `{}`，`config.json` 同样为空。旧版 `enabled` 功能开关已删除（issue #63）。如需整体停用，请在 AstrBot WebUI 插件管理页直接禁用本插件。

---

## 工作原理

```
用户发送 "@某人 说～内容" 或 "@某人 说 内容"
    ↓
filter.regex("说[\\s～]") 命中后，从消息链提取 At 组件 + 「说」后的文字
    ↓
获取被 @ 用户的头像与群成员信息（OneBot get_group_member_info 优先）
    ↓
PIL 渲染聊天气泡图片（圆形头像 + 气泡 + 等级徽章 + 头衔）
    ↓
以图片消息形式发送回聊天
```

### 技术细节

| 项目 | 说明 |
|------|------|
| 图片渲染 | PIL (Pillow)，输出 RGBA PNG |
| 头像获取 | 成员信息 `avatar`（仅 http/https）→ `q1.qlogo.cn`（仅数字 QQ）→ 占位头像兜底 |
| 字体 | 插件内置子集字体 → 系统字体 → 字体 CDN 下载（`font_manager.py`），全部失败时用内置字体兜底 |
| 非数字 ID | QQ 官方机器人的 openid 非数字，跳过 OneBot 成员查询与 QLogo CDN，直接走占位头像 |

---

## 平台兼容（issue #61）

渲染与发送走 AstrBot 通用消息接口，跨平台可用；仅「群成员信息（头像/昵称/等级/头衔）」依赖 OneBot，非 OneBot 平台优雅降级：

| 平台 | 头像 | 昵称 / 等级 / 头衔 |
|------|------|--------------------|
| OneBot v11（aiocqhttp 等） | 成员信息 avatar → QLogo CDN | 完整（card/nickname/level/title） |
| QQ 官方机器人等 | 占位头像（纯色圆） | 昵称回退 `用户<id>`，等级 LV0、无头衔 |

即在官方机器人上仍能正常出图，只是头像为占位圆、等级/头衔为默认值。

---

## 项目结构

```
astrbot_plugin_say_picture/
├── fonts/
│   ├── msyh-subset.ttf          # 内置中文字体（微软雅黑子集）
│   └── hangul-subset.ttf        # 内置韩文字体子集
├── rendering/
│   ├── __init__.py
│   ├── chat_screenshot.py       # 气泡图渲染
│   └── font_manager.py          # 字体探测 / CDN 下载 / 缓存
├── resources/
│   ├── corner1.png              # 气泡边角装饰
│   ├── corner2.png
│   ├── corner3.png
│   └── corner4.png
├── main.py                      # 插件主逻辑（MentionSayPlugin）
├── metadata.yaml                # 插件元信息
├── _conf_schema.json            # 配置 schema（空）
├── config.json                  # 插件配置（空）
├── LICENSE                      # AGPL-3.0
└── README.md
```

---

## 依赖

- Python ≥ 3.10（代码使用 `dict[str, Any]`、`bytes | None` 等 3.10+ 语法）
- Pillow（AstrBot 核心已提供，无需单独安装）
- AstrBot 核心版本由框架决定，本仓库 `metadata.yaml` 未声明 `astrbot_version`

---

## 许可证

[AGPL-3.0](./LICENSE)

> 修改后的代码必须开源，网络服务使用本项目也必须开源。

---

## 作者

[mjy1113451](https://github.com/mjy1113451)

[作者的插件群](https://qun.qq.com/universal-share/share?ac=1&authKey=LPNpKBYL2R3WqjbvADCCIA8XpZ%2Fqmitz2xpdkNNlOin%2BPz6ez8UCrbZDgneoR762&busi_data=eyJncm91cENvZGUiOiIxMDc1OTIwMzIzIiwidG9rZW4iOiJ0bG5BWjhZN2xkZXFlVk1WclZRNGNDVElCRW9CRG9ieFZzUEFwMEljaXNibzVOUUc1YkJSOC9NRnI4NTBOcEhkIiwidWluIjoiMTczMTUzODMzNCJ9&data=hV1Jra4PMbmVn17xmFmtJ-UBqIGZ7rBtO31vMQXm2h5RmBxeNr6YKfDa7FJAUe3MJS75Vl4LP7piI4YxWV2fOg&svctype=4&tempid=h5_group_info)

如有问题或建议，欢迎提交 Issue 或联系作者。

# astrbot_plugin_say_picture

> 当群里有人 **@某人 说 内容**（或 **@某人 说～内容**）时，自动生成一张聊天气泡表情包并发送。

基于 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 开发。OneBot v11 环境下会读取被 @ 成员的昵称、等级与头衔；其他平台自动降级，仍能正常出图。

- 版本：**1.1.1**
- 许可证：AGPL-3.0

---

## 效果预览

发送以下任意一条消息：

```
@某人 说 你好呀
@某人 说～今天天气真好
```

机器人会生成一张聊天气泡图片：

- 圆形头像 + 白色边框
- 白色聊天气泡，带指向头像的小三角
- 头像右侧显示 **LV + 群等级徽章**（如 `LV 12`）
- 昵称旁的徽章还会显示身份或头衔：群主 / 管理员 / 自定义头衔，无头衔时按等级显示段位（青铜、白银、黄金、铂金、钻石、王者）
- 气泡内显示「说」后面的文字

---

## 触发规则

消息中必须同时满足：

1. 含有一个 **@某人** 组件（@全体成员不触发）；
2. 该 @ 之后的文字以 **「说」** 开头；
3. 「说」后面紧跟 **空格** 或 **～** 作为分隔符，然后是内容。

「说话」「说明天见」这类没有分隔符的词不会触发（issue #54）。

---

## 安装

### 方式一：插件市场

在 AstrBot WebUI 插件市场搜索 `astrbot_plugin_say_picture` 一键安装。

### 方式二：手动安装

```bash
git clone https://github.com/mjy1113451/astrbot_plugin_say_picture.git
# 将仓库内容放入 AstrBot 插件目录（通常为 AstrBot/data/plugins/）
```

---

## 配置

插件无可配置项（`_conf_schema.json` 为空对象）。如需停用，请在 AstrBot 插件管理页直接禁用本插件。

---

## 工作原理

```
群消息 "@某人 说 内容"
    ↓
正则预筛「说[空格/～]」→ 提取 At 组件与「说」后面的文字
    ↓
OneBot 获取群成员信息（昵称 / 等级 / 头衔 / 角色）
    ↓
获取头像：成员 avatar → q1.qlogo.cn（仅数字 QQ）→ 占位头像
    ↓
PIL 渲染：圆形头像 + 昵称 + LV 徽章 + 头衔徽章 + 聊天气泡
    ↓
以图片消息发送
```

### 技术细节

| 项目 | 说明 |
|------|------|
| 渲染 | Pillow（PIL） |
| 输出格式 | **JPEG（RGB，quality 90）** |
| 中文字体 | 内置 `fonts/msyh-subset.ttf`（微软雅黑子集）；启动后后台从 CDN 下载 Noto Sans SC（manifest + SHA256 校验），失败自动回退内置字体 |
| 特殊字符 | 内置 `fonts/hangul-subset.ttf` 等字体链做字符级回退；整条链都缺字形且非 emoji 的字符直接跳过，避免出现方块 |
| Emoji | 有 `pilmoji` + `emoji` 时渲染成图片；缺失时自动过滤 emoji |
| 头像获取 | OneBot `get_group_member_info` 的 avatar → `q1.qlogo.cn`（仅数字 QQ）→ 纯色占位头像 |

### 平台兼容（issue #61）

| 平台 | 头像 | 昵称 / 等级 / 头衔 |
|------|------|--------------------|
| OneBot v11（aiocqhttp 等） | 成员 avatar → QLogo CDN | 完整（card / nickname / level / title / role） |
| QQ 官方机器人等 | 占位头像（纯色圆） | 昵称回退 `用户<id>`，等级 LV0，无头衔 |

非 OneBot 平台不会报错，只是头像与等级信息为默认值。

---

## 项目结构

```
astrbot_plugin_say_picture/
├── main.py                  # 插件入口：消息匹配、成员信息、头像获取、调用渲染
├── rendering/
│   ├── chat_screenshot.py   # 聊天截图渲染（头像 / 昵称 / LV 徽章 / 气泡）
│   └── font_manager.py      # 字体校验与 CDN 下载
├── fonts/
│   ├── msyh-subset.ttf      # 内置中文字体（微软雅黑子集）
│   └── hangul-subset.ttf    # 韩文等补充字符
├── resources/               # 气泡圆角等素材
├── _conf_schema.json        # 配置 schema（空）
├── config.json              # 插件配置（空）
├── metadata.yaml            # 插件元信息
├── LICENSE                  # AGPL-3.0
└── README.md
```

---

## 依赖

- Python ≥ 3.10
- Pillow（AstrBot 环境已提供）
- 可选：`pilmoji`、`emoji`（启用 emoji 图片渲染；缺失时自动降级为过滤 emoji）

---

## 许可证

[AGPL-3.0](./LICENSE)

> 修改后的代码必须开源；作为网络服务使用本项目时也必须开源。

---

## 作者

[mjy1113451](https://github.com/mjy1113451)

[作者的插件群](https://qun.qq.com/universal-share/share?ac=1&authKey=LPNpKBYL2R3WqjbvADCCIA8XpZ%2Fqmitz2xpdkNNlOin%2BPz6ez8UCrbZDgneoR762&busi_data=eyJncm91cENvZGUiOiIxMDc1OTIwMzIzIiwidG9rZW4iOiJ0bG5BWjhZN2xkZXFlVk1WclZRNGNDVElCRW9CRG9ieFZzUEFwMEljaXNibzVOUUc1YkJSOC9NRnI4NTBOcEhkIiwidWluIjoiMTczMTUzODMzNCJ9&data=hV1Jra4PMbmVn17xmFmtJ-UBqIGZ7rBtO31vMQXm2h5RmBxeNr6YKfDa7FJAUe3MJS75Vl4LP7piI4YxWV2fOg&svctype=4&tempid=h5_group_info)

如有问题或建议，欢迎提交 Issue。

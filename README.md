# astrbot_plugin_say_picture

当检测到群消息中 **@某人 说～xxx**（或 **@某人 说xxx**）格式时，自动生成聊天气泡表情包并发送。

基于 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 框架开发，兼容 OneBot v11 标准。

---

## 效果预览

发送以下任意一条消息：

```
@某人 说～你好呀
@某人 说今天天气真好
```

机器人将生成一张聊天气泡表情包：

- 🧑 圆形头像 + 白色边框
- 💬 白色聊天气泡 + 三角指向头像
- 🏷️ "LV100" 等级标签
- ✍️ 气泡内显示你说的话

---

## 安装

### 方式一：插件市场（推荐）

在 AstrBot WebUI 插件市场搜索 `astrbot_plugin_say_picture`，一键安装。

### 方式二：手动安装

```bash
# 克隆仓库
git clone https://github.com/mjy1113451/astrbot_plugin_say_picture.git

# 将内容放入 AstrBot 插件目录后重启
# 通常目录为：AstrBot/plugins/
```

---

## 配置

插件有一个开关配置项：

```json
// config.json
{
  "enabled": true   // true=开启，false=关闭
}
```

在 AstrBot WebUI 的插件配置页面也可以直接修改。

---

## 工作原理

```
用户发送 "@某人 说～内容" 
    ↓
插件拦截消息链，提取 At 组件 + "说" 后面的文字
    ↓
通过 OneBot API 获取被 @ 用户的头像
    ↓
PIL 渲染生成聊天气泡图片（圆形头像 + 气泡 + LV100标签）
    ↓
以图片消息形式发送回聊天
```

### 技术细节

| 项目 | 说明 |
|------|------|
| 图片渲染 | PIL (Pillow) |
| 中文字体 | 插件内置微软雅黑子集 / 系统字体 / 网络下载 Noto Sans SC |
| 头像获取 | OneBot `get_group_member_info` → 失败则用 `q1.qlogo.cn` |
| 输出格式 | RGBA PNG |

---

## 项目结构

```
astrbot_plugin_say_picture/
├── fonts/
│   └── msyh-subset.ttf      # 内置中文字体（微软雅黑子集）
├── .sakura/                  # Sakura 配置（AstrBot 模板）
├── .gitignore
├── _conf_schema.json          # 配置 schema
├── config.json               # 插件配置
├── LICENSE                   # AGPL-3.0
├── main.py                   # 插件主逻辑
├── metadata.yaml             # 插件元信息
└── README.md
```

---

## 依赖

- Python ≥ 3.10
- Pillow (`pip install Pillow`)
- astrbot ≥ 对应版本（由 AstrBot 框架提供）

---

## 许可证

[AGPL-3.0](./LICENSE)

> 修改后的代码必须开源，网络服务使用本项目也必须开源。

---

## 作者

[mjy1113451](https://github.com/mjy1113451)

如有问题或建议，欢迎提交 Issue 或联系作者。

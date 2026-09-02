# Issue #47: 合并 anti_revoke 渲染格式 — 方案 Proposal

## 背景

issue #47 要求将 https://github.com/Foolllll-J/astrbot_plugin_anti_revoke 的聊天图片生成格式与本仓库合并，使两个插件生成风格一致。

issue 原文里有两条要求常被混在一起：

1. "将这个仓库的生成聊天图片格式与本仓库合并，使本仓库和链接仓库生成聊天图片形式一样" — 风格统一
2. **"检测说字后面的话生成图片不变"** — say_picture 触发时文字呈现保持现状

## anti_revoke 仓库分析

### 文件结构（实测，HEAD）

```
rendering/
  __init__.py            (2 B)
  chat_screenshot.py     (17 097 B, 主渲染)
  font_manager.py        (7 739 B, 字体加载)
resources/
  corner1.png            (965 B)
  corner2.png            (2 800 B)
  corner3.png            (2 689 B)
  corner4.png            (2 628 B)
                       ─── 小计 9 082 B ≈ 9 KB
```

字体文件**不随仓库发布**。`font_manager.py` 在加载时按以下顺序查找：

1. `resources/fonts/NotoSansSC-Regular.ttf` 等本地路径
2. CDN（jsDelivr）
3. `ImageFont.load_default()` 兜底

所以方案 A 实际新增的 repo 体积是 **~9 KB**（4 个 PNG），不是之前文档里写的 "~8MB"。8MB 那个数字是假设把 NotoSansSC 全量字体打进 repo，**这不是 anti_revoke 当前的做法**。

### 渲染函数签名

```python
async def render_chat_screenshot(
    name: str,         # 昵称
    avatar_bytes: bytes,
    text: str,         # 消息内容
    role: str = "member",
    title: str = "",
    level: int = 0,
    show_title: bool = True,
) -> bytes
```

### 与当前 say_picture 的差异

| 维度 | anti_revoke | 当前 say_picture |
|------|-------------|------------------|
| 样式 | 完整聊天截图（昵称+气泡+群头衔+LV 斜体徽章） | 简化的头像+气泡 |
| 输入参数 | name/role/level/title/avatar/text | 头像+文字 |
| 字体 | NotoSansSC（CDN） | msyh 子集 5.8MB（已内置） |
| 输出 | JPEG q=90 | PNG |
| 资源文件 | 4 个角标 PNG（~9KB） | 1 个 msyh 子集字体（5.8MB） |
| 气泡宽 / 字体 | 900px / 55px | 480px / 26px |

## 建议方案

### 方案 A：完全替换 `_render_bubble`

将 anti_revoke 的 `render_chat_screenshot` 整入本仓库。`on_mention_say` 调用时从 OneBot 适配器取 `name/get_member_nickname`、`level/get_member_level`、`role/get_member_role`（这部分已用 `get_group_member_info` 走过）。

**改动量**：
- 复制 `rendering/chat_screenshot.py` + `font_manager.py` 进本仓库（~25KB）
- 复制 4 个 corner PNG 到 `resources/`（~9KB）
- 字体沿用 anti_revoke 的 CDN+兜底策略，与本仓库内置的 msyh 子集并存
- 在 `on_mention_say` 中取 nickname/level/role 后传入
- 删除现有 `_render_bubble`

**优点**：风格完全一致  
**缺点**：引入 17KB 第三方代码 + Pilmoji 依赖；用户首次使用需联网下载 NotoSansSC 字体

### 方案 B：部分复用（推荐）

只复用 anti_revoke 的气泡框 + 三角指针 + 角标装饰这层"壳"，保留 say_picture 现有的简化布局（头像在左，气泡在右）和排版参数（26px 字体 / 480px 宽）。

具体动作：
- 把 4 个 corner PNG 复制到 `resources/`
- 在 `_render_bubble` 中用 corner PNG 替换当前 `rounded_rectangle`
- 保持 say_picture 当前的字体、宽高、文字渲染

**优点**：插件体积小（+9KB），无第三方依赖，say_picture 的视觉风格基本不变（仅气泡四角的描边质感升级）  
**缺点**：与 anti_revoke 仍非像素级一致，但符合 issue 原文"检测说字后面的话生成图片不变"的硬约束

### 关于"生成图片不变"的实现保证

issue #47 第二条要求"检测说字后面的话生成图片不变"。我对此约束的理解是：

- 文字**内容**不变（这是基本的，不需要任何工作）
- 文字**排版**（字号、行高、字间距、换行宽度）应保持 say_picture 现状

**无论选 A 还是 B，say_picture 触发时都不能照搬 anti_revoke 的 55px 字体 / 900px 气泡**。方案 A 如果原样搬运就违反这条约束，必须把 `make_dialog_box` 的字号/宽度参数化，由 say_picture 调用时显式传入 26px / 480px。

## 回退路径

如果 owner 选 A 后又想退回 B（或反之）：

- **从 A 退回 B**：删除 `rendering/chat_screenshot.py` 和 `font_manager.py`；保留 corner PNG（4 个文件，B 也要用）；恢复 `_render_bubble`。`on_mention_say` 不再调用 `get_group_member_info` 的 nickname/level/role 字段。`git revert` 即可一行回滚。
- **从 B 退回原状**（即 B 实施前）：`git revert` 整条 commit；4 个 corner PNG 可直接删除。

代码改动量都很小，回退成本可忽略。**不需要保留"老模板"分支做向后兼容**。

## 待定 / 等待 owner 答复

1. 选 A 还是 B？（默认推荐 B：体积小、不引入第三方依赖、符合"图片不变"约束）
2. 方案 A 如果选了，是否允许 say_picture 触发时沿用 anti_revoke 的排版参数（即放弃"图片不变"约束）？还是必须保留 26px / 480px？
3. 是否需要可配置开关（让用户在群里选"简版"或"anti_revoke 版"）？我倾向**不引入**，因为可配置开关会显著放大代码分支面，与 say_picture 的"开箱即用"定位冲突。

## 字体策略（关键决策点）

当前 say_picture 已经内置 `fonts/msyh-subset.ttf`（5.8MB，bundle 路径）作为首选字体，这是 #21 / #29 的修复成果。方案 A 引入 anti_revoke 后会同时存在两条字体来源：

- `fonts/msyh-subset.ttf`（say_picture 内置）
- NotoSansSC（anti_revoke `font_manager.py` 从 CDN 下载，失败时回退到 `load_default()`）

reviewer 指出的"两条字体链路冲突"是真实风险。处理方式：

- **方案 A**：统一为 anti_revoke 的策略，删除 `msyh-subset.ttf`，仅保留 CDN+兜底路径。**风险**：首次使用需联网，#21 的修复成果被推翻。**或者**保留 `msyh-subset.ttf` 作为 NotoSansSC 下载失败时的兜底，但此时 anti_revoke 的 `font_manager.py` 需要小改以支持"外部字体路径注入"。
- **方案 B**：不动字体。say_picture 继续用 `msyh-subset.ttf`，仅复用 anti_revoke 的 4 个 corner PNG。字体链路单一，无冲突。

**默认推荐方案 B** 的另一个理由就是它绕开了这个字体链路问题。方案 A 要做，必须先解决"msyh-subset.ttf vs NotoSansSC CDN"的并存策略。

### 与历史修复的兼容

- **方案 A + 选"统一为 CDN+兜底"**：会回退 #21（Chinese 字体渲染失败）和 #29（内置字体）这两个 issue 的修复成果。落地需要 owner 显式接受"首次使用需联网"这个回归。
- **方案 A + 选"保留 msyh-subset.ttf 作为兜底"**：#21 / #29 修复成果保留，但需要修改 anti_revoke 的 `font_manager.py`。
- **方案 B**：完全不涉及字体，#21 / #29 修复不受影响。

### 字体接口草案（仅在方案 A 选"保留 msyh-subset.ttf"时需要）

改动 `font_manager.py` 的 `load_font(size, bold=False)`，允许调用方注入外部字体路径：

```python
from __future__ import annotations
from typing import List, Optional

def load_font(
    size: int,
    bold: bool = False,
    fallback_paths: Optional[List[str]] = None,  # 新增
) -> ImageFont.FreeTypeFont:
    """fallback_paths 在 CDN 失败后才会被使用"""
```

> 备注：anti_revoke `font_manager.py` 已使用 PEP 604 语法（`dict | None`），最低 Python 3.10。所以 `list[str] | None` 是兼容的，无需 `from __future__ import annotations` / `Optional`。这里写 `Optional[List[str]]` 是冗余保守的写法，落地时直接用 PEP 604 即可。

调用方（say_picture）传入 `[os.path.join(os.path.dirname(__file__), "fonts/msyh-subset.ttf")]`。默认值为 `None`，向后兼容 anti_revoke 原有用法。

接口变更很小，不影响 anti_revoke 自身的使用方式。

## 状态

- 2026-09-02: 初版提交（[ba7d688](https://github.com/mjy1113451/astrbot_plugin_say_picture/pull/48/commits/ba7d688)）
- 2026-09-02: 修正资源体积估算（实为 9KB 而非 8MB），补 issue 硬约束"图片不变"，补回退路径（[bd4b88d](https://github.com/mjy1113451/astrbot_plugin_say_picture/pull/48/commits/bd4b88d)）
- 2026-09-02: 补"字体策略"章节，回应 reviewer 提出的两条字体链路冲突（[3ffd174](https://github.com/mjy1113451/astrbot_plugin_say_picture/pull/48/commits/3ffd174)）

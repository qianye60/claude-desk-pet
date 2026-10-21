# Claude Desk Pet

一只住在 Claude Desktop 窗口边上的桌宠（Windows，Python + PySide6）。

- 窗口上方放得下，她就**站在窗口上边缘**；窗口贴顶或最大化，就**坐在右下角、输入框右边的空位**，不挡标题栏和聊天内容
- 三种形态可切换，**切换形态时 AI 的人格也跟着换**：像素机器人 / 元气少女 / 成熟御姐
- 立绘是静态图，用程序做出“活”的感觉：呼吸、轻微摇摆、鼠标靠近时歪头、点击压扁再弹回、拖动像钟摆晃、落地压扁
- 点她一下弹出**额度卡片**（5 小时 / 7 天剩余额度，圆环显示）；右键是控制台式菜单
- 接了 AI（本机 Claude Code 命令行）：会自己冒台词、陪你聊天、偶尔翻翻你的文件夹调侃两句
- 可以**调教**：话多/活泼程度、爱说什么、对某句“喜欢”或“别再说”，拖到哪儿松手她就记住坐哪儿

## 安装

1. 装好 Python 3.9+（安装时勾选 Add Python to PATH）
2. 双击 `install.bat`（装 PySide6 和 Pillow）
3. 第一次运行先拿角色图：`python get_skin.py`（下载 [Ancean/claude-musume](https://github.com/Ancean/claude-musume)，MIT 许可，会连同 LICENSE 放进 `skin` 文件夹）
4. 像素机器人形态：`python make_pixel_skin.py`（代码画的，已经生成好放在 `skins/pixel`）
5. 打开 Claude Desktop，双击 `start.bat`；出问题运行 `debug.bat` 看报错，也可以看 `pet.log`

开机跟随：双击 `enable_autostart.bat`。之后登录 Windows 会悄悄跑一个小哨兵 `follow_claude.pyw`，打开 Claude Desktop 桌宠就自己出来，关掉 Claude（包括关到托盘）她会道别退出，最小化不退出。想关：`disable_autostart.bat`。登记的是当前文件夹路径，挪了文件夹要重新运行一次。

## 三种形态

形态就是 `skins/<名字>/` 里的一套图（旧版的 `skin/` 也算一个），菜单顶部的卡片就是它们，最多显示三个。

| 形态 | 来源 | 人格 |
|---|---|---|
| 像素机器人 | `make_pixel_skin.py` 生成（`skins/pixel`） | 安静、冷幽默、程序员口吻 |
| 元气少女 | `skin/`（get_skin.py 下载的立绘） | 活泼可爱、爱撒娇 |
| 成熟御姐 | `skins/yujie`（AI 生成的一套 10 张全身立绘；想重做见 `tools/gen_yujie.py`） | 从容、毒舌心软 |

御姐形态的提示词见 [docs/生图提示词.md](docs/生图提示词.md)。`tools/gen_yujie.py` 能用兼容 OpenAI 图像接口的服务批量生成：先出以设定图为参考的 `sit.png`，其余 9 张以它为参考，背景用绿幕，生成后自动抠成透明并统一脚底位置（接口地址和密钥只通过环境变量 `IMG_BASE`、`IMG_KEY` 传入，不会写进任何文件）。`skin_template/yujie/skin.json` 是配置模板。

每个形态文件夹：

| 文件 | 用途 | 必须 |
|---|---|---|
| `sit.png` 或 `idle.png` | 平时的样子 | 是 |
| `blink` `happy` `cheer` `wave` `pout` `worried` `working` `sleep` `drag` | 眨眼、开心、欢呼、挥手、鼓脸、担心、工作、睡着、被拎起 | 否 |

没有的图会自动用相近的代替（欢呼/挥手→开心，鼓脸→担心…）。同一种表情可以放多张，命名 `working_写笔记.png` 这样，会轮流用。所有图要同样的画布大小。

`skin.json`：

```json
{ "name": "成熟御姐", "tagline": "从容 · 毒舌心软", "persona": "这个形态的 AI 人格描述",
  "height": 300, "edge": 1.0, "head": 0.12, "pixel": false }
```

`height` 是显示高度（像素）；`edge` 是窗口上边缘落在图片的哪个高度（全身站立填 1.0，腿垂下来的图填 0.7~0.85）；`head` 是气泡对准的高度；`pixel: true` 表示像素风，放大时不做平滑。

## 动作是怎么触发的

没有“点一下做动作”的按钮。动作只在这些情况下自己发生：

- 条件触发：刚出来和告别时挥手；Claude 窗口回来了欢呼；窗口不见了担心；额度快见底（85%）担心、重置了欢呼；连戳 5 下鼓脸；你在 Claude 里打字时她拿出本子陪你“工作”；闲着时随机伸懒腰、蹦一下
- AI 触发：AI 的每句台词和聊天回复都带一个动作，她会一边说一边做
- 在“调教”里把“活泼程度”调低，随机动作就变少

## AI（可选，默认开启）

用的是你本机已经登录的 **Claude Code 命令行**（`claude -p`），程序本身不碰任何令牌。装好并登录 Claude Code 就能用；没装就自动用内置台词。

- 台词：后台批量生成并缓存（`ai_lines.json`），用完再生成；每个形态用自己的人格
- 聊天：右键 → 聊天，回车发送。她会先“想一想”（拿出本子）
- 隔离运行：不读你的全局设置/CLAUDE.md/技能/连接器，只用桌宠自己的人设，所以不会“出戏”
- 模型：`config.json` 的 `ai_model`，默认 `claude-haiku-5-5`（Haiku 5.5，又快又省）。想和窗口一致就改成 `sonnet`、`opus` 等。Claude Desktop 窗口当前选的模型没有对外接口，没法自动同步
- 出错原因写在 `ai.log`

### 自己翻文件夹（默认关，需要你打开）

右键 → 调教 → “自己翻文件夹并点评”打开后，条件合适时（启动 15 分钟后、距上次 ≥ 3 小时、你最近 5 分钟有操作、她没睡着，每天最多 3 次）她会看看桌面、文档、视频文件夹，调侃两句。

- **只读文件名、类型、大小、修改时间，不读内容**；这些信息会通过你的 Claude 账号发给 AI
- 最多往下两层；隐藏文件、依赖目录跳过；名字带 password / token / secret / key / .env / 证件等的不会发出去
- 看到明显的成人内容文件名会调皮地笑话一下，不会描写内容
- 文件夹可在 `config.json` 的 `snoop_folders` 改；`snoop_enabled: false` 彻底禁用

## 额度

点桌宠弹出的卡片显示 5 小时 / 7 天窗口的剩余额度和重置时间。

- 默认读 Claude Desktop 自己记录的 `plan-usage-history.json`（不联网、不碰凭据）：百分比是它记录的值，约 15 分钟更新一次，重置时间是从历史推算的
- 想要实时、精确：右键菜单里打开“精确额度（官方接口）”，或 `config.json` 里 `accurate_usage: true`。会用 Claude Code 的登录令牌请求官方额度接口，**只在本机读取令牌、只发给 api.anthropic.com、不写日志、不刷新令牌**（令牌过期时自动退回本地记录）。这个接口没有官方文档、限流较严，也有人认为第三方程序使用该令牌可能不符合服务条款，开不开请自己判断
- 文件位置不对时用 `usage_file` 指定

## 调教

右键 → 调教：

- 话多程度、活泼程度（滑块）
- 爱说的内容：日常 / Claude 语录 / 封号额度 / 热梗 / AI 即兴，可单独关
- 刚说的那句：喜欢（以后多说）/ 别再说（永远不再说）
- 把她拖到窗口上边的某个位置松手，她记住，以后都坐那儿

调教结果存在 `training.json`。台词库在 `lines.py`，想加自己的台词：把 `lines_example.txt` 改名成 `lines.txt`，按里面说明写（`[meme]` `[claude]` 等分池子）。

## 界面

主题跟随 Windows 浅色/深色（`theme`: auto / light / dark）。可选的美术资源放 `ui` 文件夹，没有也能正常显示：

- `ui/clawd.png`：Claude 的小图标，会出现在卡片、菜单和托盘（没有就自动用像素机器人）
- `ui/card_header.png`：额度卡片的头图

## config.json

| 项 | 说明 |
|---|---|
| `form` | 当前形态（菜单里切换后自动记住） |
| `perch_position` | 站在窗口上边的位置，0 最左、1 最右（拖动后自动记住） |
| `always_on_top` | 是否永远置顶（默认只比 Claude 窗口高一层） |
| `quiet` | 安静模式 |
| `chat_interval_seconds` | 自言自语间隔范围，受“话多程度”缩放 |
| `sleep_after_seconds` | 多久不理她会睡着 |
| `claude_process_names` | Claude 进程名，一般不用改 |
| `follow_claude` | Claude 关掉时她是否跟着退出 |
| `click_opens_panel` | 点击弹出额度卡片 |
| `work_with_claude` | 你在 Claude 里打字时她陪你“工作” |
| `usage_file` / `accurate_usage` | 额度文件路径 / 是否用官方接口 |
| `theme` | 界面主题 |
| `ai_enabled` / `ai_model` | 是否用 AI / 用哪个模型 |
| `snoop_enabled` / `snoop_consent` / `snoop_folders` | 翻文件夹：总开关 / 你是否同意（调教里的开关）/ 文件夹 |

config.json 用记事本改也行（带不带 BOM 都能读）。改完重启生效。

## 文件说明

`desktop_pet.py` 主程序 · `ui.py` 额度卡片与主题 · `ui_menu.py` 右键菜单/调教/聊天 · `skins.py` 形态加载 · `lines.py` 台词 · `ai_brain.py` AI · `snoop.py` 文件夹扫描 · `training.py` 调教 · `usage_info.py` / `usage_api.py` 额度 · `claude_win.py` Win32 工具 · `follow_claude.pyw` 开机哨兵 · `make_pixel_skin.py` / `get_skin.py` 生成/下载形态

## 版权

`skin/` 里的立绘来自 [Ancean/claude-musume](https://github.com/Ancean/claude-musume)（MIT，LICENSE 在该文件夹内）。其余代码为本项目原创。你自己放进 `skins/` 的图片版权归你；用别人的图请先取得作者同意。

## 打包（可选）

```
pip install pyinstaller
pyinstaller -w -F desktop_pet.py
```

打包版不支持“跟随 Claude 启动”，这个功能请用源码版。

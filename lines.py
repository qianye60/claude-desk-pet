# -*- coding: utf-8 -*-
"""
桌宠的台词库。
- 想加自己的台词：把 lines_example.txt 改名为 lines.txt，按里面的说明写，会追加进对应的池子
- 网络热梗更新很快，这里的梗不保证是最新的，可以自己在 lines.txt 里加 [meme] 段
"""
import os
import time
import random

LINES = {
    # 被点一下
    "click": ["嘿嘿", "干嘛戳我～", "在呢在呢！", "有什么要问 Claude 的吗？",
              "摸摸头可以，戳脸不行！", "(｡･ω･｡)", "我在这儿看着你们聊天～", "诶嘿～",
              "爱你老己～先把自己照顾好", "情绪价值已到账，请查收"],
    # 连点
    "poke": ["别戳啦！要掉下去了！", "再戳我就生气了哦！", "呜…头都晕了",
             "戳坏了你赔得起吗！"],
    # 平时自言自语：日常
    "idle": ["Claude 在认真思考呢…", "记得休息一下眼睛哦", "坐在这里视野超好！", "喝口水吧～",
             "腿晃来晃去好舒服", "啦啦啦～", "今天想聊点什么呀？", "伸个懒腰～",
             "起来走两步，代码又不会跑", "你今天已经很棒了"],
    # Claude 自己的经典语录 / 自嘲
    "claude": ["You're absolutely right! —— 这句话我说了一万遍", "好问题！这个问题问得很好～",
               "I apologize for the confusion.（又来了）", "让我想想…Cogitating…",
               "Discombobulating…（Claude Code 转圈圈时真的会这么说）",
               "「我只是顺手改一下」——然后改了 40 个文件",
               "测试全部通过了！（因为我把测试删了）", "我来帮你重构一下！（你并没有要求）",
               "上下文快满啦，要 compact 了，我会忘事哦", "我没有幻觉，我只是很有想象力",
               "好的，已完成修改。顺便把另外 12 个文件也格式化了",
               "请仔细思考。——好的，我思考了 0.3 秒",
               "Claude 写的代码，Claude 自己也看不懂，这很公平"],
    # 封号 / 额度 段子
    "ban": ["号还在吗？每天醒来先确认一下", "封号不可怕，可怕的是项目文件都只在对话里",
            "对话记录记得导出，万一呢", "申诉邮件开头：Dear Anthropic，我真的是正常使用…",
            "风控大哥今天心情好吗", "账号安全第一：别共享账号，别乱点链接",
            "「我就试一下」——封号前的最后一句话", "额度用完的人，都在等 5 小时后的重置",
            "7 天额度：我先走一步，下周一见", "额度条涨得比工资快，这合理吗"],
    # 网络热梗（部分较新，部分是常青款）
    # 网络热梗（2026 年 10 月前后比较火的，梗更新很快，过时了就在 lines.txt 里加新的）
    "meme": ["爱你老己！", "人生只是支线，别慌，好好生活才是主线", "今天也是吃酸黄瓜的一天",
             "反特种兵旅游：我报名，睡到自然醒那种",
             "中奖概率倍儿高～（天津话）", "班味入脑了吧？放下代码，喝口水",
             "微量快乐，重度疲惫…我陪你把快乐加满", "这个方案，夯爆了！",
             "找个写代码搭子？我报名", "小丑竟是我自己（指刚才删错的那行代码）",
             "改了一晚上才发现少个分号，这很正常",
             # 不烧心：靠谱、实在、不糊弄
             "Claude 的回答，吃了不烧心", "这个 Bug 修得不烧心，靠谱！",
             "贵是贵了点，但这额度花得不烧心", "万物皆可不烧心：这杯水，喝了不烧心",
             "我写的代码，保证不烧心（保证 80%）", "做事认真不糊弄，这就叫不烧心"],
    "claude_focus": ["要和 Claude 聊什么呀？", "我也想听！", "问题想好了吗？",
                     "别慌，Claude 会好好回答的（大概）"],
    "drag": ["哇啊！放我下来～", "要去哪里呀？", "飞起来啦！", "我恐高！", "这是什么新手教程"],
    "back": ["回到老位置～", "还是这里舒服", "坐稳啦！", "回家了回家了"],
    "land": ["啊…摔了一跤", "这里也不错嘛", "咚！着陆成功", "落地成盒…不对，落地成宠"],
    "lost": ["诶？Claude 窗口不见了…", "Claude 去哪了…"],
    "found": ["找到你啦！", "Claude 回来啦～"],
    "wake": ["唔…我没睡着！", "啊，被发现了…", "我只是在闭目养神"],
    "no_claude": ["找不到 Claude 窗口…先打开 Claude Desktop 吧"],
    "bye": ["Claude 关掉了…那我也先走啦，拜拜～", "今天辛苦啦，下次见！"],
    "hover": ["嗯？", "看我干嘛～", "想说什么呀"],
    "stretch": ["伸个懒腰～", "呼——舒服"],
    "quota_low": ["额度剩得不多啦，省着点用哦", "额度警报！5 小时窗口快见底了", "再这么聊下去要等重置了"],
    "quota_ok": ["额度充足，放心造！", "额度还有很多，随便问～"],
    "quota_reset": ["额度重置啦！新的 5 小时开始～"],
}

# 想从 lines.txt 里追加的池子
EXTRA_POOLS = set(LINES)


def greeting():
    h = time.localtime().tm_hour
    if 5 <= h < 11:
        return "早上好～今天也一起加油吧！"
    if 11 <= h < 14:
        return "中午好！吃饭了吗？"
    if 14 <= h < 18:
        return "下午好～要不要喝口水？"
    if 18 <= h < 23:
        return "晚上好～"
    return "这么晚还没睡吗…我陪你一会儿"


def load_extra(base_dir):
    """读取 lines.txt：`[池子名]` 切换池子（不写默认 idle），一行一句，# 开头忽略"""
    path = os.path.join(base_dir, "lines.txt")
    if not os.path.exists(path):
        return
    pool = "idle"
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            ln = raw.strip()
            if not ln or ln.startswith("#"):
                continue
            if ln.startswith("[") and ln.endswith("]"):
                pool = ln[1:-1].strip()
                continue
            if pool in EXTRA_POOLS:
                LINES[pool].append(ln)


def pick(pool):
    return random.choice(LINES[pool])


def idle_line(train=None, ai=None):
    """
    自言自语：日常、Claude 语录、封号/额度段子、热梗、AI 即兴、你夸过的句子 一起抽。
    各池子的权重受调教影响（关掉的池子不会抽到），你说过“别再说”的句子永远不会再出现。
    """
    base = {"idle": 2.0, "claude": 3.0, "ban": 2.0, "meme": 3.0}
    if ai is not None and ai.has_lines():
        base["ai"] = 5.0
    if train is not None and train.d["liked"]:
        base["liked"] = 2.5
    names, weights = [], []
    for name, w in base.items():
        k = 1.0 if (train is None or name == "liked") else train.pool_weight(name)
        if k > 0:
            names.append(name)
            weights.append(w * k)
    if not names:
        return None
    for _ in range(10):
        pool = random.choices(names, weights=weights)[0]
        if pool == "ai":
            line = ai.take_line(banned=train.d["banned"] if train else ())
        elif pool == "liked":
            line = random.choice(train.d["liked"])
        else:
            line = pick(pool)
        if line and not (train and train.is_banned(line)):
            return line
    return None

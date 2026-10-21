# -*- coding: utf-8 -*-
"""
调教：把桌宠的性格存成 training.json，像训练宠物一样慢慢调出你喜欢的样子。
- 话多程度 / 活泼程度：控制自言自语和随机小动作的频率
- 爱说的内容 / 爱做的动作：可以整类关掉，或者调多调少
- 刚说的那句：喜欢（以后多说）/ 别再说（永远不再说）
- 你把她拖到喜欢的位置松手，她会记住，以后就坐那儿
"""
import os
import json

POOLS = (("idle", "日常"), ("claude", "Claude 语录"), ("ban", "封号额度"), ("meme", "热梗"), ("ai", "AI 即兴"))
ACTIONS = (("wave", "挥手"), ("cheer", "欢呼"), ("working", "工作"), ("stretch", "伸懒腰"),
           ("hop", "蹦跳"), ("worried", "担心"))

DEFAULTS = {
    "talk": 1.0,       # 0 = 不主动说话，1 = 正常，2 = 话痨
    "lively": 1.0,     # 0 = 不乱动，1 = 正常，2 = 很活泼
    "pools": {k: 1.0 for k, _ in POOLS},
    "actions": {k: 1.0 for k, _ in ACTIONS},
    "banned": [],
    "liked": [],
}


class Training:
    def __init__(self, base_dir):
        self.path = os.path.join(base_dir, "training.json")
        self.d = json.loads(json.dumps(DEFAULTS))
        try:
            with open(self.path, "r", encoding="utf-8-sig") as f:
                saved = json.load(f)
            for k in ("talk", "lively"):
                if isinstance(saved.get(k), (int, float)):
                    self.d[k] = float(saved[k])
            for k in ("pools", "actions"):
                if isinstance(saved.get(k), dict):
                    self.d[k].update({a: float(b) for a, b in saved[k].items()
                                      if isinstance(b, (int, float))})
            for k in ("banned", "liked"):
                if isinstance(saved.get(k), list):
                    self.d[k] = [str(x) for x in saved[k]][-200:]
        except (OSError, ValueError):
            pass

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.d, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    # 读取
    @property
    def talk(self):
        return self.d["talk"]

    @property
    def lively(self):
        return self.d["lively"]

    def pool_weight(self, name):
        return self.d["pools"].get(name, 1.0)

    def action_weight(self, name):
        return self.d["actions"].get(name, 1.0)

    def is_banned(self, line):
        return line in self.d["banned"]

    # 调整
    def set_talk(self, v):
        self.d["talk"] = max(0.0, min(2.0, float(v)))
        self.save()

    def set_lively(self, v):
        self.d["lively"] = max(0.0, min(2.0, float(v)))
        self.save()

    def toggle_pool(self, name, on):
        self.d["pools"][name] = 1.0 if on else 0.0
        self.save()

    def toggle_action(self, name, on):
        self.d["actions"][name] = 1.0 if on else 0.0
        self.save()

    def ban(self, line):
        if line and line not in self.d["banned"]:
            self.d["banned"].append(line)
        if line in self.d["liked"]:
            self.d["liked"].remove(line)
        self.save()

    def like(self, line):
        if line and line not in self.d["liked"]:
            self.d["liked"].append(line)
        if line in self.d["banned"]:
            self.d["banned"].remove(line)
        self.save()

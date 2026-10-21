# -*- coding: utf-8 -*-
"""
让桌宠“有脑子”：通过本机已登录的 Claude Code 命令行（claude -p）生成台词、陪你聊天、点评文件夹。

- 用的是官方命令行，走你已经登录的账号，程序本身不碰任何令牌
- 隔离运行：不读你的全局设置 / CLAUDE.md / 技能 / 连接器，只用下面的人设提示词，所以她不会“出戏”
- 每个形态可以有自己的人格（skin.json 里的 persona），切换形态时人格跟着换
- AI 的回复带一个“动作”（挥手/欢呼/开心…），她会一边说一边做；动作不是靠手动点出来的
- 每次调用约 10~25 秒，台词是批量生成并缓存的（ai_lines.json），聊天时她会先“想一想”
- 模型用 config.json 里的 "ai_model"（默认 Haiku 5.5，又快又省；想和窗口一致就改成 sonnet / opus 等）
- 没装命令行或没登录时自动静默失败，桌宠照常用内置台词（失败原因写在 ai.log）
"""
import os
import re
import sys
import json
import time
import shutil
import tempfile
import threading
import subprocess

DEFAULT_PERSONA = (
    "你是住在电脑桌面 Claude 窗口边上的一只小桌宠，是个活泼可爱、有点小幽默的少女形象，陪主人写代码、聊天。"
    "说话简短自然，每句不超过 24 个汉字，口语化。"
)
RULES = (
    "不用 emoji，不用括号描写动作；不自称 AI 助手，不说教，不讲大道理；"
    "不要提任务、工具、连接器、额度数字之类的“系统信息”，也不要问主人“要我做什么”。"
    "可以偶尔玩一点网络梗，但要自然不油腻，不要硬凹。"
)
ACTS = ("wave", "cheer", "happy", "pout", "worried", "working", "stretch", "hop", "shy", "tease", "laugh", "think",
        "yawn", "nod", "shake", "dance", "spin", "dizzy", "walk", "none")
ACT_HELP = ("wave=挥手, cheer=欢呼, happy=开心, pout=鼓脸生气, worried=担心, working=认真看书, stretch=伸懒腰, hop=蹦一下, "
            "shy=害羞, tease=坏笑调侃, laugh=大笑, think=托腮思考, yawn=打哈欠, nod=点头, shake=摇头, dance=跳舞, "
            "spin=转身, dizzy=头晕, walk=在窗口边上散步, none=不做动作")


def find_claude():
    """找 claude 可执行文件。npm 装的是 .cmd 外壳，会把中文参数搞乱，所以尽量直接找真正的 claude.exe"""
    found = None
    for name in ("claude", "claude.cmd", "claude.exe"):
        p = shutil.which(name)
        if not p:
            continue
        real = os.path.join(os.path.dirname(p), "node_modules", "@anthropic-ai", "claude-code", "bin", "claude.exe")
        if os.path.exists(real):
            return real
        if p.lower().endswith(".exe"):
            return p
        found = found or p
    return found


def _clean_text(t):
    t = t.strip().strip('"“”')
    return re.sub(r"\s+", " ", t)


def shorten(text, limit=70):
    """气泡里放不下长篇大论：超过 limit 就在最后一个句号/感叹号处截断，没有就加省略号"""
    text = _clean_text(text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    best = max(cut.rfind(c) for c in "。！？!?~～")
    return cut[:best + 1] if best >= 8 else cut.rstrip("，、,; ") + "…"


def parse_json_obj(out):
    m = re.search(r"\{.*\}", out, re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            if isinstance(d, dict):
                return d
        except ValueError:
            pass
    return None


def parse_items(out):
    """从模型输出里取出 [(台词, 动作)]：优先 JSON 数组（元素是字符串或 {t,a}），否则按行"""
    res = []
    m = re.search(r"\[.*\]", out, re.S)
    if m:
        try:
            for x in json.loads(m.group(0)):
                if isinstance(x, str):
                    res.append((x, "none"))
                elif isinstance(x, dict) and isinstance(x.get("t"), str):
                    a = x.get("a") if x.get("a") in ACTS else "none"
                    res.append((x["t"], a))
        except ValueError:
            pass
    if not res:
        for ln in out.splitlines():
            ln = re.sub(r"^[\-\d\.\s、*]+", "", ln)
            if ln.strip():
                res.append((ln, "none"))
    out = []
    for t, a in res:
        t = _clean_text(t)
        if 2 <= len(t) <= 60:
            out.append((t, a))
    return out


class AiBrain:
    def __init__(self, base_dir, model="claude-haiku-5-5", enabled=True):
        self.base_dir = base_dir
        self.model = model
        self.enabled = enabled
        self.persona = DEFAULT_PERSONA
        self.cmd = find_claude() if enabled else None
        self.path = os.path.join(base_dir, "ai_lines.json")
        self.log_path = os.path.join(base_dir, "ai.log")
        self.lines = []            # 还没说过的 AI 台词 [(文本, 动作)]
        self.pending_act = "none"  # 刚取走的那句台词配的动作
        self.updated = 0.0
        self.persona_tag = ""      # 缓存是为哪个人格生成的，换人格要重新生成
        self.busy = False
        self.fail_until = 0.0
        self.results = []          # [(tag, 文本, 动作)]，主线程取走
        self.history = []
        self._lock = threading.Lock()
        self._load()

    # ---- 人格
    def set_persona(self, text, tag=""):
        self.persona = text or DEFAULT_PERSONA
        if tag != self.persona_tag:                      # 换了人格，旧台词不合适了
            with self._lock:
                self.lines = []
                self.updated = 0.0
                self.persona_tag = tag
                self.history = []
                self._save()

    def _system(self):
        return self.persona + RULES

    # ---- 缓存
    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8-sig") as f:
                d = json.load(f)
            for x in d.get("lines", []):
                if isinstance(x, str):
                    self.lines.append((x, "none"))
                elif isinstance(x, list) and len(x) == 2:
                    self.lines.append((str(x[0]), str(x[1])))
            self.updated = float(d.get("updated", 0))
            self.persona_tag = d.get("persona_tag", "")
        except (OSError, ValueError):
            pass

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"lines": self.lines, "updated": self.updated, "persona_tag": self.persona_tag},
                          f, ensure_ascii=False, indent=1)
        except OSError:
            pass

    def _log(self, msg):
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg[:400] + "\n")
        except OSError:
            pass

    @property
    def available(self):
        return bool(self.enabled and self.cmd)

    def take_line(self, banned=()):
        """取一句还没说过的 AI 台词（取走后就从池子里删掉），配的动作放在 pending_act"""
        with self._lock:
            while self.lines:
                ln, act = self.lines.pop(0)
                if ln not in banned:
                    self.pending_act = act
                    self._save()
                    return ln
        return None

    def has_lines(self):
        return bool(self.lines)

    # ---- 调用命令行
    def _run(self, prompt, timeout=90):
        # 隔离：不读全局设置/CLAUDE.md/技能/连接器（--setting-sources local + --strict-mcp-config），
        # 用自己的系统提示词，否则她会“出戏”变成 Claude Code 问你要干什么。
        # 提示词走标准输入（utf-8），避免命令行里中文被 .cmd 外壳搞乱。
        args = [self.cmd, "-p", "--model", self.model, "--tools", "",
                "--no-session-persistence", "--disable-slash-commands",
                "--setting-sources", "local", "--strict-mcp-config",
                "--system-prompt", self._system(), "--output-format", "text"]
        flags = 0x08000000 if sys.platform == "win32" else 0      # 不弹黑窗口
        r = subprocess.run(args, input=prompt.encode("utf-8"), capture_output=True, timeout=timeout,
                           cwd=tempfile.gettempdir(), creationflags=flags)
        if r.returncode != 0:
            raise RuntimeError("exit %s: %s" % (r.returncode, (r.stderr or b"").decode("utf-8", "replace")[:300]))
        out = r.stdout.decode("utf-8", "replace").strip()
        if not out:
            raise RuntimeError("empty output")
        return out

    def _spawn(self, fn):
        if self.busy or not self.available or time.monotonic() < self.fail_until:
            return False
        self.busy = True

        def run():
            try:
                fn()
            except Exception as e:
                self._log("error: %r" % (e,))
                self.fail_until = time.monotonic() + 600      # 出错后 10 分钟内不再试
            finally:
                self.busy = False
        threading.Thread(target=run, daemon=True).start()
        return True

    def refill(self, context, liked=(), banned=(), n=12):
        """批量生成台词；context 是一句话描述现在的情况"""
        def job():
            like = ("她以前被夸过、风格可以参考的句子：" + "；".join(list(liked)[-5:]) + "。") if liked else ""
            ban = ("这些风格主人不喜欢，别再写：" + "；".join(list(banned)[-5:]) + "。") if banned else ""
            prompt = (f"请写 {n} 句桌宠自言自语的台词，每句一个独立想法，别重复。现在的情况：{context}。{like}{ban}"
                      "可以是吐槽、关心、冷笑话、写代码的小感悟，别每句都带梗，要符合你的人设语气。"
                      f"每句配一个动作 a，可选：{ACT_HELP}。"
                      "只输出一个 JSON 数组，元素形如 {\"t\":\"台词\",\"a\":\"happy\"}，不要任何其他文字。")
            out = self._run(prompt)
            new = [(t, a) for t, a in parse_items(out) if t not in banned]
            if not new:
                raise RuntimeError("no lines parsed from: " + out[:100])
            with self._lock:
                self.lines = (self.lines + new)[-60:]
                self.updated = time.time()
                self._save()
        return self._spawn(job)

    def _reply_job(self, tag, prompt, limit, timeout):
        def job():
            out = self._run(prompt, timeout=timeout)
            d = parse_json_obj(out)
            if d and isinstance(d.get("say"), str):
                text, act = d["say"], (d.get("act") if d.get("act") in ACTS else "none")
            else:
                text, act = out, "none"
            text = shorten(text.replace("你：", "", 1), limit)
            with self._lock:
                self.results.append((tag, text, act))
        return job

    def chat(self, text, context=""):
        """聊天：回复放进 results，tag 是 'chat'"""
        hist = "\n".join(f"主人：{a}\n你：{b}" for a, b in self.history[-4:])
        prompt = (f"现在的情况：{context}。\n{hist}\n主人说：{text}\n"
                  "请以你的人设回复，不超过 40 个汉字，不换行。同时选一个配合这句话的动作 act，"
                  f"可选：{ACT_HELP}。只输出 JSON：{{\"say\":\"回复\",\"act\":\"happy\"}}")
        inner = self._reply_job("chat", prompt, 70, 120)

        def job():
            inner()
            with self._lock:
                if self.results and self.results[-1][0] == "chat":
                    self.history.append((text, self.results[-1][1]))
        ok = self._spawn(job)
        if not ok:
            self.results.append(("chat_fail", "", "none"))
        return ok

    def snoop(self, listing, total, context=""):
        """翻文件夹后的点评：listing 只有文件名等元数据；结果 tag 是 'snoop'"""
        prompt = (
            f"你偷偷翻了一下主人的桌面/文档/视频文件夹（一共 {total} 项，下面是抽样，只有文件名和元数据，你并没有看内容）：\n"
            f"{listing}\n\n现在的情况：{context}。\n"
            "请挑 1~2 个最有意思的点调侃一下，总共不超过 60 个汉字。要符合你的人设：嘴上损两句、心里是关心主人的，"
            "结尾可以带一句暖心的话。\n"
            "要求：如果看到明显是成人内容的文件名，就调皮地笑话一下主人（比如“被我发现啦”这种语气），"
            "绝对不要描写内容、不要露骨；如果看到学习/工作资料，夸一句或者催他劳逸结合；如果文件很杂乱，吐槽一下；"
            "不要照抄长文件名，不要暴露完整路径。"
            f"同时选一个动作 act，可选：{ACT_HELP}。只输出 JSON：{{\"say\":\"点评\",\"act\":\"cheer\"}}")
        ok = self._spawn(self._reply_job("snoop", prompt, 90, 150))
        if not ok:
            self.results.append(("snoop_fail", "", "none"))
        return ok

    def pop_results(self):
        with self._lock:
            r, self.results = self.results, []
        return r

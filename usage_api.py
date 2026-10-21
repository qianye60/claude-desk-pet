# -*- coding: utf-8 -*-
"""
精确额度（可选，默认关闭）：和 Claude Code 一样，用 Claude 的登录令牌向官方接口查 5 小时 / 7 天额度。

接口 GET https://api.anthropic.com/api/oauth/usage 没有官方文档，返回里 five_hour / seven_day 各有
utilization（已用 %）和 resets_at（重置时刻）。

!! 开启前请知道：
   - 这是社区摸出来的未公开接口，随时可能变；而且限流很凶（容易 429）
   - 有人认为消费者条款只允许 OAuth 令牌用在 Claude Code 和 Claude.ai 里，第三方程序用它有账号风险，
     是否开启请自己判断（config.json 里 "accurate_usage": true 才会启用，默认 false）
   - 令牌只在本机从 ~/.claude/.credentials.json 读出、只发给 api.anthropic.com、不写日志不落盘
   - 不会刷新令牌（刷新会轮换 refresh token，可能让 Claude Code 掉登录）。令牌过期（约 1 小时）时
     自动退回本地记录，Claude Code 运行时会自己续期，之后这里会自动恢复
"""
import os
import json
import time
import threading
import urllib.request
import urllib.error
from datetime import datetime, timezone

URL = "https://api.anthropic.com/api/oauth/usage"
MIN_INTERVAL = 300          # 两次请求至少隔 5 分钟
BACKOFF_429 = 1800          # 被限流后 30 分钟不再请求
FRESH = 900                 # 结果 15 分钟内算新鲜


def credentials_path():
    return os.path.join(os.path.expanduser("~"), ".claude", ".credentials.json")


def parse_iso(text):
    if not isinstance(text, str):
        return None
    t = text.strip().replace("Z", "+00:00")
    if "." in t:                       # 去掉小数秒，避免不同 Python 版本解析不了
        head, rest = t.split(".", 1)
        tz = ""
        for sign in ("+", "-"):
            if sign in rest:
                rest, tz = rest.split(sign, 1)
                tz = sign + tz
                break
        t = head + tz
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def parse_usage(data):
    """把接口返回解析成 (five%, five_reset, seven%, seven_reset)，字段缺失就是 None"""
    def part(key):
        d = data.get(key) if isinstance(data, dict) else None
        if not isinstance(d, dict):
            return None, None
        u = d.get("utilization")
        return (float(u) if isinstance(u, (int, float)) else None), parse_iso(d.get("resets_at"))
    f, fr = part("five_hour")
    s, sr = part("seven_day")
    return f, fr, s, sr


class UsageApi:
    def __init__(self):
        self.result = None          # (five, five_reset, seven, seven_reset, 取到的时间)
        self.next_try = 0.0
        self.busy = False
        self.status = ""            # ok / token_expired / no_token / rate_limited / error

    def poll(self, now):
        if self.busy or now < self.next_try:
            return
        self.busy = True
        self.next_try = now + MIN_INTERVAL
        threading.Thread(target=self._worker, daemon=True).start()

    def fresh(self):
        return self.result is not None and time.time() - self.result[4] < FRESH

    def _token(self):
        try:
            with open(credentials_path(), "r", encoding="utf-8") as f:
                oauth = json.load(f).get("claudeAiOauth") or {}
        except (OSError, ValueError):
            self.status = "no_token"
            return None
        tok, exp = oauth.get("accessToken"), oauth.get("expiresAt")
        if not tok:
            self.status = "no_token"
            return None
        if isinstance(exp, (int, float)) and exp / 1000.0 < time.time() + 30:
            self.status = "token_expired"       # 不刷新，等 Claude Code 自己续期
            return None
        return tok

    def _worker(self):
        try:
            tok = self._token()
            if not tok:
                self.next_try = time.monotonic() + 120
                return
            req = urllib.request.Request(URL, headers={
                "Authorization": "Bearer " + tok,
                "anthropic-beta": "oauth-2025-04-20",
                "Accept": "application/json",
                "User-Agent": "claude-desk-pet",
            })
            with urllib.request.urlopen(req, timeout=12) as r:
                data = json.loads(r.read().decode("utf-8"))
            f, fr, s, sr = parse_usage(data)
            if f is None and s is None:
                self.status = "error"
                return
            self.result = (f, fr, s, sr, time.time())
            self.status = "ok"
        except urllib.error.HTTPError as e:
            if e.code == 429:
                self.status = "rate_limited"
                self.next_try = time.monotonic() + BACKOFF_429
            elif e.code in (401, 403):
                self.status = "token_expired"
                self.next_try = time.monotonic() + 600
            else:
                self.status = "error"
        except Exception:
            self.status = "error"
        finally:
            self.busy = False

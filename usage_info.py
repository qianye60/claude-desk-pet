# -*- coding: utf-8 -*-
"""
Claude 额度读取（只读本地文件，不碰登录凭据，不联网）。

Claude Desktop 大约每 15 分钟会把 5 小时额度和 7 天额度的已用百分比记到
plan-usage-history.json（样本里 t 是毫秒时间戳，u.fh 是 5 小时、u.sd 是 7 天已用 %）。
文件里没有重置时间，所以重置时间是从历史里推算的，显示时要标“约”。
推算思路参考了 Ancean/claude-musume（MIT）的做法，代码是自己写的。

文件位置因安装方式而异，会在几个常见位置里挑最近改过的；
也可以在 config.json 里用 "usage_file" 指定。
"""
import os
import glob
import json
import math
import time
from dataclasses import dataclass

FIVE_HOURS = 5 * 3600
WEEK = 7 * 86400
MAX_GAP = 45 * 60          # 相邻样本隔太久，就推不准窗口从哪开始
STALE_AFTER = 40 * 60      # 最新样本比这还旧，说明 Claude Desktop 没在更新


@dataclass
class Usage:
    five: float = None         # 5 小时已用 %
    seven: float = None        # 7 天已用 %
    at: float = None           # 最新样本时间（秒）
    five_reset: float = None   # 推算的重置时刻（秒）
    seven_reset: float = None
    missing: bool = False      # 找不到数据文件
    exact: bool = False        # 来自官方接口（精确）；否则是本地记录 + 推算

    def known(self):
        return self.five is not None or self.seven is not None

    def stale(self, now=None):
        return self.at is not None and (now or time.time()) - self.at > STALE_AFTER


def candidate_files(configured=None):
    if configured:
        return [configured]
    appdata = os.environ.get("APPDATA", "")
    local = os.environ.get("LOCALAPPDATA", "")
    pats = [
        os.path.join(appdata, "Claude", "plan-usage-history.json"),
        os.path.join(local, "Claude-Data", "*", "plan-usage-history.json"),   # 商店版/新版目录
        os.path.join(local, "Claude-Data", "plan-usage-history.json"),
        os.path.join(local, "Packages", "Claude_*", "LocalCache", "Roaming", "Claude", "plan-usage-history.json"),
        os.path.join(local, "Claude", "plan-usage-history.json"),
    ]
    out = []
    for p in pats:
        out.extend(glob.glob(p))
    return out


def find_file(configured=None):
    files = [f for f in candidate_files(configured) if os.path.isfile(f)]
    return max(files, key=os.path.getmtime) if files else None


def _series(samples, key):
    return [(s["t"] / 1000.0, float(s["u"][key])) for s in samples
            if isinstance(s.get("u"), dict) and isinstance(s["u"].get(key), (int, float))]


def five_hour_reset(points):
    """5 小时窗口从空闲后第一次使用开始计时：找最近一次“0 变正”或“明显回落”，起点取两条样本中点再加 5 小时"""
    if not points or points[-1][1] <= 0:
        return None
    for (t0, v0), (t1, v1) in zip(reversed(points[:-1]), reversed(points[1:])):
        if v1 > 0 and (v0 == 0 or v1 <= v0 - 3):
            if t1 - t0 > MAX_GAP:
                return None
            reset = (t0 + t1) / 2 + FIVE_HOURS
            return reset if reset > points[-1][0] else None
    return None


def seven_day_reset(points, now):
    """7 天额度每周固定时刻重置：取近 5 周里间隔最短的一次回落，按 7 天周期推到下一次"""
    best = None
    for (t0, v0), (t1, v1) in zip(points, points[1:]):
        if t1 < now - 5 * WEEK:
            continue
        if (v0 > 0 and v1 == 0) or v1 <= v0 - 5:
            if best is None or t1 - t0 < best[0]:
                best = (t1 - t0, (t0 + t1) / 2)
    if best is None or best[0] > 12 * 3600:
        return None
    mid = best[1]
    return mid + max(1, math.ceil((now - mid) / WEEK)) * WEEK


class UsageReader:
    def __init__(self, configured=None, use_api=False):
        self.configured = configured
        self.api = None
        if use_api:
            import usage_api
            self.api = usage_api.UsageApi()
        self.path = None
        self._mtime = None
        self.usage = Usage(missing=True)

    def read(self):
        """优先用官方接口的新鲜结果（开启 accurate_usage 时），否则读本地记录"""
        if self.api is not None:
            self.api.poll(time.monotonic())
            r = self.api.result
            if r and self.api.fresh():
                return Usage(five=r[0], seven=r[2], at=r[4], five_reset=r[1], seven_reset=r[3], exact=True)
        return self.read_local()

    def read_local(self):
        """文件没变就直接返回上一次的结果"""
        now = time.time()
        path = find_file(self.configured)
        if not path:
            self.usage = Usage(missing=True)
            return self.usage
        try:
            mtime = os.path.getmtime(path)
            if path == self.path and mtime == self._mtime:
                return self.usage
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw = data.get("samples") if isinstance(data, dict) else data
            samples = sorted((s for s in raw if isinstance(s, dict) and isinstance(s.get("t"), (int, float))),
                             key=lambda s: s["t"])
            if samples:   # 只留最新那个账号的样本
                org = samples[-1].get("org")
                samples = [s for s in samples if s.get("org") == org]
            five, seven = _series(samples, "fh"), _series(samples, "sd")
            self.usage = Usage(
                five=five[-1][1] if five else None,
                seven=seven[-1][1] if seven else None,
                at=samples[-1]["t"] / 1000.0 if samples else None,
                five_reset=five_hour_reset(five),
                seven_reset=seven_day_reset(seven, now),
            )
            self.path, self._mtime = path, mtime
        except (OSError, ValueError, KeyError, TypeError):
            self.usage = Usage(missing=True)
        return self.usage


def fmt_remaining(ts, now=None):
    """'2 小时 57 分后' / '3 天 4 小时后'"""
    secs = max(0, int(ts - (now or time.time())))
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d} 天 {h} 小时后"
    if h:
        return f"{h} 小时 {m} 分后"
    return f"{m} 分钟后"


def fmt_clock(ts):
    t = time.localtime(ts)
    today = time.localtime()
    if (t.tm_year, t.tm_yday) == (today.tm_year, today.tm_yday):
        return time.strftime("%H:%M", t)
    return time.strftime("%m/%d %H:%M", t)

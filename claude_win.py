# -*- coding: utf-8 -*-
"""
Windows 相关的小工具（只用标准库）：
找 Claude Desktop 窗口、调整桌宠层级、单实例、开机自启登记。
桌宠本体和常驻哨兵 follow_claude.pyw 共用。
"""
import os
import sys
import time
import ctypes
import subprocess
import winreg

from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
for _f in ("IsWindowVisible", "IsIconic", "IsWindow"):
    getattr(user32, _f).argtypes = [wintypes.HWND]
    getattr(user32, _f).restype = wintypes.BOOL
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = wintypes.LONG
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.SetWindowPos.restype = wintypes.BOOL
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.OpenMutexW.restype = wintypes.HANDLE
dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long

HWND_TOP = None
HWND_TOPMOST = wintypes.HWND(-1)
HWND_NOTOPMOST = wintypes.HWND(-2)
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
SWP_FLAGS = SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
GW_HWNDPREV = 3
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14

def _hwnd_int(h):
    return int(h) if h else 0

class ClaudeFinder:
    """在所有窗口里找 Claude Desktop 的主窗口"""

    def __init__(self, process_names):
        self.names = {n.lower() for n in process_names}
        self.name_cache = {}
        self.hwnd = 0
        self.last_scan = 0.0
        self.my_pid = os.getpid()

    def _pid(self, hwnd):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value

    def _proc_name(self, pid):
        if pid in self.name_cache:
            return self.name_cache[pid]
        name = ""
        h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if h:
            try:
                buf = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(1024)
                if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                    name = os.path.basename(buf.value).lower()
            finally:
                kernel32.CloseHandle(h)
        if len(self.name_cache) > 500:
            self.name_cache.clear()
        self.name_cache[pid] = name
        return name

    @staticmethod
    def _text(fn, hwnd):
        buf = ctypes.create_unicode_buffer(256)
        fn(hwnd, buf, 256)
        return buf.value

    @staticmethod
    def rect(hwnd):
        r = wintypes.RECT()
        if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
                                        ctypes.byref(r), ctypes.sizeof(r)) != 0:
            user32.GetWindowRect(hwnd, ctypes.byref(r))
        return r.left, r.top, r.right, r.bottom

    @staticmethod
    def _cloaked(hwnd):
        v = wintypes.DWORD(0)
        dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(v), ctypes.sizeof(v))
        return v.value != 0

    def _usable(self, hwnd):
        return (hwnd and user32.IsWindow(hwnd) and user32.IsWindowVisible(hwnd)
                and not user32.IsIconic(hwnd) and not self._cloaked(hwnd))

    def _matching(self):
        """所有属于 Claude 的可见顶层窗口"""
        found = []

        def cb(hwnd, _lp):
            if not user32.IsWindowVisible(hwnd):
                return True
            pid = self._pid(hwnd)
            if pid == self.my_pid:
                return True
            match = self._proc_name(pid) in self.names
            if not match:
                title = self._text(user32.GetWindowTextW, hwnd)
                cls = self._text(user32.GetClassNameW, hwnd)
                match = title == "Claude" and cls.startswith("Chrome_WidgetWin")
            if match:
                found.append(_hwnd_int(hwnd))
            return True

        user32.EnumWindows(WNDENUMPROC(cb), 0)
        return found

    def _scan(self):
        best, best_area = 0, 0
        for h in self._matching():
            if not self._usable(h):
                continue
            l, t, r, b = self.rect(h)
            w, hh = r - l, b - t
            if w < 300 or hh < 200:
                continue
            if w * hh > best_area:
                best, best_area = h, w * hh
        return best

    def exists(self):
        """Claude 主窗口是否开着（最小化也算；关掉或缩到托盘不算）"""
        for h in self._matching():
            if user32.IsIconic(h):
                return True
            l, t, r, b = self.rect(h)
            if r - l >= 300 and b - t >= 200:
                return True
        return False

    def get(self):
        """返回 (hwnd, (l,t,r,b) 物理像素) 或 None"""
        now = time.monotonic()
        if self.hwnd and not self._usable(self.hwnd):
            self.hwnd = 0
            self.last_scan = 0.0
        interval = 1.5 if self.hwnd else 0.5
        if now - self.last_scan > interval:
            self.last_scan = now
            self.hwnd = self._scan()
        if not self.hwnd:
            return None
        return self.hwnd, self.rect(self.hwnd)

def set_topmost(me, on):
    user32.SetWindowPos(me, HWND_TOPMOST if on else HWND_NOTOPMOST, 0, 0, 0, 0, SWP_FLAGS)

def place_just_above(me, target):
    """把桌宠的层级放到 target 窗口正上方（不是永远置顶）"""
    prev = _hwnd_int(user32.GetWindow(target, GW_HWNDPREV))
    steps = 0
    while prev and prev != me and not user32.IsWindowVisible(prev) and steps < 60:
        prev = _hwnd_int(user32.GetWindow(prev, GW_HWNDPREV))
        steps += 1
    if prev == me:
        return
    if not prev or (user32.GetWindowLongW(prev, GWL_EXSTYLE) & WS_EX_TOPMOST):
        insert = HWND_TOP
    else:
        insert = prev
    user32.SetWindowPos(me, insert, 0, 0, 0, 0, SWP_FLAGS)

def foreground():
    return _hwnd_int(user32.GetForegroundWindow())


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


user32.GetLastInputInfo.argtypes = [ctypes.POINTER(_LASTINPUTINFO)]
user32.GetLastInputInfo.restype = wintypes.BOOL
kernel32.GetTickCount.restype = wintypes.DWORD


def idle_seconds():
    """距离上一次键盘/鼠标输入过了多少秒（取不到就返回很大的数）"""
    li = _LASTINPUTINFO()
    li.cbSize = ctypes.sizeof(li)
    if not user32.GetLastInputInfo(ctypes.byref(li)):
        return 9999.0
    return ((kernel32.GetTickCount() - li.dwTime) & 0xFFFFFFFF) / 1000.0


# ---------------------------------------------------------------- 单实例
PET_MUTEX = "Local\\ClaudeDesktopPet_Instance"
SENTINEL_MUTEX = "Local\\ClaudeDesktopPet_Sentinel"
_held = []


def single_instance(name):
    """拿到互斥体返回 True；已经有同名实例在跑返回 False"""
    h = kernel32.CreateMutexW(None, False, name)
    err = ctypes.get_last_error()
    if not h:
        return True
    if err == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(h)
        return False
    _held.append(h)
    return True


def instance_running(name):
    h = kernel32.OpenMutexW(0x00100000, False, name)  # SYNCHRONIZE
    if h:
        kernel32.CloseHandle(h)
        return True
    return False


# ---------------------------------------------------------------- 开机自启
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "ClaudeDesktopPet"


def pythonw_path():
    exe = sys.executable
    cand = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return cand if os.path.exists(cand) else exe


def autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as k:
            winreg.QueryValueEx(k, RUN_NAME)
        return True
    except OSError:
        return False


def set_autostart(on, base_dir):
    """登记/取消登录时自动运行哨兵；登记时顺便把哨兵立刻启动"""
    sentinel = os.path.join(base_dir, "follow_claude.pyw")
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, f'"{pythonw_path()}" "{sentinel}"')
        else:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except OSError:
                pass
    if on and not instance_running(SENTINEL_MUTEX):
        subprocess.Popen([pythonw_path(), sentinel], cwd=base_dir, creationflags=0x08000000)

"""PMO Guard agent. Runs in the user's session (launched by the service).

- Low-level keyboard hook; only while a browser is the foreground window.
- Keystrokes live in a small in-memory ring buffer. Nothing typed is saved or sent anywhere.
- Second layer: polls the browser window title (catches links / pasted URLs).
- On match: close the tab (Ctrl+W), show a message, lock the PC after repeated hits.
"""
import ctypes
import ctypes.wintypes as wt
import os
import queue
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import CONFIG_PATH, Matcher, load_config, log  # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

ULONG_PTR = ctypes.c_size_t
LRESULT = ctypes.c_ssize_t
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t


class KBDLL(ctypes.Structure):
    _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, WPARAM, LPARAM)

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, WPARAM, LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.GetForegroundWindow.restype = ctypes.c_void_p
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.GetKeyboardLayout.argtypes = [wt.DWORD]
user32.GetKeyboardLayout.restype = ctypes.c_void_p
user32.ToUnicodeEx.argtypes = [wt.UINT, wt.UINT, ctypes.POINTER(ctypes.c_ubyte),
                               wt.LPWSTR, ctypes.c_int, wt.UINT, ctypes.c_void_p]
user32.ToUnicodeEx.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [ctypes.c_void_p, wt.LPWSTR, ctypes.c_int]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetKeyState.argtypes = [ctypes.c_int]
user32.keybd_event.argtypes = [wt.BYTE, wt.BYTE, wt.DWORD, ULONG_PTR]
user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), ctypes.c_void_p, wt.UINT, wt.UINT]
user32.MessageBoxW.argtypes = [ctypes.c_void_p, wt.LPCWSTR, wt.LPCWSTR, wt.UINT]
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
kernel32.GetModuleHandleW.restype = wt.HINSTANCE
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.OpenProcess.restype = ctypes.c_void_p
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
kernel32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, wt.DWORD, wt.LPWSTR,
                                                ctypes.POINTER(wt.DWORD)]
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
kernel32.CreateMutexW.restype = ctypes.c_void_p

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_SYSKEYDOWN = 0x100, 0x104
LLKHF_INJECTED = 0x10
VK_BACK, VK_TAB, VK_RETURN, VK_ESCAPE = 0x08, 0x09, 0x0D, 0x1B
VK_SHIFT, VK_CONTROL, VK_MENU, VK_CAPITAL = 0x10, 0x11, 0x12, 0x14
RESET_KEYS = {VK_TAB, VK_RETURN, VK_ESCAPE, 0x21, 0x22, 0x23, 0x24,   # PgUp..Home
              0x25, 0x26, 0x27, 0x28, 0x2E}                            # arrows, Del
KEYEVENTF_KEYUP = 0x2


class State:
    cfg = None
    matcher = None
    mtime = 0
    last_hit = 0.0
    hits = []
    box_open = False
    lock = threading.Lock()


S = State()
events = queue.Queue(maxsize=2000)
_proc_cache = {}


def reload_config(force=False):
    try:
        mt = os.path.getmtime(CONFIG_PATH)
    except OSError:
        mt = 0
    if force or mt != S.mtime:
        S.mtime = mt
        S.cfg = load_config()
        S.matcher = Matcher(S.cfg)


def proc_name(hwnd):
    now = time.time()
    c = _proc_cache.get(hwnd)
    if c and now - c[1] < 5:
        return c[0]
    pid = wt.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    name = ""
    h = kernel32.OpenProcess(0x1000, False, pid.value)   # QUERY_LIMITED_INFORMATION
    if h:
        buf = ctypes.create_unicode_buffer(520)
        size = wt.DWORD(520)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            name = os.path.basename(buf.value).lower()
        kernel32.CloseHandle(h)
    if len(_proc_cache) > 200:
        _proc_cache.clear()
    _proc_cache[hwnd] = (name, now)
    return name


def is_browser(hwnd):
    return bool(hwnd) and proc_name(hwnd) in S.cfg["browsers"]


def translate(vk, scan, hwnd):
    state = (ctypes.c_ubyte * 256)()
    if user32.GetAsyncKeyState(VK_SHIFT) & 0x8000:
        state[VK_SHIFT] = 0x80
    if user32.GetKeyState(VK_CAPITAL) & 1:
        state[VK_CAPITAL] = 1
    tid = user32.GetWindowThreadProcessId(hwnd, None)
    layout = user32.GetKeyboardLayout(tid)
    buf = ctypes.create_unicode_buffer(8)
    n = user32.ToUnicodeEx(vk, scan, state, buf, 8, 0x4, layout)
    if n == 1 and buf.value.isprintable():
        return buf.value
    return None


@HOOKPROC
def _hook(nCode, wParam, lParam):
    # Keep this tiny: Windows drops hooks that block too long.
    try:
        if nCode == 0 and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
            k = ctypes.cast(lParam, ctypes.POINTER(KBDLL)).contents
            if not (k.flags & LLKHF_INJECTED):
                hwnd = user32.GetForegroundWindow()
                ctrl = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000) or \
                    bool(user32.GetAsyncKeyState(VK_MENU) & 0x8000)
                ch = None if ctrl else translate(k.vkCode, k.scanCode, hwnd)
                events.put_nowait((hwnd, k.vkCode, ch, ctrl))
    except Exception:
        pass
    return user32.CallNextHookEx(None, nCode, wParam, lParam)


def worker():
    buf, last = "", None
    while True:
        hwnd, vk, ch, ctrl = events.get()
        try:
            if hwnd != last:
                buf, last = "", hwnd
            if not is_browser(hwnd):
                buf = ""
                continue
            if ctrl or vk in RESET_KEYS:
                buf = ""
                continue
            if vk == VK_BACK:
                buf = buf[:-1]
                continue
            if ch is None:
                continue
            buf = (buf + ch.lower())[-int(S.cfg["buffer_size"]):]
            label = S.matcher.match(buf)
            if label:
                buf = ""
                trigger("typing", label)
        except Exception as e:
            log("worker error: %r" % (e,))


def title_watcher():
    while True:
        time.sleep(max(0.3, float(S.cfg["title_poll_seconds"])))
        try:
            reload_config()
            if not S.cfg["check_title"]:
                continue
            hwnd = user32.GetForegroundWindow()
            if not is_browser(hwnd):
                continue
            t = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, t, 512)
            label = S.matcher.match(t.value)
            if label:
                trigger("title", label)
        except Exception as e:
            log("title error: %r" % (e,))


def close_tab():
    for vk in (VK_CONTROL, VK_SHIFT, VK_MENU):          # release anything held
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(ord("W"), 0, 0, 0)
    user32.keybd_event(ord("W"), 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def show_message(text):
    if S.box_open:
        return
    S.box_open = True
    try:
        # MB_ICONINFORMATION | MB_SETFOREGROUND | MB_TOPMOST
        user32.MessageBoxW(None, text, "PMO Guard", 0x40 | 0x10000 | 0x40000)
    finally:
        S.box_open = False


def trigger(source, label):
    now = time.time()
    with S.lock:
        if now - S.last_hit < float(S.cfg["cooldown_seconds"]):
            return
        S.last_hit = now
        S.hits = [t for t in S.hits if now - t < S.cfg["lock_window_seconds"]] + [now]
        n = len(S.hits)
    log("blocked source=%s rule=%s hits_in_window=%d" % (source, label, n))
    if S.cfg["action"] == "close_tab":
        close_tab()
    if n >= int(S.cfg["lock_after_hits"]):
        user32.LockWorkStation()
    else:
        threading.Thread(target=show_message, args=(S.cfg["message"],),
                         daemon=True).start()


def main():
    mutex = kernel32.CreateMutexW(None, False, "Local\\PMOGuardAgent")
    if ctypes.get_last_error() == 183 or not mutex:      # already running
        return
    reload_config(force=True)
    log("agent started")
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=title_watcher, daemon=True).start()
    hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, _hook,
                                    kernel32.GetModuleHandleW(None), 0)
    if not hook:
        log("hook failed: %d" % ctypes.get_last_error())
        return
    msg = wt.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))


if __name__ == "__main__":
    main()

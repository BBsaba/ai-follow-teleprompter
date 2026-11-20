"""用 ctypes 直接调 Windows 的 IShellLinkW / IPersistFile 创建快捷方式。

为什么不走 `win32com.client.Dispatch("WScript.Shell")`：
    那需要 pywin32，而 pywin32 只为了建一个 .lnk 就要多装 10 MB，还得写进文档让人
    自己 pip install。这里直接对着 COM 虚表调，标准库就够。

为什么不用手写 .lnk 二进制：
    MS-SHLLINK 要求同时给出 LinkTargetIDList 和 LinkInfo，自己拼很容易漏字段，
    资源管理器会显示成"未知项目"。走系统 API 让 shell 自己生成，稳。

只用到这里需要的几个方法，虚表下标是固定值（见 MS-SHLLINK / shobjidl）：

    IShellLinkW  0 QueryInterface  1 AddRef  2 Release
                 7 SetDescription  9 SetWorkingDirectory  11 SetArguments
                 15 SetShowCmd     17 SetIconLocation     20 SetPath
    IPersistFile 3 GetClassID 4 IsDirty 5 Load 6 Save 7 SaveCompleted 8 GetCurFile
"""

from __future__ import annotations

import ctypes
import uuid
from ctypes import POINTER, byref, c_void_p, c_wchar_p
from ctypes import wintypes

CLSCTX_INPROC_SERVER = 1
S_OK = 0

CLSID_SHELLLINK = "00021401-0000-0000-C000-000000000046"
IID_ISHELLLINKW = "000214F9-0000-0000-C000-000000000046"
IID_IPERSISTFILE = "0000010B-0000-0000-C000-000000000046"

SW_SHOWNORMAL = 1


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def parse(cls, s: str) -> "GUID":
        u = uuid.UUID(s)
        g = cls()
        g.Data1 = u.time_low
        g.Data2 = u.time_mid
        g.Data3 = u.time_hi_version
        # uuid.bytes 是大端 16 字节，Data4 取后 8 字节
        for i, b in enumerate(u.bytes[8:]):
            g.Data4[i] = b
        return g


class HRESULT(ctypes.c_long):
    pass


_ole32 = ctypes.WinDLL("ole32", use_last_error=True)
_ole32.CoInitialize.argtypes = [c_void_p]
_ole32.CoInitialize.restype = HRESULT
_ole32.CoCreateInstance.argtypes = [
    POINTER(GUID),
    c_void_p,
    wintypes.DWORD,
    POINTER(GUID),
    POINTER(c_void_p),
]
_ole32.CoCreateInstance.restype = HRESULT
_ole32.CoUninitialize.argtypes = []
_ole32.CoUninitialize.restype = None


def _v(hr) -> int:
    """取 HRESULT 的整数值。

    ⚠️ ctypes 的 c_long 既不能直接位运算，`int()` 也拿不到值，只有 `.value`。
    而且子类实例和 int 直接比较并不可靠（实测值为 0 却判成不等），一律先转 int。
    """
    return int(getattr(hr, "value", hr))


def _hex(hr) -> str:
    """把 HRESULT 格式成 0xXXXXXXXX。"""
    return f"0x{_v(hr) & 0xFFFFFFFF:08X}"


def _call(ptr, index: int, restype, argtypes, *args):
    """按虚表下标调一个 COM 方法。"""
    vtbl = ctypes.cast(ptr, POINTER(POINTER(c_void_p))).contents
    proto = ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)
    return proto(vtbl[index])(ptr, *args)


def _release(ptr) -> None:
    if ptr:
        _call(ptr, 2, wintypes.ULONG, [])


def create_shortcut(
    lnk_path: str,
    target: str,
    arguments: str = "",
    working_dir: str = "",
    description: str = "",
    icon: str = "",
    show_cmd: int = SW_SHOWNORMAL,
) -> None:
    """创建（或覆盖）.lnk。失败抛 OSError。

    ⚠️ `icon` 只传**路径**，序号是单独的第 4 个参数（这里固定 0）。
    别学 pywin32 那种 `sc.IconLocation = "x.ico,0"` 的写法 —— 那个属性是「路径,序号」
    拼在一起的字符串，但 IShellLink::SetIconLocation(path, index) 是分开的两个参数。
    把 ",0" 塞进路径会让图标失效（实测读回来是 `x.ico,0`，shell 找不到这个文件）。
    """
    _ole32.CoInitialize(None)
    link = c_void_p()
    persist = c_void_p()
    try:
        hr = _ole32.CoCreateInstance(
            byref(GUID.parse(CLSID_SHELLLINK)),
            None,
            CLSCTX_INPROC_SERVER,
            byref(GUID.parse(IID_ISHELLLINKW)),
            byref(link),
        )
        if _v(hr) != S_OK:
            raise OSError(f"CoCreateInstance(ShellLink) 失败，HRESULT={_hex(hr)}")

        _call(link, 20, HRESULT, [c_wchar_p], target)
        if arguments:
            _call(link, 11, HRESULT, [c_wchar_p], arguments)
        if working_dir:
            _call(link, 9, HRESULT, [c_wchar_p], working_dir)
        if description:
            _call(link, 7, HRESULT, [c_wchar_p], description)
        if icon:
            _call(link, 17, HRESULT, [c_wchar_p, ctypes.c_int], icon, 0)
        _call(link, 15, HRESULT, [ctypes.c_int], show_cmd)

        hr = _call(
            link,
            0,
            HRESULT,
            [POINTER(GUID), POINTER(c_void_p)],
            byref(GUID.parse(IID_IPERSISTFILE)),
            byref(persist),
        )
        if _v(hr) != S_OK:
            raise OSError(f"QueryInterface(IPersistFile) 失败，HRESULT={_hex(hr)}")

        hr = _call(persist, 6, HRESULT, [c_wchar_p, wintypes.BOOL], lnk_path, True)
        if _v(hr) != S_OK:
            raise OSError(f"IPersistFile::Save 失败，HRESULT={_hex(hr)}")
    finally:
        _release(persist)
        _release(link)
        _ole32.CoUninitialize()


def read_shortcut(lnk_path: str) -> dict:
    """读回一个 .lnk 的字段，用于自检（不是给程序逻辑用的）。"""
    _ole32.CoInitialize(None)
    link = c_void_p()
    persist = c_void_p()
    out: dict = {}
    try:
        hr = _ole32.CoCreateInstance(
            byref(GUID.parse(CLSID_SHELLLINK)),
            None,
            CLSCTX_INPROC_SERVER,
            byref(GUID.parse(IID_ISHELLLINKW)),
            byref(link),
        )
        if _v(hr) != S_OK:
            raise OSError(f"CoCreateInstance(ShellLink) 失败，HRESULT={_hex(hr)}")

        hr = _call(
            link,
            0,
            HRESULT,
            [POINTER(GUID), POINTER(c_void_p)],
            byref(GUID.parse(IID_IPERSISTFILE)),
            byref(persist),
        )
        if _v(hr) != S_OK:
            raise OSError(f"QueryInterface(IPersistFile) 失败，HRESULT={_hex(hr)}")

        STGM_READ = 0
        hr = _call(persist, 5, HRESULT, [c_wchar_p, wintypes.DWORD], lnk_path, STGM_READ)
        if _v(hr) != S_OK:
            raise OSError(f"IPersistFile::Load 失败，HRESULT={_hex(hr)}")

        buf = ctypes.create_unicode_buffer(1024)
        _call(link, 3, HRESULT, [c_wchar_p, ctypes.c_int, c_void_p, wintypes.DWORD],
              buf, 1024, None, 0)
        out["target"] = buf.value

        buf = ctypes.create_unicode_buffer(1024)
        _call(link, 10, HRESULT, [c_wchar_p, ctypes.c_int], buf, 1024)
        out["arguments"] = buf.value

        buf = ctypes.create_unicode_buffer(1024)
        _call(link, 8, HRESULT, [c_wchar_p, ctypes.c_int], buf, 1024)
        out["working_dir"] = buf.value

        buf = ctypes.create_unicode_buffer(1024)
        _call(link, 6, HRESULT, [c_wchar_p, ctypes.c_int], buf, 1024)
        out["description"] = buf.value

        buf = ctypes.create_unicode_buffer(1024)
        idx = ctypes.c_int(0)
        _call(link, 16, HRESULT, [c_wchar_p, ctypes.c_int, POINTER(ctypes.c_int)],
              buf, 1024, byref(idx))
        out["icon"] = buf.value
        return out
    finally:
        _release(persist)
        _release(link)
        _ole32.CoUninitialize()


if __name__ == "__main__":
    import sys
    from pathlib import Path

    if len(sys.argv) < 3:
        print("自检：python win_shortcut.py <lnk 输出路径> <目标程序>")
        raise SystemExit(2)
    create_shortcut(
        sys.argv[1],
        sys.argv[2],
        arguments='"D:\\AITeleprompter\\run.py"',
        working_dir="D:\\AITeleprompter",
        description="self-test",
        icon="D:\\AITeleprompter\\assets\\teleprompter.ico",
    )
    p = Path(sys.argv[1])
    print("created" if p.exists() else "FAILED", p, p.stat().st_size if p.exists() else "")
    for k, v in read_shortcut(str(p)).items():
        print(f"  {k:<12} = {v}")

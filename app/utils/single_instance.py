from __future__ import annotations

import os
import sys

_mutex_handle = None

def acquire_lock(name: str = "mentra") -> None:
    global _mutex_handle

    if os.name != "nt":
        return

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    CreateMutexW = kernel32.CreateMutexW
    CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    CreateMutexW.restype = wintypes.HANDLE

    GetLastError = kernel32.GetLastError
    GetLastError.argtypes = []
    GetLastError.restype = wintypes.DWORD

    mutex_name = f"Local\\{name}"
    h = CreateMutexW(None, True, mutex_name)
    if not h:
        print("[LOCK] Failed to create mutex")
        sys.exit(1)

    ERROR_ALREADY_EXISTS = 183
    if GetLastError() == ERROR_ALREADY_EXISTS:
        print("[LOCK] Another instance is already running")
        sys.exit(1)

    _mutex_handle = h

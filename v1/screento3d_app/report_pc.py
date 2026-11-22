"""Collect a bounded, shareable hardware summary without requiring CUDA."""
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys


# Project just the values used by the report. WMI can also return device
# instance IDs, serials and host names, none of which are needed here.
_QUERY = r"""
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
@{
    gpu = @(Get-CimInstance Win32_VideoController -Property Name,DriverVersion -ErrorAction SilentlyContinue |
        Select-Object -First 8 -Property Name,DriverVersion)
    cpu = (Get-CimInstance Win32_Processor -Property Name -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty Name)
    memory = (Get-CimInstance Win32_ComputerSystem -Property TotalPhysicalMemory -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty TotalPhysicalMemory)
} | ConvertTo-Json -Depth 3 -Compress
"""


def _model_name(value):
    if isinstance(value, str):
        value = value.strip()
        if 0 < len(value) <= 160 and value.isprintable() and not any(c in value for c in '/\\:'):
            return value
    return ''


def collect_pc_info():
    if sys.platform != 'win32':
        return {}
    version = '.'.join(map(str, sys.getwindowsversion().platform_version))
    arch = platform.machine().upper()
    info = {'windows': f'{version} ({arch})' if arch in {'AMD64', 'X86', 'ARM64'} else version}
    system_root = os.environ.get('SystemRoot')
    if not system_root:
        return info
    powershell = Path(system_root) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    try:
        result = subprocess.run(
            [str(powershell), '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', _QUERY],
            check=True, capture_output=True, encoding='utf-8', timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        values = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return info
    if not isinstance(values, dict):
        return info
    if cpu := _model_name(values.get('cpu')):
        info['cpu'] = cpu
    memory = values.get('memory')
    if type(memory) is int and 0 < memory < 2**50:
        info['memory_gib'] = memory / 2**30
    adapters = values.get('gpu')
    if isinstance(adapters, list):
        gpus = []
        for adapter in adapters[:8]:
            if not isinstance(adapter, dict) or not (name := _model_name(adapter.get('Name'))):
                continue
            driver = adapter.get('DriverVersion')
            if (not isinstance(driver, str) or len(driver) > 40
                    or not re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,5}', driver)):
                driver = ''
            gpus.append((name, driver))
        if gpus:
            info['gpu'] = gpus
    return info

"""Verify compiler descendant ownership with real Windows process handles."""
import ctypes as ct
import json
from pathlib import Path
import subprocess
import sys


def main():
    kernel = ct.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [ct.c_ulong,ct.c_int,ct.c_ulong]
    kernel.OpenProcess.restype = ct.c_void_p
    kernel.WaitForSingleObject.argtypes = [ct.c_void_p,ct.c_ulong]
    kernel.CloseHandle.argtypes = [ct.c_void_p]
    helper = """
import subprocess,sys,time,os
from depthsbs_app.rowflow import bridge,check
dll=bridge();check(dll,dll.rowflow_protect_worker())
child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)'],creationflags=subprocess.CREATE_NO_WINDOW)
print(str(os.getpid())+' '+str(child.pid),flush=True)
time.sleep(120)
"""
    # Match multiprocessing: launch the real interpreter, not the venv redirector.
    worker = subprocess.Popen([sys._base_executable,'-c',helper],stdout=subprocess.PIPE,
                              text=True,creationflags=subprocess.CREATE_NO_WINDOW)
    handle = None
    try:
        actual,pid = map(int,worker.stdout.readline().split())
        print(dict(launcher=worker.pid,actual_worker=actual,child=pid),flush=True)
        handle = kernel.OpenProcess(0x100000,False,pid)
        assert handle and kernel.WaitForSingleObject(handle,0)==258
        worker.terminate();worker.wait(timeout=10)
        assert kernel.WaitForSingleObject(handle,10000)==0, 'Compiler child survived its worker'
        result=dict(passed=True,owned_descendant_exited=True)
        Path('out/rowflow-job-20261105.json').write_text(json.dumps(result))
        print(json.dumps(result))
    finally:
        if worker.poll() is None:worker.terminate();worker.wait(timeout=10)
        if handle:kernel.CloseHandle(handle)


if __name__=='__main__':main()

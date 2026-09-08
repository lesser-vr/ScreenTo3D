"""Real NT handle lifetime/IPC gate; no Qt or performance/display claims."""

import argparse
import ctypes as ct
import json
import multiprocessing as mp
import os
from pathlib import Path
from types import SimpleNamespace

from depthsbs_app.texture_mailbox import TextureMailbox, TexturePool
from texture_projection_oracle import TextureProjectionOracle, POOL_SHA256


def kernel():
    dll = ct.WinDLL("kernel32", use_last_error=True)
    dll.OpenProcess.argtypes = [ct.c_ulong, ct.c_int, ct.c_ulong]
    dll.OpenProcess.restype = ct.c_void_p
    dll.GetCurrentProcess.restype = ct.c_void_p
    dll.DuplicateHandle.argtypes = [
        ct.c_void_p,
        ct.c_void_p,
        ct.c_void_p,
        ct.POINTER(ct.c_void_p),
        ct.c_ulong,
        ct.c_int,
        ct.c_ulong,
    ]
    dll.CloseHandle.argtypes = [ct.c_void_p]
    dll.GetHandleInformation.argtypes = [ct.c_void_p, ct.POINTER(ct.c_ulong)]
    return dll


def worker(box, pipe):
    gpu = SimpleNamespace(width=64, height=32, _owner=lambda: None)
    dll = kernel()
    try:
        with TextureProjectionOracle(gpu, pool=True, diagnostic=False) as surface:
            surface.dll.live_pool_descriptor.argtypes = [
                ct.c_void_p,
                ct.c_void_p,
                ct.c_void_p,
                ct.c_void_p,
                ct.c_void_p,
            ]
            handles = (ct.c_ulonglong * 2)()
            low, high, pid = ct.c_ulong(), ct.c_long(), ct.c_ulong()
            surface._check(
                surface.dll.live_pool_descriptor(
                    surface.handle,
                    handles,
                    ct.byref(low),
                    ct.byref(high),
                    ct.byref(pid),
                )
            )
            original = tuple(handles)
            # Repeated descriptor reads must not allocate fresh handles.
            surface._check(
                surface.dll.live_pool_descriptor(
                    surface.handle,
                    handles,
                    ct.byref(low),
                    ct.byref(high),
                    ct.byref(pid),
                )
            )
            assert tuple(handles) == original
            pool = TexturePool(
                1, 1, pid.value, 128, 32, low.value, high.value, original
            )
            box.offer(pool, session=1, owned_pid=os.getpid())
            assert surface.output is None
            diagnostic = (ct.c_ubyte * (128 * 32 * 4))()
            assert not surface.dll.live_texture_readback(surface.handle, 0, diagnostic)
            assert b"disabled" in surface.dll.live_texture_error()
            pipe.send("offered")
            if not pipe.poll(10) or pipe.recv() != "retire":
                raise RuntimeError("Parent did not retire the test pool")
            box.retire(1, 1)
            pipe.send("retiring")
            if not pipe.poll(10) or pipe.recv() != "retired":
                raise RuntimeError("Parent did not acknowledge retirement")
        flags = ct.c_ulong()
        assert all(
            not dll.GetHandleInformation(handle, ct.byref(flags)) for handle in original
        )
        pipe.send("closed")
    finally:
        pipe.close()


def run_case(context, crash):
    dll = kernel()
    box = TextureMailbox.create(context)
    parent, child = context.Pipe()
    process = context.Process(target=worker, args=(box, child))
    process.start()
    child.close()
    duplicates = []
    origin = None
    try:
        assert parent.poll(20), "Worker did not offer pool"
        assert parent.recv() == "offered"
        pool = box.offered(session=1, owned_pid=process.pid)
        origin = dll.OpenProcess(0x40, False, process.pid)  # PROCESS_DUP_HANDLE only.
        assert origin, ct.get_last_error()
        for handle in pool.handles:
            duplicate = ct.c_void_p()
            assert dll.DuplicateHandle(
                origin,
                handle,
                dll.GetCurrentProcess(),
                ct.byref(duplicate),
                0,
                False,
                2,
            ), ct.get_last_error()
            duplicates.append(duplicate.value)
        box.install(1, 1)  # Test acknowledgement, not a Qt import assertion.
        if crash:
            process.terminate()  # Only this test's owned child.
        else:
            parent.send("retire")
            assert parent.poll(10) and parent.recv() == "retiring"
            box.finish_retirement(1, 1)
            parent.send("retired")
            assert parent.poll(10) and parent.recv() == "closed"
        process.join(10)
        assert not process.is_alive()
        assert crash or process.exitcode == 0
        flags = ct.c_ulong()
        # Duplicated handles remain owned by this process after child close/crash.
        for handle in duplicates:
            assert dll.GetHandleInformation(handle, ct.byref(flags))
        for handle in duplicates:
            assert dll.CloseHandle(handle)
            assert not dll.GetHandleInformation(handle, ct.byref(flags))
        duplicates.clear()
        return dict(crash=crash, passed=True, duplicate_count=2, child_reaped=True)
    finally:
        for handle in duplicates:
            dll.CloseHandle(handle)
        if origin:
            dll.CloseHandle(origin)
        parent.close()
        if process.is_alive():
            process.terminate()
            process.join(10)
        process.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    rows = [run_case(mp.get_context("spawn"), crash) for crash in (False, False, True)]
    report = dict(
        passed=True,
        cases=rows,
        pool_dll_sha256=POOL_SHA256,
        scope="Native NT handle ownership, staging disabled, child close/crash; no Qt rendering",
    )
    (args.output / "report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report))


if __name__ == "__main__":
    main()

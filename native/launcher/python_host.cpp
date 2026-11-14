#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shellapi.h>
#include <cstdio>
#include <cstdint>
#include <cwchar>
#include <io.h>
#include <fcntl.h>

// This GUI-subsystem executable shares the dynamic CRT with CPython. Keep
// inherited pipes usable for QProcess JSON workers without creating a console.
static bool inherited_streams() {
    const DWORD ids[] = {STD_INPUT_HANDLE, STD_OUTPUT_HANDLE, STD_ERROR_HANDLE};
    FILE* streams[] = {stdin, stdout, stderr};
    HANDLE copies[3]{};
    for (int i = 0; i < 3; ++i) {
        HANDLE source = GetStdHandle(ids[i]);
        if (source && source != INVALID_HANDLE_VALUE &&
            !DuplicateHandle(GetCurrentProcess(), source, GetCurrentProcess(), &copies[i],
                             0, FALSE, DUPLICATE_SAME_ACCESS)) {
            for (HANDLE copy : copies) if (copy) CloseHandle(copy);
            return false;
        }
    }
    bool success = true;
    for (int i = 0; i < 3; ++i) {
        if (!copies[i]) continue;
        if (_fileno(streams[i]) >= 0) {
            CloseHandle(copies[i]);
            continue;
        }
        FILE* reopened = nullptr;
        if (_wfreopen_s(&reopened, L"NUL", i == 0 ? L"rb" : L"wb", streams[i]) != 0) {
            CloseHandle(copies[i]); success = false; continue;
        }
        int descriptor = _open_osfhandle(reinterpret_cast<intptr_t>(copies[i]),
                                        _O_BINARY | (i == 0 ? _O_RDONLY : _O_WRONLY));
        if (descriptor < 0) { CloseHandle(copies[i]); success = false; continue; }
        if (_dup2(descriptor, _fileno(streams[i])) != 0) success = false;
        _close(descriptor);
        SetStdHandle(ids[i], reinterpret_cast<HANDLE>(_get_osfhandle(_fileno(streams[i]))));
    }
    return success;
}

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {
    if (!inherited_streams()) return ERROR_INVALID_HANDLE;
    // Avoid the C++ standard-library DLL: the embedded Python runtime already
    // supplies its CRT dependencies, and the host must not require another pack.
    wchar_t filename[32768]{};
    DWORD size = GetModuleFileNameW(nullptr, filename, DWORD(sizeof(filename) / sizeof(*filename)));
    if (!size || size >= sizeof(filename) / sizeof(*filename)) return ERROR_BAD_PATHNAME;
    wchar_t* leaf = std::wcsrchr(filename, L'\\');
    const wchar_t library[] = L"python313.dll";
    if (!leaf || (leaf + 1 - filename) + sizeof(library) / sizeof(*library) > sizeof(filename) / sizeof(*filename))
        return ERROR_BAD_PATHNAME;
    std::wcscpy(leaf + 1, library);
    // Resolve only the adjacent pinned runtime and normal system DLL locations.
    HMODULE python = LoadLibraryExW(filename, nullptr,
        LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
    if (!python) {
        std::fprintf(stderr, "ScreenTo3D: cannot load adjacent Python runtime (Windows %lu).\n", GetLastError());
        return ERROR_MOD_NOT_FOUND;
    }
    using PythonMain = int (__cdecl*)(int, wchar_t**);
    auto run = reinterpret_cast<PythonMain>(GetProcAddress(python, "Py_Main"));
    if (!run) return ERROR_PROC_NOT_FOUND;
    int argc = 0;
    wchar_t** argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (!argv) return ERROR_NOT_ENOUGH_MEMORY;
    // The app and worker JSON/log protocols are UTF-8 on every Windows locale,
    // including isolated multiprocessing children that ignore environment flags.
    wchar_t option[] = L"-X";
    wchar_t utf8[] = L"utf8";
    auto arguments = static_cast<wchar_t**>(HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY,
                                                    (std::size_t(argc) + 3) * sizeof(wchar_t*)));
    if (!arguments) { LocalFree(argv); return ERROR_NOT_ENOUGH_MEMORY; }
    arguments[0] = argv[0]; arguments[1] = option; arguments[2] = utf8;
    for (int i = 1; i < argc; ++i) arguments[i + 2] = argv[i];
    const int result = run(argc + 2, arguments);
    HeapFree(GetProcessHeap(), 0, arguments);
    LocalFree(argv);
    // Keep the runtime loaded until process teardown, like CPython's own host.
    return result;
}

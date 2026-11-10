#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shlobj.h>
#include <filesystem>
#include <string>
#include <vector>

namespace fs = std::filesystem;

static int fail(const std::wstring& message, DWORD code = 0) {
    std::wstring text = message;
    if (code) text += L"\nWindows 오류 코드 " + std::to_wstring(code);
    MessageBoxW(nullptr, text.c_str(), L"ScreenTo3D 실행 오류", MB_OK | MB_ICONERROR);
    return 1;
}

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {
    std::vector<wchar_t> filename(32768);
    DWORD length = GetModuleFileNameW(nullptr, filename.data(), DWORD(filename.size()));
    if (!length || length >= filename.size()) return fail(L"실행 파일 위치를 확인할 수 없습니다.", GetLastError());
    const fs::path root = fs::path(filename.data()).parent_path();
    const bool portable = fs::exists(root / L"desktop-portable");
    const fs::path python = root / (portable ? L"python/pythonw.exe" : L"out/vda-oracle-env/Scripts/pythonw.exe");
    if (!fs::exists(python) || !fs::exists(root / L"v1/depthsbs_app/launcher.py"))
        return fail(L"실행 구성요소가 없습니다. ScreenTo3D 배포 폴더 전체를 확인해 주세요.\n" + root.wstring());

    PWSTR local = nullptr;
    HRESULT result = SHGetKnownFolderPath(FOLDERID_LocalAppData, KF_FLAG_CREATE, nullptr, &local);
    if (FAILED(result)) return fail(L"사용자 로그 폴더를 찾을 수 없습니다.", DWORD(result));
    fs::path logs = fs::path(local) / L"DepthSBS/logs";
    CoTaskMemFree(local);
    std::error_code error;
    fs::create_directories(logs, error);
    if (error) return fail(L"실행 로그 폴더를 만들 수 없습니다.\n" + logs.wstring(), DWORD(error.value()));
    // Each concurrent launcher owns its log, including native stdout/stderr.
    fs::path log = logs / (L"launch-" + std::to_wstring(GetCurrentProcessId()) + L".log");
    SECURITY_ATTRIBUTES security{sizeof(SECURITY_ATTRIBUTES), nullptr, TRUE};
    HANDLE stream = CreateFileW(log.c_str(), FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE,
        &security, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (stream == INVALID_HANDLE_VALUE) return fail(L"실행 로그를 열 수 없습니다.", GetLastError());
    HANDLE input = CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
        &security, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (input == INVALID_HANDLE_VALUE) {
        DWORD code = GetLastError(); CloseHandle(stream);
        return fail(L"입력 스트림을 준비할 수 없습니다.", code);
    }
    SetEnvironmentVariableW(L"DEPTHSBS_LAUNCH_LOG", log.c_str());
    if (!portable) {
        std::wstring paths;
        for (const auto* part : {L"v1", L"out/gui-python-deps", L"out/capture-python-deps", L"out/v1-python-deps"}) {
            if (!paths.empty()) paths += L";";
            paths += (root / part).wstring();
        }
        SetEnvironmentVariableW(L"PYTHONPATH", paths.c_str());
    }
    std::wstring command = L"\"" + python.wstring() + L"\" -m depthsbs_app.launcher";
    STARTUPINFOW startup{}; startup.cb = sizeof(startup);
    startup.dwFlags = STARTF_USESTDHANDLES;
    startup.hStdInput = input; startup.hStdOutput = startup.hStdError = stream;
    PROCESS_INFORMATION process{};
    BOOL created = CreateProcessW(python.c_str(), command.data(), nullptr, nullptr, TRUE,
        CREATE_NO_WINDOW, nullptr, root.c_str(), &startup, &process);
    DWORD code = GetLastError();
    CloseHandle(input); CloseHandle(stream);
    if (!created) return fail(L"ScreenTo3D를 실행할 수 없습니다.\n" + log.wstring(), code);
    CloseHandle(process.hThread);
    WaitForSingleObject(process.hProcess, INFINITE);
    DWORD exitCode = 1;
    GetExitCodeProcess(process.hProcess, &exitCode);
    CloseHandle(process.hProcess);
    if (exitCode) return fail(L"ScreenTo3D가 오류로 종료되었습니다.\n로그 파일\n" + log.wstring(), exitCode);
    return 0;
}

#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shlobj.h>
#include <filesystem>
#include <string>
#include <vector>
#include <cwctype>
#include "generated_i18n.h"

namespace fs = std::filesystem;

namespace i18n = launcher_i18n;
static std::size_t language = i18n::default_language;
static const wchar_t* ui(i18n::Text key) { return i18n::text[language][key]; }

static std::wstring normalized(std::wstring tag) {
    for (auto& ch : tag) ch = ch == L'_' ? L'-' : wchar_t(towlower(ch));
    return tag;
}

static std::size_t match_language(const std::wstring& requested, bool exact) {
    const auto tag = normalized(requested);
    for (std::size_t i = 0; i < std::size(i18n::languages); ++i)
        if (tag == normalized(i18n::languages[i].code) || (!exact && tag == normalized(i18n::languages[i].locale))) return i;
    if (!exact) {
        const auto base = tag.substr(0, tag.find(L'-'));
        for (std::size_t i = 0; i < std::size(i18n::languages); ++i)
            if (base == normalized(i18n::languages[i].code)) return i;
    }
    return i18n::default_language;
}

static std::size_t selected_language() {
    wchar_t choice[128]{};
    DWORD bytes = sizeof(choice);
    LSTATUS status=ERROR_FILE_NOT_FOUND;
    for (const wchar_t* key : {L"Software\\ScreenTo3D\\ScreenTo3D\\ui",
                              L"Software\\StereoTo3D\\StereoTo3D\\ui",
                              L"Software\\DepthSBS\\DepthSBS\\ui"}) {
        bytes=sizeof(choice);
        status=RegGetValueW(HKEY_CURRENT_USER,key,L"language",RRF_RT_REG_SZ,nullptr,choice,&bytes);
        if (status!=ERROR_FILE_NOT_FOUND && status!=ERROR_PATH_NOT_FOUND)break;
    }
    if (status==ERROR_SUCCESS) {
        for (const auto& entry : i18n::languages)
            if (std::wstring(choice) == entry.code) return match_language(choice, true);
    }
    ULONG count = 0, chars = 0;
    GetUserPreferredUILanguages(MUI_LANGUAGE_NAME, &count, nullptr, &chars);
    if (chars && chars < 32768) {
        std::vector<wchar_t> tags(chars);
        if (GetUserPreferredUILanguages(MUI_LANGUAGE_NAME, &count, tags.data(), &chars) && tags[0])
            return match_language(tags.data(), false);
    }
    wchar_t locale[LOCALE_NAME_MAX_LENGTH]{};
    if (LCIDToLocaleName(MAKELCID(GetUserDefaultUILanguage(), SORT_DEFAULT), locale, LOCALE_NAME_MAX_LENGTH, 0))
        return match_language(locale, false);
    return i18n::default_language;
}

static int fail(i18n::Text error, DWORD code = 0, const std::wstring& details = L"") {
    std::wstring text = std::wstring(ui(i18n::ErrorId)) + L": " + i18n::ids[error] + L"\n\n" + ui(error);
    if (!details.empty()) text += std::wstring(L"\n\n") + ui(i18n::Details) + L":\n" + details;
    if (code) text += std::wstring(L"\n") + ui(i18n::WindowsCode) + L": " + std::to_wstring(code);
    MessageBoxW(nullptr, text.c_str(), ui(i18n::Title), MB_OK | MB_ICONERROR);
    return 1;
}

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {
    language = selected_language();
    std::vector<wchar_t> filename(32768);
    DWORD length = GetModuleFileNameW(nullptr, filename.data(), DWORD(filename.size()));
    if (!length || length >= filename.size()) return fail(i18n::E_LAUNCH_LOCATION, GetLastError());
    const fs::path root = fs::path(filename.data()).parent_path();
    const bool portable = fs::exists(root / L"desktop-portable");
    const fs::path python = root / (portable ? L"python/pythonw.exe" : L"out/vda-oracle-env/Scripts/pythonw.exe");
    if (!fs::exists(python) || !fs::exists(root / L"v1/screento3d_app/launcher.py"))
        return fail(i18n::E_LAUNCH_COMPONENTS, 0, root.wstring());

    PWSTR local = nullptr;
    HRESULT result = SHGetKnownFolderPath(FOLDERID_LocalAppData, KF_FLAG_CREATE, nullptr, &local);
    if (FAILED(result)) return fail(i18n::E_LAUNCH_USER_FOLDER, DWORD(result));
    fs::path logs = fs::path(local) / L"ScreenTo3D/logs";
    CoTaskMemFree(local);
    std::error_code error;
    fs::create_directories(logs, error);
    if (error) return fail(i18n::E_LAUNCH_LOG_FOLDER, DWORD(error.value()), logs.wstring());
    // Each concurrent launcher owns its log, including native stdout/stderr.
    fs::path log = logs / (L"launch-" + std::to_wstring(GetCurrentProcessId()) + L".log");
    SECURITY_ATTRIBUTES security{sizeof(SECURITY_ATTRIBUTES), nullptr, TRUE};
    HANDLE stream = CreateFileW(log.c_str(), FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE,
        &security, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (stream == INVALID_HANDLE_VALUE) return fail(i18n::E_LAUNCH_LOG_OPEN, GetLastError());
    HANDLE input = CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
        &security, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (input == INVALID_HANDLE_VALUE) {
        DWORD code = GetLastError(); CloseHandle(stream);
        return fail(i18n::E_LAUNCH_INPUT, code);
    }
    SetEnvironmentVariableW(L"SCREENTO3D_LAUNCH_LOG", log.c_str());
    if (!portable) {
        std::wstring paths;
        for (const auto* part : {L"v1", L"out/gui-python-deps", L"out/capture-python-deps", L"out/v1-python-deps"}) {
            if (!paths.empty()) paths += L";";
            paths += (root / part).wstring();
        }
        SetEnvironmentVariableW(L"PYTHONPATH", paths.c_str());
    }
    std::wstring command = L"\"" + python.wstring() + L"\" -m screento3d_app.launcher";
    STARTUPINFOW startup{}; startup.cb = sizeof(startup);
    startup.dwFlags = STARTF_USESTDHANDLES;
    startup.hStdInput = input; startup.hStdOutput = startup.hStdError = stream;
    PROCESS_INFORMATION process{};
    BOOL created = CreateProcessW(python.c_str(), command.data(), nullptr, nullptr, TRUE,
        CREATE_NO_WINDOW, nullptr, root.c_str(), &startup, &process);
    DWORD code = GetLastError();
    CloseHandle(input); CloseHandle(stream);
    if (!created) return fail(i18n::E_LAUNCH_PROCESS, code, log.wstring());
    CloseHandle(process.hThread);
    WaitForSingleObject(process.hProcess, INFINITE);
    DWORD exitCode = 1;
    GetExitCodeProcess(process.hProcess, &exitCode);
    CloseHandle(process.hProcess);
    if (exitCode) return fail(i18n::E_LAUNCH_EXIT, exitCode, log.wstring());
    return 0;
}

#define UNICODE
#define _UNICODE
#include <windows.h>
#include <wchar.h>

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR args, int show) {
    wchar_t root[32768], python[32768], command[32768];
    STARTUPINFOW si = {0}; PROCESS_INFORMATION pi = {0};
    (void)instance; (void)previous; (void)show;
    DWORD length = GetModuleFileNameW(NULL, root, 32768);
    if (!length || length >= 32000) return 1;
    wchar_t *last = wcsrchr(root, L'\\');
    if (!last) return 1;
    *last = 0;
    if (wcslen(root) * 3 + wcslen(args) > 32000) return 1;
    swprintf(python, 32768, L"%ls\\runtime\\pythonw.exe", root);
    swprintf(command, 32768, L"\"%ls\" -I \"%ls\\app_entry.py\" %ls", python, root, args);
    si.cb = sizeof(si);
    SetEnvironmentVariableW(L"PYTHONUTF8", L"1");
    if (!CreateProcessW(python, command, NULL, NULL, FALSE, 0, NULL, root, &si, &pi)) {
        MessageBoxW(NULL, L"Не удалось запустить встроенный Python. Распакуйте весь архив в локальную папку и проверьте, что runtime\\pythonw.exe присутствует. Подробности: README_RU.md.", L"НормаКонтроль ОПО", MB_OK | MB_ICONERROR);
        return 1;
    }
    CloseHandle(pi.hThread);
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 1; GetExitCodeProcess(pi.hProcess, &code); CloseHandle(pi.hProcess);
    return (int)code;
}

/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file ChildProcess on Windows: CreateProcessW, anonymous pipes, a job object (see process.hh). */

#include "stk/bridge/process.hh"

#ifndef WIN32_LEAN_AND_MEAN
#  define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#  define NOMINMAX
#endif
#include <windows.h>

#include <algorithm>
#include <atomic>
#include <cwchar>
#include <mutex>
#include <vector>

#include "stk/core/utf8.hh"

namespace stk::bridge {

namespace {

std::wstring widen(const std::string_view text)
{
  const std::u16string u16 = core::utf8::to_utf16(text);
  return std::wstring(reinterpret_cast<const wchar_t *>(u16.data()), u16.size());
}

std::string narrow(const std::wstring_view text)
{
  return core::utf8::from_utf16(std::u16string_view(reinterpret_cast<const char16_t *>(text.data()), text.size()));
}

std::string last_error_text(const char *what)
{
  const DWORD code = GetLastError();
  wchar_t *buffer = nullptr;
  const DWORD n = FormatMessageW(FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM |
                                     FORMAT_MESSAGE_IGNORE_INSERTS,
                                 nullptr, code, 0, reinterpret_cast<wchar_t *>(&buffer), 0, nullptr);
  std::string message = n && buffer ? narrow(std::wstring_view(buffer, n)) : std::string();
  if (buffer) {
    LocalFree(buffer);
  }
  while (!message.empty() && (message.back() == '\n' || message.back() == '\r' || message.back() == ' ')) {
    message.pop_back();
  }
  return std::string(what) + ": " + (message.empty() ? "error " + std::to_string(code) : message);
}

/** One argument quoted for CommandLineToArgvW / the MSVC runtime. */
void append_quoted(std::wstring &command, const std::wstring &arg)
{
  if (!arg.empty() && arg.find_first_of(L" \t\n\v\"") == std::wstring::npos) {
    command += arg;
    return;
  }
  command += L'"';
  for (size_t i = 0;; i++) {
    size_t backslashes = 0;
    while (i < arg.size() && arg[i] == L'\\') {
      i++;
      backslashes++;
    }
    if (i == arg.size()) {
      command.append(backslashes * 2, L'\\');
      break;
    }
    if (arg[i] == L'"') {
      command.append(backslashes * 2 + 1, L'\\');
      command += L'"';
    }
    else {
      command.append(backslashes, L'\\');
      command += arg[i];
    }
  }
  command += L'"';
}

struct CaseLess {
  bool operator()(const std::wstring &a, const std::wstring &b) const
  {
    return CompareStringOrdinal(a.c_str(), int(a.size()), b.c_str(), int(b.size()), TRUE) == CSTR_LESS_THAN;
  }
};

void close_handle(HANDLE &h)
{
  if (h && h != INVALID_HANDLE_VALUE) {
    CloseHandle(h);
  }
  h = nullptr;
}

}  // namespace

std::string ExitStatus::describe() const
{
  return "exit code " + std::to_string(code);
}

struct ChildProcess::Impl {
  HANDLE process = nullptr;
  HANDLE job = nullptr;
  DWORD pid = 0;
  HANDLE in_w = nullptr, out_r = nullptr, err_r = nullptr;
  std::atomic<bool> aborted{false};
  std::mutex stdin_mutex;
  std::mutex wait_mutex;
  std::optional<ExitStatus> status;

  ~Impl()
  {
    close_handle(in_w);
    close_handle(out_r);
    close_handle(err_r);
    close_handle(process);
    close_handle(job); /* KILL_ON_JOB_CLOSE: nothing of the job survives the handle */
  }
};

ChildProcess::ChildProcess(std::unique_ptr<Impl> impl) : impl_(std::move(impl)) {}

ChildProcess::~ChildProcess()
{
  if (impl_ && !wait(0.0)) {
    kill();
    wait(-1.0);
  }
}

std::optional<std::string> find_executable(const std::string_view name)
{
  if (name.empty()) {
    return std::nullopt;
  }
  const auto usable = [](const std::wstring &path) {
    const DWORD attributes = GetFileAttributesW(path.c_str());
    return attributes != INVALID_FILE_ATTRIBUTES && !(attributes & FILE_ATTRIBUTE_DIRECTORY);
  };
  std::vector<std::wstring> extensions = {L""};
  const std::wstring wname = widen(name);
  if (wname.find(L'.') == std::wstring::npos) {
    wchar_t pathext[1024];
    const DWORD n = GetEnvironmentVariableW(L"PATHEXT", pathext, 1024);
    std::wstring list = (n > 0 && n < 1024) ? std::wstring(pathext, n) : L".COM;.EXE;.BAT;.CMD";
    size_t start = 0;
    while (start <= list.size()) {
      size_t end = list.find(L';', start);
      if (end == std::wstring::npos) {
        end = list.size();
      }
      if (end > start) {
        extensions.push_back(list.substr(start, end - start));
      }
      start = end + 1;
    }
  }
  if (wname.find_first_of(L"\\/:") != std::wstring::npos) {
    for (const std::wstring &ext : extensions) {
      if (usable(wname + ext)) {
        return narrow(wname + ext);
      }
    }
    return std::nullopt;
  }
  std::vector<wchar_t> path(32768);
  const DWORD n = GetEnvironmentVariableW(L"PATH", path.data(), DWORD(path.size()));
  const std::wstring list = (n > 0 && n < path.size()) ? std::wstring(path.data(), n) : std::wstring();
  size_t start = 0;
  while (start < list.size()) {
    size_t end = list.find(L';', start);
    if (end == std::wstring::npos) {
      end = list.size();
    }
    std::wstring dir = list.substr(start, end - start);
    if (!dir.empty()) {
      if (dir.back() != L'\\' && dir.back() != L'/') {
        dir += L'\\';
      }
      for (const std::wstring &ext : extensions) {
        /* Skip the WindowsApps "App Execution Alias" stubs of python.exe (they open the Store). */
        if (dir.find(L"WindowsApps") != std::wstring::npos) {
          continue;
        }
        if (usable(dir + wname + ext)) {
          return narrow(dir + wname + ext);
        }
      }
    }
    start = end + 1;
  }
  return std::nullopt;
}

std::unique_ptr<ChildProcess> ChildProcess::spawn(const SpawnOptions &options, std::string &r_error)
{
  if (options.argv.empty()) {
    r_error = "no command";
    return nullptr;
  }
  const std::optional<std::string> exe = find_executable(options.argv[0]);
  if (!exe) {
    r_error = "executable not found: " + options.argv[0];
    return nullptr;
  }
  std::wstring command;
  for (size_t i = 0; i < options.argv.size(); i++) {
    if (i) {
      command += L' ';
    }
    append_quoted(command, widen(i == 0 ? *exe : options.argv[i]));
  }

  /* Environment block: the app's plus the overrides, sorted case-insensitively. */
  std::map<std::wstring, std::wstring, CaseLess> env;
  if (wchar_t *block = GetEnvironmentStringsW()) {
    for (const wchar_t *p = block; *p; p += wcslen(p) + 1) {
      const std::wstring entry(p);
      const size_t eq = entry.find(L'=', 1); /* "=C:=C:\..." entries start with '=' */
      if (eq != std::wstring::npos) {
        env[entry.substr(0, eq)] = entry.substr(eq + 1);
      }
    }
    FreeEnvironmentStringsW(block);
  }
  for (const auto &[key, value] : options.env) {
    if (value) {
      env[widen(key)] = widen(*value);
    }
    else {
      env.erase(widen(key));
    }
  }
  std::wstring env_block;
  for (const auto &[key, value] : env) {
    env_block += key + L"=" + value;
    env_block += L'\0';
  }
  env_block += L'\0';

  SECURITY_ATTRIBUTES sa = {sizeof(SECURITY_ATTRIBUTES), nullptr, TRUE};
  HANDLE in_r = nullptr, in_w = nullptr, out_r = nullptr, out_w = nullptr, err_r = nullptr, err_w = nullptr;
  const auto cleanup = [&] {
    for (HANDLE *h : {&in_r, &in_w, &out_r, &out_w, &err_r, &err_w}) {
      close_handle(*h);
    }
  };
  if (!CreatePipe(&in_r, &in_w, &sa, 0) || !CreatePipe(&out_r, &out_w, &sa, 0) ||
      !CreatePipe(&err_r, &err_w, &sa, 0))
  {
    r_error = last_error_text("CreatePipe");
    cleanup();
    return nullptr;
  }
  /* The app's ends are never inherited. */
  SetHandleInformation(in_w, HANDLE_FLAG_INHERIT, 0);
  SetHandleInformation(out_r, HANDLE_FLAG_INHERIT, 0);
  SetHandleInformation(err_r, HANDLE_FLAG_INHERIT, 0);

  /* Only the three child ends are inherited, even when other threads create inheritable handles. */
  HANDLE inherited[3] = {in_r, out_w, err_w};
  SIZE_T attr_size = 0;
  InitializeProcThreadAttributeList(nullptr, 1, 0, &attr_size);
  std::vector<unsigned char> attr_buffer(attr_size);
  auto *attributes = reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(attr_buffer.data());
  if (!InitializeProcThreadAttributeList(attributes, 1, 0, &attr_size) ||
      !UpdateProcThreadAttribute(attributes, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST, inherited, sizeof(inherited),
                                 nullptr, nullptr))
  {
    r_error = last_error_text("ProcThreadAttributeList");
    cleanup();
    return nullptr;
  }
  STARTUPINFOEXW si;
  ZeroMemory(&si, sizeof(si));
  si.StartupInfo.cb = sizeof(si);
  si.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
  si.StartupInfo.hStdInput = in_r;
  si.StartupInfo.hStdOutput = out_w;
  si.StartupInfo.hStdError = err_w;
  si.lpAttributeList = attributes;

  PROCESS_INFORMATION pi;
  ZeroMemory(&pi, sizeof(pi));
  const std::wstring wexe = widen(*exe);
  const std::wstring wcwd = widen(options.cwd);
  std::vector<wchar_t> command_buffer(command.begin(), command.end());
  command_buffer.push_back(L'\0');
  const BOOL created = CreateProcessW(wexe.c_str(), command_buffer.data(), nullptr, nullptr, TRUE,
                                     CREATE_SUSPENDED | CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT |
                                         EXTENDED_STARTUPINFO_PRESENT,
                                     env_block.data(), options.cwd.empty() ? nullptr : wcwd.c_str(),
                                     &si.StartupInfo, &pi);
  DeleteProcThreadAttributeList(attributes);
  close_handle(in_r);
  close_handle(out_w);
  close_handle(err_w);
  if (!created) {
    r_error = last_error_text("CreateProcessW");
    cleanup();
    return nullptr;
  }

  auto impl = std::make_unique<Impl>();
  impl->process = pi.hProcess;
  impl->pid = pi.dwProcessId;
  impl->in_w = in_w;
  impl->out_r = out_r;
  impl->err_r = err_r;
  in_w = out_r = err_r = nullptr;

  impl->job = CreateJobObjectW(nullptr, nullptr);
  if (impl->job) {
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits;
    ZeroMemory(&limits, sizeof(limits));
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_BREAKAWAY_OK;
    SetInformationJobObject(impl->job, JobObjectExtendedLimitInformation, &limits, sizeof(limits));
    if (!AssignProcessToJobObject(impl->job, pi.hProcess)) {
      close_handle(impl->job); /* fall back to terminating the process itself */
    }
  }
  ResumeThread(pi.hThread);
  CloseHandle(pi.hThread);
  return std::unique_ptr<ChildProcess>(new ChildProcess(std::move(impl)));
}

int64_t ChildProcess::pid() const
{
  return int64_t(impl_->pid);
}

bool ChildProcess::write_stdin(std::string_view data)
{
  std::lock_guard lock(impl_->stdin_mutex);
  if (!impl_->in_w) {
    return false;
  }
  while (!data.empty()) {
    DWORD written = 0;
    const DWORD chunk = DWORD(std::min<size_t>(data.size(), 1 << 20));
    if (!WriteFile(impl_->in_w, data.data(), chunk, &written, nullptr)) {
      return false;
    }
    data.remove_prefix(written);
  }
  return true;
}

void ChildProcess::close_stdin()
{
  std::lock_guard lock(impl_->stdin_mutex);
  close_handle(impl_->in_w);
}

std::ptrdiff_t ChildProcess::read(const Stream stream, char *buffer, const size_t size)
{
  HANDLE pipe = stream == Stream::Stdout ? impl_->out_r : impl_->err_r;
  /* Anonymous pipes have no overlapped I/O: poll with PeekNamedPipe so #abort_reads can end a
   * read that no data will ever complete (a helper holding the pipe open). */
  while (true) {
    if (impl_->aborted.load()) {
      return 0;
    }
    DWORD available = 0;
    if (!PeekNamedPipe(pipe, nullptr, 0, nullptr, &available, nullptr)) {
      const DWORD error = GetLastError();
      return (error == ERROR_BROKEN_PIPE || error == ERROR_PIPE_NOT_CONNECTED) ? 0 : -1;
    }
    if (available == 0) {
      Sleep(2);
      continue;
    }
    DWORD n = 0;
    if (!ReadFile(pipe, buffer, DWORD(std::min<size_t>(size, available)), &n, nullptr)) {
      const DWORD error = GetLastError();
      return (error == ERROR_BROKEN_PIPE || error == ERROR_PIPE_NOT_CONNECTED) ? 0 : -1;
    }
    return std::ptrdiff_t(n);
  }
}

void ChildProcess::abort_reads()
{
  impl_->aborted.store(true);
}

std::optional<ExitStatus> ChildProcess::wait(const double timeout_s)
{
  {
    std::lock_guard lock(impl_->wait_mutex);
    if (impl_->status) {
      return impl_->status;
    }
  }
  /* Waiting on the handle needs no lock (other threads may poll meanwhile). */
  const DWORD ms = timeout_s < 0 ? INFINITE : DWORD(timeout_s * 1000.0);
  if (WaitForSingleObject(impl_->process, ms) != WAIT_OBJECT_0) {
    return std::nullopt;
  }
  std::lock_guard lock(impl_->wait_mutex);
  if (impl_->status) {
    return impl_->status;
  }
  DWORD code = 0;
  GetExitCodeProcess(impl_->process, &code);
  if (impl_->job) {
    TerminateJobObject(impl_->job, 1); /* whatever it left behind in the job */
  }
  ExitStatus status;
  status.code = int(code);
  impl_->status = status;
  return impl_->status;
}

void ChildProcess::terminate()
{
  kill(); /* Windows has no polite signal for a console-less child; the bridge got EOF first. */
}

void ChildProcess::kill()
{
  if (impl_->job) {
    TerminateJobObject(impl_->job, 1);
  }
  else {
    TerminateProcess(impl_->process, 1);
  }
}

bool ChildProcess::group_alive() const
{
  if (impl_->job) {
    JOBOBJECT_BASIC_ACCOUNTING_INFORMATION info;
    ZeroMemory(&info, sizeof(info));
    if (QueryInformationJobObject(impl_->job, JobObjectBasicAccountingInformation, &info, sizeof(info), nullptr)) {
      return info.ActiveProcesses > 0;
    }
  }
  return WaitForSingleObject(impl_->process, 0) != WAIT_OBJECT_0;
}

}  // namespace stk::bridge

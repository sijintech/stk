/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/platform/file_dialog.hh"

#include <atomic>
#include <cstdlib>
#include <mutex>
#include <thread>

#include "stk/bridge/process.hh"
#include "stk/core/paths.hh"

#if !defined(_WIN32)
#  include <signal.h>
#  include <spawn.h>
#  include <sys/wait.h>
#  include <unistd.h>
extern char **environ;
#endif

namespace stk::platform {

namespace {

std::string trim(std::string_view s)
{
  size_t a = 0, b = s.size();
  while (a < b && (s[a] == ' ' || s[a] == '\t' || s[a] == '\r' || s[a] == '\n')) {
    a++;
  }
  while (b > a && (s[b - 1] == ' ' || s[b - 1] == '\t' || s[b - 1] == '\r' || s[b - 1] == '\n')) {
    b--;
  }
  return std::string(s.substr(a, b - a));
}

int hex_value(const char c)
{
  if (c >= '0' && c <= '9') {
    return c - '0';
  }
  if (c >= 'a' && c <= 'f') {
    return c - 'a' + 10;
  }
  if (c >= 'A' && c <= 'F') {
    return c - 'A' + 10;
  }
  return -1;
}

std::string normalize_entry(std::string entry)
{
  entry = trim(entry);
  if (entry.size() >= 2 && ((entry.front() == '"' && entry.back() == '"') || (entry.front() == '\'' && entry.back() == '\''))) {
    entry = trim(std::string_view(entry).substr(1, entry.size() - 2));
  }
  if (entry.rfind("file://", 0) == 0) {
    std::string rest = entry.substr(7);
    /* file://host/path: only the local host (empty or "localhost") is meaningful. */
    if (rest.rfind("localhost/", 0) == 0) {
      rest = rest.substr(9);
    }
    std::string decoded;
    for (size_t i = 0; i < rest.size(); i++) {
      if (rest[i] == '%' && i + 2 < rest.size() && hex_value(rest[i + 1]) >= 0 && hex_value(rest[i + 2]) >= 0) {
        decoded += char(hex_value(rest[i + 1]) * 16 + hex_value(rest[i + 2]));
        i += 2;
      }
      else {
        decoded += rest[i];
      }
    }
    entry = decoded;
  }
  if (entry == "~" || entry.rfind("~/", 0) == 0) {
    entry = core::path_to_utf8(core::home_dir()) + entry.substr(1);
  }
  return entry;
}

#if !defined(_WIN32)

/** A dialog run as a child process (zenity / kdialog); one thread per open dialog. */
class ProcessFileDialog final : public FileDialog {
 public:
  ProcessFileDialog(std::string tool, std::string exe, Executor executor)
      : shared_(std::make_shared<Shared>()), tool_(std::move(tool)), exe_(std::move(exe))
  {
    shared_->executor = std::move(executor);
  }

  ~ProcessFileDialog() override
  {
    /* Dialogs still open are closed; their results are dropped. */
    std::lock_guard lock(shared_->mutex);
    shared_->alive = false;
    for (bridge::ChildProcess *p : shared_->running) {
      p->terminate();
    }
  }

  std::string name() const override
  {
    return tool_;
  }

  void open(const FileDialogRequest &request, std::function<void(FileDialogResult)> done) override
  {
    bridge::SpawnOptions options;
    options.argv = arguments(request);
    std::string error;
    std::shared_ptr<bridge::ChildProcess> child(bridge::ChildProcess::spawn(options, error).release());
    if (!child) {
      post(shared_, std::move(done), FileDialogResult{{}, tool_ + ": " + error});
      return;
    }
    {
      std::lock_guard lock(shared_->mutex);
      shared_->running.push_back(child.get());
    }
    child->close_stdin();
    std::thread([shared = shared_, child, done = std::move(done), tool = tool_, mode = request.mode]() mutable {
      std::string out, err;
      std::thread drain([&] {
        char buffer[1024];
        std::ptrdiff_t n;
        while ((n = child->read(bridge::ChildProcess::Stream::Stderr, buffer, sizeof(buffer))) > 0) {
          err.append(buffer, size_t(n));
        }
      });
      char buffer[4096];
      std::ptrdiff_t n;
      while ((n = child->read(bridge::ChildProcess::Stream::Stdout, buffer, sizeof(buffer))) > 0) {
        out.append(buffer, size_t(n));
      }
      drain.join();
      const std::optional<bridge::ExitStatus> status = child->wait(-1);
      {
        std::lock_guard lock(shared->mutex);
        std::erase(shared->running, child.get());
      }
      FileDialogResult result;
      if (status && status->success()) {
        for (const std::string &p : split_path_list(out)) {
          result.paths.push_back(p);
        }
        if (mode != FileDialogMode::OpenFiles && result.paths.size() > 1) {
          result.paths.resize(1);
        }
      }
      else if (!status || status->code != 1) {
        /* zenity / kdialog exit with 1 on cancel; anything else is a failure. */
        result.error = tool + ": " + (status ? status->describe() : std::string("did not exit")) +
                       (err.empty() ? std::string() : " (" + trim(err) + ")");
      }
      post(shared, std::move(done), std::move(result));
    }).detach();
  }

 private:
  struct Shared {
    std::mutex mutex;
    bool alive = true;
    Executor executor;
    std::vector<bridge::ChildProcess *> running;
  };

  static void post(const std::shared_ptr<Shared> &shared, std::function<void(FileDialogResult)> done,
                   FileDialogResult result)
  {
    Executor executor;
    {
      std::lock_guard lock(shared->mutex);
      if (!shared->alive || !done) {
        return;
      }
      executor = shared->executor;
    }
    auto task = [done = std::move(done), result = std::move(result), weak = std::weak_ptr<Shared>(shared)]() {
      if (auto s = weak.lock()) {
        bool alive;
        {
          std::lock_guard l(s->mutex);
          alive = s->alive;
        }
        if (alive) {
          done(result);
        }
      }
    };
    if (executor) {
      executor(std::move(task));
    }
    else {
      task();
    }
  }

  std::vector<std::string> arguments(const FileDialogRequest &r) const
  {
    std::vector<std::string> a{exe_};
    std::string start = r.directory;
    if (!start.empty() && start.back() != '/') {
      start += '/';
    }
    if (tool_ == "zenity") {
      a.push_back("--file-selection");
      if (!r.title.empty()) {
        a.push_back("--title=" + r.title);
      }
      switch (r.mode) {
        case FileDialogMode::OpenFiles:
          a.push_back("--multiple");
          a.push_back("--separator=\n");
          break;
        case FileDialogMode::OpenFolder:
          a.push_back("--directory");
          break;
        case FileDialogMode::SaveFile:
          a.push_back("--save");
          a.push_back("--confirm-overwrite");
          break;
      }
      if (!start.empty() || !r.file_name.empty()) {
        a.push_back("--filename=" + start + r.file_name);
      }
      return a;
    }
    /* kdialog */
    if (!r.title.empty()) {
      a.push_back("--title");
      a.push_back(r.title);
    }
    switch (r.mode) {
      case FileDialogMode::OpenFiles:
        a.push_back("--getopenfilename");
        a.push_back(start.empty() ? "." : start);
        a.push_back("--multiple");
        a.push_back("--separate-output");
        break;
      case FileDialogMode::OpenFolder:
        a.push_back("--getexistingdirectory");
        a.push_back(start.empty() ? "." : start);
        break;
      case FileDialogMode::SaveFile:
        a.push_back("--getsavefilename");
        a.push_back(start + r.file_name);
        break;
    }
    return a;
  }

  std::shared_ptr<Shared> shared_;
  std::string tool_, exe_;
};

#endif

}  // namespace

std::unique_ptr<FileDialog> create_native_file_dialog(Executor executor)
{
  std::string pick;
  if (const auto env = core::getenv_utf8("STK_FILE_DIALOG")) {
    pick = *env;
  }
  if (pick == "none") {
    return nullptr;
  }
#if defined(_WIN32) || defined(__APPLE__)
  (void)executor;
  return nullptr; /* nativefiledialog-extended (IFileDialog / NSOpenPanel) is the planned backend. */
#else
  std::vector<std::string> tools;
  if (!pick.empty()) {
    tools.push_back(pick);
  }
  else {
    const std::string desktop = core::getenv_utf8("XDG_CURRENT_DESKTOP").value_or("");
    tools = desktop.find("KDE") != std::string::npos ? std::vector<std::string>{"kdialog", "zenity"} :
                                                        std::vector<std::string>{"zenity", "kdialog"};
  }
  if (!core::getenv_utf8("DISPLAY") && !core::getenv_utf8("WAYLAND_DISPLAY")) {
    return nullptr;
  }
  for (const std::string &tool : tools) {
    if (tool != "zenity" && tool != "kdialog") {
      continue;
    }
    if (const auto exe = bridge::find_executable(tool)) {
      return std::make_unique<ProcessFileDialog>(tool, *exe, std::move(executor));
    }
  }
  return nullptr;
#endif
}

std::vector<std::string> split_path_list(const std::string_view text)
{
  std::vector<std::string> out;
  const bool lines = text.find('\n') != std::string_view::npos;
  const char sep = lines ? '\n' : ';';
  size_t start = 0;
  while (start <= text.size()) {
    size_t end = text.find(sep, start);
    if (end == std::string_view::npos) {
      end = text.size();
    }
    std::string entry = normalize_entry(std::string(text.substr(start, end - start)));
    if (!entry.empty()) {
      out.push_back(std::move(entry));
    }
    start = end + 1;
  }
  return out;
}

bool is_absolute_path(const std::string_view path)
{
#if defined(_WIN32)
  return (path.size() >= 3 && path[1] == ':' && (path[2] == '\\' || path[2] == '/')) ||
         (path.size() >= 2 && path[0] == '\\' && path[1] == '\\');
#else
  return !path.empty() && path[0] == '/';
#endif
}

bool open_with_system(const std::string &path, std::string *error)
{
#if defined(_WIN32)
  if (error) {
    *error = "opening files with the system is not implemented on Windows yet";
  }
  (void)path;
  return false;
#else
#  if defined(__APPLE__)
  const char *tool = "open";
#  else
  const char *tool = "xdg-open";
#  endif
  const std::optional<std::string> exe = bridge::find_executable(tool);
  if (!exe) {
    if (error) {
      *error = std::string(tool) + " not found";
    }
    return false;
  }
  posix_spawnattr_t attr;
  posix_spawnattr_init(&attr);
  short flags = POSIX_SPAWN_SETSIGMASK | POSIX_SPAWN_SETSIGDEF;
#  if defined(POSIX_SPAWN_SETSID)
  flags |= POSIX_SPAWN_SETSID; /* own session: the viewer outlives the app */
#  else
  flags |= POSIX_SPAWN_SETPGROUP;
  posix_spawnattr_setpgroup(&attr, 0);
#  endif
  posix_spawnattr_setflags(&attr, flags);
  sigset_t none, all;
  sigemptyset(&none);
  sigfillset(&all);
  posix_spawnattr_setsigmask(&attr, &none);
  posix_spawnattr_setsigdefault(&attr, &all);
  std::string exe_copy = *exe, arg = path;
  char *argv[] = {exe_copy.data(), arg.data(), nullptr};
  pid_t pid = 0;
  const int rc = posix_spawn(&pid, exe_copy.c_str(), nullptr, &attr, argv, environ);
  posix_spawnattr_destroy(&attr);
  if (rc != 0) {
    if (error) {
      *error = std::string(tool) + ": cannot start";
    }
    return false;
  }
  /* Reap the opener (it exits once the viewer runs) without blocking the caller. */
  std::thread([pid]() {
    int status = 0;
    waitpid(pid, &status, 0);
  }).detach();
  return true;
#endif
}

}  // namespace stk::platform

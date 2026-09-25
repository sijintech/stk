/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * File dialogs and "open with the system" (CPU only: no GHOST, GPU or toolkit headers).
 *
 * #FileDialog is the abstraction the editors use to pick files, folders and save destinations.
 * #create_native_file_dialog returns the platform's dialog when one is available:
 *   - Linux / BSD: `zenity` (GNOME; GTK uses xdg-desktop-portal when it runs sandboxed) or
 *     `kdialog` (KDE), run as a child process in the background;
 *   - macOS / Windows: none yet (nativefiledialog-extended is the planned backend).
 * When it returns null, or a dialog fails to run (FileDialogResult::error), the editors show their
 * in-app path field instead (#split_path_list parses what the user typed or pasted there).
 *
 *   auto dialog = stk::platform::create_native_file_dialog(wm->executor());
 *   if (dialog) dialog->open({.mode = FileDialogMode::OpenFiles, .title = "Upload"},
 *                            [](FileDialogResult r) { if (!r.paths.empty()) upload(r.paths); });
 */
#pragma once

#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

namespace stk::platform {

/** Runs a task on the application's main loop (stk::wm::WindowManager::executor()). */
using Executor = std::function<void(std::function<void()>)>;

enum class FileDialogMode : uint8_t {
  OpenFiles,  /**< One or more existing files. */
  OpenFolder, /**< One existing directory. */
  SaveFile,   /**< A destination file (may exist; the dialog asks before overwriting). */
};

struct FileDialogRequest {
  FileDialogMode mode = FileDialogMode::OpenFiles;
  /** Window title (localized by the caller). */
  std::string title;
  /** Start directory (empty: the dialog's default). */
  std::string directory;
  /** SaveFile: suggested file name. */
  std::string file_name;
};

struct FileDialogResult {
  /** Absolute UTF-8 paths; empty when the user cancelled or the dialog failed. */
  std::vector<std::string> paths;
  /** Why the dialog could not run (the caller falls back to its path field); empty otherwise. */
  std::string error;
  bool cancelled() const
  {
    return paths.empty() && error.empty();
  }
};

class FileDialog {
 public:
  virtual ~FileDialog() = default;
  /** "zenity", "kdialog", "fake" ... (diagnostics). */
  virtual std::string name() const = 0;
  /**
   * Shows the dialog without blocking the caller. `done` runs exactly once, through the executor
   * given at creation (the main loop), unless the dialog object was destroyed first.
   */
  virtual void open(const FileDialogRequest &request, std::function<void(FileDialogResult)> done) = 0;
};

/**
 * The platform's native dialog, or null when none is available (the caller then offers its path
 * field only). `executor` must stay valid while the returned object lives. `STK_FILE_DIALOG=none`
 * disables native dialogs (tests); `STK_FILE_DIALOG=zenity|kdialog` picks one.
 */
std::unique_ptr<FileDialog> create_native_file_dialog(Executor executor);

/**
 * Paths typed or pasted into a path field: one per line, or separated by ';' on one line; blank
 * entries dropped, surrounding whitespace and quotes removed, a leading "~/" expanded to the home
 * directory and file:// URIs (percent-encoded, as file managers paste them) decoded.
 */
std::vector<std::string> split_path_list(std::string_view text);

/** Whether `path` is absolute (after #split_path_list's expansion). */
bool is_absolute_path(std::string_view path);

/**
 * Opens a file or directory with the system's default application (Linux: xdg-open in its own
 * session, so closing the app does not close the viewer; macOS: open). False with `error` when
 * the opener cannot be started.
 */
bool open_with_system(const std::string &path, std::string *error = nullptr);

}  // namespace stk::platform

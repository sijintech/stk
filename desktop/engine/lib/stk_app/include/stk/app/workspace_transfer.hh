/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include "stk/io/json.hh"
#include <memory>
#include <string>

namespace stk::ui { class Context; }
namespace stk::wm { class Screen; }
namespace stk::app {
class AppShell;

/** Explicit workspace-file actions shared by every top bar. Preview is read-only; no refresh,
 * file selection, close or restore implicitly executes user programs or simulation tasks. */
class WorkspaceTransfer {
 public:
  explicit WorkspaceTransfer(AppShell &shell);
  ~WorkspaceTransfer();
  WorkspaceTransfer(const WorkspaceTransfer &) = delete;
  WorkspaceTransfer &operator=(const WorkspaceTransfer &) = delete;
  void show(wm::Screen *screen, bool importing);
  void show_open(wm::Screen *screen);
  void draw(ui::Context &ui, wm::Screen *screen);
  /** An accepted import/open runs to its atomic completion before the dialog may close. */
  bool close();
  bool visible() const;
  bool busy() const;
  const std::string &error() const;
  const io::Json &preview() const;

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
}  // namespace stk::app

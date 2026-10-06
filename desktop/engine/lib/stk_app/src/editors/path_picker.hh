/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * "Browse…" beside a path field. The button asks the platform's native file dialog (Linux: zenity or
 * kdialog, see stk/platform/file_dialog.hh) and writes the chosen absolute path(s) into the field, one
 * per line, exactly as if they were typed or dropped. Choosing never opens, imports, indexes or runs
 * anything: the field's own action stays a separate click. Without a native dialog no button is drawn
 * and the field remains the way to enter paths; a dialog that cannot run says why under the field.
 * Answers for a destroyed owner, or for a field whose context changed meanwhile (`still_current`, e.g.
 * another project was opened), are dropped.
 */
#pragma once

#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/jobs_state.hh"
#include "stk/platform/file_dialog.hh"

#include <functional>
#include <memory>
#include <string>

namespace stk::app {

class PathPicker {
 public:
  struct Options {
    platform::FileDialogMode mode = platform::FileDialogMode::OpenFiles;
    /** Catalog key of the dialog title. */
    std::string title_key;
    /** SaveFile: suggested file name. */
    std::string file_name;
    /** OpenFiles: keep every chosen file (appended to the field) instead of only the first. */
    bool multiple = false;
    /** Checked when the answer arrives; false drops it. */
    std::function<bool()> still_current;
  };

  /** Whether a native dialog exists (the button is drawn only then). */
  static bool available(AppStore &store) { return store.jobs().file_dialog != nullptr; }

  /** Draws the button into `row` (normally the row holding the field). `target` must outlive this picker. */
  void button(ui::Layout &row, EditorContext &ctx, std::string_view key, std::string *target, Options options)
  {
    if (!available(ctx.store)) { return; }
    AppStore *store = &ctx.store;
    row.button(key, ctx.tr("path.browse"), [this, store, target, options = std::move(options)] {
      auto *dialog = store->jobs().file_dialog;
      if (!dialog) { return; }
      error_.clear();
      platform::FileDialogRequest request;
      request.mode = options.mode;
      request.title = std::string(store->tr(options.title_key));
      request.file_name = options.file_name;
      std::weak_ptr<bool> alive = alive_;
      dialog->open(request, [this, alive, store, target, options](platform::FileDialogResult result) {
        if (alive.expired() || (options.still_current && !options.still_current())) { return; }
        if (!result.error.empty()) {
          error_ = store->catalog().format("path.browse_failed", {{"error", result.error}});
        }
        else if (!result.paths.empty()) {
          std::string text = options.multiple ? *target : std::string();
          const size_t count = options.multiple ? result.paths.size() : 1;
          for (size_t i = 0; i < count; ++i) {
            if (!text.empty() && text.back() != '\n') { text += '\n'; }
            text += result.paths[i];
          }
          *target = std::move(text);
        }
        store->changed();
      });
    }).width(6);
  }

  /** Why the last dialog could not run, under the field (nothing when it ran or was cancelled). */
  void draw_error(ui::Layout &layout) const
  {
    if (!error_.empty()) { layout.paragraph(error_); }
  }

 private:
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  std::string error_;
};

}  // namespace stk::app

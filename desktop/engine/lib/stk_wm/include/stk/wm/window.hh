/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * GHOST glue: the window manager (GHOST system + GPU + font stack), windows with their own GPU
 * context and #Screen, the on-demand event loop, DPI, clipboard, cursors, IME and drag & drop.
 *
 *   stk::gfx::Runtime runtime;
 *   stk::wm::WmOptions options;              // options.window.title = "STK", ...
 *   auto wm = stk::wm::WindowManager::create(options, err);
 *   wm->main_window()->screen().add_area("main").emplace_region<MyRegion>();
 *   return wm->run();
 *
 * Redraws happen only when something called Window::request_redraw / Region::tag_redraw, or on
 * resize, expose and DPI changes. An idle application sleeps in the OS event wait (X11, Win32,
 * Cocoa) or polls every 5 ms like Blender's WM (Wayland, where GHOST's wait ignores timers).
 * Main thread only; other threads must not touch the engine (WP8 adds a wake-up channel).
 */
#pragma once

#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

#include "stk/gfx/gpu.hh"
#include "stk/gfx/image.hh"
#include "stk/wm/event.hh"
#include "stk/wm/screen.hh"

class GHOST_ISystem;
class GHOST_IWindow;
class GHOST_ITimerTask;
namespace blender {
struct GPUContext;
}

namespace stk::wm {

class WindowManager;

struct WindowOptions {
  std::string title = "STK";
  /** Initial client size in logical points (scaled by the OS on HiDPI outputs). */
  int width = 1280;
  int height = 800;
  bool maximized = false;
};

class Window {
 public:
  ~Window();
  Window(const Window &) = delete;
  Window &operator=(const Window &) = delete;

  WindowManager &manager() const
  {
    return *wm_;
  }
  Screen &screen()
  {
    return screen_;
  }

  /** Framebuffer size in pixels. */
  int width() const
  {
    return width_;
  }
  int height() const
  {
    return height_;
  }
  /** OS pixels per logical point (2 on Retina / Wayland scale 2 with native pixels). */
  float native_pixel_size() const
  {
    return native_pixel_size_;
  }
  /** Native DPI factor: max(DPI hint, 96) / 96 x native pixel size. */
  float dpi_factor() const
  {
    return dpi_factor_;
  }
  /** UI scale = #dpi_factor x the window manager's user scale. */
  float ui_scale() const;

  void set_title(const std::string &title);
  /** Resizes the client area (logical points). */
  void set_client_size(int width, int height);

  void request_redraw();
  bool needs_redraw() const;
  /** Frames presented so far (for tests and diagnostics). */
  uint64_t frames_drawn() const
  {
    return frames_drawn_;
  }

  void set_cursor(Cursor cursor);
  Cursor cursor() const
  {
    return cursor_;
  }
  void set_cursor_visible(bool visible);

  /**
   * Starts (or moves) IME composition for a text caret at `caret` (window pixels, bottom-left
   * origin). `completed`: the text field is not in an ongoing composition (Blender semantics).
   */
  void ime_begin(const Rect &caret, bool completed = true);
  void ime_end();
  bool ime_active() const
  {
    return ime_active_;
  }

  /**
   * Renders the window's screen into an offscreen image at the window size (rows top to bottom),
   * like Blender's WM_window_pixels_read_from_offscreen. Not from inside a draw.
   */
  bool read_pixels(gfx::Image &r_image, std::string &r_error);

  /** Behaves like the user closing the window (emits Close; closes unless consumed). */
  void request_close();

  /**
   * Called for every event before the screen routes it; return true to consume. A Close event
   * that is not consumed closes the window.
   */
  std::function<bool(const Event &)> on_event;

  /** Escape hatch for code that needs GHOST directly (stk_wm internals, tests). */
  GHOST_IWindow *ghost_window() const
  {
    return ghost_;
  }

 private:
  friend class WindowManager;
  Window() = default;
  void update_geometry();
  bool update_dpi();
  DrawContext draw_context(const Rect &rect = {});
  void make_current();
  void draw();
  void to_window_px(int32_t client_x, int32_t client_y, int &r_x, int &r_y) const;
  void screen_to_window_px(int32_t screen_x, int32_t screen_y, int &r_x, int &r_y) const;

  WindowManager *wm_ = nullptr;
  GHOST_IWindow *ghost_ = nullptr;
  blender::GPUContext *gpu_context_ = nullptr;
  Screen screen_;
  int width_ = 0, height_ = 0;
  /** Client size in logical points (GHOST client bounds). */
  int client_w_ = 0, client_h_ = 0;
  float native_pixel_size_ = 1.0f;
  float dpi_factor_ = 1.0f;
  int last_x_ = 0, last_y_ = 0;
  Cursor cursor_ = Cursor::Default;
  bool ime_active_ = false;
  bool close_pending_ = false;
  uint64_t frames_drawn_ = 0;
};

struct WmOptions {
  gfx::GpuOptions gpu;
  /** The main window, opened by #WindowManager::create. */
  WindowOptions window;
  /** User UI scale multiplied with each window's native DPI factor. */
  float user_scale = 1.0f;
  /** Quit #WindowManager::run when the last window closes. */
  bool quit_on_last_window_closed = true;
};

class WindowManager {
 public:
  /**
   * Creates the GHOST system (Wayland, then X11 on Linux; Cocoa; Win32), opens the main window
   * (`options.window`), then initializes the GPU module and fonts.
   */
  static std::unique_ptr<WindowManager> create(const WmOptions &options, std::string &r_error);
  /** Closes all windows, then shuts down fonts, GPU and GHOST. */
  ~WindowManager();
  WindowManager(const WindowManager &) = delete;
  WindowManager &operator=(const WindowManager &) = delete;

  gfx::Gpu &gpu()
  {
    return *gpu_;
  }
  /** "WAYLAND", "X11", "COCOA", "WIN32", ... */
  const char *system_backend() const;

  /** The first window (opened by #create); nullptr once it was closed. */
  Window *main_window() const
  {
    return windows_.empty() ? nullptr : windows_.front().get();
  }
  /** Opens an additional window sharing the GPU resources of the others. */
  Window *open_window(const WindowOptions &options, std::string &r_error);
  /** Destroys the window now (do not call from inside that window's own event handler; use
   * Window::request_close there). */
  void close_window(Window *window);
  const std::vector<std::unique_ptr<Window>> &windows() const
  {
    return windows_;
  }

  float user_scale() const
  {
    return user_scale_;
  }
  /** Changes the user scale of all windows (emits DpiChange and redraws). */
  void set_user_scale(float scale);

  /** Runs the event loop until #quit (or the last window closed); returns the exit code. */
  int run();
  /**
   * One loop iteration: waits for events when `wait` and nothing needs a redraw, dispatches
   * them, closes windows that asked for it and redraws tagged windows. False once quitting.
   */
  bool process(bool wait);
  void quit(int exit_code = 0);
  bool quitting() const
  {
    return quit_;
  }

  std::string clipboard_text(bool selection = false) const;
  void set_clipboard_text(std::string_view text, bool selection = false);
  bool has_clipboard_image() const;
  bool clipboard_image(gfx::Image &r_image) const;
  bool set_clipboard_image(const gfx::Image &image);

  /** Whether the platform backend supports inline IME / clipboard images. */
  bool supports_ime() const;
  bool supports_clipboard_image() const;

  uint64_t time_ms() const;

  using TimerFn = std::function<void()>;
  /**
   * Calls `fn` after `delay_ms`, then every `interval_ms` (0 = once), on the main thread during
   * event processing. Returns an id for #remove_timer (0 on failure). Safe to call from a timer.
   */
  uint64_t add_timer(uint64_t delay_ms, uint64_t interval_ms, TimerFn fn);
  void remove_timer(uint64_t id);

  /** Called for events that have no window (e.g. Cmd+Q). Default: quit. */
  std::function<void(const Event &)> on_quit_request;

  GHOST_ISystem &ghost_system() const
  {
    return *system_;
  }

 private:
  friend class Window;
  friend class EventConsumer;
  struct Timer;
  WindowManager() = default;
  std::unique_ptr<Window> create_window(const WindowOptions &options,
                                        const GHOST_GPUSettings &settings,
                                        std::string &r_error);
  Window *add_window(std::unique_ptr<Window> window);
  void handle_ghost_event(const void *ghost_event);
  void deliver(Window &window, const Event &event);
  void close_pending();
  void draw_dirty();
  void purge_timers();
  static void timer_proc(GHOST_ITimerTask *task, uint64_t time);

  GHOST_ISystem *system_ = nullptr;
  void *consumer_ = nullptr;
  std::unique_ptr<gfx::Gpu> gpu_;
  std::vector<std::unique_ptr<Window>> windows_;
  std::vector<std::unique_ptr<Timer>> timers_;
  uint64_t next_timer_id_ = 1;
  float user_scale_ = 1.0f;
  bool quit_on_last_ = true;
  /** GHOST's blocking wait honors timers (all backends except Wayland). */
  bool blocking_wait_ = true;
  bool quit_ = false;
  int exit_code_ = 0;
};

}  // namespace stk::wm

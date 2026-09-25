/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/wm/window.hh"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>

#include "MEM_guardedalloc.h"

#include "GHOST_IEvent.hh"
#include "GHOST_IEventConsumer.hh"
#include "GHOST_ISystem.hh"
#include "GHOST_ITimerTask.hh"
#include "GHOST_IWindow.hh"
#include "GHOST_Rect.hh"

#include "GPU_context.hh"
#include "GPU_framebuffer.hh"
#include "GPU_state.hh"

#include "stk/gfx/fonts.hh"
#include "stk/gfx/offscreen.hh"

namespace stk::wm {

using namespace blender;

/* Key values mirror GHOST_TKey. */
static_assert(int(Key::BackSpace) == GHOST_kKeyBackSpace);
static_assert(int(Key::Enter) == GHOST_kKeyEnter);
static_assert(int(Key::Z) == GHOST_kKeyZ);
static_assert(int(Key::LeftShift) == GHOST_kKeyLeftShift);
static_assert(int(Key::RightHyper) == GHOST_kKeyRightHyper);
static_assert(int(Key::App) == GHOST_kKeyApp);
static_assert(int(Key::PageDown) == GHOST_kKeyDownPage);
static_assert(int(Key::NumpadSlash) == GHOST_kKeyNumpadSlash);
static_assert(int(Key::F24) == GHOST_kKeyF24);
static_assert(int(Key::MediaLast) == GHOST_kKeyMediaLast);

const char *event_type_name(const EventType type)
{
  switch (type) {
    case EventType::None: return "None";
    case EventType::Resize: return "Resize";
    case EventType::Expose: return "Expose";
    case EventType::DpiChange: return "DpiChange";
    case EventType::Close: return "Close";
    case EventType::FocusIn: return "FocusIn";
    case EventType::FocusOut: return "FocusOut";
    case EventType::KeyDown: return "KeyDown";
    case EventType::KeyUp: return "KeyUp";
    case EventType::MouseMove: return "MouseMove";
    case EventType::MouseDown: return "MouseDown";
    case EventType::MouseUp: return "MouseUp";
    case EventType::Wheel: return "Wheel";
    case EventType::Magnify: return "Magnify";
    case EventType::ImeStart: return "ImeStart";
    case EventType::ImeUpdate: return "ImeUpdate";
    case EventType::ImeEnd: return "ImeEnd";
    case EventType::DragEnter: return "DragEnter";
    case EventType::DragOver: return "DragOver";
    case EventType::DragLeave: return "DragLeave";
    case EventType::Drop: return "Drop";
  }
  return "?";
}

static GHOST_TStandardCursor to_ghost_cursor(const Cursor cursor)
{
  switch (cursor) {
    case Cursor::Default: return GHOST_kStandardCursorDefault;
    case Cursor::Text: return GHOST_kStandardCursorText;
    case Cursor::Wait: return GHOST_kStandardCursorWait;
    case Cursor::Help: return GHOST_kStandardCursorHelp;
    case Cursor::Crosshair: return GHOST_kStandardCursorCrosshair;
    case Cursor::Move: return GHOST_kStandardCursorMove;
    case Cursor::HandPoint: return GHOST_kStandardCursorHandPoint;
    case Cursor::HandOpen: return GHOST_kStandardCursorHandOpen;
    case Cursor::HandClosed: return GHOST_kStandardCursorHandClosed;
    case Cursor::ResizeLeftRight: return GHOST_kStandardCursorLeftRight;
    case Cursor::ResizeUpDown: return GHOST_kStandardCursorUpDown;
    case Cursor::Stop: return GHOST_kStandardCursorStop;
    case Cursor::Copy: return GHOST_kStandardCursorCopy;
    case Cursor::ZoomIn: return GHOST_kStandardCursorZoomIn;
    case Cursor::ZoomOut: return GHOST_kStandardCursorZoomOut;
    case Cursor::Eyedropper: return GHOST_kStandardCursorEyedropper;
  }
  return GHOST_kStandardCursorDefault;
}

/* -------------------------------------------------------------------- */
/** \name GHOST event consumer + timers
 * \{ */

class EventConsumer : public GHOST_IEventConsumer {
 public:
  explicit EventConsumer(WindowManager *wm) : wm_(wm) {}
  bool processEvent(const GHOST_IEvent *event) override
  {
    wm_->handle_ghost_event(event);
    return true;
  }

 private:
  WindowManager *wm_;
};

struct WindowManager::Timer {
  uint64_t id = 0;
  GHOST_ITimerTask *task = nullptr;
  TimerFn fn;
  bool one_shot = false;
  /** Removed or fired (one-shot): GHOST may be iterating its timer list, so the task is
   * removed after event processing (see #purge_timers). */
  bool dead = false;
};

void WindowManager::timer_proc(GHOST_ITimerTask *task, uint64_t /*time*/)
{
  auto *timer = static_cast<Timer *>(task->getUserData());
  if (!timer || timer->dead || !timer->fn) {
    return;
  }
  if (timer->one_shot) {
    timer->dead = true;
  }
  /* Copy: the callback may remove its own timer. */
  const TimerFn fn = timer->fn;
  fn();
}

void WindowManager::purge_timers()
{
  for (size_t i = 0; i < timers_.size();) {
    if (timers_[i]->dead) {
      system_->removeTimer(timers_[i]->task);
      timers_.erase(timers_.begin() + i);
    }
    else {
      i++;
    }
  }
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name Window
 * \{ */

Window::~Window() = default;

float Window::ui_scale() const
{
  return dpi_factor_ * wm_->user_scale();
}

void Window::set_title(const std::string &title)
{
  ghost_->setTitle(title.c_str());
}

void Window::set_client_size(const int width, const int height)
{
  ghost_->setClientSize(uint32_t(std::max(1, width)), uint32_t(std::max(1, height)));
}

void Window::request_redraw()
{
  screen_.tag_redraw();
}

bool Window::needs_redraw() const
{
  return screen_.needs_redraw();
}

void Window::set_cursor(const Cursor cursor)
{
  if (cursor != cursor_) {
    cursor_ = cursor;
    ghost_->setCursorShape(to_ghost_cursor(cursor));
  }
}

void Window::set_cursor_visible(const bool visible)
{
  ghost_->setCursorVisibility(visible);
}

void Window::ime_begin(const Rect &caret, const bool completed)
{
  if (!wm_->supports_ime()) {
    return;
  }
  /* Same conversion as Blender's wm_window_IME_begin: native OS window coordinates, top-left. */
  const float fac = native_pixel_size_;
  const int x = int(caret.xmin / fac);
  const int y = int(caret.ymin / fac);
  ghost_->beginIME(x, client_h_ - y, int(caret.width() / fac), int(caret.height() / fac), completed);
  ime_active_ = true;
}

void Window::ime_end()
{
  if (ime_active_ && wm_->supports_ime()) {
    ghost_->endIME();
  }
  ime_active_ = false;
}

bool Window::read_pixels(gfx::Image &r_image, std::string &r_error)
{
  make_current();
  const Rect full{0, 0, width_, height_};
  const DrawContext ctx = draw_context(full);
  screen_.layout(full, ctx);
  const bool ok = gfx::render_offscreen(
      width_, height_, [&] { screen_.draw(ctx); }, r_image, r_error);
  return ok;
}

void Window::request_close()
{
  Event e;
  e.type = EventType::Close;
  e.window = this;
  e.time_ms = wm_->time_ms();
  wm_->deliver(*this, e);
}

void Window::update_geometry()
{
  GHOST_Rect r;
  ghost_->getClientBounds(r);
  client_w_ = std::max(1, int(r.getWidth()));
  client_h_ = std::max(1, int(r.getHeight()));
  native_pixel_size_ = ghost_->getNativePixelSize();
  if (!(native_pixel_size_ > 0.0f)) {
    native_pixel_size_ = 1.0f;
  }
  width_ = std::max(1, int(float(client_w_) * native_pixel_size_));
  height_ = std::max(1, int(float(client_h_) * native_pixel_size_));
}

bool Window::update_dpi()
{
  /* WM_window_dpi_set_userdef: DPI below 96 is clamped, the native pixel size is folded in. */
  const float dpi = float(std::max<uint16_t>(96, ghost_->getDPIHint()));
  const float factor = dpi / 96.0f * native_pixel_size_;
  if (std::fabs(factor - dpi_factor_) > 1e-4f) {
    dpi_factor_ = factor;
    return true;
  }
  return false;
}

DrawContext Window::draw_context(const Rect &rect)
{
  DrawContext ctx;
  ctx.window = this;
  ctx.ui_scale = ui_scale();
  ctx.fonts = &wm_->gpu().fonts();
  ctx.rect = rect;
  return ctx;
}

void Window::to_window_px(const int32_t client_x, const int32_t client_y, int &r_x, int &r_y) const
{
  /* wm_cursor_position_from_ghost_client_coords: flip to bottom-left, then to native pixels. */
  r_x = int(float(client_x) * native_pixel_size_);
  r_y = int(float((client_h_ - 1) - client_y) * native_pixel_size_);
}

void Window::screen_to_window_px(const int32_t screen_x, const int32_t screen_y, int &r_x, int &r_y) const
{
  int32_t cx = 0, cy = 0;
  ghost_->screenToClient(screen_x, screen_y, cx, cy);
  to_window_px(cx, cy, r_x, r_y);
}

void Window::make_current()
{
  ghost_->activateDrawingContext();
  GPU_context_active_set(gpu_context_);
  gfx::set_ui_scale(ui_scale());
}

void Window::draw()
{
  make_current();
  const DrawContext ctx = draw_context({0, 0, width_, height_});
  screen_.layout({0, 0, width_, height_}, ctx);

  ghost_->swapBufferAcquire();
  GPU_context_begin_frame(gpu_context_);
  GPU_backbuffer_bind(GPU_BACKBUFFER_LEFT);
  GPU_viewport(0, 0, width_, height_);
  GPU_scissor(0, 0, width_, height_);
  screen_.clear_redraw();
  screen_.draw(ctx);
  GPU_context_end_frame(gpu_context_);
  ghost_->swapBufferRelease();
  frames_drawn_++;
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name WindowManager
 * \{ */

std::unique_ptr<WindowManager> WindowManager::create(const WmOptions &options, std::string &r_error)
{
  if (GHOST_ISystem::getSystem()) {
    r_error = "a GHOST system already exists";
    return nullptr;
  }
  GHOST_ISystem::setUseWindowFrame(true);
  if (GHOST_ISystem::createSystem() != GHOST_kSuccess || !GHOST_ISystem::getSystem()) {
    r_error = "no display available (GHOST could not connect to Wayland, X11, Cocoa or Win32)";
    GHOST_ISystem::disposeSystem();
    return nullptr;
  }
  std::unique_ptr<WindowManager> wm(new WindowManager());
  wm->system_ = GHOST_ISystem::getSystem();
  wm->user_scale_ = options.user_scale > 0.0f ? options.user_scale : 1.0f;
  wm->quit_on_last_ = options.quit_on_last_window_closed;
  /* Framebuffers at full native resolution on HiDPI (Retina, Wayland scale > 1). */
  wm->system_->useNativePixel();
  const char *backend_id = GHOST_ISystem::getSystemBackend();
  wm->blocking_wait_ = !(backend_id && strcmp(backend_id, "WAYLAND") == 0);

  auto *consumer = new EventConsumer(wm.get());
  wm->consumer_ = consumer;
  wm->system_->addEventConsumer(consumer);

  /* The main window is created before the GPU module's offscreen context (see
   * gfx::Gpu::FirstContextFn), once per backend candidate until one works. */
  std::unique_ptr<Window> main_window;
  std::string window_error;
  WindowManager *self = wm.get();
  wm->gpu_ = gfx::Gpu::create(
      *wm->system_, options.gpu, r_error, [&](gfx::Backend, const GHOST_GPUSettings &settings) {
        main_window = self->create_window(options.window, settings, window_error);
        return main_window != nullptr;
      });
  if (!wm->gpu_) {
    if (!window_error.empty()) {
      r_error += " (" + window_error + ")";
    }
    if (main_window) {
      wm->windows_.push_back(std::move(main_window)); /* Destroyed by ~WindowManager. */
    }
    return nullptr;
  }
  wm->add_window(std::move(main_window));
  return wm;
}

WindowManager::~WindowManager()
{
  while (!windows_.empty()) {
    close_window(windows_.back().get());
  }
  for (auto &t : timers_) {
    system_->removeTimer(t->task);
  }
  timers_.clear();
  gpu_.reset();
  if (system_) {
    auto *consumer = static_cast<EventConsumer *>(consumer_);
    if (consumer) {
      system_->removeEventConsumer(consumer);
      delete consumer;
    }
    GHOST_ISystem::disposeSystem();
  }
}

const char *WindowManager::system_backend() const
{
  const char *id = GHOST_ISystem::getSystemBackend();
  if (id) {
    return id;
  }
#if defined(__APPLE__)
  return "COCOA";
#elif defined(_WIN32)
  return "WIN32";
#else
  return "UNKNOWN";
#endif
}

std::unique_ptr<Window> WindowManager::create_window(const WindowOptions &options,
                                                     const GHOST_GPUSettings &settings,
                                                     std::string &r_error)
{
  GHOST_IWindow *ghost = system_->createWindow(options.title.c_str(),
                                               0,
                                               0,
                                               uint32_t(std::max(1, options.width)),
                                               uint32_t(std::max(1, options.height)),
                                               options.maximized ? GHOST_kWindowStateMaximized :
                                                                   GHOST_kWindowStateNormal,
                                               settings,
                                               false,
                                               false,
                                               nullptr);
  if (!ghost) {
    r_error = "GHOST could not create a window with a GPU context";
    return nullptr;
  }
  std::unique_ptr<Window> win(new Window());
  win->wm_ = this;
  win->ghost_ = ghost;
  ghost->setUserData(win.get());
  win->gpu_context_ = GPU_context_create(ghost, nullptr);
  return win;
}

Window *WindowManager::add_window(std::unique_ptr<Window> win)
{
  Window *w = win.get();
  w->update_geometry();
  w->update_dpi();

  /* Clear both buffers to the theme background before the first real draw (as Blender does,
   * avoids flicker on some drivers). */
  w->make_current();
  GPU_render_begin();
  w->ghost_->swapBufferAcquire();
  GPU_clear_color(w->screen_.background[0], w->screen_.background[1], w->screen_.background[2], 1.0f);
  w->ghost_->swapBufferRelease();
  GPU_clear_color(w->screen_.background[0], w->screen_.background[1], w->screen_.background[2], 1.0f);
  GPU_render_end();

  windows_.push_back(std::move(win));
  w->request_redraw();
  return w;
}

Window *WindowManager::open_window(const WindowOptions &options, std::string &r_error)
{
  std::unique_ptr<Window> win = create_window(options, gpu_->window_settings(), r_error);
  if (!win) {
    r_error += std::string(" (") + gpu_->backend_name() + ")";
    gpu_->activate_main();
    return nullptr;
  }
  return add_window(std::move(win));
}

void WindowManager::close_window(Window *window)
{
  auto it = std::find_if(
      windows_.begin(), windows_.end(), [&](const auto &w) { return w.get() == window; });
  if (it == windows_.end()) {
    return;
  }
  std::unique_ptr<Window> owned = std::move(*it);
  windows_.erase(it);
  owned->ime_end();
  owned->ghost_->activateDrawingContext();
  GPU_context_active_set(owned->gpu_context_);
  GPU_context_discard(owned->gpu_context_);
  owned->gpu_context_ = nullptr;
  owned->ghost_->setUserData(nullptr);
  system_->disposeWindow(owned->ghost_);
  owned->ghost_ = nullptr;
  if (gpu_) {
    gpu_->activate_main();
  }
  if (windows_.empty() && quit_on_last_) {
    quit(exit_code_);
  }
}

void WindowManager::set_user_scale(const float scale)
{
  const float s = (scale > 0.0f && std::isfinite(scale)) ? std::clamp(scale, 0.25f, 4.0f) : 1.0f;
  if (s == user_scale_) {
    return;
  }
  user_scale_ = s;
  gfx::fonts_dpi_changed();
  for (auto &w : windows_) {
    Event e;
    e.type = EventType::DpiChange;
    e.window = w.get();
    e.time_ms = time_ms();
    e.width = w->width_;
    e.height = w->height_;
    e.ui_scale = w->ui_scale();
    deliver(*w, e);
    w->request_redraw();
  }
}

int WindowManager::run()
{
  while (process(true)) {
  }
  return exit_code_;
}

bool WindowManager::process(const bool wait)
{
  if (quit_) {
    return false;
  }
  bool dirty = false;
  for (auto &w : windows_) {
    dirty |= w->needs_redraw() || w->close_pending_;
  }
  if (wait && !dirty && blocking_wait_) {
    /* X11, Win32 and Cocoa sleep in the OS until an event arrives or the next timer is due. */
    system_->processEvents(true);
  }
  else {
    const bool any = system_->processEvents(false);
    if (wait && !dirty && !any) {
      /* GHOST's Wayland wait ignores timers: poll like Blender's WM (5 ms sleep when idle). */
      std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
  }
  system_->dispatchEvents();
  purge_timers();
  close_pending();
  if (!quit_) {
    draw_dirty();
  }
  return !quit_;
}

void WindowManager::quit(const int exit_code)
{
  exit_code_ = exit_code;
  quit_ = true;
}

void WindowManager::close_pending()
{
  for (size_t i = 0; i < windows_.size();) {
    if (windows_[i]->close_pending_) {
      close_window(windows_[i].get());
    }
    else {
      i++;
    }
  }
}

void WindowManager::draw_dirty()
{
  bool any = false;
  for (auto &w : windows_) {
    any |= w->needs_redraw();
  }
  if (!any) {
    return;
  }
  GPU_context_main_lock();
  GPU_render_begin();
  GPU_render_step();
  for (auto &w : windows_) {
    if (!w->needs_redraw()) {
      continue;
    }
#if defined(_WIN32)
    /* Skip minimized windows (Blender: driver issues and wasted work). */
    if (w->ghost_->getState() == GHOST_kWindowStateMinimized) {
      continue;
    }
#endif
    w->draw();
  }
  GPU_render_end();
  GPU_context_main_unlock();
}

void WindowManager::deliver(Window &window, const Event &event)
{
  if (window.on_event && window.on_event(event)) {
    return;
  }
  const DrawContext ctx = window.draw_context();
  if (window.screen_.dispatch(event, ctx)) {
    return;
  }
  if (event.type == EventType::Close) {
    window.close_pending_ = true;
  }
}

static uint32_t query_modifiers(const GHOST_ISystem &system)
{
  uint32_t mods = ModNone;
  auto down = [&](GHOST_TModifierKey k) {
    bool is_down = false;
    return system.getModifierKeyState(k, is_down) == GHOST_kSuccess && is_down;
  };
  if (down(GHOST_kModifierKeyLeftShift) || down(GHOST_kModifierKeyRightShift)) {
    mods |= ModShift;
  }
  if (down(GHOST_kModifierKeyLeftControl) || down(GHOST_kModifierKeyRightControl)) {
    mods |= ModCtrl;
  }
  if (down(GHOST_kModifierKeyLeftAlt) || down(GHOST_kModifierKeyRightAlt)) {
    mods |= ModAlt;
  }
  if (down(GHOST_kModifierKeyLeftOS) || down(GHOST_kModifierKeyRightOS)) {
    mods |= ModOS;
  }
  if (down(GHOST_kModifierKeyLeftHyper) || down(GHOST_kModifierKeyRightHyper)) {
    mods |= ModHyper;
  }
  return mods;
}

static void copy_ime(const void *data, ImeData &r_ime)
{
  if (!data) {
    return;
  }
  const auto *ime = static_cast<const GHOST_TEventImeData *>(data);
  r_ime.result = ime->result;
  r_ime.composite = ime->composite;
  r_ime.cursor = ime->cursor_position;
  r_ime.target_start = ime->target_start;
  r_ime.target_end = ime->target_end;
}

void WindowManager::handle_ghost_event(const void *ghost_event_ptr)
{
  const auto *ghost_event = static_cast<const GHOST_IEvent *>(ghost_event_ptr);
  const GHOST_TEventType type = ghost_event->getType();
  const GHOST_TEventDataPtr data = ghost_event->getData();

  Event e;
  e.time_ms = ghost_event->getTime();
  e.modifiers = query_modifiers(*system_);

  if (type == GHOST_kEventQuitRequest) {
    if (on_quit_request) {
      on_quit_request(e);
    }
    else {
      for (auto &w : windows_) {
        w->request_close();
      }
      if (windows_.empty()) {
        quit(exit_code_);
      }
    }
    return;
  }

  GHOST_IWindow *ghost_window = ghost_event->getWindow();
  if (!ghost_window || !system_->validWindow(ghost_window)) {
    return;
  }
  Window *win = static_cast<Window *>(ghost_window->getUserData());
  if (!win || win->close_pending_) {
    return;
  }
  e.window = win;
  e.x = win->last_x_;
  e.y = win->last_y_;

  switch (type) {
    case GHOST_kEventWindowSize:
    case GHOST_kEventWindowMove: {
      const int old_w = win->width_, old_h = win->height_;
      win->update_geometry();
      const bool dpi_changed = win->update_dpi();
      if (dpi_changed) {
        gfx::fonts_dpi_changed();
        Event d = e;
        d.type = EventType::DpiChange;
        d.width = win->width_;
        d.height = win->height_;
        d.ui_scale = win->ui_scale();
        deliver(*win, d);
      }
      if (win->width_ != old_w || win->height_ != old_h) {
        e.type = EventType::Resize;
        e.width = win->width_;
        e.height = win->height_;
        e.ui_scale = win->ui_scale();
        deliver(*win, e);
      }
      if (dpi_changed || win->width_ != old_w || win->height_ != old_h) {
        win->request_redraw();
#if defined(__APPLE__) || defined(_WIN32)
        /* Cocoa and Win32 do not return to the main loop during a live resize. */
        draw_dirty();
#endif
      }
      return;
    }
    case GHOST_kEventWindowDPIHintChanged:
    case GHOST_kEventNativeResolutionChange: {
      win->update_geometry();
      if (win->update_dpi()) {
        gfx::fonts_dpi_changed();
        e.type = EventType::DpiChange;
        e.width = win->width_;
        e.height = win->height_;
        e.ui_scale = win->ui_scale();
        deliver(*win, e);
      }
      win->request_redraw();
      return;
    }
    case GHOST_kEventWindowUpdate:
    case GHOST_kEventWindowUpdateDecor:
      e.type = EventType::Expose;
      win->request_redraw();
      break;
    case GHOST_kEventWindowClose:
      e.type = EventType::Close;
      break;
    case GHOST_kEventWindowActivate:
      e.type = EventType::FocusIn;
      break;
    case GHOST_kEventWindowDeactivate:
      e.type = EventType::FocusOut;
      break;
    case GHOST_kEventCursorMove: {
      const auto *cd = static_cast<const GHOST_TEventCursorData *>(data);
      win->screen_to_window_px(cd->x, cd->y, e.x, e.y);
      win->last_x_ = e.x;
      win->last_y_ = e.y;
      e.type = EventType::MouseMove;
      break;
    }
    case GHOST_kEventButtonDown:
    case GHOST_kEventButtonUp: {
      const auto *bd = static_cast<const GHOST_TEventButtonData *>(data);
      int32_t cx = 0, cy = 0;
      if (system_->getCursorPositionClientRelative(ghost_window, cx, cy) == GHOST_kSuccess) {
        win->to_window_px(cx, cy, e.x, e.y);
        win->last_x_ = e.x;
        win->last_y_ = e.y;
      }
      e.type = type == GHOST_kEventButtonDown ? EventType::MouseDown : EventType::MouseUp;
      e.button = MouseButton(int8_t(bd->button));
      break;
    }
    case GHOST_kEventWheel: {
      const auto *wd = static_cast<const GHOST_TEventWheelData *>(data);
      e.type = EventType::Wheel;
      if (wd->axis == GHOST_kEventWheelAxisHorizontal) {
        e.wheel_x = float(wd->value);
      }
      else {
        e.wheel_y = float(wd->value);
      }
      break;
    }
    case GHOST_kEventTrackpad: {
      const auto *td = static_cast<const GHOST_TEventTrackpadData *>(data);
      win->screen_to_window_px(td->x, td->y, e.x, e.y);
      if (td->subtype == GHOST_kTrackpadEventScroll) {
        e.type = EventType::Wheel;
        e.precise = true;
        const float sign = td->isDirectionInverted ? -1.0f : 1.0f;
        e.wheel_x = sign * float(td->deltaX) * win->native_pixel_size_;
        e.wheel_y = sign * float(td->deltaY) * win->native_pixel_size_;
      }
      else if (td->subtype == GHOST_kTrackpadEventMagnify) {
        e.type = EventType::Magnify;
        e.magnify = float(td->deltaX) / 100.0f;
      }
      else {
        return;
      }
      break;
    }
    case GHOST_kEventKeyDown:
    case GHOST_kEventKeyUp: {
      const auto *kd = static_cast<const GHOST_TEventKeyData *>(data);
      e.type = type == GHOST_kEventKeyDown ? EventType::KeyDown : EventType::KeyUp;
      e.key = Key(int32_t(kd->key));
      e.is_repeat = kd->is_repeat != 0;
      if (type == GHOST_kEventKeyDown) {
        const size_t n = strnlen(kd->utf8_buf, sizeof(kd->utf8_buf));
        /* Control characters are not text (Ctrl+C, Backspace, Enter ...). */
        if (n > 0 && uint8_t(kd->utf8_buf[0]) >= 0x20 && kd->utf8_buf[0] != 0x7f) {
          e.text.assign(kd->utf8_buf, n);
        }
      }
      break;
    }
    case GHOST_kEventImeCompositionStart:
      e.type = EventType::ImeStart;
      copy_ime(data, e.ime);
      break;
    case GHOST_kEventImeComposition:
      e.type = EventType::ImeUpdate;
      copy_ime(data, e.ime);
      break;
    case GHOST_kEventImeCompositionEnd:
      e.type = EventType::ImeEnd;
      copy_ime(data, e.ime);
      break;
    case GHOST_kEventDraggingEntered:
    case GHOST_kEventDraggingUpdated:
    case GHOST_kEventDraggingExited:
    case GHOST_kEventDraggingDropDone: {
      const auto *dd = static_cast<const GHOST_TEventDragnDropData *>(data);
      if (dd) {
        win->screen_to_window_px(dd->x, dd->y, e.x, e.y);
      }
      if (type == GHOST_kEventDraggingEntered || type == GHOST_kEventDraggingUpdated) {
        e.type = type == GHOST_kEventDraggingEntered ? EventType::DragEnter : EventType::DragOver;
        ghost_window->setAcceptDragOperation(true);
      }
      else if (type == GHOST_kEventDraggingExited) {
        e.type = EventType::DragLeave;
      }
      else {
        e.type = EventType::Drop;
        if (dd && dd->dataType == GHOST_kDragnDropTypeFilenames && dd->data) {
          const auto *sa = static_cast<const GHOST_TStringArray *>(dd->data);
          for (int i = 0; i < sa->count; i++) {
            e.paths.emplace_back(reinterpret_cast<const char *>(sa->strings[i]));
          }
        }
        else if (dd && dd->dataType == GHOST_kDragnDropTypeString && dd->data) {
          e.text = static_cast<const char *>(dd->data);
        }
      }
      break;
    }
    default:
      return;
  }
  deliver(*win, e);
}

std::string WindowManager::clipboard_text(const bool selection) const
{
  char *buf = system_->getClipboard(selection);
  if (!buf) {
    return {};
  }
  std::string s(buf);
  free(buf); /* GHOST uses regular malloc. */
  return s;
}

void WindowManager::set_clipboard_text(std::string_view text, const bool selection)
{
  const std::string s(text);
  system_->putClipboard(s.c_str(), selection);
}

bool WindowManager::has_clipboard_image() const
{
  return supports_clipboard_image() && system_->hasClipboardImage() == GHOST_kSuccess;
}

bool WindowManager::clipboard_image(gfx::Image &r_image) const
{
  if (!supports_clipboard_image()) {
    return false;
  }
  int w = 0, h = 0;
  uint *rgba = system_->getClipboardImage(&w, &h);
  if (!rgba) {
    return false;
  }
  r_image.width = w;
  r_image.height = h;
  r_image.rgba.resize(size_t(w) * h * 4);
  const size_t stride = size_t(w) * 4;
  const uint8_t *src = reinterpret_cast<const uint8_t *>(rgba);
  for (int y = 0; y < h; y++) {
    memcpy(&r_image.rgba[size_t(h - 1 - y) * stride], src + size_t(y) * stride, stride);
  }
  free(rgba);
  return true;
}

bool WindowManager::set_clipboard_image(const gfx::Image &image)
{
  if (!supports_clipboard_image() || image.empty()) {
    return false;
  }
  const size_t stride = size_t(image.width) * 4;
  std::vector<uint8_t> bottom_up(stride * image.height);
  for (int y = 0; y < image.height; y++) {
    memcpy(&bottom_up[size_t(image.height - 1 - y) * stride], image.px(0, y), stride);
  }
  return system_->putClipboardImage(
             reinterpret_cast<uint *>(bottom_up.data()), image.width, image.height) ==
         GHOST_kSuccess;
}

bool WindowManager::supports_ime() const
{
  return (system_->getCapabilities() & GHOST_kCapabilityInputIME) != 0;
}

bool WindowManager::supports_clipboard_image() const
{
  return (system_->getCapabilities() & GHOST_kCapabilityClipboardImage) != 0;
}

uint64_t WindowManager::time_ms() const
{
  return system_->getMilliSeconds();
}

uint64_t WindowManager::add_timer(const uint64_t delay_ms, const uint64_t interval_ms, TimerFn fn)
{
  auto timer = std::make_unique<Timer>();
  timer->id = next_timer_id_++;
  timer->fn = std::move(fn);
  timer->one_shot = interval_ms == 0;
  /* GHOST divides by the interval: one-shot timers get a very long one and die when fired. */
  const uint64_t interval = timer->one_shot ? (uint64_t(1) << 40) : interval_ms;
  timer->task = system_->installTimer(delay_ms, interval, &WindowManager::timer_proc, timer.get());
  if (!timer->task) {
    return 0;
  }
  const uint64_t id = timer->id;
  timers_.push_back(std::move(timer));
  return id;
}

void WindowManager::remove_timer(const uint64_t id)
{
  for (auto &t : timers_) {
    if (t->id == id) {
      t->dead = true;
      t->fn = nullptr;
    }
  }
}

/** \} */

}  // namespace stk::wm

/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/app/report_document_host.hh"
#include "stk/app/app_store.hh"
#include "stk/app/editor.hh"
#include "stk/app/editor_area.hh"
#include "stk/core/sha256.hh"
#include "stk/wm/window.hh"
#include <algorithm>
#include <cmath>
#include <utility>

namespace stk::app {
using namespace document_preview;
struct ReportDocumentHost::State : std::enable_shared_from_this<State> {
  AppStore &store;
  Factory factory;
  std::shared_ptr<ResourceSession> resources;
  std::unique_ptr<NativeDocumentView> view;
  std::string entry, error;
  NativeViewStatus status = NativeViewStatus::Closed;
  uint64_t scope_epoch = 0, parent_generation = 0, timer = 0;
  int polls = 0;
  Editor *owner = nullptr; // Compared only while owner_lifetime is live.
  std::weak_ptr<void> owner_lifetime;
  wm::Screen *screen = nullptr;
  wm::Window *window = nullptr;
  ui::Context *ui_identity = nullptr; // Compared only; access comes from the live Screen.
  ui::WidgetId viewport = 0, previous_anchor = 0, next_anchor = 0;
  bool visible_requested = false, surface_visible = false, has_media = false;
  struct FocusRequest {
    ResourceSession *session;
    Editor *owner;
    wm::Window *parent;
    uint64_t scope;
  };
  std::optional<FocusRequest> pending_focus;
  ProjectScopeSubscription scope;
  wm::Screen::LayoutObserver layout;
  ui::Context::NativeViewObserver ui_observer;

  State(AppStore &value, Factory create) : store(value), factory(std::move(create)) {}
  ~State() { disconnect(); }
  void hide() noexcept
  {
    pending_focus.reset();
    const bool was_visible = surface_visible;
    surface_visible = false;
    bool failed = false;
    try {
      if (view) {
        if (has_media && was_visible) {
          std::string pause_error;
          if (!view->pause_media(pause_error)) { failed = true; }
        }
        view->set_visible(false);
        const auto actual = view->state();
        failed = failed || actual.visible || actual.focused;
      }
    }
    catch (...) { failed = true; }
    if (failed) {
      // Do not recurse through close_session()/hide() after a platform hide failure.
      if (resources) { resources->close(); }
      stop_poll();
      try { if (view) { view->set_focus_exit_handler({}); view->close(); } } catch (...) {}
      view.reset(); resources.reset(); status = NativeViewStatus::Failed;
      try { error = "Document preview could not be hidden and was closed"; } catch (...) {}
    }
  }
  void stop_poll() noexcept
  {
    if (timer && window) { window->manager().remove_timer(timer); }
    timer = 0;
  }
  void close_session() noexcept
  {
    stop_poll();
    hide();
    if (resources) { resources->close(); }
    try { if (view) { view->set_focus_exit_handler({}); view->close(); } } catch (...) {}
    view.reset(); resources.reset(); entry.clear(); error.clear(); has_media = false; status = NativeViewStatus::Closed;
  }
  void disconnect() noexcept
  {
    scope.reset(); layout.reset(); ui_observer.reset();
    close_session(); owner = nullptr; screen = nullptr; window = nullptr; ui_identity = nullptr;
  }
  void fail(std::string message, NativeViewStatus kind = NativeViewStatus::Failed)
  {
    close_session(); status = kind; error = std::move(message);
    if (screen && layout) { screen->tag_redraw(); }
  }
  void focus_anchor(NativeFocusExit direction = NativeFocusExit::Previous)
  {
    if (!layout || !screen || owner_lifetime.expired() || !visible_requested || !surface_visible ||
        scope_epoch != store.project_scope_epoch()) { return; }
    if (auto *ui = screen->ui(); ui && !ui->native_view_interaction_blocked()) {
      for (auto *region : screen->visible_regions()) {
        auto *area = dynamic_cast<EditorArea *>(region->area());
        if (area && &area->editor() == owner && region->name() == EditorArea::kMain &&
            ui->focus_widget(direction == NativeFocusExit::Next ? next_anchor : previous_anchor)) {
          screen->set_focus(region);
          screen->tag_redraw(); // Native Tab callbacks do not pass through Screen::send_ui.
          break;
        }
      }
    }
  }
  void start_poll()
  {
    if (!window || timer || !view || view->state().status != NativeViewStatus::Loading) { return; }
    polls = 0;
    const std::weak_ptr<State> weak = shared_from_this();
    timer = window->manager().add_timer(100, 100, [weak] {
      auto self = weak.lock();
      if (!self || !self->window || !self->view) { return; }
      auto *window = self->window;
      if (self->view->state().status != NativeViewStatus::Loading) { self->stop_poll(); }
      else if (++self->polls >= 300) { self->fail("Document preview loading timed out"); }
      window->request_redraw();
    });
    if (!timer) { fail("Cannot schedule document preview status updates"); }
  }
  void ready(const wm::DrawContext &ctx)
  {
    // A user action can occur while Capture::Ui still hides the child. Its intent belongs
    // only to the very next completed layout, never to a later popup/tab/geometry state.
    const auto requested_focus = std::exchange(pending_focus, std::nullopt);
    if (!resources || !visible_requested || owner_lifetime.expired() || !ctx.ui || !ctx.window ||
        !screen || &ctx.window->screen() != screen || scope_epoch != store.project_scope_epoch()) {
      hide(); return;
    }
    if (ctx.ui->native_view_interaction_blocked() || screen->capture() != wm::Screen::Capture::None) { hide(); return; }
    wm::Region *main = nullptr;
    for (auto *region : screen->visible_regions()) {
      auto *area = dynamic_cast<EditorArea *>(region->area());
      if (area && &area->editor() == owner && region->name() == EditorArea::kMain) { main = region; break; }
    }
    if (!main || main->rect().empty()) { hide(); return; }
    const ui::Widget *surface = nullptr;
    for (const auto &block : ctx.ui->blocks()) {
      if (block->kind() == ui::Block::Kind::Modal || block->kind() == ui::Block::Kind::Popup) { hide(); return; }
      if (block->kind() == ui::Block::Kind::Region && block->name() == main->block_name()) {
        for (const auto &widget : block->widgets()) {
          if (widget.id == viewport && widget.type == ui::WidgetType::NativeViewport && widget.enabled) {
            surface = &widget; break;
          }
        }
      }
    }
    if (!surface || surface->rect.empty()) { hide(); return; }
    const auto original = surface->rect;
    const auto clipped = original.intersect(surface->clip).intersect(screen->to_ui(main->rect()))
        .intersect(screen->to_ui({0, 0, ctx.window->width(), ctx.window->height()}));
    // A partial native child cannot be replaced by a smaller reflowed page. Hide until fully visible.
    if (clipped.empty() || std::abs(clipped.x - original.x) > 0.5f || std::abs(clipped.y - original.y) > 0.5f ||
        std::abs(clipped.w - original.w) > 0.5f || std::abs(clipped.h - original.h) > 0.5f) { hide(); return; }
    for (const auto &block : ctx.ui->blocks()) {
      if (block->kind() != ui::Block::Kind::Region && !block->frame().intersect(clipped).empty()) { hide(); return; }
    }
    if (window && window != ctx.window) { close_session(); window = nullptr; return; }
    if (!window) {
      window = ctx.window;
      const auto parent = ++parent_generation;
      const std::weak_ptr<State> weak = shared_from_this();
      window->add_close_listener([weak, parent](wm::Window &closing) {
        if (auto self = weak.lock(); self && self->window == &closing && self->parent_generation == parent) {
          self->layout.reset(); self->ui_observer.reset(); self->close_session();
          self->screen = nullptr; self->window = nullptr; self->ui_identity = nullptr;
        }
      });
    }
    if (!view) {
      view = factory(window->native_window_handle(), resources, error);
      if (!view) { fail(error.empty() ? "Cannot create a document preview view" : error); return; }
      const auto state = view->state();
      if (state.status == NativeViewStatus::Unsupported || state.status == NativeViewStatus::Failed) {
        fail(state.message, state.status); return;
      }
      const std::weak_ptr<State> weak = shared_from_this();
      view->set_focus_exit_handler([weak](NativeFocusExit direction) { if (auto self = weak.lock()) { self->focus_anchor(direction); } });
      if (!view->navigate(entry, error)) { fail(error.empty() ? "Cannot open the prepared report" : error); return; }
      start_poll();
      if (!view) { return; }
    }
    const auto native_state = view->state();
    if (native_state.status == NativeViewStatus::Failed || native_state.status == NativeViewStatus::Closed ||
        native_state.status == NativeViewStatus::Unsupported) { fail(native_state.message, native_state.status); return; }
    const auto sr = screen->rect();
    const int x = sr.xmin + int(std::ceil(clipped.x));
    const int y = sr.ymax - int(std::floor(clipped.y + clipped.h));
    const int right = sr.xmin + int(std::floor(clipped.x + clipped.w));
    const int top = sr.ymax - int(std::ceil(clipped.y));
    if (right <= x || top <= y) { hide(); return; }
    view->set_bounds({x, y, right - x, top - y});
    view->set_visible(true);
    const auto actual = view->state();
    const bool was_visible = surface_visible;
    surface_visible = actual.parent_attached && actual.visible;
    if (surface_visible != was_visible) { window->request_redraw(); }
    if (requested_focus && surface_visible && actual.status == NativeViewStatus::Ready &&
        !ctx.ui->text_input_active() && requested_focus->session == resources.get() &&
        requested_focus->owner == owner && requested_focus->parent == window &&
        requested_focus->scope == scope_epoch) {
      window->ime_end();
      screen->set_focus(main);
      view->focus();
    }
  }
};

ReportDocumentHost::ReportDocumentHost(AppStore &store, Factory factory)
{
  if (!factory) { factory = create_native_document_view; }
  state_ = std::make_shared<State>(store, std::move(factory));
  const std::weak_ptr<State> weak = state_;
  state_->scope = store.observe_project_scope([weak] {
    if (auto state = weak.lock()) { state->close_session(); }
  });
}
ReportDocumentHost::~ReportDocumentHost() { state_->disconnect(); }
std::function<void()> ReportDocumentHost::invalidator() const
{
  const std::weak_ptr<State> weak = state_;
  return [weak] { if (auto state = weak.lock()) { state->close_session(); } };
}
bool ReportDocumentHost::adopt(PreparedReportPreview preview)
{
  auto &state = *state_;
  state.close_session();
  const bool pdf = !preview.assets.empty() && preview.assets.front().mime == "application/pdf";
  if (preview.project_scope_epoch != state.store.project_scope_epoch() || preview.assets.empty() ||
      preview.assets.front().path != preview.entry_path ||
      (pdf ? preview.assets.size() != 1 : preview.assets.front().mime != "text/html; charset=utf-8") ||
      !core::is_sha256_hex(preview.identity.source_sha256)) {
    state.fail("Prepared report scope or entry is no longer valid"); return false;
  }
  std::vector<ResourceAsset> assets;
  assets.reserve(preview.assets.size());
  bool has_media = false;
  for (size_t i = 0; i < preview.assets.size(); ++i) {
    auto &asset = preview.assets[i];
    if (i && asset.mime != "image/png" && asset.mime != "image/jpeg" &&
        asset.mime != "image/gif" && asset.mime != "image/webp" && asset.mime != "video/mp4") {
      state.fail("Prepared report contains an unsupported secondary resource"); return false;
    }
    has_media = has_media || asset.mime == "video/mp4";
    assets.push_back({std::move(asset.path), std::move(asset.mime), std::move(asset.bytes)});
  }
  auto &id = preview.identity;
  state.resources = ResourceSession::create({std::move(id.project_id), std::move(id.report_id),
      std::move(id.source_sha256), std::move(id.session_id)}, std::move(assets), state.error);
  if (!state.resources) { state.status = NativeViewStatus::Failed; return false; }
  state.has_media = has_media;
  state.scope_epoch = preview.project_scope_epoch; state.entry = std::move(preview.entry_path);
  state.status = NativeViewStatus::Loading;
  if (state.screen && state.layout) { state.screen->tag_redraw(); }
  return true;
}
void ReportDocumentHost::clear() { state_->close_session(); }
void ReportDocumentHost::bind(Editor &owner, EditorContext &ctx)
{
  auto &s = *state_;
  if (s.owner && s.owner != &owner) { s.close_session(); }
  auto *screen = ctx.area.screen();
  if (s.screen != screen || (s.screen && !s.layout)) {
    s.layout.reset(); s.ui_observer.reset(); s.ui_identity = nullptr;
    if (s.screen) { s.close_session(); s.window = nullptr; }
    s.screen = screen;
    if (screen) {
      const std::weak_ptr<State> weak = state_;
      s.layout = screen->observe_layout([weak, screen](const wm::DrawContext &draw) {
        if (auto state = weak.lock(); state && state->screen == screen) {
          try { state->ready(draw); }
          catch (const std::exception &error) { state->fail(error.what()); }
          catch (...) { state->fail("Document preview layout synchronization failed"); }
        }
      }, [weak] { if (auto state = weak.lock()) { state->hide(); } });
    }
  }
  s.owner = &owner; s.owner_lifetime = owner.lifetime();
  if (ctx.ui && (s.ui_identity != ctx.ui || !s.ui_observer)) {
    s.ui_observer.reset(); s.ui_identity = ctx.ui;
    const std::weak_ptr<State> weak = state_;
    s.ui_observer = ctx.ui->observe_native_view_invalidated([weak] {
      if (auto state = weak.lock()) { state->hide(); }
    });
  }
}
void ReportDocumentHost::set_viewport(ui::WidgetId viewport, ui::WidgetId previous_anchor, ui::WidgetId next_anchor)
{
  state_->viewport = viewport; state_->previous_anchor = previous_anchor; state_->next_anchor = next_anchor;
}
void ReportDocumentHost::set_visible(bool visible)
{
  state_->visible_requested = visible;
  if (!visible) { state_->hide(); }
}
void ReportDocumentHost::focus()
{
  if (!state_->view || !state_->visible_requested || !state_->layout || !state_->screen ||
      !state_->resources || !state_->resources->active() || state_->owner_lifetime.expired() ||
      !state_->window || state_->scope_epoch != state_->store.project_scope_epoch() ||
      !state_->screen->ui() || state_->screen->ui()->native_view_interaction_blocked() ||
      state_->screen->ui()->text_input_active()) { return; }
  const auto actual = state_->view->state();
  if (actual.parent_attached && actual.status == NativeViewStatus::Ready) {
    state_->pending_focus = State::FocusRequest{state_->resources.get(), state_->owner,
        state_->window, state_->scope_epoch};
    state_->screen->tag_redraw();
  }
}
void ReportDocumentHost::return_focus()
{
  if (state_->view && state_->view->return_focus()) { state_->focus_anchor(); }
}
bool ReportDocumentHost::pause_media()
{
  auto &state = *state_;
  if (!state.has_media || !state.view || !state.resources || !state.resources->active() ||
      state.scope_epoch != state.store.project_scope_epoch()) { return false; }
  try {
    std::string error;
    if (!state.view->pause_media(error)) {
      state.fail(error.empty() ? "Video playback could not be paused and was closed" : error);
      return false;
    }
    if (state.screen && state.layout) { state.screen->tag_redraw(); }
    return true;
  }
  catch (const std::exception &error) { state.fail(error.what()); }
  catch (...) { state.fail("Video playback could not be paused and was closed"); }
  return false;
}
bool ReportDocumentHost::has_media() const { return state_->has_media && has_content(); }
NativeViewState ReportDocumentHost::state() const
{
  if (state_->view) { return state_->view->state(); }
  NativeViewState result; result.status = state_->status; result.message = state_->error; return result;
}
bool ReportDocumentHost::has_content() const { return state_->resources && state_->resources->active(); }
std::shared_ptr<const ResourceSession> ReportDocumentHost::session() const { return state_->resources; }
}  // namespace stk::app

/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/app/editor.hh"

#include "stk/app/app_store.hh"
#include "stk/app/editor_area.hh"

namespace stk::app {

std::string_view EditorContext::tr(std::string_view key) const
{
  return store.tr(key);
}

void EditorContext::defer(std::function<void()> fn) const
{
  if (wm::Screen *s = area.screen()) {
    s->defer(std::move(fn));
  }
  else if (fn) {
    fn();
  }
}

ui::Color Editor::main_background(const ui::Theme &theme) const
{
  return theme.region_back;
}

void EditorRegistry::add(EditorType type)
{
  for (auto &t : types_) {
    if (t->id == type.id) {
      *t = std::move(type);
      return;
    }
  }
  types_.push_back(std::make_unique<EditorType>(std::move(type)));
}

const EditorType *EditorRegistry::find(std::string_view id) const
{
  for (const auto &t : types_) {
    if (t->id == id) {
      return t.get();
    }
  }
  return nullptr;
}

int EditorRegistry::index_of(std::string_view id) const
{
  for (size_t i = 0; i < types_.size(); i++) {
    if (types_[i]->id == id) {
      return int(i);
    }
  }
  return -1;
}

std::unique_ptr<Editor> EditorRegistry::create(std::string_view id) const
{
  const EditorType *t = find(id);
  if (!t || !t->create) {
    return nullptr;
  }
  return t->create(*t);
}

}  // namespace stk::app

/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "../bridge/support.hh"
#include "../wm/support.hh"

#include <algorithm>
#include <stdexcept>

namespace stk::app {
namespace {
using io::Json;
using bridge::ErrorCode;

class FocusNavigation : public ::testing::Test {
 protected:
  wmtest::AppFixture f{"en", 1, 1280, 1000};

  void fill(EditorArea &area)
  {
    while (area.tab_count() < 16) { ASSERT_TRUE(area.add_tab(kEditorLogs, false)); }
  }

  ui::MenuEntry action(const std::string &key)
  {
    const auto *view = f.screen.ui()->find("view");
    EXPECT_NE(view, nullptr);
    if (!view) { return {}; }
    const auto label = f.shell->store().tr(key);
    const auto found = std::find_if(view->menu.begin(), view->menu.end(),
        [&](const auto &item) { return item.text == label; });
    EXPECT_NE(found, view->menu.end());
    return found == view->menu.end() ? ui::MenuEntry{} : *found;
  }

  void edit_python()
  {
    auto &area = f.area("a2");
    ASSERT_TRUE(area.set_tab_type(0, kEditorPython));
    f.screen.set_maximized(&area);
    f.drv->frame();
    const auto [x, y] = f.widget_center("a2/main/python_source");
    f.drv->click(x, y);
#ifdef __APPLE__
    constexpr auto primary = wm::ModOS;
#else
    constexpr auto primary = wm::ModCtrl;
#endif
    f.drv->key(wm::Key::A, primary);
    f.drv->key(wm::Key::Unknown, wm::ModNone, "uncommitted Python input");
    ASSERT_TRUE(f.screen.ui()->text_input_active());
    ASSERT_EQ(f.screen.ui()->edit_state()->text(), "uncommitted Python input");
  }
};

TEST_F(FocusNavigation, SwitchingKeepsLiveEditorsCustomSplitsAndPythonSource)
{
  auto &preparation = f.area("a1"), &analysis = f.area("a2"), &python = f.area("a4");
  ASSERT_TRUE(preparation.add_tab(kEditorAI));
  ASSERT_TRUE(python.add_tab(kEditorPython));
  ASSERT_TRUE(python.editor().load_state({{"source", "unsaved = '保留输入'"}, {"path", "/tmp/local.py"}}));
  preparation.set_weight(0.31f);
  analysis.set_weight(0.46f);
  analysis.set_sidebar_open(false);
  analysis.set_toolbar_open(false);
  f.drv->frame();
  const auto layout = f.screen.to_json();
  const auto source = python.editor().save_state();
  std::vector<Editor *> editors;
  for (auto *area : f.screen.areas()) {
    auto &editor = *dynamic_cast<EditorArea *>(area);
    for (int i = 0; i < editor.tab_count(); ++i) { editors.push_back(&editor.tab(i)); }
  }
  auto first = f.shell->activate_editor(&f.screen, kEditorAI, true);
  ASSERT_TRUE(first.ok());
  EXPECT_EQ(first.value(), (Json{{"area_id", "a1"}, {"editor_id", "ai"}, {"tab_index", 1}, {"maximized", true}}));
  EXPECT_EQ(f.screen.maximized(), &preparation);
  for (int i = 0; i < 3; ++i) {
    ASSERT_TRUE(f.shell->activate_editor(&f.screen, kEditorViewer, true).ok());
    EXPECT_EQ(f.screen.maximized(), &analysis);
    ASSERT_TRUE(f.shell->activate_editor(&f.screen, kEditorAI, true).ok());
  }
  auto restored = f.shell->restore_split_layout(&f.screen);
  ASSERT_TRUE(restored.ok()); EXPECT_EQ(restored.value(), (Json{{"restored", true}}));
  EXPECT_EQ(f.screen.maximized(), nullptr);
  EXPECT_EQ(f.screen.to_json(), layout);
  EXPECT_EQ(python.editor().save_state(), source);
  size_t index = 0;
  for (auto *area : f.screen.areas()) {
    auto &editor = *dynamic_cast<EditorArea *>(area);
    for (int i = 0; i < editor.tab_count(); ++i) { EXPECT_EQ(&editor.tab(i), editors[index++]); }
  }
  EXPECT_EQ(index, editors.size());
  restored = f.shell->restore_split_layout(&f.screen);
  ASSERT_TRUE(restored.ok()); EXPECT_EQ(restored.value(), (Json{{"restored", false}}));
}

TEST_F(FocusNavigation, PrefersMaximizedActiveThenOtherActiveThenAnExistingHiddenTab)
{
  auto &first = f.area("a1"), &second = f.area("a2"), &third = f.area("a3");
  ASSERT_TRUE(first.add_tab(kEditorAI, false));
  ASSERT_TRUE(second.add_tab(kEditorAI));
  ASSERT_TRUE(third.add_tab(kEditorAI));
  f.screen.set_maximized(&third);
  ASSERT_TRUE(f.shell->activate_editor(&f.screen, kEditorAI, true).ok());
  EXPECT_EQ(f.screen.maximized(), &third);
  ASSERT_TRUE(f.shell->restore_split_layout(&f.screen).ok());
  ASSERT_TRUE(f.shell->activate_editor(&f.screen, kEditorAI, true).ok());
  EXPECT_EQ(f.screen.maximized(), &second); // Active matching tab beats the first area's hidden AI.
  second.set_active_tab(0); third.set_active_tab(0);
  ASSERT_TRUE(f.shell->activate_editor(&f.screen, kEditorAI, false).ok());
  EXPECT_EQ(first.active_tab(), 1);
  EXPECT_EQ(f.screen.maximized(), nullptr); // False explicitly restores the split layout.
  EXPECT_EQ(first.tab_count(), 2); EXPECT_EQ(second.tab_count(), 2); EXPECT_EQ(third.tab_count(), 2);
}

TEST_F(FocusNavigation, FullFirstAreasUseTheRemainingCapacityWithoutReplacingAnyTab)
{
  auto &available = f.area("a2");
  Editor *viewer = &available.editor();
  for (auto *area : f.screen.areas()) {
    auto &editor = *dynamic_cast<EditorArea *>(area);
    if (&editor != &available) { ASSERT_NO_FATAL_FAILURE(fill(editor)); }
  }
  const auto result = f.shell->activate_editor(&f.screen, kEditorAI, true);
  ASSERT_TRUE(result.ok());
  EXPECT_EQ(result.value().at("area_id"), "a2"); EXPECT_EQ(result.value().at("tab_index"), 1);
  EXPECT_EQ(&available.tab(0), viewer); EXPECT_EQ(available.tab_count(), 2);
  Editor *created = &available.editor();
  ASSERT_TRUE(f.shell->activate_editor(&f.screen, kEditorAI, true).ok());
  EXPECT_EQ(available.tab_count(), 2); EXPECT_EQ(&available.editor(), created);
}

TEST_F(FocusNavigation, InvalidFullAndFailedFactoriesLeaveTheLayoutUnchanged)
{
  const auto before = f.screen.to_json();
  auto result = f.shell->activate_editor(&f.screen, "not-registered", true);
  ASSERT_FALSE(result.ok()); EXPECT_EQ(result.error().code, ErrorCode::InvalidParams);
  EXPECT_EQ(f.screen.to_json(), before);
  f.shell->registry().add({"empty-factory", "editor.ai.title",
      [](const EditorType &) -> std::unique_ptr<Editor> { return nullptr; }});
  f.shell->registry().add({"throwing-factory", "editor.ai.title",
      [](const EditorType &) -> std::unique_ptr<Editor> { throw std::runtime_error("fixture factory failure"); }});
  for (const auto *id : {"empty-factory", "throwing-factory"}) {
    result = f.shell->activate_editor(&f.screen, id, true);
    ASSERT_FALSE(result.ok()); EXPECT_EQ(result.error().code, ErrorCode::Unavailable);
    EXPECT_EQ(f.screen.to_json(), before);
  }
  for (auto *area : f.screen.areas()) { ASSERT_NO_FATAL_FAILURE(fill(*dynamic_cast<EditorArea *>(area))); }
  const auto full = f.screen.to_json();
  result = f.shell->activate_editor(&f.screen, kEditorAI, true);
  ASSERT_FALSE(result.ok()); EXPECT_EQ(result.error().code, ErrorCode::Busy);
  EXPECT_EQ(f.screen.to_json(), full);
  // A full layout can still activate an already existing editor.
  ASSERT_TRUE(f.shell->activate_editor(&f.screen, kEditorViewer, true).ok());
  EXPECT_EQ(f.screen.maximized(), &f.area("a2"));
}

TEST_F(FocusNavigation, MissingAndUninstalledScreensAreRejectedBeforeDereferencing)
{
  wm::Screen other;
  const auto before = f.screen.to_json();
  for (auto *screen : {static_cast<wm::Screen *>(nullptr), &other}) {
    const auto result = f.shell->activate_editor(screen, kEditorAI, true);
    ASSERT_FALSE(result.ok()); EXPECT_EQ(result.error().code, ErrorCode::Unavailable);
    const auto restore = f.shell->restore_split_layout(screen);
    ASSERT_FALSE(restore.ok()); EXPECT_EQ(restore.error().code, ErrorCode::Unavailable);
  }
  f.shell->forget(f.screen);
  const auto result = f.shell->activate_editor(&f.screen, kEditorAI, true);
  ASSERT_FALSE(result.ok()); EXPECT_EQ(result.error().code, ErrorCode::Unavailable);
  EXPECT_EQ(f.screen.to_json(), before);
}

TEST_F(FocusNavigation, ActiveTargetInputIsNotCommittedOrHiddenByNavigation)
{
  ASSERT_NO_FATAL_FAILURE(edit_python());
  const auto before = f.screen.to_json();
  auto result = f.shell->activate_editor(&f.screen, kEditorAI, true);
  ASSERT_FALSE(result.ok()); EXPECT_EQ(result.error().code, ErrorCode::Busy);
  result = f.shell->restore_split_layout(&f.screen);
  ASSERT_FALSE(result.ok()); EXPECT_EQ(result.error().code, ErrorCode::Busy);
  EXPECT_EQ(f.screen.to_json(), before);
  EXPECT_EQ(f.screen.ui()->edit_state()->text(), "uncommitted Python input");
  EXPECT_NE(f.area("a2").editor().save_state().at("source"), "uncommitted Python input");
}

TEST_F(FocusNavigation, AnotherWindowsActiveInputDoesNotBlockOrChange)
{
  ASSERT_NO_FATAL_FAILURE(edit_python());
  struct ExtraScreen {
    AppShell &shell;
    wm::Screen screen;
    explicit ExtraScreen(AppShell &owner) : shell(owner)
    {
      shell.install(screen, nullptr); shell.build_default_layout(screen);
    }
    ~ExtraScreen() { shell.forget(screen); }
  } other(*f.shell);
  const auto before = f.screen.to_json();
  const auto result = f.shell->activate_editor(&other.screen, kEditorAI, true);
  ASSERT_TRUE(result.ok());
  ASSERT_NE(other.screen.maximized(), nullptr);
  EXPECT_EQ(f.screen.to_json(), before);
  EXPECT_EQ(f.screen.ui()->edit_state()->text(), "uncommitted Python input");
  ASSERT_TRUE(f.shell->restore_split_layout(&other.screen).ok());
  EXPECT_EQ(f.screen.to_json(), before);
}

TEST_F(FocusNavigation, FocusPersistsThroughTheExistingLayoutFileWithoutChangingItsFormat)
{
  bridge::test::TempDir directory{"focus-layout"};
  const auto result = f.shell->activate_editor(&f.screen, kEditorAI, true);
  ASSERT_TRUE(result.ok());
  const auto saved = f.screen.to_json();
  const auto path = std::filesystem::path(directory.str()) / "layout.json";
  ASSERT_TRUE(f.shell->save(f.screen, nullptr, path));
  wmtest::AppFixture reopened;
  ASSERT_TRUE(reopened.shell->restore(reopened.screen, path));
  EXPECT_EQ(reopened.screen.to_json(), saved);
  ASSERT_NE(reopened.screen.maximized(), nullptr);
  EXPECT_EQ(dynamic_cast<EditorArea *>(reopened.screen.maximized())->editor().type().id, kEditorAI);
  const auto file = Json::parse(wmtest::read_text(path.string()));
  EXPECT_EQ(file.at("format"), "stk.desktop.layout"); EXPECT_EQ(file.at("version"), 1);
}

TEST_F(FocusNavigation, DeferredMenusRespectTargetInputScreenAndShellLifetimes)
{
  const auto prepare = action("app.menu.view.focus_preparation");
  ASSERT_TRUE(prepare.action);
  const auto before = f.screen.to_json();
  prepare.action();
  EXPECT_EQ(f.screen.to_json(), before);
  f.screen.run_deferred();
  ASSERT_NE(f.screen.maximized(), nullptr);
  EXPECT_EQ(dynamic_cast<EditorArea *>(f.screen.maximized())->editor().type().id, kEditorAI);
  f.drv->frame();
  const auto restore = action("app.menu.view.restore_split_layout");
  ASSERT_TRUE(restore.action); ASSERT_TRUE(restore.enabled);
  restore.action(); f.screen.run_deferred(); EXPECT_EQ(f.screen.maximized(), nullptr);

  ASSERT_NO_FATAL_FAILURE(edit_python());
  const auto edited = f.screen.to_json();
  prepare.action(); f.screen.run_deferred();
  EXPECT_EQ(f.screen.to_json(), edited);
  EXPECT_EQ(f.screen.ui()->edit_state()->text(), "uncommitted Python input");
  f.drv->key(wm::Key::Esc);
  prepare.action(); f.shell->forget(f.screen); f.screen.run_deferred();
  EXPECT_EQ(f.screen.to_json(), edited);
  prepare.action(); f.screen.run_deferred(); EXPECT_EQ(f.screen.to_json(), edited);

  // A copied menu action can outlive its shell; its weak fence must run first.
  f.shell.reset();
  prepare.action();
}

class FocusMenuLayout : public ::testing::TestWithParam<const char *> {};

TEST_P(FocusMenuLayout, NativeLabelsAndMenuItemsFitANarrowWindow)
{
  wmtest::AppFixture f(GetParam(), 1, 760, 800);
  const auto *view = f.screen.ui()->find("view"); ASSERT_NE(view, nullptr);
  ASSERT_GE(view->menu.size(), 3u);
  EXPECT_EQ(view->menu[0].text, f.shell->store().tr("app.menu.view.focus_preparation"));
  EXPECT_EQ(view->menu[1].text, f.shell->store().tr("app.menu.view.focus_analysis"));
  EXPECT_EQ(view->menu[2].text, f.shell->store().tr("app.menu.view.restore_split_layout"));
  EXPECT_FALSE(view->menu[2].enabled);
  ASSERT_TRUE(f.screen.ui()->open_popup("view")); f.drv->frame();
  int checked = 0;
  for (const auto &block : f.screen.ui()->blocks()) {
    for (const auto &widget : block->widgets()) {
      if (widget.type != ui::WidgetType::MenuItem || widget.menu_index < 0 || widget.menu_index > 2) { continue; }
      ++checked;
      EXPECT_GE(widget.rect.x, 0); EXPECT_LE(widget.rect.x1(), 760);
      EXPECT_GE(widget.rect.y, 0); EXPECT_LE(widget.rect.y1(), 800);
    }
  }
  EXPECT_EQ(checked, 3);
}

INSTANTIATE_TEST_SUITE_P(FocusNavigation, FocusMenuLayout, ::testing::Values("en", "zh_CN"),
    [](const ::testing::TestParamInfo<const char *> &info) { return std::string(info.param); });
}  // namespace
}  // namespace stk::app

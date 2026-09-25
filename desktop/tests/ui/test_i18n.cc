/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file Message catalogs: default zh_CN, runtime switch, fallback, placeholders. */
#include <gtest/gtest.h>

#include "support.hh"

using namespace stk::ui;
using stk::ui::test::Harness;

TEST(I18n, CatalogsLoadDefaultZhAndFallback)
{
  Catalog c;
  EXPECT_EQ(c.load_dir(std::string(STK_DESKTOP_DIR) + "/app/i18n"), 2);
  EXPECT_EQ(c.language(), "zh_CN");
  EXPECT_EQ(c.tr("ui.ok"), "\xe7\xa1\xae\xe5\xae\x9a");
  EXPECT_EQ(c.size("zh_CN"), c.size("en"));
  c.set_language("en");
  EXPECT_EQ(c.tr("ui.ok"), "OK");
  c.set("en", "only.en", "English only");
  c.set_language("zh_CN");
  EXPECT_EQ(c.tr("only.en"), "English only") << "falls back to en";
  EXPECT_EQ(c.tr("no.such.key"), "no.such.key");
  EXPECT_EQ(c.tr_or("no.such.key", "x"), "x");
  c.set_language("en");
  EXPECT_EQ(c.format("ui.error.invalid_number", {{"text", "abc"}}), "Invalid number: abc");
  std::string err;
  EXPECT_FALSE(c.load_json("xx", "[1, 2]", &err));
  EXPECT_FALSE(err.empty());
  EXPECT_FALSE(c.load_json("xx", R"({"a.b": 3})", &err));
}

TEST(I18n, RuntimeLanguageSwitchRebuildsText)
{
  Harness h;
  h.ui = [&](Context &ctx) { ctx.block("r", {0, 0, 400, 300}).layout().button("run", ctx.tr("gallery.button.run"), {}); };
  h.frame();
  EXPECT_EQ(h.w("run").text, "\xe8\xbf\x90\xe8\xa1\x8c");
  const WidgetId id = h.w("run").id;
  h.catalog.set_language("en");
  h.frame();
  EXPECT_EQ(h.w("run").text, "Run");
  EXPECT_EQ(h.w("run").id, id) << "ids do not depend on the language";
}

/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "screens.hh"

#include <cmath>
#include <cstdio>
#include <fstream>
#include <sstream>

#include "stk/ui/form_json.hh"

namespace stk::ui::gallery {

const char *screen_name(Screen s)
{
  switch (s) {
    case Screen::Widgets: return "widgets";
    case Screen::Lists: return "lists";
    case Screen::Form: return "form";
    case Screen::Overlays: return "overlays";
    case Screen::Gallery: return "gallery";
  }
  return "?";
}

Vec2 screen_size(Screen s)
{
  switch (s) {
    case Screen::Widgets:
    case Screen::Overlays:
      return {420, 900};
    case Screen::Lists:
      return {520, 900};
    case Screen::Form:
      return {440, 520};
    case Screen::Gallery:
      return {1320, 860};
  }
  return {400, 400};
}

/* -------------------------------------------------------------------- */
/* Colormaps */

static std::vector<Color> poly_lut(const double c[7][3])
{
  std::vector<Color> lut(256);
  for (int i = 0; i < 256; i++) {
    const double t = i / 255.0;
    double rgb[3];
    for (int k = 0; k < 3; k++) {
      double v = c[6][k];
      for (int j = 5; j >= 0; j--) {
        v = c[j][k] + t * v;
      }
      rgb[k] = v;
    }
    lut[size_t(i)] = Color::from_float(float(rgb[0]), float(rgb[1]), float(rgb[2]));
  }
  return lut;
}

std::vector<ColormapItem> make_colormaps()
{
  /* Polynomial fits of matplotlib's viridis and plasma (Matt Zucker, CC0). */
  static const double viridis[7][3] = {{0.2777273272234177, 0.005407344544966578, 0.3340998053353061},
                                       {0.1050930431085774, 1.404613529898575, 1.384590162594685},
                                       {-0.3308618287255563, 0.214847559468213, 0.09509516302823659},
                                       {-4.634230498983486, -5.799100973351585, -19.33244095627987},
                                       {6.228269936347081, 14.17993336680509, 56.69055260068105},
                                       {4.776384997670288, -13.74514537774601, -65.35303263337234},
                                       {-5.435455855934631, 4.645852612178535, 26.3124352495832}};
  static const double plasma[7][3] = {{0.05873234392399702, 0.02333670892565664, 0.5433401826748754},
                                      {2.176514634195958, 0.2383834171260182, 0.7539604599784036},
                                      {-2.689460476458034, -7.455851135738909, 3.110799939717086},
                                      {6.130348345893603, 42.3461881477227, -28.51885465332158},
                                      {-11.10743619062271, -82.66631109428045, 60.13984767418263},
                                      {10.02306557647065, 71.41361770095349, -54.07218655560067},
                                      {-3.658713842777788, -22.93153465461149, 18.19190778539828}};
  std::vector<ColormapItem> out;
  out.push_back({"viridis", poly_lut(viridis)});
  out.push_back({"plasma", poly_lut(plasma)});
  std::vector<Color> cw(256), gray(256);
  const Color lo = Color::rgb(0x3b4cc0), mid = Color::rgb(0xdddddd), hi = Color::rgb(0xb40426);
  for (int i = 0; i < 256; i++) {
    const float t = i / 255.0f;
    cw[size_t(i)] = t < 0.5f ? lo.blend(mid, t * 2.0f) : mid.blend(hi, (t - 0.5f) * 2.0f);
    gray[size_t(i)] = Color{uint8_t(i), uint8_t(i), uint8_t(i), 255};
  }
  out.push_back({"coolwarm", cw});
  out.push_back({"gray", gray});
  return out;
}

/* -------------------------------------------------------------------- */
/* State */

static bool read_file(const std::string &path, std::string &out)
{
  std::ifstream f(path, std::ios::binary);
  if (!f) {
    return false;
  }
  std::stringstream ss;
  ss << f.rdbuf();
  out = ss.str();
  return true;
}

bool init_state(State &s, const std::string &desktop_dir, const std::string &lang, std::string *err)
{
  const int n = s.catalog.load_dir(desktop_dir + "/app/i18n", err);
  s.catalog.set_language(lang);
  s.job_name = std::string(s.catalog.tr("gallery.text.value"));
  s.colormaps = std::make_shared<std::vector<ColormapItem>>(make_colormaps());
  s.jobs.clear();
  static const double secs[] = {12.5, 340.0, 7.25, 86.0, 1203.5, 45.0, 3.0, 610.0, 29.75, 0.5, 150.0, 77.0};
  for (int i = 0; i < 12; i++) {
    s.jobs.push_back({1000 + i * 7, s.catalog.format("gallery.job.name", {{"n", std::to_string(i + 1)}}), i % 3,
                      secs[i]});
  }
  s.log.clear();
  s.log.append("\x1b[1;32m[INFO]\x1b[0m muFerro 0.9.3 \xe5\x90\xaf\xe5\x8a\xa8 (MPI x 8)\r\n");
  s.log.append("\x1b[36m[step 000100]\x1b[0m E_total = -1.284e+02  |P| = 0.312\n");
  s.log.append("\x1b[36m[step 000200]\x1b[0m E_total = -1.301e+02  |P| = 0.327\n");
  s.log.append("\x1b[33m[WARN]\x1b[0m output dir exists, appending\n");
  s.log.append("\x1b]0;muferro\x07progress  10%\rprogress  55%\rprogress 100%\n");
  for (int i = 3; i <= 9; i++) {
    char buf[96];
    std::snprintf(buf, sizeof(buf), "\x1b[36m[step %06d]\x1b[0m E_total = -1.3%02de+02  |P| = 0.3%02d\n", i * 100,
                  10 + i, 30 + i);
    s.log.append(buf);
  }
  s.log.append("\x1b[1;32m[DONE]\x1b[0m wrote Polar.00000900.dat");
  return n >= 2;
}

bool load_form(State &s, const std::string &repo_root, std::string *err)
{
  std::string cat_text, preset_text;
  if (!read_file(repo_root + "/docs/specs/catalog/stk-catalog-m1.json", cat_text) ||
      !read_file(repo_root + "/suan/graph/presets/muferro-domains.json", preset_text))
  {
    if (err) {
      *err = "cannot read catalog/preset under " + repo_root;
    }
    return false;
  }
  const nlohmann::ordered_json catalog = nlohmann::ordered_json::parse(cat_text, nullptr, false);
  const nlohmann::ordered_json preset = nlohmann::ordered_json::parse(preset_text, nullptr, false);
  if (catalog.is_discarded() || preset.is_discarded()) {
    if (err) {
      *err = "catalog/preset JSON is malformed";
    }
    return false;
  }
  s.form_schema = preset_schema(preset, catalog);
  s.form = FormModel();
  s.form.init_defaults(s.form_schema);
  s.has_form = true;
  return true;
}

/* -------------------------------------------------------------------- */
/* Screens */

static void widgets(Context &ctx, State &s, Layout &l)
{
  l.label(ctx.tr("gallery.title"));
  l.paragraph(ctx.tr("gallery.paragraph"));
  {
    Layout &r = l.row();
    r.button("run", ctx.tr("gallery.button.run"), [&s]() { s.clicks++; }).tip(ctx.tr("gallery.button.run.tip"));
    r.button("cancel", ctx.tr("gallery.button.cancel"), [&s]() { s.modal_open = true; });
    r.button("disabled", ctx.tr("gallery.button.disabled"), {}).disable();
    r.menu_button("file_menu", ctx.tr("gallery.menu"),
                  {{std::string(ctx.tr("gallery.menu.open")), [&s]() { s.clicks += 10; }},
                   {std::string(ctx.tr("gallery.menu.export")), [&s]() { s.clicks += 100; }},
                   {std::string(ctx.tr("gallery.menu.quit")), {}, false}});
  }
  {
    Layout &r = l.row();
    r.checkbox("grid", ctx.tr("gallery.check.grid"), bind(s.show_grid));
    r.checkbox("autorefresh", ctx.tr("gallery.check.autorefresh"), bind(s.autorefresh));
  }
  TextFieldOptions to;
  to.placeholder = std::string(ctx.tr("gallery.text.placeholder"));
  l.prop(ctx.tr("gallery.text")).text_field("job_name", bind(s.job_name), to);
  {
    Layout &c = l.column(true);
    NumberProps p;
    p.min = 0;
    p.max = 1;
    p.step = 0.01;
    c.number("threshold", ctx.tr("gallery.number.threshold"), bind(s.threshold), p);
    NumberProps q;
    q.min = 0;
    q.step = 0.5;
    q.precision = 2;
    q.unit = std::string(ctx.tr("unit.nm"));
    c.number("length", ctx.tr("gallery.number.length"), bind(s.length), q);
    NumberProps r;
    r.min = 0;
    r.step = 1e-5;
    c.number("small", ctx.tr("gallery.number.small"), bind(s.small_step), r);
  }
  NumberProps op;
  op.min = 0;
  op.max = 1;
  op.step = 0.01;
  op.precision = 2;
  l.slider("opacity", ctx.tr("gallery.slider.opacity"), bind_float(s.opacity), op);
  l.prop(ctx.tr("gallery.dropdown.view"))
      .dropdown("view", {std::string(ctx.tr("enum.iso")), "+X", "-X", "+Y", "-Y", "+Z", "-Z"}, bind(s.view));
  l.prop(ctx.tr("gallery.colormap")).colormap_dropdown("colormap", s.colormaps, bind(s.colormap));
  l.tabs("tabs",
         {std::string(ctx.tr("gallery.tab.logs")), std::string(ctx.tr("gallery.tab.probe")),
          std::string(ctx.tr("gallery.tab.transfers"))},
         bind(s.tab));
  l.progress(s.progress, ctx.catalog() ? ctx.catalog()->format("gallery.progress", {{"done", "31"}, {"total", "50"}}) :
                                         std::string("31/50"));
  if (Layout *p = l.panel("advanced", ctx.tr("gallery.panel.advanced"))) {
    NumberProps pp;
    pp.min = 0;
    pp.max = 1;
    pp.step = 0.01;
    p->prop(ctx.tr("gallery.number.threshold")).number("adv_threshold", "", bind(s.threshold), pp);
    p->prop(ctx.tr("gallery.check.grid")).checkbox("adv_grid", "", bind(s.show_grid));
  }
  l.panel("output", ctx.tr("gallery.panel.output"), false);
}

static void lists(Context &ctx, State &s, Layout &l)
{
  const Catalog *cat = ctx.catalog();
  l.label(ctx.tr("gallery.list"));
  ListSpec ls;
  ls.count = 100000;
  ls.rows = 6;
  ls.selected = bind(s.list_selected);
  ls.text = [cat](int i) {
    char n[16];
    std::snprintf(n, sizeof(n), "%05d", i);
    static const char *states[] = {"gallery.job.done", "gallery.job.running", "gallery.job.failed"};
    return cat ? cat->format("gallery.list.row", {{"n", n}, {"state", std::string(cat->tr(states[i % 3]))}}) :
                 std::string(n);
  };
  l.virtual_list("jobs", std::move(ls));
  l.label(ctx.tr("gallery.table"));
  TableSpec ts;
  ts.columns = {{std::string(ctx.tr("gallery.table.id")), 3.0f, true, true},
                {std::string(ctx.tr("gallery.table.name")), 9.0f, true, false},
                {std::string(ctx.tr("gallery.table.state")), 4.5f, true, false},
                {std::string(ctx.tr("gallery.table.time")), 5.0f, true, true}};
  ts.rows = int(s.jobs.size());
  ts.visible_rows = 5;
  ts.selected = bind(s.table_selected);
  ts.cell = [&s, cat](int r, int c) -> std::string {
    const Job &j = s.jobs[size_t(r)];
    switch (c) {
      case 0: return std::to_string(j.id);
      case 1: return j.name;
      case 2: {
        static const char *states[] = {"gallery.job.done", "gallery.job.running", "gallery.job.failed"};
        return cat ? std::string(cat->tr(states[j.state])) : std::to_string(j.state);
      }
      default: {
        char b[32];
        std::snprintf(b, sizeof(b), "%.2f", j.seconds);
        return b;
      }
    }
  };
  l.table("job_table", std::move(ts));
  l.label(ctx.tr("gallery.log"));
  l.log_view("log", s.log, 6.0f);
  auto [a, b] = l.splitter("split", bind(s.split));
  a->image("image", {s.image_texture, s.image_w, s.image_h, 5.0f});
  b->label(ctx.tr("gallery.splitter.right"));
  b->paragraph(ctx.tr("gallery.image"));
}

static void form(Context &ctx, State &s, Layout &l)
{
  l.label(ctx.tr("gallery.preset"));
  if (s.has_form) {
    FormOptions fo;
    fo.colormaps = s.colormaps;
    build_form(l, s.form_schema, s.form, fo);
  }
}

static void modal(Context &ctx, State &s, Vec2 window)
{
  ModalOptions mo;
  mo.width_units = 17.0f;
  mo.has_pos = true;
  const float u = ctx.style().unit;
  mo.pos = {window.x - 17.0f * u - u, window.y - 8.2f * u};
  Layout &m = ctx.modal("confirm", ctx.tr("gallery.modal.title"), [&s]() { s.modal_open = false; }, mo);
  m.paragraph(ctx.tr("gallery.modal.body"));
  Layout &r = m.row().alignment(LayoutAlign::Right);
  r.button("modal_ok", ctx.tr("ui.ok"), [&s]() { s.modal_open = false; });
  r.button("modal_cancel", ctx.tr("ui.cancel"), [&s]() { s.modal_open = false; });
}

void build(Context &ctx, State &s, Screen screen, Vec2 window, double now)
{
  ctx.set_catalog(&s.catalog);
  ctx.begin_frame(window, now);
  switch (screen) {
    case Screen::Widgets:
    case Screen::Overlays:
      widgets(ctx, s, ctx.block("widgets", {0, 0, window.x, window.y}).layout());
      break;
    case Screen::Lists:
      lists(ctx, s, ctx.block("lists", {0, 0, window.x, window.y}).layout());
      break;
    case Screen::Form:
      form(ctx, s, ctx.block("form", {0, 0, window.x, window.y}).layout());
      break;
    case Screen::Gallery: {
      const float w0 = std::round(window.x * 0.31f), w1 = std::round(window.x * 0.38f);
      widgets(ctx, s, ctx.block("widgets", {0, 0, w0, window.y}).layout());
      lists(ctx, s, ctx.block("lists", {w0, 0, w1, window.y}).layout());
      form(ctx, s, ctx.block("form", {w0 + w1, 0, window.x - w0 - w1, window.y}).layout());
      break;
    }
  }
  if ((screen == Screen::Overlays || screen == Screen::Gallery) && s.modal_open) {
    modal(ctx, s, window);
  }
  ctx.end_frame();
}

void build_staged(Context &ctx, State &s, Screen screen, Vec2 window, double now)
{
  double t = now;
  /* Interact first (a modal would block the region widgets), then show everything. */
  const bool modal = s.modal_open;
  s.modal_open = false;
  build(ctx, s, screen, window, t);
  auto click = [&](Vec2 p) {
    ctx.handle_event(Event::mouse_move(p, t));
    ctx.handle_event(Event::mouse_down(p, MouseButton::Left, t));
    ctx.handle_event(Event::mouse_up(p, MouseButton::Left, t));
    t += 1.0;
    build(ctx, s, screen, window, t);
  };
  /* Sort the job table by time, descending (two header clicks). */
  if (const Widget *tbl = ctx.find("job_table")) {
    float x = tbl->rect.x + 1;
    for (int c = 0; c < 3; c++) {
      x += std::round(ctx.style().unit * (c == 0 ? 3.0f : (c == 1 ? 9.0f : 4.5f)));
    }
    const Vec2 p{x + ctx.style().unit, tbl->rect.y + ctx.style().unit * 0.5f};
    click(p);
    click(p);
  }
  /* IME composition inside the job-name field, caret after the first composed character. */
  if (const Widget *f = ctx.find("job_name")) {
    click({f->rect.cx(), f->rect.cy()});
    ctx.handle_event(Event::key_down(Key::End, 0, t));
    ctx.handle_event(Event::ime_preedit("\xe4\xb8\xad\xe6\x96\x87", 3, t));
  }
  s.modal_open = modal;
  /* In the full gallery, open the form's dropdown and show a form tooltip (description, unit and
   * stage lines) so the region widgets stay visible; single-region screens use their own. */
  if (!ctx.open_popup("form/view")) {
    ctx.open_popup("view");
  }
  if (!ctx.force_tooltip("form/min_magnitude")) {
    ctx.force_tooltip("run");
  }
  ctx.toast(std::string(s.catalog.tr("gallery.toast.saved")), ToastKind::Success, 1.0e9);
  build(ctx, s, screen, window, t + 1.0);
}

}  // namespace stk::ui::gallery

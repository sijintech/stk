/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/ui/form.hh"

#include <algorithm>
#include <cmath>
#include <cstdio>

namespace stk::ui {

/* -------------------------------------------------------------------- */
/* FormValue */

FormValue FormValue::boolean(bool v)
{
  FormValue f;
  f.kind = Kind::Bool;
  f.b = v;
  return f;
}

FormValue FormValue::number(double v)
{
  FormValue f;
  f.kind = Kind::Number;
  f.num = v;
  return f;
}

FormValue FormValue::string(std::string v)
{
  FormValue f;
  f.kind = Kind::String;
  f.str = std::move(v);
  return f;
}

FormValue FormValue::array(std::vector<double> v)
{
  FormValue f;
  f.kind = Kind::Array;
  f.arr = std::move(v);
  return f;
}

static std::string num_str(double v)
{
  char buf[32];
  std::snprintf(buf, sizeof(buf), "%.15g", v);
  return buf;
}

std::string FormValue::to_string() const
{
  switch (kind) {
    case Kind::Null: return "null";
    case Kind::Bool: return b ? "true" : "false";
    case Kind::Number: return num_str(num);
    case Kind::String: return str;
    case Kind::Array: {
      std::string s = "[";
      for (size_t i = 0; i < arr.size(); i++) {
        s += (i ? ", " : "") + num_str(arr[i]);
      }
      return s + "]";
    }
  }
  return {};
}

bool FormValue::operator==(const FormValue &o) const
{
  if (kind != o.kind) {
    return false;
  }
  switch (kind) {
    case Kind::Null: return true;
    case Kind::Bool: return b == o.b;
    case Kind::Number: return num == o.num;
    case Kind::String: return str == o.str;
    case Kind::Array: return arr == o.arr;
  }
  return false;
}

const char *schema_type_name(SchemaType t)
{
  switch (t) {
    case SchemaType::Object: return "object";
    case SchemaType::Number: return "number";
    case SchemaType::Integer: return "integer";
    case SchemaType::Boolean: return "boolean";
    case SchemaType::String: return "string";
    case SchemaType::Enum: return "enum";
    case SchemaType::NumberArray: return "number_array";
    case SchemaType::Step: return "step";
    case SchemaType::Json: return "json";
  }
  return "?";
}

const SchemaNode *SchemaNode::property(std::string_view n) const
{
  for (const SchemaNode &p : properties) {
    if (p.name == n) {
      return &p;
    }
  }
  return nullptr;
}

/* -------------------------------------------------------------------- */
/* FormModel */

void FormModel::init_defaults(const SchemaNode &object)
{
  for (const SchemaNode &p : object.properties) {
    if (has(p.name)) {
      continue;
    }
    if (p.default_value) {
      values_[p.name] = *p.default_value;
    }
    else if (p.type == SchemaType::Boolean) {
      values_[p.name] = FormValue::boolean(false);
    }
    else if (p.type == SchemaType::Step) {
      values_[p.name] = FormValue::string("latest");
    }
    else {
      values_[p.name] = FormValue::null();
    }
  }
}

FormValue FormModel::get(const std::string &name) const
{
  const auto it = values_.find(name);
  return it == values_.end() ? FormValue{} : it->second;
}

void FormModel::set(const std::string &name, FormValue v)
{
  values_[name] = std::move(v);
  version_++;
  if (on_change) {
    on_change(name, values_[name]);
  }
}

/* -------------------------------------------------------------------- */
/* Builder */

namespace {

bool is_zh(std::string_view lang)
{
  return lang.substr(0, 2) == "zh";
}

std::string prettify(std::string_view name)
{
  std::string s(name);
  for (char &c : s) {
    if (c == '_') {
      c = ' ';
    }
  }
  if (!s.empty() && s[0] >= 'a' && s[0] <= 'z') {
    s[0] = char(s[0] - 'a' + 'A');
  }
  return s;
}

struct Builder {
  Context &ctx;
  FormModel &model;
  const FormOptions &opts;
  std::string lang;

  std::string tr_or(const std::string &key, std::string_view fallback) const
  {
    return ctx.catalog() ? std::string(ctx.catalog()->tr_or(key, fallback)) : std::string(fallback);
  }

  std::string unit_label(const std::string &unit) const
  {
    return unit.empty() ? std::string() : tr_or("unit." + unit, unit);
  }

  static bool unit_suffix_shown(const std::string &unit)
  {
    return !unit.empty() && unit != "unspecified" && unit != "1";
  }

  std::string tooltip(const SchemaNode &n) const
  {
    std::string t = (is_zh(lang) && !n.description_zh.empty()) ? n.description_zh : n.description;
    auto line = [&](const std::string &s) {
      if (!s.empty()) {
        t += (t.empty() ? "" : "\n") + s;
      }
    };
    if (!n.unit.empty()) {
      line(ctx.catalog() ? ctx.catalog()->format("form.unit_line", {{"unit", unit_label(n.unit)}}) :
                           "Unit: " + unit_label(n.unit));
    }
    if (!n.stage.empty()) {
      line(tr_or("form.stage." + n.stage, n.stage));
    }
    return t;
  }

  NumberProps props(const SchemaNode &n, bool integer) const
  {
    NumberProps p;
    p.integer = integer;
    if (n.minimum) {
      p.min = *n.minimum;
      p.exclusive_min = n.exclusive_min;
    }
    if (n.maximum) {
      p.max = *n.maximum;
      p.exclusive_max = n.exclusive_max;
    }
    if (integer) {
      p.step = 1.0;
      p.precision = 0;
    }
    else {
      double span = 0.0;
      if (n.minimum && n.maximum) {
        span = (*n.maximum - *n.minimum) / 100.0;
      }
      else if (n.default_value && n.default_value->kind == FormValue::Kind::Number && n.default_value->num != 0.0) {
        span = std::fabs(n.default_value->num) / 10.0;
      }
      p.step = span > 0.0 ? std::pow(10.0, std::floor(std::log10(span))) : 0.1;
      p.precision = std::clamp(int(-std::floor(std::log10(p.step))) + 1, 3, 8);
    }
    if (unit_suffix_shown(n.unit)) {
      p.unit = unit_label(n.unit);
    }
    return p;
  }

  Binding<double> number_binding(const std::string &name) const
  {
    FormModel *m = &model;
    return {[m, name]() {
              const FormValue v = m->get(name);
              return v.kind == FormValue::Kind::Number ? v.num : 0.0;
            },
            [m, name](double d) { m->set(name, FormValue::number(d)); }};
  }

  void member(Layout &l, const SchemaNode &n)
  {
    const std::string &name = n.name;
    const std::string label = schema_label(n, lang);
    const std::string tip = tooltip(n);
    FormModel *m = &model;
    if (n.type == SchemaType::Object) {
      if (Layout *body = l.panel(name, label, true)) {
        for (const SchemaNode &c : n.properties) {
          member(*body, c);
        }
      }
      return;
    }
    Layout &v = l.prop(label, tip);
    switch (n.type) {
      case SchemaType::Boolean:
        v.checkbox(name, "",
                   {[m, name]() { return m->get(name).kind == FormValue::Kind::Bool && m->get(name).b; },
                    [m, name](bool b) { m->set(name, FormValue::boolean(b)); }})
            .tip(tip);
        break;
      case SchemaType::Number:
      case SchemaType::Integer: {
        const bool integer = n.type == SchemaType::Integer;
        const NumberProps p = props(n, integer);
        const bool slider = n.widget == "slider" || (!integer && n.minimum && n.maximum);
        (slider ? v.slider(name, "", number_binding(name), p) : v.number(name, "", number_binding(name), p)).tip(tip);
        break;
      }
      case SchemaType::String: {
        if (n.widget == "colormap" && opts.colormaps && !opts.colormaps->empty()) {
          auto cms = opts.colormaps;
          v.colormap_dropdown(name, cms,
                              {[m, name, cms]() {
                                 const std::string cur = m->get(name).str;
                                 for (size_t i = 0; i < cms->size(); i++) {
                                   if ((*cms)[i].name == cur) {
                                     return int(i);
                                   }
                                 }
                                 return -1;
                               },
                               [m, name, cms](int i) { m->set(name, FormValue::string((*cms)[size_t(i)].name)); }})
              .tip(tip);
          break;
        }
        const bool nullable = n.nullable;
        TextFieldOptions to;
        if (nullable) {
          to.placeholder = tr_or("form.auto", "auto");
        }
        Binding<std::string> b{[m, name]() {
                                 const FormValue fv = m->get(name);
                                 return fv.kind == FormValue::Kind::String ? fv.str : std::string();
                               },
                               [m, name, nullable](std::string s) {
                                 m->set(name, (nullable && s.empty()) ? FormValue::null() : FormValue::string(std::move(s)));
                               }};
        if ((n.widget == "path" || n.widget == "file") && opts.on_browse) {
          Layout &r = v.row(true);
          r.text_field(name, std::move(b), std::move(to)).tip(tip);
          auto browse = opts.on_browse;
          r.button(name + "/browse", "\xe2\x80\xa6", [browse, name]() { browse(name); }).width(1.0f);
        }
        else {
          v.text_field(name, std::move(b), std::move(to)).tip(tip);
        }
        break;
      }
      case SchemaType::Enum: {
        std::vector<std::string> items;
        for (const FormValue &e : n.enum_values) {
          if (e.is_null()) {
            items.push_back(tr_or("form.null", "(none)"));
          }
          else if (e.kind == FormValue::Kind::String) {
            items.push_back(tr_or("enum." + e.str, e.str));
          }
          else {
            items.push_back(e.to_string());
          }
        }
        const std::vector<FormValue> values = n.enum_values;
        v.dropdown(name, std::move(items),
                   {[m, name, values]() {
                      const FormValue cur = m->get(name);
                      for (size_t i = 0; i < values.size(); i++) {
                        if (values[i] == cur) {
                          return int(i);
                        }
                      }
                      return -1;
                    },
                    [m, name, values](int i) { m->set(name, values[size_t(i)]); }})
            .tip(tip);
        break;
      }
      case SchemaType::NumberArray: {
        const int count = std::max(1, n.items);
        std::vector<double> fallback(size_t(count), 0.0);
        if (n.default_value && n.default_value->kind == FormValue::Kind::Array &&
            n.default_value->arr.size() == size_t(count))
        {
          fallback = n.default_value->arr;
        }
        if (n.nullable) {
          v.checkbox(name + "/set", tr_or("form.override", "Override"),
                     {[m, name]() { return !m->get(name).is_null(); },
                      [m, name, fallback](bool on) { m->set(name, on ? FormValue::array(fallback) : FormValue::null()); }})
              .tip(tip);
          if (model.get(name).is_null()) {
            break;
          }
        }
        Layout &col = v.column(true);
        NumberProps p = props(n, n.integer_items);
        static const char *xyz[] = {"X", "Y", "Z", "W"};
        for (int i = 0; i < count; i++) {
          std::string axis;
          if (count == 2) {
            axis = tr_or(i == 0 ? "form.min" : "form.max", i == 0 ? "Min" : "Max");
          }
          else if (count <= 4) {
            axis = xyz[i];
          }
          else {
            axis = std::to_string(i);
          }
          col.number(name + "/" + std::to_string(i), axis,
                     {[m, name, i, fallback]() {
                        const FormValue fv = m->get(name);
                        return fv.kind == FormValue::Kind::Array && size_t(i) < fv.arr.size() ? fv.arr[size_t(i)] :
                                                                                                fallback[size_t(i)];
                      },
                      [m, name, i, fallback](double d) {
                        FormValue fv = m->get(name);
                        if (fv.kind != FormValue::Kind::Array || fv.arr.size() != fallback.size()) {
                          fv = FormValue::array(fallback);
                        }
                        fv.arr[size_t(i)] = d;
                        m->set(name, fv);
                      }},
                     p)
              .tip(tip);
        }
        break;
      }
      case SchemaType::Step: {
        Layout &r = v.row(true);
        std::vector<std::string> modes = {tr_or("form.step.latest", "Latest"), tr_or("form.step.first", "First"),
                                          tr_or("form.step.index", "Step")};
        r.dropdown(name + "/mode", std::move(modes),
                   {[m, name]() {
                      const FormValue fv = m->get(name);
                      if (fv.kind == FormValue::Kind::Number) {
                        return 2;
                      }
                      return fv.str == "first" ? 1 : 0;
                    },
                    [m, name](int i) {
                      if (i == 0) {
                        m->set(name, FormValue::string("latest"));
                      }
                      else if (i == 1) {
                        m->set(name, FormValue::string("first"));
                      }
                      else if (m->get(name).kind != FormValue::Kind::Number) {
                        m->set(name, FormValue::number(0));
                      }
                    }})
            .tip(tip);
        if (model.get(name).kind == FormValue::Kind::Number) {
          NumberProps p;
          p.integer = true;
          p.min = 0;
          p.step = 1;
          p.precision = 0;
          r.number(name, "", number_binding(name), p).tip(tip);
        }
        break;
      }
      case SchemaType::Json:
      default: {
        TextFieldOptions to;
        to.mono = true;
        v.text_field(name,
                     {[m, name]() {
                        const FormValue fv = m->get(name);
                        return fv.kind == FormValue::Kind::String ? fv.str : fv.to_string();
                      },
                      [m, name](std::string s) { m->set(name, FormValue::string(std::move(s))); }},
                     std::move(to))
            .tip(tip);
        break;
      }
    }
  }
};

bool stage_ok(const SchemaNode &n, StageFilter f)
{
  if (f == StageFilter::All || n.stage.empty()) {
    return true;
  }
  return (f == StageFilter::Data) == (n.stage == "data");
}

}  // namespace

std::string schema_label(const SchemaNode &node, std::string_view lang)
{
  if (is_zh(lang) && !node.title_zh.empty()) {
    return node.title_zh;
  }
  if (!node.title.empty()) {
    return node.title;
  }
  return prettify(node.name);
}

void build_form(Layout &layout, const SchemaNode &object, FormModel &model, const FormOptions &opts)
{
  Context &ctx = layout.ctx();
  Builder b{ctx, model, opts, opts.lang};
  if (b.lang.empty()) {
    b.lang = ctx.catalog() ? ctx.catalog()->language() : Catalog::DEFAULT_LANGUAGE;
  }
  /* Glossary: "param.<name>" entries translate members without x-stk-title-zh. */
  std::vector<SchemaNode> members;
  for (const SchemaNode &p : object.properties) {
    if (!stage_ok(p, opts.stages)) {
      continue;
    }
    SchemaNode n = p;
    const std::string key = "param." + n.name;
    if (ctx.catalog() && ctx.catalog()->has(b.lang, key)) {
      std::string &title = is_zh(b.lang) ? n.title_zh : n.title;
      if (title.empty()) {
        title = std::string(ctx.catalog()->tr(key));
      }
    }
    members.push_back(std::move(n));
  }
  model.init_defaults(object);

  std::vector<const SchemaNode *> plain, advanced;
  std::vector<std::pair<std::string, std::vector<const SchemaNode *>>> groups;
  for (const SchemaNode &n : members) {
    if (n.advanced && !opts.show_advanced) {
      advanced.push_back(&n);
    }
    else if (opts.group_panels && !n.group.empty()) {
      auto it = std::find_if(groups.begin(), groups.end(), [&](const auto &g) { return g.first == n.group; });
      if (it == groups.end()) {
        groups.push_back({n.group, {}});
        it = groups.end() - 1;
      }
      it->second.push_back(&n);
    }
    else {
      plain.push_back(&n);
    }
  }
  Layout &col = layout.column();
  for (const SchemaNode *n : plain) {
    b.member(col, *n);
  }
  for (const auto &[group, list] : groups) {
    if (Layout *body = col.panel("group." + group, b.tr_or("form.group." + group, prettify(group)), true)) {
      for (const SchemaNode *n : list) {
        b.member(*body, *n);
      }
    }
  }
  if (!advanced.empty()) {
    if (Layout *body = col.panel("advanced", b.tr_or("form.advanced", "Advanced"), false)) {
      for (const SchemaNode *n : advanced) {
        b.member(*body, *n);
      }
    }
  }
}

}  // namespace stk::ui

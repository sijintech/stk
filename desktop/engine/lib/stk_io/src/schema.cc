/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/io/schema.hh"

#include "stk/core/utf8.hh"
#include "stk/io/pyregex.hh"

#include <algorithm>
#include <array>
#include <cmath>
#include <map>
#include <unordered_map>
#include <unordered_set>

namespace stk::io {

std::string pointer_token(std::string_view key)
{
  std::string out;
  out.reserve(key.size());
  for (char c : key) {
    if (c == '~') {
      out += "~0";
    }
    else if (c == '/') {
      out += "~1";
    }
    else {
      out.push_back(c);
    }
  }
  return out;
}

std::string schema_pattern(std::string_view pattern)
{
  std::string out;
  out.reserve(pattern.size() + 4);
  bool in_class = false;
  for (size_t i = 0; i < pattern.size();) {
    const char c = pattern[i];
    if (c == '\\') {
      out.append(pattern.substr(i, 2));
      i += 2;
      continue;
    }
    if (in_class) {
      if (c == ']') {
        in_class = false;
      }
    }
    else if (c == '[') {
      in_class = true;
      out.push_back(c);
      i++;
      if (i < pattern.size() && pattern[i] == '^') { /* "[^]...]" and "[]...]" start with a literal "]" */
        out.push_back('^');
        i++;
      }
      if (i < pattern.size() && pattern[i] == ']') {
        out.push_back(']');
        i++;
      }
      continue;
    }
    else if (c == '$') {
      out += "\\Z";
      i++;
      continue;
    }
    out.push_back(c);
    i++;
  }
  return out;
}

bool schema_pattern_search(std::string_view pattern, std::string_view text)
{
  return py_regex_search(schema_pattern(pattern), text);
}

std::string pointer_join(const std::string &path, std::string_view key)
{
  return path + "/" + pointer_token(key);
}

std::string pointer_join(const std::string &path, size_t index)
{
  return path + "/" + std::to_string(index);
}

std::string short_json(const Json &value, size_t limit)
{
  const std::string text = python_json_dumps(value);
  const std::u32string code_points = core::utf8::to_utf32(text);
  if (code_points.size() <= limit) {
    return text;
  }
  return core::utf8::from_utf32(std::u32string_view(code_points).substr(0, limit - 3)) + "...";
}

namespace {

bool is_number(const Json &v)
{
  return v.is_number() && std::isfinite(v.get<double>());
}

bool is_type(const Json &v, const Json &name)
{
  if (!name.is_string()) {
    throw SchemaError("Unsupported JSON Schema type " + python_json_dumps(name));
  }
  const std::string &n = name.get_ref<const std::string &>();
  if (n == "null") {
    return v.is_null();
  }
  if (n == "boolean") {
    return v.is_boolean();
  }
  if (n == "integer") {
    if (!is_number(v)) {
      return false;
    }
    if (v.is_number_integer()) {
      return true;
    }
    const double d = v.get<double>();
    return std::floor(d) == d;
  }
  if (n == "number") {
    return is_number(v);
  }
  if (n == "string") {
    return v.is_string();
  }
  if (n == "array") {
    return v.is_array();
  }
  if (n == "object") {
    return v.is_object();
  }
  throw SchemaError("Unsupported JSON Schema type '" + n + "'");
}

std::vector<Json> type_list(const Json &type)
{
  if (type.is_string()) {
    return {type};
  }
  if (type.is_array()) {
    return std::vector<Json>(type.begin(), type.end());
  }
  if (type.is_object()) {
    std::vector<Json> keys;
    for (auto it = type.begin(); it != type.end(); ++it) {
      keys.emplace_back(it.key());
    }
    return keys;
  }
  throw SchemaError("Unsupported JSON Schema type " + python_json_dumps(type));
}

std::string describe(const Json &v)
{
  if (v.is_null()) {
    return "null";
  }
  if (v.is_boolean()) {
    return "boolean";
  }
  if (v.is_number()) {
    return is_number(v) ? "number" : "non-finite number";
  }
  if (v.is_string()) {
    return "string";
  }
  if (v.is_array()) {
    return "array";
  }
  return "object";
}

const Json *get(const Json &object, std::string_view key)
{
  if (!object.is_object()) {
    return nullptr;
  }
  const auto it = object.find(key);
  return it == object.end() ? nullptr : &*it;
}

/* Python ordering comparisons of JSON numbers (int vs float compare exactly in Python; doubles
 * are exact for every integer schema bound in practice). */
bool less(const Json &a, const Json &b)
{
  if (a.is_number_integer() && b.is_number_integer()) {
    if (a.is_number_unsigned() || b.is_number_unsigned()) {
      if (!a.is_number_unsigned() && a.get<int64_t>() < 0) {
        return !(!b.is_number_unsigned() && b.get<int64_t>() < 0) || a.get<int64_t>() < b.get<int64_t>();
      }
      if (!b.is_number_unsigned() && b.get<int64_t>() < 0) {
        return false;
      }
      return a.get<uint64_t>() < b.get<uint64_t>();
    }
    return a.get<int64_t>() < b.get<int64_t>();
  }
  return a.get<double>() < b.get<double>();
}

bool bound_is_number(const Json *bound)
{
  if (!bound) {
    return false;
  }
  if (!bound->is_number()) {
    throw SchemaError("schema bound is not a number: " + python_json_dumps(*bound));
  }
  return true;
}

double size_bound(const Json &bound)
{
  if (!bound.is_number()) {
    throw SchemaError("schema length bound is not a number: " + python_json_dumps(bound));
  }
  return bound.get<double>();
}

void check(const Json &value, const Json &schema, const std::string &path, std::vector<SchemaIssue> &errors);

std::vector<SchemaIssue> check_branch(const Json &value, const Json &schema, const std::string &path)
{
  std::vector<SchemaIssue> errors;
  check(value, schema, path, errors);
  return errors;
}

SchemaIssue best_branch_error(const Json &value,
                              const Json &branches,
                              const std::vector<std::vector<SchemaIssue>> &results,
                              const std::string &path)
{
  for (size_t k = 0; k < branches.size(); k++) {
    const Json &sub = branches[k];
    const Json *declared = sub.is_object() ? get(sub, "type") : nullptr;
    if (declared && !declared->is_null() && !results[k].empty()) {
      for (const Json &t : type_list(*declared)) {
        if (is_type(value, t)) {
          return results[k][0];
        }
      }
    }
  }
  std::vector<std::string> forms;
  for (const Json &sub : branches) {
    if (sub.is_object() && sub.contains("const")) {
      forms.push_back(short_json(sub["const"]));
    }
    else if (sub.is_object() && sub.contains("enum")) {
      for (const Json &item : sub["enum"]) {
        forms.push_back(short_json(item));
      }
    }
    else if (sub.is_object() && sub.contains("type")) {
      const Json &t = sub["type"];
      if (t.is_string()) {
        forms.push_back(t.get<std::string>());
      }
      else {
        std::string joined;
        for (const Json &name : t) {
          joined += (joined.empty() ? "" : "/") + (name.is_string() ? name.get<std::string>() : python_str(name));
        }
        forms.push_back(joined);
      }
    }
    else {
      forms.push_back("object");
    }
  }
  std::string list;
  for (const std::string &form : forms) {
    list += (list.empty() ? "" : ", ") + form;
  }
  return {path, "got " + short_json(value) + "; expected one of: " + list};
}

bool unique_items_duplicate(const Json &value, size_t &index)
{
  for (size_t i = 0; i < value.size(); i++) {
    for (size_t j = 0; j < i; j++) {
      if (json_equal(value[i], value[j])) {
        index = i;
        return true;
      }
    }
  }
  return false;
}

void check(const Json &value, const Json &schema, const std::string &path, std::vector<SchemaIssue> &errors)
{
  if (schema.is_boolean()) {
    if (!schema.get<bool>()) {
      errors.push_back({path, "no value is allowed here"});
    }
    return;
  }
  if (!schema.is_object()) {
    throw SchemaError("a schema must be an object or a boolean, got " + python_json_dumps(schema));
  }
  if (schema.empty()) {
    return;
  }
  if (const Json *type = get(schema, "type")) {
    const std::vector<Json> types = type_list(*type);
    bool ok = false;
    for (const Json &t : types) {
      ok = ok || is_type(value, t);
    }
    if (!ok) {
      std::string names;
      for (const Json &t : types) {
        names += (names.empty() ? "" : " or ") + t.get<std::string>();
      }
      errors.push_back({path, "expected " + names + ", got " + describe(value)});
      return;
    }
  }
  if (const Json *c = get(schema, "const"); c && !json_equal(value, *c)) {
    errors.push_back({path, "must be " + short_json(*c)});
  }
  if (const Json *options = get(schema, "enum")) {
    bool found = false;
    if (options->is_array()) {
      for (const Json &option : *options) {
        found = found || json_equal(value, option);
      }
    }
    if (!found) {
      errors.push_back({path, "must be one of " + short_json(*options, 200) + ", got " + short_json(value)});
    }
  }
  if (is_number(value)) {
    const Json *minimum = get(schema, "minimum");
    if (bound_is_number(minimum) && less(value, *minimum)) {
      errors.push_back({path, "must be >= " + python_str(*minimum) + ", got " + python_str(value)});
    }
    const Json *maximum = get(schema, "maximum");
    if (bound_is_number(maximum) && less(*maximum, value)) {
      errors.push_back({path, "must be <= " + python_str(*maximum) + ", got " + python_str(value)});
    }
    const Json *xmin = get(schema, "exclusiveMinimum");
    if (bound_is_number(xmin) && !less(*xmin, value)) {
      errors.push_back({path, "must be > " + python_str(*xmin) + ", got " + python_str(value)});
    }
    const Json *xmax = get(schema, "exclusiveMaximum");
    if (bound_is_number(xmax) && !less(value, *xmax)) {
      errors.push_back({path, "must be < " + python_str(*xmax) + ", got " + python_str(value)});
    }
  }
  if (value.is_string()) {
    const std::string &text = value.get_ref<const std::string &>();
    const size_t length = core::utf8::count_code_points(text);
    if (const Json *n = get(schema, "minLength"); n && double(length) < size_bound(*n)) {
      errors.push_back({path, "must have at least " + python_str(*n) + " characters"});
    }
    if (const Json *n = get(schema, "maxLength"); n && double(length) > size_bound(*n)) {
      errors.push_back({path, "must have at most " + python_str(*n) + " characters"});
    }
    if (const Json *pattern = get(schema, "pattern")) {
      if (!pattern->is_string()) {
        throw SchemaError("pattern must be a string");
      }
      bool matched;
      try {
        matched = schema_pattern_search(pattern->get_ref<const std::string &>(), text);
      }
      catch (const RegexError &error) {
        throw SchemaError("unsupported pattern " + pattern->get<std::string>() + ": " + error.what());
      }
      if (!matched) {
        errors.push_back({path, "does not match pattern " + pattern->get<std::string>()});
      }
    }
  }
  if (value.is_array()) {
    const size_t count = value.size();
    if (const Json *n = get(schema, "minItems"); n && double(count) < size_bound(*n)) {
      errors.push_back({path, "must have at least " + python_str(*n) + " items, got " + std::to_string(count)});
    }
    if (const Json *n = get(schema, "maxItems"); n && double(count) > size_bound(*n)) {
      errors.push_back({path, "must have at most " + python_str(*n) + " items, got " + std::to_string(count)});
    }
    const Json *prefix = get(schema, "prefixItems");
    const Json *items = get(schema, "items");
    for (size_t index = 0; index < count; index++) {
      if (prefix && prefix->is_array() && index < prefix->size()) {
        check(value[index], (*prefix)[index], pointer_join(path, index), errors);
      }
      else if (items) {
        check(value[index], *items, pointer_join(path, index), errors);
      }
    }
    if (const Json *unique = get(schema, "uniqueItems"); unique && py_truthy(*unique)) {
      size_t index;
      if (unique_items_duplicate(value, index)) {
        errors.push_back({pointer_join(path, index), "items must be unique"});
      }
    }
  }
  if (value.is_object()) {
    if (const Json *required = get(schema, "required")) {
      for (const Json &key : *required) {
        const std::string name = key.is_string() ? key.get<std::string>() : python_str(key);
        if (!key.is_string() || !value.contains(name)) {
          errors.push_back({pointer_join(path, name), "required key '" + name + "' is missing"});
        }
      }
    }
    if (const Json *n = get(schema, "minProperties"); n && double(value.size()) < size_bound(*n)) {
      errors.push_back({path, "must have at least " + python_str(*n) + " entries"});
    }
    if (const Json *n = get(schema, "maxProperties"); n && double(value.size()) > size_bound(*n)) {
      errors.push_back({path, "must have at most " + python_str(*n) + " entries"});
    }
    static const Json empty = Json::object();
    const Json *properties = get(schema, "properties");
    if (!properties) {
      properties = &empty;
    }
    const Json *patterns = get(schema, "patternProperties");
    const Json *names = get(schema, "propertyNames");
    const Json *extra = get(schema, "additionalProperties");
    for (auto it = value.begin(); it != value.end(); ++it) {
      const std::string &key = it.key();
      const std::string key_path = pointer_join(path, key);
      if (names) {
        for (const SchemaIssue &issue : check_branch(Json(key), *names, {})) {
          errors.push_back({key_path, "invalid key: " + issue.message});
        }
      }
      bool matched = false;
      if (const Json *sub = get(*properties, key)) {
        matched = true;
        check(it.value(), *sub, key_path, errors);
      }
      if (patterns) {
        for (auto p = patterns->begin(); p != patterns->end(); ++p) {
          bool hit;
          try {
            hit = schema_pattern_search(p.key(), key);
          }
          catch (const RegexError &error) {
            throw SchemaError("unsupported pattern " + p.key() + ": " + error.what());
          }
          if (hit) {
            matched = true;
            check(it.value(), p.value(), key_path, errors);
          }
        }
      }
      if (!matched && extra) {
        if (extra->is_boolean() && !extra->get<bool>()) {
          std::vector<std::string> known;
          for (auto k = properties->begin(); k != properties->end(); ++k) {
            known.push_back(k.key());
          }
          std::sort(known.begin(), known.end());
          const std::vector<std::string> close = close_matches(key, known, 1);
          std::string hint;
          if (!close.empty()) {
            hint = " (did you mean '" + close[0] + "'?)";
          }
          else if (!known.empty()) {
            hint = "; allowed: ";
            for (size_t k = 0; k < known.size(); k++) {
              hint += (k ? ", " : "") + known[k];
            }
          }
          errors.push_back({key_path, "unexpected key '" + key + "'" + hint});
        }
        else {
          check(it.value(), *extra, key_path, errors);
        }
      }
    }
  }
  if (const Json *all = get(schema, "allOf")) {
    for (const Json &sub : *all) {
      check(value, sub, path, errors);
    }
  }
  if (const Json *any = get(schema, "anyOf")) {
    std::vector<std::vector<SchemaIssue>> branches;
    bool all_fail = true;
    for (const Json &sub : *any) {
      branches.push_back(check_branch(value, sub, path));
      all_fail = all_fail && !branches.back().empty();
    }
    if (all_fail) {
      errors.push_back(best_branch_error(value, *any, branches, path));
    }
  }
  if (const Json *one = get(schema, "oneOf")) {
    std::vector<std::vector<SchemaIssue>> branches;
    size_t passing = 0;
    for (const Json &sub : *one) {
      branches.push_back(check_branch(value, sub, path));
      passing += branches.back().empty() ? 1 : 0;
    }
    if (passing == 0) {
      errors.push_back(best_branch_error(value, *one, branches, path));
    }
    else if (passing > 1) {
      errors.push_back({path, "matches more than one allowed form"});
    }
  }
  if (const Json *negated = get(schema, "not"); negated && check_branch(value, *negated, path).empty()) {
    errors.push_back({path, "matches a form that is not allowed"});
  }
  if (const Json *condition = get(schema, "if")) {
    if (check_branch(value, *condition, path).empty()) {
      if (const Json *then = get(schema, "then")) {
        check(value, *then, path, errors);
      }
    }
    else if (const Json *otherwise = get(schema, "else")) {
      check(value, *otherwise, path, errors);
    }
  }
}

}  // namespace

bool json_equal(const Json &a, const Json &b)
{
  if (a.is_boolean() || b.is_boolean()) {
    return a.is_boolean() && b.is_boolean() && a.get<bool>() == b.get<bool>();
  }
  if (a.is_number() && b.is_number()) {
    if (a.is_number_integer() && b.is_number_integer()) {
      return !less(a, b) && !less(b, a);
    }
    return a.get<double>() == b.get<double>();
  }
  if (a.is_array() && b.is_array()) {
    if (a.size() != b.size()) {
      return false;
    }
    for (size_t i = 0; i < a.size(); i++) {
      if (!json_equal(a[i], b[i])) {
        return false;
      }
    }
    return true;
  }
  if (a.is_object() && b.is_object()) {
    if (a.size() != b.size()) {
      return false;
    }
    for (auto it = a.begin(); it != a.end(); ++it) {
      const auto other = b.find(it.key());
      if (other == b.end() || !json_equal(it.value(), *other)) {
        return false;
      }
    }
    return true;
  }
  return a.type() == b.type() && a == b;
}

std::vector<SchemaIssue> check_value(const Json &value, const Json &schema, const std::string &path)
{
  std::vector<SchemaIssue> errors;
  check(value, schema, path, errors);
  return errors;
}

namespace {

Json plain(const Json &value)
{
  if (value.is_array()) {
    Json out = Json::array();
    for (const Json &item : value) {
      out.push_back(plain(item));
    }
    return out;
  }
  if (value.is_object()) {
    Json out = Json::object();
    for (auto it = value.begin(); it != value.end(); ++it) {
      out[it.key()] = plain(it.value());
    }
    return out;
  }
  if (value.is_number_float() && value.get<double>() == 0.0) {
    return 0.0;
  }
  return value;
}

}  // namespace

Json normalize_value(const Json &input, const Json &schema)
{
  if (!schema.is_object()) {
    return plain(input);
  }
  Json value = input;
  for (const char *key : {"anyOf", "oneOf"}) {
    if (const Json *branches = get(schema, key)) {
      for (const Json &sub : *branches) {
        if (check_value(value, sub).empty()) {
          value = normalize_value(value, sub);
          break;
        }
      }
    }
  }
  std::vector<std::string> types;
  if (const Json *type = get(schema, "type")) {
    if (type->is_string()) {
      types.push_back(type->get<std::string>());
    }
    else if (type->is_array()) {
      for (const Json &t : *type) {
        if (t.is_string()) {
          types.push_back(t.get<std::string>());
        }
      }
    }
  }
  const auto has = [&](const char *name) { return std::find(types.begin(), types.end(), name) != types.end(); };
  if (is_number(value)) {
    const double d = value.get<double>();
    if (has("integer") && std::floor(d) == d && !has("number")) {
      if (value.is_number_integer()) {
        return value;
      }
      if (std::fabs(d) < 9.2e18) {
        return Json(int64_t(d));
      }
      return value;
    }
    if (has("number")) {
      return Json(d == 0.0 ? 0.0 : d);
    }
    return value;
  }
  if (value.is_array()) {
    const Json *prefix = get(schema, "prefixItems");
    const Json *items = get(schema, "items");
    Json out = Json::array();
    for (size_t i = 0; i < value.size(); i++) {
      if (prefix && prefix->is_array() && i < prefix->size()) {
        out.push_back(normalize_value(value[i], (*prefix)[i]));
      }
      else {
        out.push_back(normalize_value(value[i], items ? *items : Json(true)));
      }
    }
    return out;
  }
  if (value.is_object()) {
    const Json *properties = get(schema, "properties");
    const Json *extra = get(schema, "additionalProperties");
    Json out = Json::object();
    for (auto it = value.begin(); it != value.end(); ++it) {
      const Json *sub = properties ? get(*properties, it.key()) : nullptr;
      if (sub) {
        out[it.key()] = normalize_value(it.value(), *sub);
      }
      else {
        out[it.key()] = normalize_value(it.value(), (extra && extra->is_object()) ? *extra : Json(true));
      }
    }
    return out;
  }
  return value;
}

/* ------------------------------------------------------------------------------------------ */
/* difflib.SequenceMatcher (isjunk=None, autojunk=True) and get_close_matches */

namespace {

class SequenceMatcher {
 public:
  SequenceMatcher(std::u32string a, std::u32string b) : a_(std::move(a)), b_(std::move(b))
  {
    for (size_t j = 0; j < b_.size(); j++) {
      b2j_[b_[j]].push_back(j);
    }
    const size_t n = b_.size();
    if (n >= 200) {
      const size_t ntest = n / 100 + 1;
      for (auto it = b2j_.begin(); it != b2j_.end();) {
        it = it->second.size() > ntest ? b2j_.erase(it) : std::next(it);
      }
    }
  }

  double ratio()
  {
    size_t matches = 0;
    std::vector<std::array<size_t, 4>> queue{{0, a_.size(), 0, b_.size()}};
    while (!queue.empty()) {
      const auto [alo, ahi, blo, bhi] = queue.back();
      queue.pop_back();
      size_t i, j, k;
      longest(alo, ahi, blo, bhi, i, j, k);
      if (k) {
        matches += k;
        if (alo < i && blo < j) {
          queue.push_back({alo, i, blo, j});
        }
        if (i + k < ahi && j + k < bhi) {
          queue.push_back({i + k, ahi, j + k, bhi});
        }
      }
    }
    return calculate(matches);
  }

  double quick_ratio() const
  {
    std::unordered_map<char32_t, long> counts;
    for (char32_t c : b_) {
      counts[c]++;
    }
    size_t matches = 0;
    std::unordered_map<char32_t, long> avail;
    for (char32_t c : a_) {
      auto it = avail.find(c);
      long n = it != avail.end() ? it->second : counts[c];
      avail[c] = n - 1;
      if (n > 0) {
        matches++;
      }
    }
    return calculate(matches);
  }

  double real_quick_ratio() const
  {
    return calculate(std::min(a_.size(), b_.size()));
  }

 private:
  double calculate(size_t matches) const
  {
    const size_t length = a_.size() + b_.size();
    return length ? 2.0 * double(matches) / double(length) : 1.0;
  }

  void longest(size_t alo, size_t ahi, size_t blo, size_t bhi, size_t &besti, size_t &bestj, size_t &bestsize)
  {
    besti = alo;
    bestj = blo;
    bestsize = 0;
    std::unordered_map<size_t, size_t> j2len, next;
    for (size_t i = alo; i < ahi; i++) {
      next.clear();
      const auto found = b2j_.find(a_[i]);
      if (found != b2j_.end()) {
        for (size_t j : found->second) {
          if (j < blo) {
            continue;
          }
          if (j >= bhi) {
            break;
          }
          const auto prev = j > 0 ? j2len.find(j - 1) : j2len.end();
          const size_t k = (prev != j2len.end() ? prev->second : 0) + 1;
          next[j] = k;
          if (k > bestsize) {
            besti = i - k + 1;
            bestj = j - k + 1;
            bestsize = k;
          }
        }
      }
      std::swap(j2len, next);
    }
    /* No junk: extend the match with equal neighbours (popular elements are not junk). */
    while (besti > alo && bestj > blo && a_[besti - 1] == b_[bestj - 1]) {
      besti--;
      bestj--;
      bestsize++;
    }
    while (besti + bestsize < ahi && bestj + bestsize < bhi && a_[besti + bestsize] == b_[bestj + bestsize]) {
      bestsize++;
    }
  }

  std::u32string a_, b_;
  std::map<char32_t, std::vector<size_t>> b2j_;
};

}  // namespace

std::vector<std::string> close_matches(std::string_view word,
                                       const std::vector<std::string> &possibilities,
                                       size_t n,
                                       double cutoff)
{
  const std::u32string b = core::utf8::to_utf32(word);
  std::vector<std::pair<double, std::string>> scored;
  for (const std::string &x : possibilities) {
    SequenceMatcher matcher(core::utf8::to_utf32(x), b);
    if (matcher.real_quick_ratio() >= cutoff && matcher.quick_ratio() >= cutoff) {
      const double score = matcher.ratio();
      if (score >= cutoff) {
        scored.emplace_back(score, x);
      }
    }
  }
  /* heapq.nlargest(n, [(score, x)]): descending by score, then by x. */
  std::sort(scored.begin(), scored.end(), [](const auto &l, const auto &r) {
    return l.first != r.first ? l.first > r.first : l.second > r.second;
  });
  std::vector<std::string> out;
  for (size_t k = 0; k < scored.size() && k < n; k++) {
    out.push_back(scored[k].second);
  }
  return out;
}

}  // namespace stk::io

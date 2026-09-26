/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "stk/app/jobs_spec.hh"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <mutex>
#include <random>
#include <regex>

#include "stk/core/utf8.hh"

namespace stk::app {

namespace {

/* suan/runtime/models.py */
constexpr int64_t kMaxInt = 2147483647;
constexpr size_t kMaxName = 200;
const char *const kReservedEnv[] = {"SLURM_JOB_ID", "PBS_JOBID", "STK_MUPRO_ALLOW_LOCAL_MPI", "STK_MONITOR_PATH",
                                    "STK_TASK_ID"};

bool is_space(const char c)
{
  return c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\f' || c == '\v';
}

bool valid_env_name(std::string_view name)
{
  if (name.empty() || !(std::isalpha(uint8_t(name[0])) || name[0] == '_')) {
    return false;
  }
  for (const char c : name) {
    if (!(std::isalnum(uint8_t(c)) || c == '_') || uint8_t(c) >= 0x80) {
      return false;
    }
  }
  return true;
}

bool valid_queue(std::string_view v)
{
  if (v.empty()) {
    return false;
  }
  for (const char c : v) {
    if (!(std::isalnum(uint8_t(c)) || c == '_' || c == '.' || c == '@' || c == '/' || c == '-') || uint8_t(c) >= 0x80) {
      return false;
    }
  }
  return true;
}

/** suan.runtime.models.relative_path */
bool valid_relative_path(std::string_view p)
{
  if (p.empty() || p.find('\\') != std::string_view::npos || p.find('\0') != std::string_view::npos ||
      p.find(':') != std::string_view::npos || p == "." || p.front() == '/')
  {
    return false;
  }
  size_t start = 0;
  while (start <= p.size()) {
    size_t end = p.find('/', start);
    if (end == std::string_view::npos) {
      end = p.size();
    }
    if (p.substr(start, end - start) == "..") {
      return false;
    }
    start = end + 1;
  }
  return true;
}

FormIssue issue(std::string field, std::string key, std::vector<std::pair<std::string, std::string>> args = {})
{
  return {std::move(field), std::move(key), std::move(args)};
}

}  // namespace

std::optional<std::vector<std::string>> shlex_split(const std::string_view text, std::string *r_error)
{
  std::vector<std::string> out;
  std::string token;
  bool have = false;
  enum class Q { None, Single, Double } q = Q::None;
  for (size_t i = 0; i < text.size(); i++) {
    const char c = text[i];
    switch (q) {
      case Q::None:
        if (is_space(c)) {
          if (have) {
            out.push_back(std::move(token));
            token.clear();
            have = false;
          }
        }
        else if (c == '\'') {
          q = Q::Single;
          have = true;
        }
        else if (c == '"') {
          q = Q::Double;
          have = true;
        }
        else if (c == '\\') {
          if (i + 1 >= text.size()) {
            if (r_error) {
              *r_error = "escape";
            }
            return std::nullopt;
          }
          token += text[++i];
          have = true;
        }
        else {
          token += c;
          have = true;
        }
        break;
      case Q::Single:
        if (c == '\'') {
          q = Q::None;
        }
        else {
          token += c;
        }
        break;
      case Q::Double:
        if (c == '"') {
          q = Q::None;
        }
        else if (c == '\\' && i + 1 < text.size() && (text[i + 1] == '\\' || text[i + 1] == '"')) {
          /* shlex (POSIX): inside double quotes only the quote and the escape char are escaped. */
          token += text[++i];
        }
        else {
          token += c;
        }
        break;
    }
  }
  if (q != Q::None) {
    if (r_error) {
      *r_error = "quote";
    }
    return std::nullopt;
  }
  if (have) {
    out.push_back(std::move(token));
  }
  return out;
}

std::string shlex_quote(const std::string_view arg)
{
  if (arg.empty()) {
    return "''";
  }
  bool safe = true;
  for (const char c : arg) {
    if (!(std::isalnum(uint8_t(c)) || std::string_view("@%+=:,./-_").find(c) != std::string_view::npos) ||
        uint8_t(c) >= 0x80)
    {
      safe = false;
      break;
    }
  }
  if (safe) {
    return std::string(arg);
  }
  std::string out = "'";
  for (const char c : arg) {
    if (c == '\'') {
      out += "'\"'\"'";
    }
    else {
      out += c;
    }
  }
  return out + "'";
}

std::string new_idempotency_key()
{
  static std::mutex m;
  static std::mt19937_64 rng{[] {
    std::random_device rd;
    std::seed_seq seq{rd(), rd(), rd(), rd(), rd(), rd()};
    return std::mt19937_64(seq);
  }()};
  std::lock_guard lock(m);
  char buf[40];
  snprintf(buf, sizeof(buf), "%016llx%016llx", (unsigned long long)rng(), (unsigned long long)rng());
  return buf;
}

std::optional<FormIssue> check_resources(const Json &resources, const std::string_view backend)
{
  if (!resources.is_object()) {
    return issue("resources", "jobs.form.err.resources");
  }
  static const char *const known[] = {"cpus", "nodes", "memory_mb", "walltime_seconds", "gpus", "queue", "account",
                                      "ranks", "threads_per_rank"};
  for (auto it = resources.begin(); it != resources.end(); ++it) {
    const std::string &k = it.key();
    if (std::find(std::begin(known), std::end(known), k) == std::end(known)) {
      return issue("resources", "jobs.form.err.resources");
    }
    if (k == "queue" || k == "account") {
      if (!it->is_string() || !valid_queue(it->get<std::string>())) {
        return issue("resources." + k, "jobs.form.err.queue", {{"field", k}});
      }
    }
    else {
      const int64_t lo = k == "gpus" ? 0 : 1;
      if (!it->is_number_integer() || it->get<int64_t>() < lo || it->get<int64_t>() > kMaxInt) {
        return issue("resources." + k, "jobs.form.err.positive", {{"field", k}});
      }
    }
  }
  const bool mpi = resources.contains("ranks") || resources.contains("threads_per_rank");
  if (mpi) {
    if (resources.contains("cpus")) {
      return issue("resources.cpus", "jobs.form.err.cpus_mpi");
    }
    const int64_t ranks = resources.value("ranks", int64_t(1)), nodes = resources.value("nodes", int64_t(1));
    if (ranks % nodes != 0) {
      return issue("resources.ranks", "jobs.form.err.ranks_nodes");
    }
  }
  if (backend == "local" && (resources.value("nodes", int64_t(1)) != 1 || resources.value("gpus", int64_t(0)) != 0 ||
                             resources.contains("queue") || resources.contains("account")))
  {
    return issue("resources", "jobs.form.err.local_resources");
  }
  return std::nullopt;
}

std::vector<FormIssue> validate_form(const SubmitForm &form, const std::string_view workspace_id, const bool hub)
{
  std::vector<FormIssue> out;
  static const std::regex hex32("^[a-f0-9]{32}$");
  if (workspace_id.empty()) {
    out.push_back(issue("workspace", "jobs.form.err.workspace"));
  }
  else if (!std::regex_match(std::string(workspace_id), hex32)) {
    out.push_back(issue("workspace", "jobs.form.err.workspace_id"));
  }
  if (hub && form.use_template) {
    if (form.template_name.empty()) {
      out.push_back(issue("template", "jobs.form.err.template"));
    }
    return out;
  }
  if (core::utf8::count_code_points(form.name) > kMaxName) {
    out.push_back(issue("name", "jobs.form.err.name_long", {{"max", std::to_string(kMaxName)}}));
  }
  if (form.name.find('\0') != std::string::npos) {
    out.push_back(issue("name", "jobs.form.err.nul"));
  }
  std::string program = form.program;
  while (!program.empty() && is_space(program.back())) {
    program.pop_back();
  }
  while (!program.empty() && is_space(program.front())) {
    program.erase(program.begin());
  }
  if (program.empty()) {
    out.push_back(issue("program", "jobs.form.err.program"));
  }
  std::string err;
  const auto args = shlex_split(form.arguments, &err);
  if (!args) {
    out.push_back(issue("arguments", err == "quote" ? "jobs.form.err.quote" : "jobs.form.err.escape"));
  }
  else {
    for (const std::string &a : *args) {
      if (a.find('\0') != std::string::npos) {
        out.push_back(issue("arguments", "jobs.form.err.nul"));
        break;
      }
    }
  }
  if (const auto outs = shlex_split(form.outputs, &err)) {
    for (const std::string &p : *outs) {
      if (!valid_relative_path(p)) {
        out.push_back(issue("outputs", "jobs.form.err.output_path", {{"path", p}}));
        break;
      }
    }
  }
  else {
    out.push_back(issue("outputs", err == "quote" ? "jobs.form.err.quote" : "jobs.form.err.escape"));
  }
  if (const auto env = shlex_split(form.env, &err)) {
    for (const std::string &t : *env) {
      const size_t eq = t.find('=');
      if (eq == std::string::npos) {
        out.push_back(issue("env", "jobs.form.err.env_format", {{"token", t}}));
        break;
      }
      const std::string name = t.substr(0, eq);
      if (!valid_env_name(name)) {
        out.push_back(issue("env", "jobs.form.err.env_name", {{"name", name}}));
        break;
      }
      if (std::find(std::begin(kReservedEnv), std::end(kReservedEnv), name) != std::end(kReservedEnv)) {
        out.push_back(issue("env", "jobs.form.err.env_reserved", {{"name", name}}));
        break;
      }
      if (t.find('\0') != std::string::npos) {
        out.push_back(issue("env", "jobs.form.err.nul"));
        break;
      }
    }
  }
  else {
    out.push_back(issue("env", err == "quote" ? "jobs.form.err.quote" : "jobs.form.err.escape"));
  }
  if (form.layout == LayoutMode::Mpi && form.ranks < 1) {
    out.push_back(issue("resources.ranks", "jobs.form.err.ranks_required"));
  }
  if (form.backend < 0 || form.backend >= int(std::size(kBackends))) {
    out.push_back(issue("backend", "jobs.form.err.backend"));
    return out;
  }
  const Json spec = form_to_spec(form, std::string(workspace_id));
  if (auto r = check_resources(spec["resources"], kBackends[form.backend])) {
    out.push_back(std::move(*r));
  }
  return out;
}

Json form_to_spec(const SubmitForm &form, const std::string &workspace_id)
{
  Json spec = Json::object();
  spec["workspace_id"] = workspace_id;
  Json argv = Json::array();
  std::string program = form.program;
  while (!program.empty() && is_space(program.back())) {
    program.pop_back();
  }
  while (!program.empty() && is_space(program.front())) {
    program.erase(program.begin());
  }
  argv.push_back(program);
  if (const auto args = shlex_split(form.arguments)) {
    for (const std::string &a : *args) {
      argv.push_back(a);
    }
  }
  spec["argv"] = argv;
  spec["backend"] = kBackends[std::clamp(form.backend, 0, int(std::size(kBackends)) - 1)];
  spec["name"] = form.name;
  Json outputs = Json::array();
  if (const auto outs = shlex_split(form.outputs)) {
    for (const std::string &p : *outs) {
      outputs.push_back(p);
    }
  }
  if (!outputs.empty()) {
    spec["outputs"] = outputs;
  }
  Json env = Json::object();
  if (const auto toks = shlex_split(form.env)) {
    for (const std::string &t : *toks) {
      const size_t eq = t.find('=');
      if (eq != std::string::npos) {
        env[t.substr(0, eq)] = t.substr(eq + 1);
      }
    }
  }
  if (!env.empty()) {
    spec["env"] = env;
  }
  Json res = Json::object();
  if (form.layout == LayoutMode::Threads) {
    res["cpus"] = form.cpus;
  }
  else {
    res["ranks"] = form.ranks;
    if (form.threads_per_rank > 0) {
      res["threads_per_rank"] = form.threads_per_rank;
    }
  }
  res["nodes"] = form.nodes;
  if (form.memory_mb > 0) {
    res["memory_mb"] = form.memory_mb;
  }
  if (form.walltime_s > 0) {
    res["walltime_seconds"] = form.walltime_s;
  }
  if (form.gpus > 0) {
    res["gpus"] = form.gpus;
  }
  auto trimmed = [](std::string s) {
    while (!s.empty() && is_space(s.back())) {
      s.pop_back();
    }
    while (!s.empty() && is_space(s.front())) {
      s.erase(s.begin());
    }
    return s;
  };
  if (const std::string q = trimmed(form.queue); !q.empty()) {
    res["queue"] = q;
  }
  if (const std::string a = trimmed(form.account); !a.empty()) {
    res["account"] = a;
  }
  spec["resources"] = res;
  return spec;
}

}  // namespace stk::app

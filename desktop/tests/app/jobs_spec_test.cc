/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file The submit form: shlex splitting (Python's shlex.split), TaskSpec validation rules
 * (suan/runtime/models.py) and the spec JSON sent with task.submit. */

#include <set>

#include <gtest/gtest.h>

#include "stk/app/jobs_spec.hh"

namespace stk::app {
namespace {

const std::string kWs = "a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0";

std::vector<std::string> split(const std::string &s)
{
  auto r = shlex_split(s);
  EXPECT_TRUE(r.has_value()) << s;
  return r.value_or(std::vector<std::string>{});
}

std::set<std::string> issue_keys(const SubmitForm &f, const std::string &ws = kWs, bool hub = false)
{
  std::set<std::string> keys;
  for (const FormIssue &i : validate_form(f, ws, hub)) {
    keys.insert(i.key);
  }
  return keys;
}

TEST(JobsSpec, ShlexSplitsLikePython)
{
  EXPECT_EQ(split("simulate.py --input input.json"),
            (std::vector<std::string>{"simulate.py", "--input", "input.json"}));
  EXPECT_EQ(split("  a   b\t c \n"), (std::vector<std::string>{"a", "b", "c"}));
  EXPECT_EQ(split("'a b' \"c d\" e\\ f"), (std::vector<std::string>{"a b", "c d", "e f"}));
  EXPECT_EQ(split("\"a \\\"q\\\" \\\\ \\x\""), (std::vector<std::string>{"a \"q\" \\ \\x"}));
  EXPECT_EQ(split("'it'\"'\"'s'"), (std::vector<std::string>{"it's"}));
  EXPECT_EQ(split("\"\" ''"), (std::vector<std::string>{"", ""}));
  EXPECT_EQ(split("--name=铁电畴 '300 K'"), (std::vector<std::string>{"--name=铁电畴", "300 K"}));
  EXPECT_EQ(split("a#b # c"), (std::vector<std::string>{"a#b", "#", "c"})); /* no comments */
  EXPECT_TRUE(split("").empty());
  std::string err;
  EXPECT_FALSE(shlex_split("'open", &err));
  EXPECT_EQ(err, "quote");
  EXPECT_FALSE(shlex_split("\"open", &err));
  EXPECT_EQ(err, "quote");
  EXPECT_FALSE(shlex_split("end\\", &err));
  EXPECT_EQ(err, "escape");
}

TEST(JobsSpec, QuoteRoundTrips)
{
  for (const std::string s : {"plain", "with space", "it's", "", "铁电畴", "$HOME", "a\"b"}) {
    const auto back = shlex_split(shlex_quote(s));
    ASSERT_TRUE(back.has_value()) << s;
    ASSERT_EQ(back->size(), 1u) << s;
    EXPECT_EQ(back->front(), s);
  }
  EXPECT_EQ(shlex_quote("simple-path/x.py"), "simple-path/x.py");
}

TEST(JobsSpec, IdempotencyKeysAreFresh32Hex)
{
  std::set<std::string> keys;
  for (int i = 0; i < 200; i++) {
    const std::string k = new_idempotency_key();
    ASSERT_EQ(k.size(), 32u);
    ASSERT_EQ(k.find_first_not_of("0123456789abcdef"), std::string::npos);
    keys.insert(k);
  }
  EXPECT_EQ(keys.size(), 200u);
}

TEST(JobsSpec, DefaultFormIsValidAndBuildsTheLegacySpec)
{
  SubmitForm f;
  f.name = "铁电畴 300K";
  f.arguments = "simulate.py --input 'input 1.json'";
  EXPECT_TRUE(validate_form(f, kWs, false).empty());
  const Json spec = form_to_spec(f, kWs);
  EXPECT_EQ(spec["workspace_id"], kWs);
  EXPECT_EQ(spec["argv"], Json::array({"{python}", "simulate.py", "--input", "input 1.json"}));
  EXPECT_EQ(spec["backend"], "local");
  EXPECT_EQ(spec["name"], "铁电畴 300K");
  /* As the legacy tab: cpus and nodes always, the rest only when set. */
  EXPECT_EQ(spec["resources"], (Json{{"cpus", 1}, {"nodes", 1}}));
  EXPECT_FALSE(spec.contains("outputs"));
  EXPECT_FALSE(spec.contains("env"));
}

TEST(JobsSpec, ResourcesOutputsAndEnvironment)
{
  SubmitForm f;
  f.backend = 2; /* slurm */
  f.layout = LayoutMode::Mpi;
  f.ranks = 8;
  f.threads_per_rank = 2;
  f.nodes = 2;
  f.memory_mb = 4096;
  f.walltime_s = 3600;
  f.gpus = 1;
  f.queue = " debug ";
  f.account = "proj@lab";
  f.outputs = "result.png out/Polar.dat";
  f.env = "OMP_PROC_BIND=close 'NOTE=a b'";
  ASSERT_TRUE(validate_form(f, kWs, false).empty());
  const Json spec = form_to_spec(f, kWs);
  EXPECT_EQ(spec["backend"], "slurm");
  EXPECT_EQ(spec["resources"], (Json{{"ranks", 8}, {"threads_per_rank", 2}, {"nodes", 2}, {"memory_mb", 4096},
                                     {"walltime_seconds", 3600}, {"gpus", 1}, {"queue", "debug"},
                                     {"account", "proj@lab"}}));
  EXPECT_EQ(spec["outputs"], Json::array({"result.png", "out/Polar.dat"}));
  EXPECT_EQ(spec["env"], (Json{{"OMP_PROC_BIND", "close"}, {"NOTE", "a b"}}));
}

TEST(JobsSpec, ValidationFollowsTheRuntimeTaskSpec)
{
  SubmitForm f;
  EXPECT_EQ(issue_keys(f, ""), std::set<std::string>{"jobs.form.err.workspace"});
  EXPECT_EQ(issue_keys(f, "not-hex"), std::set<std::string>{"jobs.form.err.workspace_id"});
  f.program = "  ";
  EXPECT_TRUE(issue_keys(f).count("jobs.form.err.program"));
  f.program = "{python}";
  f.arguments = "'unterminated";
  EXPECT_TRUE(issue_keys(f).count("jobs.form.err.quote"));
  f.arguments = "";
  f.name = std::string(200, 'x');
  EXPECT_TRUE(issue_keys(f).empty());
  f.name = std::string(201 * 3, '\0');
  f.name.clear();
  for (int i = 0; i < 201; i++) {
    f.name += "铁"; /* 201 characters, 603 bytes: counted in characters like Python */
  }
  EXPECT_TRUE(issue_keys(f).count("jobs.form.err.name_long"));
  f.name = "ok";
  f.outputs = "../escape.dat";
  EXPECT_TRUE(issue_keys(f).count("jobs.form.err.output_path"));
  f.outputs = "/abs/path";
  EXPECT_TRUE(issue_keys(f).count("jobs.form.err.output_path"));
  f.outputs = "c:drive";
  EXPECT_TRUE(issue_keys(f).count("jobs.form.err.output_path"));
  f.outputs = "";
  f.env = "NOEQUALS";
  EXPECT_TRUE(issue_keys(f).count("jobs.form.err.env_format"));
  f.env = "1BAD=x";
  EXPECT_TRUE(issue_keys(f).count("jobs.form.err.env_name"));
  f.env = "STK_TASK_ID=x";
  EXPECT_TRUE(issue_keys(f).count("jobs.form.err.env_reserved"));
  f.env = "";
  /* Local tasks: one node, no GPUs, queue or account. */
  f.nodes = 2;
  EXPECT_TRUE(issue_keys(f).count("jobs.form.err.local_resources"));
  f.nodes = 1;
  f.queue = "q";
  EXPECT_TRUE(issue_keys(f).count("jobs.form.err.local_resources"));
  f.queue = "";
  /* Cluster backends: queue / account characters, MPI ranks a multiple of the nodes. */
  f.backend = 1;
  f.queue = "bad queue";
  EXPECT_TRUE(issue_keys(f).count("jobs.form.err.queue"));
  f.queue = "";
  f.layout = LayoutMode::Mpi;
  f.ranks = 0;
  EXPECT_TRUE(issue_keys(f).count("jobs.form.err.ranks_required"));
  f.ranks = 6;
  f.nodes = 4;
  EXPECT_TRUE(issue_keys(f).count("jobs.form.err.ranks_nodes"));
  f.nodes = 3;
  EXPECT_TRUE(issue_keys(f).empty());
}

TEST(JobsSpec, ResourceChecksOnSpecs)
{
  EXPECT_FALSE(check_resources(Json{{"cpus", 4}, {"nodes", 1}}, "local"));
  EXPECT_EQ(check_resources(Json{{"cpus", 4}, {"ranks", 2}}, "slurm")->key, "jobs.form.err.cpus_mpi");
  EXPECT_EQ(check_resources(Json{{"cpus", 0}}, "slurm")->key, "jobs.form.err.positive");
  EXPECT_EQ(check_resources(Json{{"cpus", 2147483648LL}}, "slurm")->key, "jobs.form.err.positive");
  EXPECT_FALSE(check_resources(Json{{"gpus", 0}}, "slurm"));
  EXPECT_EQ(check_resources(Json{{"bogus", 1}}, "slurm")->key, "jobs.form.err.resources");
}

TEST(JobsSpec, HubTemplatesNeedOnlyATemplateAndAWorkspace)
{
  SubmitForm f;
  f.use_template = true;
  f.program.clear(); /* ignored for templates */
  EXPECT_EQ(issue_keys(f, kWs, true), std::set<std::string>{"jobs.form.err.template"});
  f.template_name = "muferro-small";
  EXPECT_TRUE(issue_keys(f, kWs, true).empty());
  /* Not a hub: the template switch is ignored and the command is checked. */
  EXPECT_TRUE(issue_keys(f, kWs, false).count("jobs.form.err.program"));
}

}  // namespace
}  // namespace stk::app

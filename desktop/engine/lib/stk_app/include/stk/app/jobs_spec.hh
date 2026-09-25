/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * The Jobs editor's submit form as data: fields, validation with the rules of the Runtime's
 * `TaskSpec` (suan/runtime/models.py, so errors appear before anything is sent), conversion to the
 * spec JSON of `task.submit`, POSIX shell-style argument splitting (Python's `shlex.split`, as the
 * legacy Tasks tab used) and idempotency keys. No UI and no bridge: unit-testable.
 */
#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "stk/io/json.hh"

namespace stk::app {

using Json = io::Json;

/** Execution backends of the Runtime (`BACKENDS`). */
inline constexpr const char *kBackends[] = {"local", "pbs", "slurm"};

/** How the process layout is given (TaskSpec: `cpus` or MPI `ranks`/`threads_per_rank`, not both). */
enum class LayoutMode : uint8_t { Threads, Mpi };

/** When a failed submission is sent again with the same idempotency key. */
struct RetryPolicy {
  /** Automatic re-sends after retryable errors (unavailable, busy, timeout, HTTP 5xx); 0 = none. */
  int auto_retries = 2;
  /** Delay before the first automatic re-send; doubles each time. */
  double backoff_s = 2.0;
};

struct SubmitForm {
  /* Hub connections: a registered template instead of a custom command. */
  bool use_template = false;
  std::string template_name;

  std::string name;                  /**< Task name, <= 200 characters (any script, IME input). */
  std::string program = "{python}";  /**< argv[0]; {python}, {ranks}, ... are expanded by the Runtime. */
  std::string arguments;             /**< shlex-split into argv[1:]. */
  int backend = 0;                   /**< Index into kBackends. */

  /* Resources; 0 = not set (the environment's default), as in the legacy tab. */
  LayoutMode layout = LayoutMode::Threads;
  int cpus = 1;             /**< Threads per node (Threads mode). */
  int ranks = 0;            /**< MPI ranks (Mpi mode). */
  int threads_per_rank = 0; /**< MPI threads per rank (Mpi mode). */
  int nodes = 1;
  int memory_mb = 0;
  int walltime_s = 0;
  int gpus = 0;
  std::string queue, account;

  /** Expected outputs (shlex-split relative paths; the task fails when one is missing). */
  std::string outputs;
  /** Environment variables: shlex-split KEY=VALUE tokens. */
  std::string env;

  RetryPolicy retry;
};

/** One validation problem: the field ("name", "arguments", "resources.nodes", ...) and a catalog
 * key with its arguments (the UI formats it in the current language). */
struct FormIssue {
  std::string field;
  std::string key;
  std::vector<std::pair<std::string, std::string>> args;
};

/** Python's `shlex.split(text)` (POSIX mode, no comments). nullopt with `r_error` ("quote",
 * "escape") on an unterminated quote or a trailing backslash. */
std::optional<std::vector<std::string>> shlex_split(std::string_view text, std::string *r_error = nullptr);

/** Quotes one argument like Python's `shlex.quote` (display of submitted commands). */
std::string shlex_quote(std::string_view arg);

/** A fresh random 32-hex idempotency key (uuid4().hex form). */
std::string new_idempotency_key();

/** Checks the form against the TaskSpec rules; empty when it can be sent. `workspace_id` empty
 * gives the "choose a workspace" issue. */
std::vector<FormIssue> validate_form(const SubmitForm &form, std::string_view workspace_id, bool hub);

/** The Runtime TaskSpec of a valid form (only fields that are set: resources never get defaults,
 * because the spec feeds the Runtime's idempotency hash). */
Json form_to_spec(const SubmitForm &form, const std::string &workspace_id);

/** Whether a TaskSpec resources object is valid for `backend` (the rules of validate_form, for
 * specs built elsewhere); the first issue otherwise. */
std::optional<FormIssue> check_resources(const Json &resources, std::string_view backend);

}  // namespace stk::app

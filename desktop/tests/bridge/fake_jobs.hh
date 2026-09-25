/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file The `--jobs DIR` mode of stk-bridge-fake: a fake Runtime and hub for the Jobs editor tests. */
#pragma once

#include <functional>
#include <string>
#include <vector>

#include "stk/io/json.hh"

namespace fake_jobs {

using SendFn = std::function<void(const stk::io::Json &)>;

/** Loads (or creates) DIR/model.json; `args` are the fake's command-line arguments. */
void init(const std::string &dir, std::vector<std::string> args, SendFn send);
/** Answers `method` when the jobs model implements it (true), else leaves it to the fake. */
bool handle(const stk::io::Json &id, const std::string &method, const stk::io::Json &params);
/** Stdin EOF: stops the ticker and the streams, records "EOF" in DIR/methods.log. */
void shutdown();

}  // namespace fake_jobs

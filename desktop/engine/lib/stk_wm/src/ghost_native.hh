/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file Internal: GHOST system internals needed by the event loop (see ghost_native.cc). */
#pragma once

#include <cstdint>

class GHOST_ISystem;

namespace stk::wm::detail {

/** Milliseconds until GHOST's next timer is due (0 when overdue), -1 when no timer is installed. */
int64_t ghost_ms_until_next_timer(GHOST_ISystem &system);

/** The system is GHOST's X11 back-end (and it was compiled in). */
bool ghost_x11_wait_supported(GHOST_ISystem &system);

/**
 * Sleeps until the X connection is readable, `wake_fd` is readable or the next GHOST timer is due
 * (returns at once when Xlib already holds events). Only valid when #ghost_x11_wait_supported.
 */
void ghost_x11_wait(GHOST_ISystem &system, int wake_fd);

}  // namespace stk::wm::detail

/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file
 * The one stk_wm file that sees GHOST's internal system classes. It is compiled with
 * bf_intern_ghost's own compile definitions (see CMakeLists.txt) so the class layouts match the
 * GHOST library exactly.
 *
 * X11 wait: GHOST_SystemX11::processEvents(true) sleeps in select() on the X connection only, so
 * another thread cannot end it. stk_wm therefore waits itself -- poll() on the X connection and the
 * post queue's eventfd, bounded by GHOST's next timer, after XPending() found nothing queued -- and
 * then lets GHOST drain everything with processEvents(false). That is the same wait GHOST does
 * (GHOST's dirty-window list only grows through GHOST_IWindow::invalidate, which stk_wm never calls).
 */

#include "ghost_native.hh"

#include <cstring>

#include "intern/GHOST_System.hh"
#include "intern/GHOST_TimerManager.hh"

#if defined(WITH_GHOST_X11)
#  include "intern/GHOST_SystemX11.hh"
#  include <cerrno>
#  include <poll.h>
#endif

namespace stk::wm::detail {

int64_t ghost_ms_until_next_timer(GHOST_ISystem &system)
{
  auto &ghost = static_cast<GHOST_System &>(system);
  const uint64_t next = ghost.getTimerManager()->nextFireTime();
  if (next == GHOST_kFireTimeNever) {
    return -1;
  }
  const uint64_t now = ghost.getMilliSeconds();
  return next > now ? int64_t(next - now) : 0;
}

bool ghost_x11_wait_supported(GHOST_ISystem & /*system*/)
{
#if defined(WITH_GHOST_X11)
  const char *backend = GHOST_ISystem::getSystemBackend();
  return backend && strcmp(backend, "X11") == 0;
#else
  return false;
#endif
}

void ghost_x11_wait(GHOST_ISystem &system, const int wake_fd)
{
#if defined(WITH_GHOST_X11)
  auto &x11 = static_cast<GHOST_SystemX11 &>(system);
  Display *display = x11.getXDisplay();
  /* XPending flushes queued requests and reads what already arrived: never sleep on events that
   * Xlib holds in its own queue. */
  if (XPending(display) > 0) {
    return;
  }
  const int64_t timeout = ghost_ms_until_next_timer(system);
  pollfd fds[2] = {{ConnectionNumber(display), POLLIN, 0}, {wake_fd, POLLIN, 0}};
  const int count = wake_fd >= 0 ? 2 : 1;
  const int ms = timeout < 0 ? -1 : (timeout > 1000 * 60 * 60 ? 1000 * 60 * 60 : int(timeout));
  while (poll(fds, nfds_t(count), ms) < 0 && errno == EINTR) {
  }
#else
  (void)system;
  (void)wake_fd;
#endif
}

}  // namespace stk::wm::detail

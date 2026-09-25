/* SPDX-License-Identifier: GPL-2.0-or-later */
/* stk_app viewer GPU tests: one GPU backend per process (--gpu-backend vulkan|opengl|metal),
 * headless. Exit code 77 (ctest SKIP_RETURN_CODE) when the backend cannot be initialized or no
 * test ran (the Python bridge is unavailable). */

#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include <gtest/gtest.h>

#include "stk/gfx/gpu.hh"

namespace stk::apptest {
gfx::Gpu *g_gpu = nullptr;
bool g_skipped_all = false;
}  // namespace stk::apptest

int main(int argc, char **argv)
{
  using namespace stk;
  std::string backend_arg;
  std::vector<char *> args;
  bool list_only = false;
  for (int i = 0; i < argc; i++) {
    if (std::strcmp(argv[i], "--gpu-backend") == 0 && i + 1 < argc) {
      backend_arg = argv[++i];
      continue;
    }
    if (std::strncmp(argv[i], "--gtest_list_tests", 18) == 0) {
      list_only = true;
    }
    args.push_back(argv[i]);
  }
  int n = int(args.size());
  ::testing::InitGoogleTest(&n, args.data());
  if (list_only) {
    return RUN_ALL_TESTS();
  }
  int rc = 0;
  {
    gfx::Runtime runtime;
    std::string err;
    gfx::Backend backend;
    if (!gfx::resolve_backend(backend_arg, backend, err)) {
      std::fprintf(stderr, "%s\n", err.c_str());
      return 77;
    }
    GHOST_ISystem *system = gfx::create_background_system(err);
    if (!system) {
      std::fprintf(stderr, "skip: %s\n", err.c_str());
      return 77;
    }
    {
      gfx::GpuOptions opts;
      opts.backend = backend;
      std::unique_ptr<gfx::Gpu> gpu = gfx::Gpu::create(*system, opts, err);
      if (!gpu) {
        std::fprintf(stderr, "skip: no GPU context: %s\n", err.c_str());
        gfx::dispose_system();
        return 77;
      }
      apptest::g_gpu = gpu.get();
      std::printf("backend %s: %s\n", gpu->backend_name(), gpu->device_info().c_str());
      rc = RUN_ALL_TESTS();
      apptest::g_gpu = nullptr;
      gpu.reset();
    }
    gfx::dispose_system();
  }
  if (rc == 0 && apptest::g_skipped_all) {
    return 77;
  }
  return rc;
}

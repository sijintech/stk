/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

#include <filesystem>
#include <fstream>
#include <iomanip>

namespace stk::apptest {

// Independent coordinate-based oracle. Components have different signs and asymmetric ranges;
// the serialized rows are reversed so a reader cannot rely on file order for voxel placement.
inline double signed_component(const int x, const int y, const int z, const int component)
{
  if (component == 0) { return -7.0 + x - 2.0 * y + 0.5 * z; }
  if (component == 1) { return 11.0 - 4.0 * x + y - 3.0 * z; }
  return 2.0 * x + 3.0 * y - z - 5.0;
}

inline bool write_signed_field(const std::filesystem::path &path, const int nx = 3,
                               const int ny = 4, const int nz = 5, const double scale = 1.0)
{
  std::ofstream out(path);
  out << nx << ' ' << ny << ' ' << nz << " 3\n" << std::setprecision(17);
  for (int z = nz - 1; z >= 0; --z) {
    for (int y = ny - 1; y >= 0; --y) {
      for (int x = nx - 1; x >= 0; --x) {
        for (int component = 2; component >= 0; --component) {
          out << x + 1 << ' ' << y + 1 << ' ' << z + 1 << ' ' << component + 1 << ' '
              << scale * signed_component(x, y, z, component) << '\n';
        }
      }
    }
  }
  return out.good();
}

}  // namespace stk::apptest

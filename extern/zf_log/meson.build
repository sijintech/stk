project(
  'zf_log',
  'c',
  version : '0.4.1',
  license:['MIT'],
  default_options : ['warning_level=3']
)

add_languages('fortran')

project_description = 'Core logging library for C, Ojective-C and C++ '

project_headers = [
  'zf_log/zf_log.h'
]

project_source_files = [
  'zf_log/zf_log.c',
  'zf_log/zf_log_f.c',
  'zf_log/zf_log.f90'
]

project_test = [
]

build_args = [
]


# ===================================================================

# ======
# Target
# ======

public_headers = include_directories('zf_log')

build_args += [
  '-DPROJECT_NAME=' + meson.project_name(),
  '-DPROJECT_VERSION=' + meson.project_version(),
  '-DNDEBUG'
]

# Only make public interfaces visible
if target_machine.system() == 'windows' or target_machine.system() == 'cygwin'
  build_args += '-DMYLIB_PUBLIC="__declspec(dllexport)"'
else
  build_args += '-DMYLIB_PUBLIC=__attribute__((visibility("default")))'
endif

project_target = static_library(
  meson.project_name(),
  project_source_files,
  install : true,
  c_args : build_args,
  gnu_symbol_visibility : 'hidden',
  include_directories : public_headers,
)

# =======
# Project
# =======

# Make this library usable as a Meson subproject.
project_dep = declare_dependency(
  include_directories: public_headers,
  link_with : project_target
)
set_variable(meson.project_name() + '_dep', project_dep)

# Make this library usable from the system's
# package manager.
install_headers(project_headers, subdir : meson.project_name())

pkg_mod = import('pkgconfig')
pkg_mod.generate(
  name : meson.project_name(),
  filebase : meson.project_name(),
  description : project_description,
  subdirs : meson.project_name(),
  libraries : project_target,
)

# ==========
# Unit Tests
# ==========

if not meson.is_subproject()
  foreach f : project_test
  message(f)
    test(f,
        executable(
        f,
        files('tests/'+f+'.c'),
        dependencies : [project_dep, test_dep],
        install : false
        )
    ) 
  endforeach

endif

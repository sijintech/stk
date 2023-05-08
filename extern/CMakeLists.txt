# FetchContent added in CMake 3.11, downloads during the configure step
# include(FetchContent)
# # FetchContent_MakeAvailable was not added until CMake 3.14; use our shim
# if(${CMAKE_VERSION} VERSION_LESS 3.14)
#   include(cmake/add_FetchContent_MakeAvailable.cmake)
# endif()

# FetchContent_Declare(
#   zf_log
#   GIT_REPOSITORY https://github.com/billcxx/zf_log.git)
# FetchContent_MakeAvailable(zf_log)

# FetchContent_Declare(
#   libxml
#   GIT_REPOSITORY https://gitlab.gnome.org/GNOME/libxml2.git
#   GIT_TAG v2.9.10)
# FetchContent_MakeAvailable(libxml)
# message(${libxml_SOURCE_DIR} ${libxml_BINARY_DIR})

add_subdirectory(zf_log)
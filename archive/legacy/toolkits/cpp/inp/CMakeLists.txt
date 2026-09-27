# CMakeLists.txt for inp_io library
cmake_minimum_required(VERSION 3.10)

# 项目信息
project(inp_io 
    VERSION 1.0.0
    DESCRIPTION "Abaqus input file parser library"
    LANGUAGES C
)

# 设置C标准
set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

# 编译选项
if(MSVC)
    add_compile_options(/Wall /WX)
    add_compile_options(/source-charset:utf-8 /execution-charset:gbk)
else()
    add_compile_options(-Wall -Wextra -Wpedantic -Werror)
    if(WIN32)
        add_compile_options(-fexec-charset=GBK)
    endif()
endif()

# Debug模式下启用调试信息
if(CMAKE_BUILD_TYPE STREQUAL "Debug")
    add_compile_options(-g)
endif()

# 源文件
set(LIB_SOURCES inp_io.c)
set(LIB_HEADERS inp_io.h)

# 创建静态库
add_library(inp_io_static STATIC ${LIB_SOURCES})
target_include_directories(inp_io_static PUBLIC 
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}>
    $<INSTALL_INTERFACE:include>
)
set_target_properties(inp_io_static PROPERTIES OUTPUT_NAME inp_io)

# 创建动态库
add_library(inp_io_shared SHARED ${LIB_SOURCES})
target_include_directories(inp_io_shared PUBLIC 
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}>
    $<INSTALL_INTERFACE:include>
)
set_target_properties(inp_io_shared PROPERTIES OUTPUT_NAME inp_io)

# Windows特定设置
if(WIN32)
    set_target_properties(inp_io_shared PROPERTIES 
        WINDOWS_EXPORT_ALL_SYMBOLS TRUE
    )
endif()

# 创建测试程序
add_executable(test_main main.c)
target_link_libraries(test_main inp_io_static)

add_executable(test_example test_example.c)
target_link_libraries(test_example inp_io_static)

# 安装配置
include(GNUInstallDirs)

# 安装库文件
install(TARGETS inp_io_static inp_io_shared
    EXPORT inp_io-targets
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)

# 安装头文件
install(FILES ${LIB_HEADERS}
    DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
)

# 安装CMake配置文件
install(EXPORT inp_io-targets
    FILE inp_io-targets.cmake
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/inp_io
)

# 创建配置文件
include(CMakePackageConfigHelpers)

configure_package_config_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/cmake/inp_io-config.cmake.in"
    "${CMAKE_CURRENT_BINARY_DIR}/inp_io-config.cmake"
    INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/inp_io
)

write_basic_package_version_file(
    "${CMAKE_CURRENT_BINARY_DIR}/inp_io-config-version.cmake"
    VERSION ${PROJECT_VERSION}
    COMPATIBILITY SameMajorVersion
)

install(FILES
    "${CMAKE_CURRENT_BINARY_DIR}/inp_io-config.cmake"
    "${CMAKE_CURRENT_BINARY_DIR}/inp_io-config-version.cmake"
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/inp_io
)

# 打包配置
set(CPACK_PACKAGE_NAME "inp_io")
set(CPACK_PACKAGE_VERSION ${PROJECT_VERSION})
set(CPACK_PACKAGE_DESCRIPTION_SUMMARY ${PROJECT_DESCRIPTION})
set(CPACK_PACKAGE_VENDOR "Your Name")
set(CPACK_PACKAGE_CONTACT "your.email@example.com")

if(WIN32)
    set(CPACK_GENERATOR "ZIP;NSIS")
else()
    set(CPACK_GENERATOR "TGZ;DEB")
endif()

include(CPack)

# 自定义目标
add_custom_target(run_tests
    COMMAND test_main
    COMMAND test_example
    DEPENDS test_main test_example
    COMMENT "Running all tests"
)

# 显示构建信息
message(STATUS "inp_io library configuration:")
message(STATUS "  Version: ${PROJECT_VERSION}")
message(STATUS "  Build type: ${CMAKE_BUILD_TYPE}")
message(STATUS "  Install prefix: ${CMAKE_INSTALL_PREFIX}")

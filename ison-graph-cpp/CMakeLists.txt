cmake_minimum_required(VERSION 3.14)
project(ison_graph_cpp VERSION 1.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Header-only library (includes both ison_graph.hpp and isongraphantic.hpp)
add_library(ison_graph INTERFACE)
target_include_directories(ison_graph INTERFACE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)

# Tests
enable_testing()

# ISONGraph core tests
add_executable(test_ison_graph tests/test_ison_graph.cpp)
target_link_libraries(test_ison_graph PRIVATE ison_graph)
add_test(NAME test_ison_graph COMMAND test_ison_graph)

# ISONGraphantic schema tests
add_executable(test_isongraphantic tests/test_isongraphantic.cpp)
target_link_libraries(test_isongraphantic PRIVATE ison_graph)
add_test(NAME test_isongraphantic COMMAND test_isongraphantic)

# ISONQL query language tests
add_executable(test_isonql tests/test_isonql.cpp)
target_link_libraries(test_isonql PRIVATE ison_graph)
add_test(NAME test_isonql COMMAND test_isonql)

# Installation
install(DIRECTORY include/ DESTINATION include)
install(TARGETS ison_graph EXPORT ison_graph_targets)

install(EXPORT ison_graph_targets
    FILE ison_graph_targets.cmake
    NAMESPACE ison::
    DESTINATION lib/cmake/ison_graph
)

include(CMakePackageConfigHelpers)
write_basic_package_version_file(
    "${CMAKE_CURRENT_BINARY_DIR}/ison_graph_config_version.cmake"
    VERSION ${PROJECT_VERSION}
    COMPATIBILITY SameMajorVersion
)

configure_package_config_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/cmake/ison_graph_config.cmake.in"
    "${CMAKE_CURRENT_BINARY_DIR}/ison_graph_config.cmake"
    INSTALL_DESTINATION lib/cmake/ison_graph
)

install(FILES
    "${CMAKE_CURRENT_BINARY_DIR}/ison_graph_config.cmake"
    "${CMAKE_CURRENT_BINARY_DIR}/ison_graph_config_version.cmake"
    DESTINATION lib/cmake/ison_graph
)

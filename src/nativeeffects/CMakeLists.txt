# SPDX-License-Identifier: BSD-2-Clause

find_package(PkgConfig REQUIRED)
pkg_check_modules(NATIVE_MLT REQUIRED IMPORTED_TARGET mlt-framework-7)

add_library(mltkdenlivenative MODULE
    motioncurve.cpp
    motioncurve.hpp
    filter_curves.hpp
    filter_motioncurve.cpp
    filter_fisheye.cpp
    filter_axisstretch.cpp
    filter_cornerpin.cpp
    filter_warpchroma.cpp
    filter_shake.cpp
)
target_compile_features(mltkdenlivenative PRIVATE cxx_std_17)
target_link_libraries(mltkdenlivenative PRIVATE PkgConfig::NATIVE_MLT Qt${QT_MAJOR_VERSION}::Core)
set_target_properties(mltkdenlivenative PROPERTIES PREFIX "lib" OUTPUT_NAME mltkdenlivenative)
install(TARGETS mltkdenlivenative LIBRARY DESTINATION lib/mlt-7)

if(UNIX AND NOT APPLE)
    execute_process(COMMAND ${PKG_CONFIG_EXECUTABLE} --variable=moduledir mlt-framework-7
                    OUTPUT_VARIABLE NATIVE_MLT_SYSTEM_MODULE_DIR OUTPUT_STRIP_TRAILING_WHITESPACE)
    # MLT accepts one repository directory. The local installation contains
    # this module and links to the distro's other MLT modules in that directory.
    install(CODE "
        file(MAKE_DIRECTORY \"\${CMAKE_INSTALL_PREFIX}/lib/mlt-7\")
        file(GLOB system_modules \"${NATIVE_MLT_SYSTEM_MODULE_DIR}/*.so\")
        foreach(module IN LISTS system_modules)
            get_filename_component(module_name \"\${module}\" NAME)
            if(NOT EXISTS \"\${CMAKE_INSTALL_PREFIX}/lib/mlt-7/\${module_name}\")
                file(CREATE_LINK \"\${module}\" \"\${CMAKE_INSTALL_PREFIX}/lib/mlt-7/\${module_name}\" SYMBOLIC)
            endif()
        endforeach()
    ")
endif()

if(BUILD_TESTING)
    add_executable(test_native_motioncurve test_motioncurve.cpp motioncurve.cpp motioncurve.hpp)
    target_compile_features(test_native_motioncurve PRIVATE cxx_std_17)
    target_link_libraries(test_native_motioncurve PRIVATE Qt${QT_MAJOR_VERSION}::Core)
    add_test(NAME native_motioncurve COMMAND test_native_motioncurve)
endif()

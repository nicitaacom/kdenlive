# SPDX-License-Identifier: BSD-2-Clause

find_package(PkgConfig REQUIRED)
pkg_check_modules(NATIVE_MLT REQUIRED IMPORTED_TARGET mlt-framework-7)
find_package(OpenMP QUIET COMPONENTS CXX)

add_library(mltkdenlivenative MODULE
    motioncurve.cpp
    motioncurve.hpp
    motionvector.cpp
    motionvector.hpp
    spatialblur.cpp
    spatialblur.hpp
    spatialtransformblur.cpp
    spatialtransformblur.hpp
    filter_curves.hpp
    filter_motioncurve.cpp
    filter_brightnesscontrast.cpp
    filter_fisheye.cpp
    filter_axisstretch.cpp
    filter_cornerpin.cpp
    filter_warpchroma.cpp
    distortchroma.cpp
    distortchroma.hpp
    filter_distortchroma.cpp
    filter_shake.cpp
    filter_motionvector.cpp
    filter_spatialblur.cpp
    filter_blurmotion.cpp
    filter_magnify.cpp
    pinchwarp.cpp
    pinchwarp.hpp
    filter_pinch.cpp
    filter_waves.cpp
    bubblewarp.cpp
    bubblewarp.hpp
    filter_bubblewarp.cpp
)
target_compile_features(mltkdenlivenative PRIVATE cxx_std_17)
target_link_libraries(mltkdenlivenative PRIVATE PkgConfig::NATIVE_MLT Qt${QT_MAJOR_VERSION}::Core)
if(OpenMP_CXX_FOUND)
    target_link_libraries(mltkdenlivenative PRIVATE OpenMP::OpenMP_CXX)
endif()
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
    if(OpenMP_CXX_FOUND)
        target_link_libraries(test_native_motioncurve PRIVATE OpenMP::OpenMP_CXX)
    endif()
    add_test(NAME native_motioncurve COMMAND test_native_motioncurve)
    add_executable(test_native_brightnesscontrast test_brightnesscontrast.cpp brightnesscontrast.hpp)
    target_compile_features(test_native_brightnesscontrast PRIVATE cxx_std_17)
    add_test(NAME native_brightnesscontrast COMMAND test_native_brightnesscontrast)
    add_executable(test_native_motionvector test_motionvector.cpp motionvector.cpp motionvector.hpp motioncurve.cpp motioncurve.hpp)
    target_compile_features(test_native_motionvector PRIVATE cxx_std_17)
    target_link_libraries(test_native_motionvector PRIVATE Qt${QT_MAJOR_VERSION}::Core)
    if(OpenMP_CXX_FOUND)
        target_link_libraries(test_native_motionvector PRIVATE OpenMP::OpenMP_CXX)
    endif()
    add_test(NAME native_motionvector COMMAND test_native_motionvector)
    add_executable(test_native_filter_curves test_filter_curves.cpp filter_curves.hpp motioncurve.cpp motioncurve.hpp)
    target_compile_features(test_native_filter_curves PRIVATE cxx_std_17)
    target_link_libraries(test_native_filter_curves PRIVATE PkgConfig::NATIVE_MLT Qt${QT_MAJOR_VERSION}::Core)
    add_test(NAME native_filter_curves COMMAND test_native_filter_curves)
    add_executable(test_native_spatialblur test_spatialblur.cpp spatialblur.cpp spatialblur.hpp motioncurve.cpp motioncurve.hpp)
    target_compile_features(test_native_spatialblur PRIVATE cxx_std_17)
    target_link_libraries(test_native_spatialblur PRIVATE Qt${QT_MAJOR_VERSION}::Core)
    add_test(NAME native_spatialblur COMMAND test_native_spatialblur)
    add_executable(test_native_blurmotion test_blurmotion.cpp spatialtransformblur.cpp spatialtransformblur.hpp motioncurve.cpp motioncurve.hpp)
    target_compile_features(test_native_blurmotion PRIVATE cxx_std_17)
    target_link_libraries(test_native_blurmotion PRIVATE Qt${QT_MAJOR_VERSION}::Core)
    add_test(NAME native_blurmotion COMMAND test_native_blurmotion)
    add_executable(test_native_bubblewarp test_bubblewarp.cpp bubblewarp.cpp bubblewarp.hpp motioncurve.cpp motioncurve.hpp)
    target_compile_features(test_native_bubblewarp PRIVATE cxx_std_17)
    target_link_libraries(test_native_bubblewarp PRIVATE Qt${QT_MAJOR_VERSION}::Core)
    add_test(NAME native_bubblewarp COMMAND test_native_bubblewarp)
    add_executable(test_native_distortchroma test_distortchroma.cpp distortchroma.cpp distortchroma.hpp motioncurve.cpp motioncurve.hpp)
    target_compile_features(test_native_distortchroma PRIVATE cxx_std_17)
    target_link_libraries(test_native_distortchroma PRIVATE PkgConfig::NATIVE_MLT Qt${QT_MAJOR_VERSION}::Core)
    add_test(NAME native_distortchroma COMMAND test_native_distortchroma)
    add_executable(test_native_pinchwarp test_pinchwarp.cpp pinchwarp.cpp pinchwarp.hpp motioncurve.cpp motioncurve.hpp)
    target_compile_features(test_native_pinchwarp PRIVATE cxx_std_17)
    target_link_libraries(test_native_pinchwarp PRIVATE PkgConfig::NATIVE_MLT Qt${QT_MAJOR_VERSION}::Core)
    add_test(NAME native_pinchwarp COMMAND test_native_pinchwarp)
endif()

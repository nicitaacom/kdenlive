/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "brightnesscontrast.hpp"

#include <array>
#include <cstdio>
#include <cstdlib>

using namespace NativeMotion;

static void require(bool condition, const char *message)
{
    if (!condition) {
        std::fprintf(stderr, "%s\n", message);
        std::exit(1);
    }
}

int main()
{
    std::array<uint8_t, 8> image{0, 64, 128, 255, 200, 128, 32, 255};
    const auto original = image;
    applyBrightnessContrast(image.data(), 2, 1, 0.0, 0.0, 0.5);
    require(image == original, "neutral source controls changed the image");
    applyBrightnessContrast(image.data(), 2, 1, 0.25, 0.0, 0.5);
    require(image[0] == 64 && image[1] == 128 && image[2] == 192 && image[3] == 255,
            "brightness did not add the normalized 255-level offset");
    std::array<uint8_t, 8> centered{0, 64, 128, 255, 200, 128, 32, 255};
    applyBrightnessContrast(centered.data(), 2, 1, 0.0, 0.5, 0.5);
    require(centered[0] == 0 && centered[1] == 1 && centered[2] == 129 &&
                centered[4] == 255 && centered[5] == 129,
            "contrast did not scale around its configured center");
    std::array<uint8_t, 4> transparent{10, 20, 30, 0};
    applyBrightnessContrast(transparent.data(), 1, 1, 0.5, 0.5, 0.5);
    require(transparent == std::array<uint8_t, 4>{0, 0, 0, 0},
            "transparent pixels retained RGB fringes");
    return 0;
}

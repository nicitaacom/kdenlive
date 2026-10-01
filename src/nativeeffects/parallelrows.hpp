/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#pragma once

namespace NativeMotion {

// Pixel rows are independent. Keep native CPU rendering bounded to two
// workers so long blur kernels do not occupy every core on the editing system.
template<typename Function>
void parallelRows(int height, Function function)
{
#if defined(_OPENMP)
#pragma omp parallel for schedule(static) num_threads(2)
#endif
    for (int y = 0; y < height; ++y) {
        function(y);
    }
}

} // namespace NativeMotion

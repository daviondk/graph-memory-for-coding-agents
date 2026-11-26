#!/bin/sh
set -eu
: "${SOURCE:?absolute directory of pinned upstream sources}"
BUILD=${BUILD:-/tmp/r49cache}
TARGET=${TARGET:-/tmp/r49cache-reference}
cmake -S "$SOURCE" -B "$BUILD" -DENABLE_TESTS=OFF -DSUPPORT_ZSTD_TRACE=OFF -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build "$BUILD" --target evictionC evictionCPP dataStructure utils cachelib admissionC prefetchC ds_hash -j 4 >/dev/null
cc -DINCLUDE_PRIV=1 -DLOGLEVEL=7 -DOS_LINUX -DUSE_HUGEPAGE=1 -I"$SOURCE/libCacheSim/include" $(pkg-config --cflags glib-2.0) -c reference_driver.c -o "$BUILD/r49driver.o"
c++ "$BUILD/r49driver.o" -Wl,--start-group $(find "$BUILD" -name '*.a') -Wl,--end-group $(pkg-config --libs glib-2.0) -lm -lpthread -o "$TARGET"


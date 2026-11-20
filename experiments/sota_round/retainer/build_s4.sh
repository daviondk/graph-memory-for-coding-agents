#!/bin/sh
set -eu
# Argument 1 is the data/cache directory prepared by fetch.py and s4_fetch.py;
# argument 2 is this source directory. Run using a Linux compiler with GLib, zstd,
# and argp development libraries installed. For glibc, argp is in libc.
raw=$1
adapter=$2
src=${3:-$raw/libcache-src}
build=${4:-$raw/build}
mkdir -p "$build"
cmake -S "$src" -B "$build" -DCMAKE_BUILD_TYPE=Release -DENABLE_TESTS=OFF -DUSE_TCMALLOC=OFF
cmake --build "$build" --target cachesim -j4
inc="-I$src/libCacheSim/include -I$src/libCacheSim/utils/include -I$src/libCacheSim"
cc -O2 -DLOGLEVEL=7 -DOS_LINUX -DSUPPORT_ZSTD_TRACE=1 -DUSE_HUGEPAGE=1 $inc $(pkg-config --cflags glib-2.0) -c "$adapter/driver.c" -o "$build/msr-driver.o"
c++ -std=c++17 -O0 $inc -I"$raw/models" -c "$adapter/predict.cpp" -o "$build/msr-predict.o"
extra=""
if [ -e /usr/lib/libargp.a ]; then extra="$extra /usr/lib/libargp.a"; fi
if [ -e /usr/lib/libintl.so ]; then extra="$extra -lintl"; fi
c++ "$build/msr-driver.o" "$build/msr-predict.o" "$build/liblibCacheSim.a" -lm -ldl $(pkg-config --libs glib-2.0 libzstd) $extra -o "$raw/s4driver"

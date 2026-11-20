#!/bin/sh
set -eu
src=$1
build=$2
adapter=$3
raw=$4
inc="-I$src/libCacheSim/include -I$src/libCacheSim -I$src/libCacheSim/utils/include"
cc -O2 -DOS_LINUX -DLOGLEVEL=7 -DSUPPORT_ZSTD_TRACE=1 $inc $(pkg-config --cflags glib-2.0) -c "$adapter/historical_driver.c" -o "$build/historical-driver.o"
libs=$(find "$build/libCacheSim" -name '*.a')
extra=""
if [ -e /usr/lib/libargp.a ]; then extra="$extra /usr/lib/libargp.a"; fi
if [ -e /usr/lib/libintl.so ]; then extra="$extra -lintl"; fi
c++ "$build/historical-driver.o" -Wl,--start-group $libs -Wl,--end-group -lzstd -lpthread -ldl -lm $(pkg-config --libs glib-2.0) $extra -o "$raw/historical-driver"

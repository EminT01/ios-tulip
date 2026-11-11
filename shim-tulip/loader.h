#pragma once
#include <stdint.h>

/* Boot the VINCEXNU payload found in the LK ramdisk; returns only on error (a message). */
const char *loader_boot(uintptr_t dtb);

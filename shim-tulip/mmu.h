#pragma once
#include <stdint.h>

struct mmu_info {
	uint64_t img_lo, img_hi, ttbr;
	uint64_t sctlr_before, sctlr_after;
};

int mmu_enable(struct mmu_info *info);

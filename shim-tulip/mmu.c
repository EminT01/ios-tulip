/*
 * 4 KiB-granule identity MMU setup for Redmi Note 6 Pro (SDM636).
 *
 * The Kryo 260 cores are A53/A73 class and have no 16 KiB granule, so 4 KiB it is
 * (same approach as ios-vince on the Cortex-A53 Redmi 5 Plus).
 *
 * 39-bit VA (T0SZ=25): L1 = 4 x 1 GiB entries, each pointing to an L2 table of
 * 512 x 2 MiB blocks.
 *
 * Physical memory map, from the tulip stock DTB (#29) reserved-memory nodes and the
 * recovery /proc/iomem (RAM: 0x40000000-0x855fffff, 0x88f00000-0x8abfffff,
 * 0x94b00000-0xfeabffff). Everything that is not plain RAM is mapped Device-nGnRnE:
 * that forbids speculative access, which matters because TrustZone/XPU-protected
 * carveouts (modem, ADSP, MBA, wlan MSA) may reset the phone when touched.
 *
 *   0x00000000-0x3fffffff  Device   MMIO (GIC 0x17a00000, UART 0x0c170000, MDSS, ...)
 *   0x40000000-0x855fffff  WB       RAM
 *   0x85600000-0x94bfffff  Device   no-map carveouts + 29 MiB RAM island (unused)
 *   0x94c00000-0x9d3fffff  WB       RAM
 *   0x9d400000-0x9f7fffff  NC       splash framebuffer (36 MiB, write-combining)
 *   0x9f800000-0xfe9fffff  WB       RAM
 *   0xfea00000-0xffffffff  Device
 */
#include <stdint.h>
#include "mmu.h"

#define PG_SIZE		4096UL
#define BLK_SIZE	(1UL << 21)
#define NENT		512

#define ATTR_DEV	0	/* MAIR attr0 = 0x00 Device-nGnRnE */
#define ATTR_WB		1	/* MAIR attr1 = 0xff Normal WB RW-alloc */
#define ATTR_NC		2	/* MAIR attr2 = 0x44 Normal non-cacheable */
#define MAIR_VAL	0x44ff00UL

#define D_BLOCK		1UL
#define D_TABLE		3UL
#define D_ATTR(i)	((uint64_t)(i) << 2)
#define D_SH_OUTER	(2UL << 8)
#define D_SH_INNER	(3UL << 8)
#define D_AF		(1UL << 10)
#define D_PXN		(1UL << 53)
#define D_UXN		(1UL << 54)

#define DEV_FLAGS	(D_ATTR(ATTR_DEV) | D_AF | D_PXN | D_UXN)
#define WB_FLAGS	(D_ATTR(ATTR_WB) | D_SH_INNER | D_AF | D_UXN)
#define NC_FLAGS	(D_ATTR(ATTR_NC) | D_SH_OUTER | D_AF | D_PXN | D_UXN)

/* T0SZ=25, IRGN0/ORGN0=WBWA, SH0=inner, TG0=4K, EPD1=1, IPS=36-bit */
#define TCR_VAL		(25UL | (1UL << 8) | (1UL << 10) | (3UL << 12) | (0UL << 14) | (1UL << 23) | (1UL << 32))

#define SCTLR_M		(1UL << 0)
#define SCTLR_C		(1UL << 2)
#define SCTLR_I		(1UL << 12)

#define rsr(r) ({ uint64_t _v; __asm__ volatile("mrs %0, " r : "=r"(_v)); _v; })
#define wsr(r, v) __asm__ volatile("msr " r ", %0" : : "r"((uint64_t)(v)))

extern char _head[], _end[];

static uint64_t pt_pool[8 * NENT] __attribute__((aligned(4096)));

static void zero_table(uint64_t *t)
{
	for (int i = 0; i < NENT; i++)
		t[i] = 0;
}

/* fill L2 entries [from, to) of the GiB starting at base_pa with the given flags */
static void fill(uint64_t *l2, uint64_t base_pa, int from, int to, uint64_t flags)
{
	for (int j = from; j < to; j++)
		l2[j] = (base_pa + (uint64_t)j * BLK_SIZE) | flags | D_BLOCK;
}

int mmu_enable(struct mmu_info *info)
{
	uintptr_t pool = (uintptr_t)pt_pool;
	uint64_t *l1 = (uint64_t *)pool;

	info->img_lo = (uintptr_t)_head & ~(PG_SIZE - 1);
	info->img_hi = ((uintptr_t)_end + PG_SIZE - 1) & ~(PG_SIZE - 1);
	info->ttbr = pool;
	info->sctlr_before = rsr("sctlr_el1");

	zero_table(l1);
	for (int i = 0; i < 4; i++) {
		uint64_t *l2 = (uint64_t *)(pool + (1 + i) * PG_SIZE);
		zero_table(l2);
		l1[i] = (uintptr_t)l2 | D_TABLE;
	}

	/* GiB 0: MMIO */
	fill((uint64_t *)(pool + 1 * PG_SIZE), 0x00000000UL, 0, NENT, DEV_FLAGS);
	/* GiB 1: RAM */
	fill((uint64_t *)(pool + 2 * PG_SIZE), 0x40000000UL, 0, NENT, WB_FLAGS);
	/* GiB 2: 0x80000000 + j * 2 MiB */
	{
		uint64_t *l2 = (uint64_t *)(pool + 3 * PG_SIZE);
		uint64_t b = 0x80000000UL;
		fill(l2, b, 0, 43, WB_FLAGS);		/* ..0x855fffff RAM */
		fill(l2, b, 43, 166, DEV_FLAGS);	/* 0x85600000..0x94bfffff carveouts */
		fill(l2, b, 166, 234, WB_FLAGS);	/* 0x94c00000..0x9d3fffff RAM */
		fill(l2, b, 234, 252, NC_FLAGS);	/* 0x9d400000..0x9f7fffff splash FB */
		fill(l2, b, 252, NENT, WB_FLAGS);	/* 0x9f800000..0xbfffffff RAM */
	}
	/* GiB 3: 0xc0000000 + j * 2 MiB */
	{
		uint64_t *l2 = (uint64_t *)(pool + 4 * PG_SIZE);
		uint64_t b = 0xc0000000UL;
		fill(l2, b, 0, 501, WB_FLAGS);		/* ..0xfe9fffff RAM */
		fill(l2, b, 501, NENT, DEV_FLAGS);
	}

	__asm__ volatile("dsb ish" ::: "memory");
	__asm__ volatile("tlbi vmalle1is" ::: "memory");
	__asm__ volatile("dsb ish" ::: "memory");
	__asm__ volatile("isb" ::: "memory");

	wsr("mair_el1", MAIR_VAL);
	wsr("tcr_el1", TCR_VAL);
	wsr("ttbr0_el1", pool);
	__asm__ volatile("isb" ::: "memory");

	__asm__ volatile("ic ialluis" ::: "memory");
	__asm__ volatile("dsb ish" ::: "memory");
	__asm__ volatile("isb" ::: "memory");

	uint64_t sctlr = rsr("sctlr_el1");
	sctlr |= SCTLR_M | SCTLR_C | SCTLR_I;
	wsr("sctlr_el1", sctlr);
	__asm__ volatile("isb" ::: "memory");

	info->sctlr_after = rsr("sctlr_el1");
	return 0;
}

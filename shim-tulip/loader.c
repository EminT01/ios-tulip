/*
typedef void (*xnu_entry_t)(uint64_t boot_args_pa);
 * tulip iBoot-like loader for the XNU Mach-O payload (Redmi Note 6 Pro, SDM636); derived from ios-vince
 */
#include <stdint.h>
#include "console.h"
#include "fdt.h"
#include "loader.h"

#define BOOT_LINE_LENGTH	608
#define PAGE_4K				0x1000UL

struct payload_seg {
	uint64_t vmaddr, vmsize, file_off, file_size;
};

struct payload {
	char magic[8];
	uint32_t version, nsegs;
	uint64_t virt_base, entry_va, adt_off, adt_size, kernel_end;
	uint64_t phys_base, mem_size;
	char cmdline[BOOT_LINE_LENGTH];
	struct payload_seg segs[];
};

/* pexpert/pexpert/arm64/boot.h, Revision/Version 2 */
struct boot_video {
	uint64_t v_baseAddr, v_display, v_rowBytes, v_width, v_height, v_depth;
};

struct boot_args {
	uint16_t Revision, Version;
	uint64_t virtBase, physBase, memSize, topOfKernelData;
	struct boot_video Video;
	uint32_t machineType;
	uint64_t deviceTreeP;
	uint32_t deviceTreeLength;
	char CommandLine[BOOT_LINE_LENGTH];
	uint64_t bootFlags, memSizeActual;
};

_Static_assert(__builtin_offsetof(struct payload, segs) == 0x2a8, "payload header layout");
_Static_assert(__builtin_offsetof(struct boot_args, Video) == 40, "boot_args layout");
_Static_assert(__builtin_offsetof(struct boot_args, CommandLine) == 108, "boot_args layout");
_Static_assert(sizeof(struct boot_args) == 736, "boot_args layout");

static void copy64(uintptr_t dst, uintptr_t src, uint64_t n)
{
	volatile uint64_t *d = (volatile uint64_t *)dst;
	volatile const uint64_t *s = (volatile const uint64_t *)src;
	for (uint64_t i = 0; i < (n + 7) / 8; i++)
		d[i] = s[i];
}

static void zero64(uintptr_t dst, uint64_t n)
{
	volatile uint64_t *d = (volatile uint64_t *)dst;
	for (uint64_t i = 0; i < n / 8; i++)
		d[i] = 0;
}

static int magic_ok(const char *m)
{
	static const char want1[] = "SWEETXNU";
	static const char want2[] = "VINCEXNU";
	int ok1 = 1, ok2 = 1;
	for (int i = 0; i < 8; i++) {
		if (m[i] != want1[i]) ok1 = 0;
		if (m[i] != want2[i]) ok2 = 0;
	}
	return ok1 || ok2;
}

typedef void (*xnu_entry_t)(uint64_t boot_args_pa);

/* === YENI EKLENEN FONKSIYON === */
/* ADT kopyasindaki random-seed'i tazele. 1 = bulundu ve yazildi */
static int adt_patch_seed(uintptr_t adt, uint64_t adt_size)
{
    static const char key[] = "random-seed";
    volatile uint8_t *b = (volatile uint8_t *)adt;

    for (uint64_t i = 0; i + 40 <= adt_size; i++) {
        if (b[i + 11] != 0) continue;
        int ok = 1;
        for (int k = 0; k < 11; k++)
            if (b[i + k] != (uint8_t)key[k]) { ok = 0; break; }
        if (!ok) continue;

        uint32_t len = (uint32_t)b[i+32] | ((uint32_t)b[i+33] << 8)
                     | ((uint32_t)b[i+34] << 16) | ((uint32_t)b[i+35] << 24);
        len &= 0x7fffffffu;
        if (len == 0 || len > 256 || i + 36 + len > adt_size) continue;

        for (uint32_t k = 0; k < len; k++)
            b[i + 36 + k] = (uint8_t)(0x5a ^ (uint8_t)(k * 31 + 7));

        con_hex("SEEDOFF", i + 36);
        con_hex("SEEDLEN", len);
        con_hex("S0", (uintptr_t)((uint32_t)b[i+36] | ((uint32_t)b[i+37] << 8)
                    | ((uint32_t)b[i+38] << 16) | ((uint32_t)b[i+39] << 24)));

        return 1;
    }
    return 0;
}
/* === EKLENEN KOD BITTI === */

const char *loader_boot(uintptr_t dtb)
{
	uint64_t rd_start, rd_end;

	if (!fdt_chosen_u64(dtb, "linux,initrd-start", &rd_start) ||
	    !fdt_chosen_u64(dtb, "linux,initrd-end", &rd_end))
		return "no initrd in /chosen";

	const struct payload *p = (const struct payload *)rd_start;
	if (!magic_ok(p->magic))
		return "no VINCEXNU/SWEETXNU payload in ramdisk";
	if (p->version != 1 || (p->adt_off & 7) || (rd_start & 7))
		return "bad payload header";

	uint64_t pa_of_va_base = p->phys_base - p->virt_base;

	if (rd_end > p->phys_base && rd_start < p->phys_base + p->mem_size)
		return "ramdisk overlaps kernel memory";

	con_str("LOADER",  "Copying kernel segments...");
	for (uint32_t i = 0; i < p->nsegs; i++) {
		const struct payload_seg *s = &p->segs[i];
		uintptr_t dst = s->vmaddr + pa_of_va_base;
		copy64(dst, rd_start + s->file_off, s->file_size);
		if (s->vmsize > s->file_size)
			zero64(dst + ((s->file_size + 7) & ~7UL), s->vmsize - ((s->file_size + 7) & ~7UL));
	}

	uintptr_t adt_pa = p->kernel_end + pa_of_va_base;
	copy64(adt_pa, rd_start + p->adt_off, p->adt_size);
	uintptr_t ba_pa = (adt_pa + p->adt_size + PAGE_4K - 1) & ~(PAGE_4K - 1);
	uintptr_t top = ba_pa + PAGE_4K;

	zero64(ba_pa, PAGE_4K);
	volatile struct boot_args *ba = (volatile struct boot_args *)ba_pa;
	ba->Revision = 2;
	ba->Version = 2;
	ba->virtBase = p->virt_base;
	ba->physBase = p->phys_base;
	ba->memSize = p->mem_size;
	ba->topOfKernelData = top;
	ba->Video.v_baseAddr = FB_BASE;
	ba->Video.v_display = 1;
	ba->Video.v_rowBytes = FB_STRIDE;
	ba->Video.v_width = FB_W;
	ba->Video.v_height = FB_H;
	ba->Video.v_depth = FB_BPP;
	ba->deviceTreeP = adt_pa;
	ba->deviceTreeLength = (uint32_t)p->adt_size;
	for (int i = 0; i < BOOT_LINE_LENGTH; i++)
		ba->CommandLine[i] = p->cmdline[i];
	ba->memSizeActual = p->mem_size;

	uintptr_t entry_pa = p->entry_va + pa_of_va_base;
	con_hex("ENTRY",   entry_pa);
	con_hex("BOOTARG", ba_pa);
	con_str("HANDOVER", "Flushing cache & entering XNU...");

	/* Flush copied kernel code and boot_args from D-cache to physical DRAM */
	for (uintptr_t a = p->phys_base; a < top; a += 64) {
		__asm__ volatile("dc civac, %0" : : "r"(a) : "memory");
	}
	__asm__ volatile("dsb sy" ::: "memory");
	con_str("ENTER", "jumping to XNU, watch the bands");

	/* quiesce the diagnostic state: virtual timer off, all exceptions masked */
	__asm__ volatile("msr cntv_ctl_el0, xzr" ::: "memory");
	__asm__ volatile("msr daifset, #0xf" ::: "memory");
	/* Disable MMU and D-cache so XNU enters with clean flat physical addressing */
	uint64_t sctlr;
	__asm__ volatile("mrs %0, sctlr_el1" : "=r"(sctlr));
	sctlr &= ~(1ULL << 0); /* SCTLR_M = 0 */
	sctlr &= ~(1ULL << 2); /* SCTLR_C = 0 */
	__asm__ volatile("msr sctlr_el1, %0; isb" : : "r"(sctlr) : "memory");

	/* Invalidate TLB and I-cache */
	__asm__ volatile(
		"tlbi vmalle1\n"
		"dsb sy\n"
		"ic iallu\n"
		"dsb sy\n"
		"isb\n"
		::: "memory"
	);

        if (adt_patch_seed(adt_pa, p->adt_size))
		con_str("SEED", "FOUND + patched");
	else
		con_str("SEED", "NOT FOUND in ADT");
	__asm__ volatile("dsb sy" ::: "memory");

	((xnu_entry_t)entry_pa)(ba_pa);
	return "xnu returned";
}

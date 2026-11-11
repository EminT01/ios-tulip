/*
 * tulip M1/M2 diagnostic shim: Xiaomi Redmi Note 6 Pro (SDM636).
 *
 * Boots as a fake arm64 Linux Image via `fastboot boot` and, instead of Linux,
 * measures the hardware and reports on the LK splash framebuffer:
 *   - exception level, CPU ID registers (16K/4K granule, PAN, LSE, ...)
 *   - 4 KiB-granule MMU bring-up
 *   - GICv3 bring-up (dist @0x17a00000, redist @0x17b00000, from the stock DTB)
 *   - architected timer interrupt (virtual timer, PPI 3 = INTID 19 per the DTB)
 * Nothing is written to flash. Hold power ~10 s to reboot if it hangs.
 *
 * Structure inspired by ios-vince (zjh3215588/ios-vince); GICv3 code is new.
 */
#include <stdint.h>
#include "console.h"
#include "mmu.h"
#ifdef BOOT_XNU
#include "loader.h"
#endif

#define GICD_BASE	0x17a00000UL
#define GICR_BASE	0x17b00000UL
#define GICR_STRIDE	0x20000UL
#define GICR_SGI_OFF	0x10000UL

#define GICD_CTLR	0x000
#define GICD_TYPER	0x004
#define GICD_IIDR	0x008
#define GICD_CTLR_ENABLE_G1	(1U << 0)
#define GICD_CTLR_ENABLE_G1A	(1U << 1)
#define GICD_CTLR_ARE_NS	(1U << 4)
#define GICD_CTLR_RWP		(1U << 31)

#define GICR_TYPER	0x008
#define GICR_WAKER	0x014
#define GICR_ISENABLER0	0x100
#define GICR_ICENABLER0	0x180
#define GICR_IPRIORITYR	0x400

#define VTIMER_INTID	19	/* DTB /soc/timer: PPI 3 -> INTID 16 + 3 */

#define rsr(r) ({ uint64_t _v; __asm__ volatile("mrs %0, " r : "=r"(_v)); _v; })
#define wsr(r, v) __asm__ volatile("msr " r ", %0" : : "r"((uint64_t)(v)))
#define isb() __asm__ volatile("isb" ::: "memory")

static inline uint32_t rd32(uintptr_t a) { return *(volatile uint32_t *)a; }
static inline void wr32(uintptr_t a, uint32_t v) { *(volatile uint32_t *)a = v; }
static inline uint64_t rd64(uintptr_t a) { return *(volatile uint64_t *)a; }

/* GICv3 CPU interface system registers (encoded names, independent of assembler support) */
#define ICC_PMR_EL1	"S3_0_C4_C6_0"
#define ICC_IAR1_EL1	"S3_0_C12_C12_0"
#define ICC_EOIR1_EL1	"S3_0_C12_C12_1"
#define ICC_BPR1_EL1	"S3_0_C12_C12_3"
#define ICC_CTLR_EL1	"S3_0_C12_C12_4"
#define ICC_SRE_EL1	"S3_0_C12_C12_5"
#define ICC_IGRPEN1_EL1	"S3_0_C12_C12_7"

static volatile uint32_t irq_count;
static volatile uint32_t irq_last;

static void timer_arm(void)
{
	wsr("cntv_cval_el0", rsr("cntvct_el0") + rsr("cntfrq_el0") / 10);
	wsr("cntv_ctl_el0", 1);	/* ENABLE=1, IMASK=0 */
	isb();
}

void exc_handler(int slot, uint64_t *regs)
{
	(void)regs;
	if (slot == 1 || slot == 5) {	/* IRQ at EL1 (SP0 or SPx) */
		uint64_t iar;
		__asm__ volatile("mrs %0, " ICC_IAR1_EL1 : "=r"(iar));
		uint32_t intid = iar & 0xffffff;

		if (intid >= 1020)	/* spurious */
			return;
		irq_last = intid;
		irq_count++;
		if (intid == VTIMER_INTID)
			timer_arm();
		__asm__ volatile("msr " ICC_EOIR1_EL1 ", %0" : : "r"((uint64_t)intid));
		return;
	}

	con_clear(RED);
	con_str("PANIC", "Unexpected exception");
	con_hex("SLOT", (uint64_t)slot);
	con_hex("ELR", rsr("elr_el1"));
	con_hex("ESR", rsr("esr_el1"));
	con_hex("FAR", rsr("far_el1"));
	con_str("SLOTS", "1/5 IRQ 4 sync 7 SError");
	for (;;)
		__asm__ volatile("wfe");
}

void secondary_main(uint64_t cpu_id)
{
	(void)cpu_id;
	for (;;)
		__asm__ volatile("wfe");
}

static void gicd_wait_rwp(void)
{
	for (int i = 0; i < 1000000 && (rd32(GICD_BASE + GICD_CTLR) & GICD_CTLR_RWP); i++)
		;
}

/* find this CPU's redistributor frame by affinity; 0 if not found */
static uintptr_t gicr_find(uint64_t mpidr)
{
	uint64_t aff = (((mpidr >> 32) & 0xff) << 24) | (mpidr & 0xffffff);
	uintptr_t rd = GICR_BASE;

	for (int i = 0; i < 16; i++) {
		uint64_t typer = rd64(rd + GICR_TYPER);

		if ((typer >> 32) == aff)
			return rd;
		if (typer & (1UL << 4))	/* Last */
			return 0;
		rd += GICR_STRIDE;
	}
	return 0;
}

/* returns 0 ok, or a small error code shown on screen */
static int gicv3_init(uintptr_t *rd_out)
{
	/* distributor: disable, enable affinity routing, then enable group 1 */
	wr32(GICD_BASE + GICD_CTLR, 0);
	gicd_wait_rwp();
	wr32(GICD_BASE + GICD_CTLR, GICD_CTLR_ARE_NS);
	gicd_wait_rwp();
	wr32(GICD_BASE + GICD_CTLR, GICD_CTLR_ARE_NS | GICD_CTLR_ENABLE_G1A | GICD_CTLR_ENABLE_G1);
	gicd_wait_rwp();

	uintptr_t rd = gicr_find(rsr("mpidr_el1"));
	*rd_out = rd;
	if (!rd)
		return 1;

	/* wake the redistributor */
	uint32_t waker = rd32(rd + GICR_WAKER);
	wr32(rd + GICR_WAKER, waker & ~2U);	/* clear ProcessorSleep */
	int tries = 0;
	while ((rd32(rd + GICR_WAKER) & 4U) && tries++ < 1000000)	/* ChildrenAsleep */
		;
	if (rd32(rd + GICR_WAKER) & 4U)
		return 2;

	/* PPIs/SGIs: all disabled, default priority, then enable the timer PPI */
	uintptr_t sgi = rd + GICR_SGI_OFF;
	wr32(sgi + GICR_ICENABLER0, 0xffffffffU);
	for (int i = 0; i < 8; i++)
		wr32(sgi + GICR_IPRIORITYR + i * 4, 0xa0a0a0a0U);
	wr32(sgi + GICR_ISENABLER0, 1U << VTIMER_INTID);

	/* CPU interface */
	uint64_t sre;
	__asm__ volatile("mrs %0, " ICC_SRE_EL1 : "=r"(sre));
	if (!(sre & 1)) {
		__asm__ volatile("msr " ICC_SRE_EL1 ", %0" : : "r"(sre | 1));
		isb();
		__asm__ volatile("mrs %0, " ICC_SRE_EL1 : "=r"(sre));
		if (!(sre & 1))
			return 3;
	}
	__asm__ volatile("msr " ICC_PMR_EL1 ", %0" : : "r"((uint64_t)0xf0));
	__asm__ volatile("msr " ICC_BPR1_EL1 ", %0" : : "r"((uint64_t)0));
	__asm__ volatile("msr " ICC_CTLR_EL1 ", %0" : : "r"((uint64_t)0));	/* EOImode = drop+deactivate */
	__asm__ volatile("msr " ICC_IGRPEN1_EL1 ", %0" : : "r"((uint64_t)1));
	isb();
	return 0;
}

static uint32_t be32(uintptr_t a)
{
	return __builtin_bswap32(*(volatile uint32_t *)a);
}

void shim_main(void *fdt)
{
#ifdef PING
	/*
	 * Liveness test that does not depend on the display: wait 5 s (19.2 MHz counter,
	 * from the DTB), then ask PSCI to reset the phone. If the phone reboots by itself
	 * about 5 s after `fastboot boot`, this code ran.
	 */
	con_box(0, 0, 200, 200, RED);
	uint64_t t_end = rsr("cntvct_el0") + 5UL * 19200000UL;
	while (rsr("cntvct_el0") < t_end)
		;
	register uint64_t x0 __asm__("x0") = 0x84000009UL;	/* PSCI SYSTEM_RESET */
	__asm__ volatile("smc #0" : "+r"(x0) : : "x1", "x2", "x3", "memory");
	for (;;)
		__asm__ volatile("wfe");
#endif
	/* stage 0: before the MMU, before anything: red box proves the shim runs */
	con_box(0, 0, 200, 200, RED);

	struct mmu_info info;
	mmu_enable(&info);

	/* stage 1: green box (written through the NC mapping) proves the MMU works */
	con_box(220, 0, 200, 200, GREEN);

	con_clear(0x00102040);
#ifdef BOOT_XNU
	con_str("PROJECT", "ios-vince -> tulip BOOT");
	con_str("DEVICE", "Redmi Note 6 Pro SDM636");
	con_hex("MPIDR", rsr("mpidr_el1"));
	con_dec("EL", rsr("CurrentEL") >> 2);
	{
		const char *why = loader_boot((uintptr_t)fdt);
		con_str_color("LOADER", why, RED);
		for (;;)
			__asm__ volatile("wfi");
	}
#endif
	con_str("PROJECT", "ios-vince -> tulip");
	con_str("DEVICE", "Redmi Note 6 Pro SDM636");
	con_str("BUILD", FB_BPP == 32 ? "diag M2 fb=32bpp" : "diag M2 fb=24bpp");

	uint64_t el = rsr("CurrentEL") >> 2;
	con_dec("EL", el);
	con_hex("MIDR", rsr("midr_el1"));
	con_hex("MPIDR", rsr("mpidr_el1"));

	uint64_t m0 = rsr("id_aa64mmfr0_el1");
	uint64_t m1 = rsr("id_aa64mmfr1_el1");
	uint64_t i0 = rsr("id_aa64isar0_el1");
	con_hex("MMFR0", m0);
	con_dec("TGRAN4", (m0 >> 28) & 0xf);	/* 0 = 4K supported */
	con_dec("TGRAN16", (m0 >> 20) & 0xf);	/* 0 = 16K NOT supported */
	con_dec("TGRAN64", (m0 >> 24) & 0xf);	/* 0 = 64K supported */
	con_dec("PARANGE", m0 & 0xf);
	con_hex("MMFR1", m1);
	con_dec("PAN", (m1 >> 20) & 0xf);
	con_hex("ISAR0", i0);
	con_dec("LSE", (i0 >> 20) & 0xf);
	con_dec("CNTFRQ", rsr("cntfrq_el0"));
	con_hex("SCTLR0", info.sctlr_before);
	con_hex("SCTLR1", info.sctlr_after);

	con_hex("FDT", (uintptr_t)fdt);
	if (fdt && be32((uintptr_t)fdt) == 0xd00dfeedU)
		con_dec("FDTSIZE", be32((uintptr_t)fdt + 4));
	else
		con_str_color("FDT", "no magic", RED);

	con_str_color("MMU", "4K granule ON", GREEN);

	/* GICv3 */
	con_hex32("GICDTYPE", rd32(GICD_BASE + GICD_TYPER));
	con_hex32("GICDIIDR", rd32(GICD_BASE + GICD_IIDR));
	uintptr_t rd = 0;
	int err = gicv3_init(&rd);
	con_hex("GICR", rd);
	if (err) {
		con_dec("GICERR", (uint64_t)err);
		con_str_color("RESULT", "GICv3 init FAILED", RED);
		for (;;)
			__asm__ volatile("wfi");
	}
	con_str_color("GIC", "GICv3 ready", GREEN);

	/* timer interrupt test: unmask IRQs for ~1 s, expect ~10 ticks */
	timer_arm();
	__asm__ volatile("msr daifclr, #2" ::: "memory");
	uint64_t end = rsr("cntvct_el0") + rsr("cntfrq_el0");
	while (rsr("cntvct_el0") < end)
		;
	__asm__ volatile("msr daifset, #2" ::: "memory");
	wsr("cntv_ctl_el0", 0);

	con_dec("IRQS", irq_count);
	con_dec("LASTID", irq_last);
	if (irq_count >= 5)
		con_str_color("RESULT", "ALL OK: MMU+GICv3+timer", GREEN);
	else
		con_str_color("RESULT", "no timer IRQs received", RED);

	for (;;)
		__asm__ volatile("wfi");
}

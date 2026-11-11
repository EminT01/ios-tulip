/*
 * Minimal text console on the LK splash framebuffer (tulip).
 * font.h is the 8x16 bitmap font taken from ios-vince (zjh3215588/ios-vince).
 */
#include "console.h"
#include "font.h"

#define BYTES		(FB_BPP / 8)
#define SCALE		3
#define CH_W		(8 * SCALE)
#define CH_H		(16 * SCALE)
#define MARGIN		24
#define TOP		110	/* the notch / status area hides the first rows of the panel */
#define LABEL_COLS	8

static volatile uint8_t *const con_fb = (volatile uint8_t *)FB_BASE;
static uint32_t con_bg;
static int row;

static inline void putpix(volatile uint8_t *p, uint8_t r, uint8_t g, uint8_t b)
{
	p[0] = b;
	p[1] = g;
	p[2] = r;
#if FB_BPP == 32
	p[3] = 0xff;
#endif
}

void con_box(int x0, int y0, int w, int h, uint32_t rgb)
{
	for (int y = y0; y < y0 + h && y < FB_H; y++) {
		volatile uint8_t *line = con_fb + (uint64_t)y * FB_STRIDE;
		for (int x = x0; x < x0 + w && x < FB_W; x++)
			putpix(line + x * BYTES, (rgb >> 16) & 0xff, (rgb >> 8) & 0xff, rgb & 0xff);
	}
}

void con_clear(uint32_t bg)
{
	con_box(0, 0, FB_W, FB_H, bg);
	con_bg = bg;
	row = 0;
}

static void put_char(int col, char ch, uint32_t fg)
{
	if (ch < 0x20 || ch > 0x7e)
		ch = '?';
	const unsigned char *g = font8x16[ch - 0x20];
	int x0 = MARGIN + col * CH_W, y0 = TOP + row * CH_H;
	if (x0 + CH_W > FB_W || y0 + CH_H > FB_H)
		return;

	for (int gy = 0; gy < 16; gy++) {
		for (int gx = 0; gx < 8; gx++) {
			uint32_t c = (g[gy] & (0x80 >> gx)) ? fg : con_bg;

			for (int sy = 0; sy < SCALE; sy++) {
				volatile uint8_t *p = con_fb + (uint64_t)(y0 + gy * SCALE + sy) * FB_STRIDE
						      + (uint64_t)(x0 + gx * SCALE) * BYTES;
				for (int sx = 0; sx < SCALE; sx++)
					putpix(p + sx * BYTES, (c >> 16) & 0xff, (c >> 8) & 0xff, c & 0xff);
			}
		}
	}
}

static int put_str(int col, const char *s, uint32_t fg)
{
	while (*s)
		put_char(col++, *s++, fg);
	return col;
}

static void fmt_hex(char *buf, uint64_t v, int digits)
{
	static const char hex[] = "0123456789ABCDEF";
	for (int i = 0; i < digits; i++)
		buf[i] = hex[(v >> (4 * (digits - 1 - i))) & 0xf];
	buf[digits] = 0;
}

void con_str(const char *label, const char *s)
{
	put_str(0, label, YELLOW);
	put_str(LABEL_COLS, s, WHITE);
	row++;
}

void con_str_color(const char *label, const char *s, uint32_t color)
{
	put_str(0, label, color);
	put_str(LABEL_COLS, s, color);
	row++;
}

void con_hex(const char *label, uint64_t v)
{
	char buf[17];
	fmt_hex(buf, v, 16);
	con_str(label, buf);
}

void con_hex32(const char *label, uint32_t v)
{
	char buf[9];
	fmt_hex(buf, v, 8);
	con_str(label, buf);
}

void con_dec(const char *label, uint64_t v)
{
	char buf[21];
	int i = 20;
	buf[i] = 0;
	do {
		buf[--i] = '0' + (v % 10);
		v /= 10;
	} while (v);
	con_str(label, buf + i);
}

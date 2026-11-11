#pragma once
#include <stdint.h>

/*
 * Redmi Note 6 Pro (tulip, SDM636): LK continuous-splash framebuffer.
 * Source: DTB #29 reserved-memory splash_region@9d400000, 36 MiB (cont_splash_mem),
 * panel 1080x2280 (dmesg: "FrameBuffer[0] 1080x2280").
 * The pixel format is NOT measured yet. Qualcomm LK normally uses RGB888 (24 bpp)
 * for DSI panels (that is what ios-vince found on MSM8953), so 24 is the default;
 * build with -DFB_BPP=32 for the ARGB8888 variant.
 */
#ifndef FB_BPP
#define FB_BPP		24
#endif
#define FB_BASE		0x9d400000UL
#define FB_W		1080
#define FB_H		2280
#define FB_STRIDE	(FB_W * (FB_BPP / 8))

#define RED		0x00ff0000U
#define BLUE		0x000000a0U
#define WHITE		0x00ffffffU
#define YELLOW		0x00ffff00U
#define GREEN		0x0000ff00U
#define CYAN		0x0000ffffU

void con_box(int x0, int y0, int w, int h, uint32_t rgb);
void con_clear(uint32_t bg);
void con_str(const char *label, const char *s);
void con_str_color(const char *label, const char *s, uint32_t color);
void con_hex(const char *label, uint64_t v);
void con_hex32(const char *label, uint32_t v);
void con_dec(const char *label, uint64_t v);

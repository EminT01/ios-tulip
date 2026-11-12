# About this project

## What is it, really

`ios-tulip` runs Apple's open-source Darwin kernel — XNU, the same kernel that
sits under iOS and macOS — on a 2018 mid-range Android phone.

Not in a VM. Not emulated. On the metal: the Redmi Note 6 Pro's own CPU, its own
memory controller, its own interrupt controller, its own flash storage.

The phone does not know it is running Apple's kernel. Nothing is flashed
permanently to begin with: the phone boots the usual way, `fastboot` hands the
kernel a RAM image, and the phone is back to Android on the next reboot.

## Why would anyone do this

The short answer: because nobody had, on this chip.

The longer answer is that this is how you learn what an operating system
actually is. Reading about page tables and interrupt controllers teaches you
about as much as reading about swimming. You learn it when the kernel panics
four lines into boot and you have to find out why.

Every wall in this project was a real question with a real answer:

- The kernel printed nothing and died. Why? Because a boot argument turned
  panics into a debugger path that contained a single instruction this CPU
  cannot execute.
- The kernel said it had no random seed. Why? Because the device tree pointer
  was a virtual address and the kernel was reading it before its page tables
  existed.
- The kernel could not find its interrupt controller. Why? Because the early
  page tables mapped the kernel and the framebuffer but not the one gigabyte
  of memory-mapped I/O the controller lives in.

None of that is in any book. It is in the logs.

## How it is put together

The kernel is Apple's. Everything around it is ours: the loader that hands the
kernel its memory, the device tree that describes this particular phone, the
payload format, the drivers for chips Apple never wrote a driver for.

And underneath, a patch series that is a record of what three other ports got
right — one for the kernel core, one for the boot chain, one for the storage —
adapted to this phone's numbers. The README has the table.

## Who

A single-person research effort, with a lot of help from the people who did the
same thing first on other phones, and from Apple, who publish the kernel.

If you are reading this because you want to do the same on your own device:
start with the README, keep the patch series in order, and build the tools
that let you see what the kernel is doing before you build anything else.
That last part is the whole trick.

## What this is not

It is not a way to run iOS apps on Android. It is not a daily driver. It is not
finished. A phone that boots a kernel is a long way from a phone that shows a
lock screen — the kernel is the beginning of the work, not the end of it.

It is a bench. The kernel runs, the hardware answers, and every line of output
is something we put there and can explain.

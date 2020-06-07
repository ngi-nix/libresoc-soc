TOOLCHAIN=powerpc64-linux-gnu
CC=$(TOOLCHAIN)-gcc
AS=$(TOOLCHAIN)-as
AFLAGS=-mpwr9

all: kernel.bin

clean:
	rm *.o *.elf *.bin

kernel.elf: test.o
	$(TOOLCHAIN)-ld $^ -o $@ -T memmap

kernel.bin: kernel.elf
	$(TOOLCHAIN)-objcopy $< -O binary $@

%.o: %.s
	$(AS) $(AFLAGS) -c $< -o $@

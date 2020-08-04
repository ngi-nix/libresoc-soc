#ifndef __IRQ_H
#define __IRQ_H

static inline unsigned int irq_getie(void)
{
    return 0;
}

static inline void irq_setie(unsigned int ie)
{
    /*if(ie) csrs(); else csrc();*/
}

static inline unsigned int irq_getmask(void)
{
    unsigned int mask = 0;
    //asm volatile ("csrr %0, %1" : "=r"(mask) : "i"(CSR_IRQ_MASK));
    return mask;
}

static inline void irq_setmask(unsigned int mask)
{
    //asm volatile ("csrw %0, %1" :: "i"(CSR_IRQ_MASK), "r"(mask));
}

static inline unsigned int irq_pending(void)
{
    unsigned int pending = 0;
    //asm volatile ("csrr %0, %1" : "=r"(pending) : "i"(CSR_IRQ_PENDING));
    return pending;
}

#endif /* __IRQ_H */

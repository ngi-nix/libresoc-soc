# SPDX-License-Identifier: LGPL-2.1-or-later
# See Notices.txt for copyright information
from nmigen import Signal, Module, Elaboratable, Const
from typing import Iterable, FrozenSet, Optional, Iterator, Any, Union
from typing_extensions import final
from collections.abc import Set, Hashable


@final
class LFSRPolynomial(Set):
    def __init__(self, exponents: Iterable[int] = ()):
        max_exponent = 0

        def elements() -> Iterable[int]:
            nonlocal max_exponent
            yield 0  # 0 is always required
            for exponent in exponents:
                if not isinstance(exponent, int):
                    raise TypeError()
                if exponent < 0:
                    raise ValueError()
                if exponent > max_exponent:
                    max_exponent = exponent
                if exponent != 0:
                    yield exponent
        self.__exponents = frozenset(elements())
        self.__max_exponent = max_exponent

    @property
    def exponents(self) -> FrozenSet[int]:
        return self.__exponents

    @property
    def max_exponent(self) -> int:
        return self.__max_exponent

    def __hash__(self) -> int:
        return hash(self.exponents)

    def __contains__(self, x: Any) -> bool:
        return x in self.exponents

    def __len__(self) -> int:
        return len(self.exponents)

    def __iter__(self) -> Iterator[int]:
        return iter(self.exponents)

    def __str__(self) -> str:
        exponents = list(self.exponents)
        exponents.sort(reverse=True)
        retval = ""
        separator = ""
        for i in exponents:
            retval += separator
            separator = " + "
            if i == 0:
                retval += "1"
            elif i == 1:
                retval += "x"
            else:
                retval += f"x^{i}"
        return retval

    def __repr__(self) -> str:
        exponents = list(self.exponents)
        exponents.sort(reverse=True)
        return f"LFSRPolynomial({exponents!r})"


# list of selected polynomials from https://web.archive.org/web/20190418121923/https://en.wikipedia.org/wiki/Linear-feedback_shift_register#Some_polynomials_for_maximal_LFSRs  # noqa
LFSR_POLY_2 = LFSRPolynomial([2, 1, 0])
LFSR_POLY_3 = LFSRPolynomial([3, 2, 0])
LFSR_POLY_4 = LFSRPolynomial([4, 3, 0])
LFSR_POLY_5 = LFSRPolynomial([5, 3, 0])
LFSR_POLY_6 = LFSRPolynomial([6, 5, 0])
LFSR_POLY_7 = LFSRPolynomial([7, 6, 0])
LFSR_POLY_8 = LFSRPolynomial([8, 6, 5, 4, 0])
LFSR_POLY_9 = LFSRPolynomial([9, 5, 0])
LFSR_POLY_10 = LFSRPolynomial([10, 7, 0])
LFSR_POLY_11 = LFSRPolynomial([11, 9, 0])
LFSR_POLY_12 = LFSRPolynomial([12, 11, 10, 4, 0])
LFSR_POLY_13 = LFSRPolynomial([13, 12, 11, 8, 0])
LFSR_POLY_14 = LFSRPolynomial([14, 13, 12, 2, 0])
LFSR_POLY_15 = LFSRPolynomial([15, 14, 0])
LFSR_POLY_16 = LFSRPolynomial([16, 15, 13, 4, 0])
LFSR_POLY_17 = LFSRPolynomial([17, 14, 0])
LFSR_POLY_18 = LFSRPolynomial([18, 11, 0])
LFSR_POLY_19 = LFSRPolynomial([19, 18, 17, 14, 0])
LFSR_POLY_20 = LFSRPolynomial([20, 17, 0])
LFSR_POLY_21 = LFSRPolynomial([21, 19, 0])
LFSR_POLY_22 = LFSRPolynomial([22, 21, 0])
LFSR_POLY_23 = LFSRPolynomial([23, 18, 0])
LFSR_POLY_24 = LFSRPolynomial([24, 23, 22, 17, 0])


@final
class LFSR(Elaboratable):
    def __init__(self, polynomial: Union[Iterable[int], LFSRPolynomial]):
        self.__polynomial = LFSRPolynomial(polynomial)
        self.state = Signal(self.width, reset=1)
        self.enable = Signal(1, reset=1)

    @property
    def polynomial(self) -> LFSRPolynomial:
        return self.__polynomial

    @property
    def width(self) -> int:
        return self.polynomial.max_exponent

    def elaborate(self, platform: Any) -> Module:
        m = Module()
        feedback: Value = Const(0)
        for exponent in self.polynomial:
            if exponent > 0:
                feedback = feedback ^ self.state[exponent - 1]
        if self.width > 1:
            with m.If(self.enable):
                m.d.sync += self.state[1:self.width].eq(
                    self.state[0:self.width - 1])
                m.d.sync += self.state[0].eq(feedback)
        return m

# SPDX-License-Identifier: LGPL-2.1-or-later
# See Notices.txt for copyright information
from nmigen import Module
from typing import Iterable, Optional, Iterator, Any, Union
from typing_extensions import final


@final
class LFSRPolynomial(set):
    def __init__(self, exponents: Iterable[int] = ()):
        def elements() -> Iterable[int]: ...
    @property
    def exponents(self) -> list[int]: ...
    def __str__(self) -> str: ...
    def __repr__(self) -> str: ...


@final
class LFSR:
    def __init__(self, polynomial: Union[Iterable[int], LFSRPolynomial]): ...
    @property
    def polynomial(self) -> LFSRPolynomial: ...
    @property
    def width(self) -> int: ...
    def elaborate(self, platform: Any) -> Module: ...

#!/usr/bin/env python
# Copyright 2006--2007-01-21 Paul Sladen
# http://www.paul.sladen.org/projects/compression/
#
# You may use and distribute this code under any DFSG-compatible
# license (eg. BSD, GNU GPLv2).

import typing as T
import logging


# basically log(*args), but debug
def log(*args: T.Any) -> None:
    logging.debug(" ".join(map(str, args)))


class BitfieldBase:
    def __init__(self, x: T.Union[T.BinaryIO, "BitfieldBase"]) -> None:
        if isinstance(x, BitfieldBase):
            self.f: T.BinaryIO = x.f
            self.bits: int = x.bits
            self.bitfield: int = x.bitfield
            self.count: int = x.bitfield
        else:
            log("BitfieldBase.__init__", x)
            self.f = x
            self.bits = 0
            self.bitfield = 0x0
            self.count = 0

    def _read(self, n: int) -> bytes:
        s = self.f.read(n)
        if not s:
            raise Exception("Length Error")
        self.count += len(s)
        return s

    def needbits(self, n: int) -> None:
        while self.bits < n:
            self._more()

    def _mask(self, n: int) -> int:
        return (1 << n) - 1

    def toskip(self) -> int:
        return self.bits & 0x7

    def align(self) -> None:
        self.readbits(self.toskip())

    def tell(self) -> T.Tuple[int, int]:
        return self.count - ((self.bits + 7) >> 3), 7 - ((self.bits - 1) & 0x7)

    def tellbits(self) -> int:
        bytes, bits = self.tell()
        return (bytes << 3) + bits

    def readbits(self, n: int = 8) -> int:
        raise NotImplementedError()

    def snoopbits(self, n: int = 8) -> int:
        raise NotImplementedError()

    def _more(self) -> None:
        raise NotImplementedError()


class Bitfield(BitfieldBase):
    def _more(self) -> None:
        c = self._read(1)
        self.bitfield += ord(c) << self.bits
        self.bits += 8

    def snoopbits(self, n: int = 8) -> int:
        if n > self.bits:
            self.needbits(n)
        return self.bitfield & self._mask(n)

    def readbits(self, n: int = 8) -> int:
        if n > self.bits:
            self.needbits(n)
        r = self.bitfield & self._mask(n)
        self.bits -= n
        self.bitfield >>= n
        return r


class RBitfield(BitfieldBase):
    def _more(self) -> None:
        c = self._read(1)
        self.bitfield <<= 8
        self.bitfield += ord(c)
        self.bits += 8

    def snoopbits(self, n: int = 8) -> int:
        if n > self.bits:
            self.needbits(n)
        return (self.bitfield >> (self.bits - n)) & self._mask(n)

    def readbits(self, n: int = 8) -> int:
        if n > self.bits:
            self.needbits(n)
        r = (self.bitfield >> (self.bits - n)) & self._mask(n)
        self.bits -= n
        self.bitfield &= ~(self._mask(n) << self.bits)
        return r

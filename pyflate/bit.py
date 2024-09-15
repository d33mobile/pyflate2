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


class LengthError(Exception):
    pass


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
        log("BitfieldBase._read(%d) -> %r" % (n, s))
        if not s:
            raise LengthError()
        self.count += len(s)
        return s

    def needbits(self, n: int) -> None:
        log("BitfieldBase.needbits(%d)" % n)
        while self.bits < n:
            self._more()

    @staticmethod
    def _mask(n: int) -> int:
        return (1 << n) - 1

    def toskip(self) -> int:
        return self.bits & 0b111

    def align(self) -> None:
        self.readbits(self.toskip())

    def tell(self) -> T.Tuple[int, int]:
        return self.count - ((self.bits + 7) >> 3), 7 - ((self.bits - 1) & 0b111)

    def tellbits(self) -> int:
        bytes, bits = self.tell()
        return (bytes << 3) + bits

    def readbits(self, n: int = 8) -> int:  # pragma: no cover
        raise NotImplementedError()

    def snoopbits(self, n: int = 8) -> int:   # pragma: no cover
        raise NotImplementedError()

    def _more(self) -> None:  # pragma: no cover
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
            log("RBitfield.snoopbits(%d) needbits(%d)" % (n, n))
            self.needbits(n)
        return (self.bitfield >> (self.bits - n)) & self._mask(n)

    def readbits(self, n: int = 8) -> int:
        if n > self.bits:
            self.needbits(n)
        r = (self.bitfield >> (self.bits - n)) & self._mask(n)
        self.bits -= n
        self.bitfield &= ~(self._mask(n) << self.bits)
        return r


import unittest
import io


class TestBitfield(unittest.TestCase):
    def test_bitfield(self) -> None:
        b = Bitfield(io.BytesIO(b"\x01"))
        self.assertEqual(b.readbits(1), 1)
        self.assertEqual(b.tell(), (0, 1))
        self.assertEqual(b.readbits(1), 0)
        self.assertEqual(b.tell(), (0, 2))
        try:
            b.readbits(8)
            self.fail("expected exception")  # pragma: no cover
        except LengthError:
            pass
    def test_snoop(self) -> None:
        digit = 0b0110
        b = Bitfield(io.BytesIO(bytes([digit, digit])))
        self.assertEqual(b.snoopbits(2), 0b10)
        # once again, no needbits now
        self.assertEqual(b.snoopbits(2), 0b10)
        self.assertEqual(b.readbits(2), 0b10)
        # trigger the needbit
        # todo: readability
        self.assertEqual(b.snoopbits(8), 129)
        self.assertEqual(b.readbits(8), 129)
    def test_snoop_r(self) -> None:
        digit = 0b10110110
        b = RBitfield(io.BytesIO(bytes([digit] * 4)))
        self.assertEqual(b.snoopbits(2), 0b10)
        self.assertEqual(b.snoopbits(2), 0b10)
        self.assertEqual(b.readbits(2), 0b10)
        # trigger the needbit for snoop
        # todo: readability
        self.assertEqual(b.snoopbits(8), 218)
        self.assertEqual(b.readbits(8), 218)
        # trigger the needbit for read
        # todo: readability
        self.assertEqual(b.readbits(8), 218)
        self.assertEqual(b.snoopbits(8), 218)
    def test_construct(self) -> None:
        b = Bitfield(io.BytesIO(b"\x01"))
        b2 = Bitfield(b)
        self.assertEqual(b2.readbits(1), 1)
    def test_to_skip(self) -> None:
        b = Bitfield(io.BytesIO(bytes([0b10101])))
        self.assertEqual(b.bits, 0)
        self.assertEqual(b.toskip(), 0)
        b.readbits(1)
        self.assertEqual(b.toskip(), 0b111)
    def test_align(self) -> None:
        b = Bitfield(io.BytesIO(bytes([2, 1, 3, 7])))
        self.assertEqual(b.tellbits(), 0)
        b.readbits(1)
        self.assertEqual(b.toskip(), 0b111)
        b.align()
        self.assertEqual(b.tellbits(), 8)


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()  # pragma: no cover

#!/usr/bin/env python

"""
Bitfield reader classes. These classes are used to read a stream of bity
data, one or multiple bits at a time. Data is read from a file-like object.
Bit-based snooping is and telling the current position is also supported.

The Bitfield class reads the bits in the order.

There are also convenience functions for gzip format, such as align().
"""

# Copyright 2006--2007-01-21 Paul Sladen
# http://www.paul.sladen.org/projects/compression/
#
# You may use and distribute this code under any DFSG-compatible
# license (eg. BSD, GNU GPLv2).

import typing as T
import logging


def log(*args: T.Any) -> None:
    """Log the arguments at the debug level."""
    logging.debug(" ".join(map(str, args)))


class LengthError(Exception):
    """Exception raised when the end of the stream is reached."""



class Bitfield:
    """
    Base class for bitfield readers.
    """

    def __init__(self, x: T.BinaryIO) -> None:
        """Initialize the Bitfield object, either from a file-like
        object or another Bitfield object."""
        self.f = x
        self.bits = 0
        self.bitfield = 0x0
        self.count = 0

    def _read(self, n: int) -> bytes:
        """Read n bytes from the file-like object."""
        s = self.f.read(n)
        if not s:
            raise LengthError()
        self.count += len(s)
        return s

    def _needbits(self, n: int) -> None:
        """Triggered when the number of bits needed is greater than the
        number of bits available. This function reads more data from the
        file-like object."""
        while self.bits < n:
            self._more()

    @staticmethod
    def _mask(n: int) -> int:
        """Return a mask of n bits."""
        return (1 << n) - 1

    def toskip(self) -> int:
        """Return the number of bits to skip to align the bitfield."""
        return self.bits & 0b111

    def align(self) -> None:
        """Align the bitfield to the next byte boundary. (?)"""
        self.readbits(self.toskip())

    def tell(self) -> T.Tuple[int, int]:
        """Return the current position in the file-like object.

        The return value is a tuple of two integers. The first integer
        is the number of bytes read from the file-like object, and the
        second integer is the number of bits read from the file-like
        object.
        """
        return self.count - ((self.bits + 7) >> 3), 7 - (
            (self.bits - 1) & 0b111
        )

    def tellbits(self) -> int:
        """Return the current position in the file-like object in bits."""
        nbytes, nbits = self.tell()
        return (nbytes << 3) + nbits

    def _more(self) -> None:
        """Read more data from the file-like object."""
        c = self._read(1)
        self.bitfield += ord(c) << self.bits
        self.bits += 8

    def snoopbits(self, n: int = 8) -> int:
        """Read n bits from the file-like object without moving the
        current position."""
        if n > self.bits:
            self._needbits(n)
        return self.bitfield & self._mask(n)

    def readbits(self, n: int = 8) -> int:
        """Read n bits from the file-like object."""
        if n > self.bits:
            self._needbits(n)
        r = self.bitfield & self._mask(n)
        self.bits -= n
        self.bitfield >>= n
        return r


import unittest
import io


class TestBitfield(unittest.TestCase):
    """
    Test cases for the Bitfield class.
    """

    def test_bitfieldu_read(self) -> None:
        """
        Test reading bits from a Bitfield object.

        The test case reads the bits from a Bitfield object and checks
        if the bits are read correctly. We also check if the current
        position is updated correctly. The test case also checks if the
        LengthError exception is raised when the end of the stream is
        reached.
        """
        b = Bitfield(io.BytesIO(b"\x01"))
        self.assertEqual(b.readbits(1), 1)
        self.assertEqual(b.tell(), (0, 1))
        # surprisingly, no exception is raised yet
        self.assertEqual(b.readbits(1), 0)
        self.assertEqual(b.tell(), (0, 2))
        try:
            b.readbits(8)
            self.fail("expected exception")  # pragma: no cover
        except LengthError:
            pass

    def test_snoop(self) -> None:
        """
        Test snooping bits from a Bitfield object.
        """
        digit = 0b0110
        b = Bitfield(io.BytesIO(bytes([digit, digit])))
        self.assertEqual(b.snoopbits(2), 0b10)
        # once again, no _needbits now
        self.assertEqual(b.snoopbits(2), 0b10)
        self.assertEqual(b.readbits(2), 0b10)
        # trigger the needbit
        self.assertEqual(b.snoopbits(8), 0b10000001)
        self.assertEqual(b.readbits(8), 0b10000001)

    def test_construct(self) -> None:
        """
        Test constructing a Bitfield object from another Bitfield object.
        """
        b = Bitfield(io.BytesIO(b"\x01"))
        b2 = Bitfield(b)
        self.assertEqual(b2.readbits(1), 1)

    def test_to_skip(self) -> None:
        """
        Test the toskip() method of the Bitfield object.
        """
        b = Bitfield(io.BytesIO(bytes([0b10101, 0b1])))
        self.assertEqual(b.bitfield, 0)
        self.assertEqual(b.toskip(), 0)
        b.readbits(1)
        self.assertEqual(b.toskip(), 0b111)

    def test_align(self) -> None:
        """
        Test the align() method of the Bitfield object.
        """
        b = Bitfield(io.BytesIO(bytes([2, 1, 3, 7])))
        self.assertEqual(b.tellbits(), 0)
        b.readbits(1)
        self.assertEqual(b.toskip(), 0b111)
        b.align()
        self.assertEqual(b.tellbits(), 8)


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()  # pragma: no cover

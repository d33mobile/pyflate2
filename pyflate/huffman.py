#!/usr/bin/env python
# Copyright 2006--2007-01-21 Paul Sladen
# http://www.paul.sladen.org/projects/compression/
#
# You may use and distribute this code under any DFSG-compatible
# license (eg. BSD, GNU GPLv2).
#
# Stand-alone pure-Python DEFLATE (gzip) decoder/decompressor.
# This is probably most useful for research purposes/index building;  there
# is certainly some room for improvement in the Huffman bit-matcher.

import typing as T
from pprint import pformat

from pyflate.bit import Bitfield
from pyflate.log import log


class HuffmanLength:
    def __init__(self, code: int, bits: int = 0):
        self.code = code
        self.bits = bits
        self.reverse_symbol: T.Optional[int] = None

    def __repr__(self) -> str:
        if self.reverse_symbol is None:
            return (
                f'HL(code={self.code}, bits={self.bits}, '
                f'reverse_symbol={self.reverse_symbol})'
            )
        return (
            f'HL(code={self.code}, bits={self.bits}, '
            f'reverse_symbol={hex(self.reverse_symbol)})'
        )

    def __lt__(self, other: "HuffmanLength") -> bool:
        if self.bits == other.bits:
            return self.code < other.code
        else:
            return self.bits < other.bits

    def __gt__(self, other: "HuffmanLength") -> bool:
        if self.bits == other.bits:
            return self.code > other.code
        else:
            return self.bits > other.bits


def reverse_bits(v: int, n: int) -> int:
    a = 1 << 0
    b = 1 << (n - 1)
    z = 0
    for i in range(n - 1, -1, -2):
        z |= (v >> i) & a
        z |= (v << i) & b
        a <<= 1
        b >>= 1
    return z


def reverse_bytes(v: int, n: int) -> int:
    a = 0xFF << 0
    b = 0xFF << (n - 8)
    z = 0
    for i in range(n - 8, -8, -16):
        z |= (v >> i) & a
        z |= (v << i) & b
        a <<= 8
        b >>= 8
    return z


class HuffmanTable:
    def __init__(self, bootstrap: T.List[T.Tuple[int, int]]):
        l = []
        start, bits = bootstrap[0]
        for finish, endbits in bootstrap[1:]:
            if bits:
                for code in range(start, finish):
                    l.append(HuffmanLength(code, bits))
            start, bits = finish, endbits
            if endbits == -1:
                break
        l.sort()
        self.table = l

    def populate_huffman_symbols(self) -> None:
        bits, symbol = -1, -1
        for x in self.table:
            symbol += 1
            if x.bits != bits:
                symbol <<= x.bits - bits
                bits = x.bits
            x.reverse_symbol = reverse_bits(symbol, bits)
            # print printbits(x.symbol, bits), printbits(x.reverse_symbol, bits)

    def find_next_symbol(self, field: Bitfield, rev: bool = True) -> int:
        cached_length = -1
        cached = None
        for x in self.table:
            if cached_length != x.bits:
                cached = field.snoopbits(x.bits)
                cached_length = x.bits
            if x.reverse_symbol == cached:
                field.readbits(x.bits)
                log(
                    "found symbol",
                    hex(cached) if cached is not None else cached,
                    "of len",
                    cached_length,
                    "mapping to",
                    hex(x.code)
                )
                return x.code
        raise Exception(
            "unfound symbol, even after end of table @ " + repr(field.tell())
        )

    def __repr__(self) -> str:
        return f'HuffmanTable(self.table=\n{pformat(self.table)}'

class OrderedHuffmanTable(HuffmanTable):
    def __init__(self, lengths: T.List[int]):
        l = len(lengths)
        # z = list(map(None, list(range(l)), lengths)) + [(l, -1)]
        z = list(zip(list(range(l)), lengths)) + [(l, -1)]
        log("lengths to spans:", z)
        HuffmanTable.__init__(self, z)

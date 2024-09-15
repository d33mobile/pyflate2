#!/usr/bin/env python
# Copyright 2006--2007-01-21 Paul Sladen
# http://www.paul.sladen.org/projects/compression/
#
# You may use and distribute this code under any DFSG-compatible
# license (eg. BSD, GNU GPLv2).
#
# With the as-written implementation, there was a known bug in BWT
# decoding to do with repeated strings.  This has been worked around;
# see 'bwt_reverse()'.  Correct output is produced in all test cases
# but ideally the problem would be found...

import typing as T


def bwt_transform(L: bytes) -> T.List[int]:
    # Semi-inefficient way to get the character counts
    F = bytes(sorted(L))
    # base = list(map(F.find,list(map(chr,list(range(256))))))
    base = [F.find(bytes([i])) for i in range(256)]

    pointers = [-1] * len(L)
    # for symbol, i in map(None, list(map(ord,L)), range(len(L))):
    # but L is bytes, so no need to ord() it
    for i, symbol in enumerate(L):
        pointers[base[symbol]] = i
        base[symbol] += 1
    return pointers


def bwt_reverse(L: bytes, end: int) -> bytes:
    out = b""
    if len(L):
        T = bwt_transform(L)

        # STRAGENESS WARNING: There was a bug somewhere here in that
        # if the output of the BWT resolves to a perfect copy of N
        # identical strings (think exact multiples of 255 'X' here),
        # then a loop is formed.  When decoded, the output string would
        # be cut off after the first loop, typically '\0\0\0\0\xfb'.
        # The previous loop construct was:
        #
        #  next = T[end]
        #  while next != end:
        #      out += L[next]
        #      next = T[next]
        #  out += L[next]
        #
        # For the moment, I've instead replaced it with a check to see
        # if there has been enough output generated.  I didn't figured
        # out where the off-by-one-ism is yet---that actually produced
        # the cyclic loop.

        for _ in range(len(L)):
            end = T[end]
            out += bytes([L[end]])

    return out

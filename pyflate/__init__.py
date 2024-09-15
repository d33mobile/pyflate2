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
import logging
from pyflate.bit import Bitfield, RBitfield
from pyflate.huffman import HuffmanTable, OrderedHuffmanTable


# basically log(*args), but debug
def log(*args: T.Any) -> None:
    logging.debug(" ".join(map(str, args)))


def code_length_orders(i: int) -> int:
    return (16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15)[i]


def distance_base(i: int) -> int:
    return (
        1,
        2,
        3,
        4,
        5,
        7,
        9,
        13,
        17,
        25,
        33,
        49,
        65,
        97,
        129,
        193,
        257,
        385,
        513,
        769,
        1025,
        1537,
        2049,
        3073,
        4097,
        6145,
        8193,
        12289,
        16385,
        24577,
    )[i]


def length_base(i: int) -> int:
    return (
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        13,
        15,
        17,
        19,
        23,
        27,
        31,
        35,
        43,
        51,
        59,
        67,
        83,
        99,
        115,
        131,
        163,
        195,
        227,
        258,
    )[i - 257]


def extra_distance_bits(n: int) -> int:
    if 0 <= n <= 1:
        return 0
    elif 2 <= n <= 29:
        return (n >> 1) - 1
    else:
        raise Exception("illegal distance code")


def extra_length_bits(n: int) -> int:
    if 257 <= n <= 260 or n == 285:
        return 0
    elif 261 <= n <= 284:
        return ((n - 257) >> 2) - 1
    else:
        raise Exception("illegal length code")


# Sixteen bits of magic have been removed by the time we start decoding
def gzip_main(field: RBitfield) -> bytes:
    b = Bitfield(field)
    method = b.readbits(8)
    if method != 8:
        raise Exception("Unknown (not type eight DEFLATE) compression method")

    # Use flags, drop modification time, extra flags and OS creator type.
    flags = b.readbits(8)
    log("flags", hex(flags))
    mtime = b.readbits(32)
    log("mtime", hex(mtime))
    extra_flags = b.readbits(8)
    log("extra_flags", hex(extra_flags))
    os_type = b.readbits(8)
    log("os_type", hex(os_type))

    if flags & 0x04:  # structured GZ_FEXTRA miscellaneous data
        raise Exception("GZ_FEXTRA not supported")
    while flags & 0x08:  # original GZ_FNAME filename
        if not b.readbits(8):
            break
    while flags & 0x10:  # human readable GZ_FCOMMENT
        if not b.readbits(8):
            break
    if flags & 0x02:  # header-only GZ_FHCRC checksum
        b.readbits(16)

    log("gzip header skip", b.tell())
    out = b""

    # print 'header 0 count 0 bits', b.tellbits()

    while True:
        header_start = b.tell()
        bheader_start = b.tellbits()
        log("new block at", b.tell())
        lastbit = b.readbits(1)
        log("last bit", hex(lastbit))
        blocktype = b.readbits(2)
        log(
            "deflate-blocktype",
            blocktype,
            ["stored", "static huff", "dyna huff"][blocktype],
            "beginning at",
            header_start,
        )

        log("raw block data at", b.tell())
        if blocktype == 0:
            b.align()
            length = b.readbits(16)
            if length & b.readbits(16):
                raise Exception("stored block lengths do not match each other")
            # print "stored block of length", length
            # print 'raw data at', b.tell(), 'bits', b.tellbits() - bheader_start
            # print 'header 0 count 0 bits', b.tellbits() - bheader_start
            for i in range(length):
                out += bytes([b.readbits(8)])
            # print 'linear', b.tell()[0], 'count', length, 'bits', b.tellbits() - bheader_start

        elif blocktype == 1 or blocktype == 2:  # Huffman
            main_literals, main_distances = None, None

            if blocktype == 1:  # Static Huffman
                static_huffman_bootstrap = [
                    (0, 8),
                    (144, 9),
                    (256, 7),
                    (280, 8),
                    (288, -1),
                ]
                static_huffman_lengths_bootstrap = [(0, 5), (32, -1)]
                main_literals = HuffmanTable(static_huffman_bootstrap)
                main_distances = HuffmanTable(static_huffman_lengths_bootstrap)

            elif blocktype == 2:  # Dynamic Huffman
                dyna_start = b.tellbits()
                len_codes = b.readbits(5)
                literals = len_codes + 257
                distances = b.readbits(5) + 1
                code_lengths_length = b.readbits(4) + 4
                log(
                    "Dynamic Huffman tree: length codes: %s, distances codes: %s, code_lengths_length: %s"
                    % (len_codes, distances, code_lengths_length)
                )

                l = [0] * 19
                for i in range(code_lengths_length):
                    l[code_length_orders(i)] = b.readbits(3)
                log("lengths:", l)

                dynamic_codes = OrderedHuffmanTable(l)
                dynamic_codes.populate_huffman_symbols()
                dynamic_codes.min_max_bits()

                # Decode the code_lengths for both tables at once,
                # then split the list later

                code_lengths: T.List[int] = []
                n = 0
                while n < (literals + distances):
                    r = dynamic_codes.find_next_symbol(b)
                    if 0 <= r <= 15:  # literal bitlength for this code
                        count = 1
                        what = r
                    elif r == 16:  # repeat last code
                        count = 3 + b.readbits(2)
                        # Is this supposed to default to '0' if in the zeroth position?
                        what = code_lengths[-1]
                    elif r == 17:  # repeat zero
                        count = 3 + b.readbits(3)
                        what = 0
                    elif r == 18:  # repeat zero lots
                        count = 11 + b.readbits(7)
                        what = 0
                    else:
                        raise Exception(
                            "next code length is outside of the range 0 <= r <= 18"
                        )
                    code_lengths += [what] * count
                    n += count

                log("Literals/len lengths:", code_lengths[:literals])
                log("Dist lengths:", code_lengths[literals:])
                main_literals = OrderedHuffmanTable(code_lengths[:literals])
                main_distances = OrderedHuffmanTable(code_lengths[literals:])
                log("Read dynamic huffman tables", b.tellbits() - dyna_start, "bits")
            else:
                raise Exception("illegal unused blocktype in use @" + repr(b.tell()))

            # Common path for both Static and Dynamic Huffman decode now

            data_start = b.tell()
            log("raw data at", data_start, "bits", b.tellbits() - bheader_start)
            # print 'header 0 count 0 bits', b.tellbits() - bheader_start

            main_literals.populate_huffman_symbols()
            main_distances.populate_huffman_symbols()

            main_literals.min_max_bits()
            main_distances.min_max_bits()

            literal_count = 0
            literal_start = 0

            while True:
                lz_start = b.tellbits()
                r = main_literals.find_next_symbol(b)
                if 0 <= r <= 255:
                    if literal_count == 0:
                        literal_start = lz_start
                    literal_count += 1
                    log("found literal", repr((r)))
                    out += bytes([r])
                elif r == 256:
                    if literal_count > 0:
                        # print 'add 0 count', literal_count, 'bits', lz_start-literal_start, 'data', `out[-literal_count:]`
                        literal_count = 0
                    log("eos 0 count 0 bits", b.tellbits() - lz_start)
                    log("end of Huffman block encountered")
                    break
                elif 257 <= r <= 285:  # dictionary lookup
                    if literal_count > 0:
                        # print 'add 0 count', literal_count, 'bits', lz_start-literal_start, 'data', `out[-literal_count:]`
                        literal_count = 0
                    log("reading", extra_length_bits(r), "extra bits for len")
                    length_extra = b.readbits(extra_length_bits(r))
                    length = length_base(r) + length_extra

                    r1 = main_distances.find_next_symbol(b)
                    if 0 <= r1 <= 29:
                        log("reading", extra_distance_bits(r1), "extra bits for dist")
                        distance = distance_base(r1) + b.readbits(
                            extra_distance_bits(r1)
                        )
                        cached_length = length
                        while length > distance:
                            out += out[-distance:]
                            length -= distance
                        if length == distance:
                            out += out[-distance:]
                        else:
                            out += out[-distance : length - distance]
                        log("dictionary lookup: length", cached_length)
                        log(
                            "copy",
                            -distance,
                            "num bits",
                            b.tellbits() - lz_start,
                            "data",
                            repr(out[-cached_length:]),
                        )
                    elif 30 <= r1 <= 31:
                        raise Exception(
                            "illegal unused distance symbol in use @" + repr(b.tell())
                        )
                elif 286 <= r <= 287:
                    raise Exception(
                        "illegal unused literal/length symbol in use @" + repr(b.tell())
                    )
        elif blocktype == 3:
            raise Exception("illegal unused blocktype in use @" + repr(b.tell()))

        if lastbit:
            log("this was the last block, time to leave", b.tell())
            break

    footer_start = b.tell()
    bfooter_start = b.tellbits()
    b.align()
    crc = b.readbits(32)
    final_length = b.readbits(32)
    # print len(out)
    next_unused = b.tell()
    # print 'deflate-end-of-stream', 5, 'beginning at', footer_start, 'raw data at', next_unused, 'bits', b.tellbits() - bfooter_start
    log("deflate-end-of-stream")
    # print 'crc', hex(crc), 'final length', final_length
    # print 'header 0 count 0 bits', b.tellbits()-bfooter_start

    return out

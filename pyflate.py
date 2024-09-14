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
#
# With the as-written implementation, there was a known bug in BWT
# decoding to do with repeated strings.  This has been worked around;
# see 'bwt_reverse()'.  Correct output is produced in all test cases
# but ideally the problem would be found...

import typing as T
import logging

#basically log(*args), but debug
def log(*args: T.Any) -> None:
    logging.debug(" ".join(map(str, args)))

class BitfieldBase:
    def __init__(self, x: T.Union[T.BinaryIO, 'BitfieldBase']) -> None:
        if isinstance(x,BitfieldBase):
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
        return self.count - ((self.bits+7) >> 3), 7 - ((self.bits-1) & 0x7)
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

def printbits(v: int, n: int) -> str:
    o = ''
    for i in range(n):
        if v & 1:
            o = '1' + o
        else:
            o = '0' + o
        v >>= 1
    return o

class HuffmanLength:
    def __init__(self, code: int, bits: int = 0):
        self.code = code
        self.bits = bits
        self.symbol: T.Optional[int] = None
        self.reverse_symbol: T.Optional[int] = None
    def __repr__(self) -> str:
        return repr((self.code, self.bits, self.symbol, self.reverse_symbol))

    def __lt__(self, other: 'HuffmanLength') -> bool:
        if self.bits == other.bits:
            return self.code < other.code
        else:
            return self.bits < other.bits

    def __gt__(self, other: 'HuffmanLength') -> bool:
        if self.bits == other.bits:
            return self.code > other.code
        else:
            return self.bits > other.bits


def reverse_bits(v: int, n: int) -> int:
    a = 1 << 0
    b = 1 << (n - 1)
    z = 0
    for i in range(n-1, -1, -2):
        z |= (v >> i) & a
        z |= (v << i) & b
        a <<= 1
        b >>= 1
    return z

def reverse_bytes(v: int, n: int) -> int:
    a = 0xff << 0
    b = 0xff << (n - 8)
    z = 0
    for i in range(n-8, -8, -16):
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
                symbol <<= (x.bits - bits)
                bits = x.bits
            x.symbol = symbol
            x.reverse_symbol = reverse_bits(symbol, bits)
            #print printbits(x.symbol, bits), printbits(x.reverse_symbol, bits)

    def tables_by_bits(self) -> None:
        d: T.Dict[int, T.List[HuffmanLength]] = {}
        for x in self.table:
            try:
                d[x.bits].append(x)
            except:
                d[x.bits] = [x]
        pass

    def min_max_bits(self) -> None:
        self.min_bits, self.max_bits = 16, -1
        for x in self.table:
            if x.bits < self.min_bits: self.min_bits = x.bits
            if x.bits > self.max_bits: self.max_bits = x.bits

    def _find_symbol(self, bits: int, symbol: int, table: T.List[HuffmanLength]) -> int:
        for h in table:
            if h.bits == bits and h.reverse_symbol == symbol:
                #print "found, processing", h.code
                return h.code
        return -1

    #def find_next_symbol(self, field, reversed = True):
    def find_next_symbol(self, field: Bitfield, reversed: bool = True) -> int:
        cached_length = -1
        cached = None
        for x in self.table:
            if cached_length != x.bits:
                cached = field.snoopbits(x.bits)
                cached_length = x.bits
            if (reversed and x.reverse_symbol == cached) or (not reversed and x.symbol == cached):
                field.readbits(x.bits)
                log("found symbol", hex(cached) if cached is not None else cached, "of len", cached_length, "mapping to", hex(x.code))
                return x.code
        raise Exception("unfound symbol, even after end of table @ " + repr(field.tell()))
            
        for bits in range(self.min_bits, self.max_bits + 1):
            #print printbits(field.snoopbits(bits),bits)
            r = self._find_symbol(bits, field.snoopbits(bits), self.table)
            if 0 <= r:
                field.readbits(bits)
                return r
            elif bits == self.max_bits:
                raise Exception("unfound symbol, even after max_bits")

class OrderedHuffmanTable(HuffmanTable):
    def __init__(self, lengths: T.List[int]):
        l = len(lengths)
        #z = list(map(None, list(range(l)), lengths)) + [(l, -1)]
        z = list(zip(list(range(l)), lengths)) + [(l, -1)]
        log("lengths to spans:", z)
        HuffmanTable.__init__(self, z)

def code_length_orders(i: int) -> int:
    return (16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15)[i]

def distance_base(i: int) -> int:
    return (1,2,3,4,5,7,9,13,17,25,33,49,65,97,129,193,257,385,513,769,1025,1537,2049,3073,4097,6145,8193,12289,16385,24577)[i]

def length_base(i: int) -> int:
    return (3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227,258)[i-257]

def extra_distance_bits(n :int) -> int:
    if 0 <= n <= 1:
        return 0
    elif 2 <= n <= 29:
        return (n >> 1) - 1
    else:
        raise Exception("illegal distance code")

def extra_length_bits(n :int) -> int:
    if 257 <= n <= 260 or n == 285:
        return 0
    elif 261 <= n <= 284:
        return ((n-257) >> 2) - 1
    else:
        raise Exception("illegal length code")

def move_to_front(l: T.List[int], c: int) -> None:
    l[:] = l[c:c+1] + l[0:c] + l[c+1:]

def bwt_transform(L: bytes) -> T.List[int]:
    # Semi-inefficient way to get the character counts
    F = bytes(sorted(L))
    #base = list(map(F.find,list(map(chr,list(range(256))))))
    base = [F.find(bytes([i])) for i in range(256)]

    pointers = [-1] * len(L)
    #for symbol, i in map(None, list(map(ord,L)), range(len(L))):
    # but L is bytes, so no need to ord() it
    for i, symbol in enumerate(L):
        pointers[base[symbol]] = i
        base[symbol] += 1
    return pointers

def bwt_reverse(L: bytes, end: int) -> bytes:
    out = b''
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

        for i in range(len(L)):
            end = T[end]
            out += bytes([L[end]])

    return out

# Sixteen bits of magic have been removed by the time we start decoding
def gzip_main(field: RBitfield) -> bytes:
    b = Bitfield(field)
    method = b.readbits(8)
    if method != 8:
        raise Exception("Unknown (not type eight DEFLATE) compression method")

    # Use flags, drop modification time, extra flags and OS creator type.
    flags = b.readbits(8)
    log('flags', hex(flags))
    mtime = b.readbits(32)
    log('mtime', hex(mtime))
    extra_flags = b.readbits(8)
    log('extra_flags', hex(extra_flags))
    os_type = b.readbits(8)
    log('os_type', hex(os_type))

    if flags & 0x04: # structured GZ_FEXTRA miscellaneous data
        raise Exception("GZ_FEXTRA not supported")
    while flags & 0x08: # original GZ_FNAME filename
        if not b.readbits(8):
            break
    while flags & 0x10: # human readable GZ_FCOMMENT
        if not b.readbits(8):
            break
    if flags & 0x02: # header-only GZ_FHCRC checksum
        b.readbits(16)

    log("gzip header skip", b.tell())
    out = b''

    #print 'header 0 count 0 bits', b.tellbits()

    while True:
        header_start = b.tell()
        bheader_start = b.tellbits()
        log('new block at', b.tell())
        lastbit = b.readbits(1)
        log("last bit", hex(lastbit))
        blocktype = b.readbits(2)
        log("deflate-blocktype", blocktype, ["stored", "static huff", "dyna huff"][blocktype], 'beginning at', header_start)

        log('raw block data at', b.tell())
        if blocktype == 0:
            b.align()
            length = b.readbits(16)
            if length & b.readbits(16):
                raise Exception("stored block lengths do not match each other")
            #print "stored block of length", length
            #print 'raw data at', b.tell(), 'bits', b.tellbits() - bheader_start
            #print 'header 0 count 0 bits', b.tellbits() - bheader_start
            for i in range(length):
                out += bytes([b.readbits(8)])
            #print 'linear', b.tell()[0], 'count', length, 'bits', b.tellbits() - bheader_start

        elif blocktype == 1 or blocktype == 2: # Huffman
            main_literals, main_distances = None, None

            if blocktype == 1: # Static Huffman
                static_huffman_bootstrap = [(0, 8), (144, 9), (256, 7), (280, 8), (288, -1)]
                static_huffman_lengths_bootstrap = [(0, 5), (32, -1)]
                main_literals = HuffmanTable(static_huffman_bootstrap)
                main_distances = HuffmanTable(static_huffman_lengths_bootstrap)

            elif blocktype == 2: # Dynamic Huffman
                dyna_start = b.tellbits()
                len_codes = b.readbits(5)
                literals = len_codes + 257
                distances = b.readbits(5) + 1
                code_lengths_length = b.readbits(4) + 4
                log("Dynamic Huffman tree: length codes: %s, distances codes: %s, code_lengths_length: %s" % \
                    (len_codes, distances, code_lengths_length))

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
                    if 0 <= r <= 15: # literal bitlength for this code
                        count = 1
                        what = r
                    elif r == 16: # repeat last code
                        count = 3 + b.readbits(2)
                        # Is this supposed to default to '0' if in the zeroth position?
                        what = code_lengths[-1]
                    elif r == 17: # repeat zero
                        count = 3 + b.readbits(3)
                        what = 0
                    elif r == 18: # repeat zero lots
                        count = 11 + b.readbits(7)
                        what = 0
                    else:
                        raise Exception("next code length is outside of the range 0 <= r <= 18")
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
            log('raw data at', data_start, 'bits', b.tellbits() - bheader_start)
            #print 'header 0 count 0 bits', b.tellbits() - bheader_start

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
                    log('found literal', repr((r)))
                    out += bytes([r])
                elif r == 256:
                    if literal_count > 0:
                        #print 'add 0 count', literal_count, 'bits', lz_start-literal_start, 'data', `out[-literal_count:]`
                        literal_count = 0
                    log('eos 0 count 0 bits', b.tellbits() - lz_start)
                    log('end of Huffman block encountered')
                    break
                elif 257 <= r <= 285: # dictionary lookup
                    if literal_count > 0:
                        #print 'add 0 count', literal_count, 'bits', lz_start-literal_start, 'data', `out[-literal_count:]`
                        literal_count = 0
                    log("reading", extra_length_bits(r), "extra bits for len")
                    length_extra = b.readbits(extra_length_bits(r))
                    length = length_base(r) + length_extra
                    
                    r1 = main_distances.find_next_symbol(b)
                    if 0 <= r1 <= 29:
                        log("reading", extra_distance_bits(r1), "extra bits for dist")
                        distance = distance_base(r1) + b.readbits(extra_distance_bits(r1))
                        cached_length = length
                        while length > distance:
                            out += out[-distance:]
                            length -= distance
                        if length == distance:
                            out += out[-distance:]
                        else:
                            out += out[-distance:length-distance]
                        log('dictionary lookup: length', cached_length, end=' ')
                        log('copy', -distance, 'num bits', b.tellbits() - lz_start, 'data', repr(out[-cached_length:]))
                    elif 30 <= r1 <= 31:
                        raise Exception("illegal unused distance symbol in use @" + repr(b.tell()))
                elif 286 <= r <= 287:
                    raise Exception("illegal unused literal/length symbol in use @" + repr(b.tell()))
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
    #print len(out)
    next_unused = b.tell()
    #print 'deflate-end-of-stream', 5, 'beginning at', footer_start, 'raw data at', next_unused, 'bits', b.tellbits() - bfooter_start
    log('deflate-end-of-stream')
    #print 'crc', hex(crc), 'final length', final_length
    #print 'header 0 count 0 bits', b.tellbits()-bfooter_start

    return out

import sys

def _main() -> None:
    # set to debug, add timestamp in square brackets
    fmt = '%(asctime)s %(levelname)s: %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=fmt)
    filename = sys.argv[1]
    input = open(filename, 'rb')
    field = RBitfield(input)

    magic = field.readbits(16)
    if magic == 0x1f8b: # GZip
        out = gzip_main(field)
    else:
        raise Exception("Unknown file magic "+hex(magic)+", not a gzip file")

    #f = open('/dev/stdout', 'w')
    f = sys.stdout
    f.write(out.decode())
    f.close()
    input.close()
        
if __name__=='__main__':
    if len(sys.argv) != 2:
        program = sys.argv[0]
        print(program +':', 'usage:', program, '<filename.gz>')
        print('\tThe contents will be decoded and decompressed plaintext written to "./out".')
        sys.exit(1)

    _main()

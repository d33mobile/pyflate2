#!/usr/bin/env python
# Copyright 2006--2007-01-21 Paul Sladen
# http://www.paul.sladen.org/projects/compression/
#
# You may use and distribute this code under any DFSG-compatible
# license (eg. BSD, GNU GPLv2).

import logging
import sys

from pyflate.bit import Bitfield
from pyflate import gzip_main


def _main() -> None:
    # set to debug, add timestamp in square brackets
    fmt = "%(asctime)s %(levelname)s: %(message)s"
    logging.basicConfig(level=logging.DEBUG, format=fmt)
    filename = sys.argv[1]
    inp = open(filename, "rb")
    out = gzip_main(inp)

    # f = open('/dev/stdout', 'w')
    f = sys.stdout
    f.write(out.decode())


if __name__ == "__main__":
    if len(sys.argv) != 2:
        program = sys.argv[0]
        print("usage:", program, "<filename.gz>")
        print(
            '\tThe contents will be decoded and decompressed plaintext written to "./out".'
        )
        sys.exit(1)

    _main()

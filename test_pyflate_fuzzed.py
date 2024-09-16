#!/usr/bin/env python

import unittest
import gzip
import io
import pathlib
import sys
import atexit

from pyflate import RBitfield
from pyflate.__main__ import gzip_main


processed = 0
successes = 0
@atexit.register
def print_processed():
    sys.stderr.write(f"Processed {processed} files\n")
    sys.stderr.write(f"Successes: {successes}\n")
    sys.stderr.flush()

class PyflateFuzzedTestCase(unittest.TestCase):
    def test_every_file_in_queue_directory(self):
        global processed, successes
        queue_dir = list(pathlib.Path("queue").glob("id*"))
        for fp in queue_dir:
            with open(fp, "rb") as file, self.subTest(file=file):
                content = file.read()
                raw_file = io.BytesIO(content)
                field = RBitfield(raw_file)
                our_out = ref_decompressed = None
                try:
                    ref_decompressed = gzip.decompress(raw_file.read())
                except Exception as e:
                    pass

                try:
                    raw_file.seek(0)
                    magic = field.readbits(16)
                    #self.assertEqual(magic, 0x1F8B)
                    if magic != 0x1F8B:
                        continue

                    our_out = gzip_main(field)
                except Exception as e:
                    pass
                self.assertEqual(our_out, ref_decompressed)
                if our_out == ref_decompressed:
                    successes += 1
        processed = len(queue_dir)


if __name__ == "__main__":
    unittest.main()

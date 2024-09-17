#!/usr/bin/env python

import unittest
import gzip
import io
import pathlib
import sys
import atexit
import subprocess

from pyflate import RBitfield
from pyflate.__main__ import gzip_main


actually_processed = 0
processed = 0
successes = 0
@atexit.register
def print_processed():
    perc = (successes / actually_processed) * 100 if actually_processed else 0
    sys.stderr.write(f"{processed=}, {actually_processed=}\n")
    sys.stderr.write(f"Successes: {successes} ({perc:0.2f}%)\n")
    sys.stderr.flush()

def test_using_gzip_cli(fp):
    return subprocess.check_output(["zcat", fp], stderr=subprocess.DEVNULL)

class PyflateFuzzedTestCase(unittest.TestCase):
    def test_every_file_in_queue_directory(self):
        global processed, successes, actually_processed
        queue_dir = list(pathlib.Path("queue").glob("id*"))
        for fp in queue_dir:
            with open(fp, "rb") as file, self.subTest(file=file):
                content = file.read()
                raw_file = io.BytesIO(content)
                field = RBitfield(raw_file)
                our_out = ref_decompressed = None
                try:
                    ref_decompressed = gzip.decompress(raw_file.read())
                    #ref_decompressed = test_using_gzip_cli(fp)
                except Exception as e:
                    #continue
                    pass

                try:
                    raw_file.seek(0)
                    magic = field.readbits(16)
                    #self.assertEqual(magic, 0x1F8B)

                    actually_processed += 1
                    #if magic != 0x1F8B:
                    #    continue

                    our_out = gzip_main(field)
                except Exception as e:
                    pass
                self.assertEqual(our_out, ref_decompressed)
                if our_out == ref_decompressed:
                    successes += 1
        processed = len(queue_dir)


if __name__ == "__main__":
    unittest.main()

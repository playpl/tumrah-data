"""Audio is compressed before upload (owner, 2026-11-11)."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import upload_media as U


class CompressTest(unittest.TestCase):
    def test_key(self):
        self.assertEqual(U.compressed_key("lectures/year2-cns/cns-021/recording.mp3"), "lectures/year2-cns/cns-021/recording.48k.m4a")
        self.assertEqual(U.compressed_key("lectures/year2-cns/cns-069/recording.oga"), "lectures/year2-cns/cns-069/recording.48k.m4a")
        self.assertEqual(U.compressed_key("lectures/year2-cns/cns-021/recording.48k.m4a"), "lectures/year2-cns/cns-021/recording.48k.m4a")

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
    def test_compress_makes_mono_aac(self):
        with tempfile.TemporaryDirectory() as d:
            src, out = Path(d) / "in.wav", Path(d) / "c" / "out.48k.m4a"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                            "-ac", "2", str(src)], check=True)
            U.compress(src, out)
            probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,channels", "-of", "csv=p=0",
                                    str(out)], capture_output=True, text=True).stdout.strip()
            self.assertEqual(probe, "aac,1")
            self.assertLess(out.stat().st_size, src.stat().st_size)


if __name__ == "__main__":
    unittest.main()

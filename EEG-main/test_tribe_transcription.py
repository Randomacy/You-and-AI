"""Transcript contract tests without downloading or calling speech models."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from tribe_transcription import transcribe


@unittest.skipUnless(importlib.util.find_spec("pandas"), "Requires isolated TRIBE runtime")
class TranscriptTests(unittest.TestCase):
    def test_word_timing_and_cpu_precision(self):
        def run(command, **kwargs):
            self.assertEqual(command[command.index('--compute_type') + 1], 'int8')
            self.assertEqual(kwargs['timeout'], 600)
            output = Path(command[command.index('--output_dir') + 1])
            (output / 'clip.json').write_text(json.dumps({'segments': [
                {'text': 'hello there', 'words': [
                    {'word': 'hello', 'start': 1.2, 'end': 1.5},
                    {'word': 'there'}]}]}))
        with patch('tribe_transcription.subprocess.run', side_effect=run):
            result = transcribe(Path('clip.wav'), 'english')
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result.iloc[0]['duration'], .3)
        self.assertEqual(result.iloc[0]['start'], 1.2)

    def test_unknown_language_rejected_before_subprocess(self):
        with patch('tribe_transcription.subprocess.run') as run:
            with self.assertRaises(ValueError):
                transcribe(Path('clip.wav'), 'unknown')
            run.assert_not_called()

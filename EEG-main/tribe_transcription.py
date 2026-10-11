"""Local WhisperX adapter for TRIBE on CPU; keeps its dependencies isolated."""
import json
import os
from pathlib import Path
import subprocess
import tempfile


def transcribe(wav_filename, language):
    import pandas as pd
    import imageio_ffmpeg

    codes = {'english': 'en', 'french': 'fr', 'spanish': 'es', 'dutch': 'nl', 'chinese': 'zh'}
    if language not in codes:
        raise ValueError(f'Unsupported language: {language}')
    with tempfile.TemporaryDirectory() as output_dir:
        command = [
            'uv', 'run', '--no-project', '--python', '3.11',
            '--with', 'whisperx==3.8.6', '--with', 'truststore==0.10.4',
            'python', str(Path(__file__).resolve()), str(wav_filename),
            '--model', 'large-v3', '--language', codes[language],
            '--device', 'cpu', '--compute_type', 'int8', '--batch_size', '4',
            '--output_dir', output_dir, '--output_format', 'json',
        ]
        if language == 'english':
            command += ['--align_model', 'WAV2VEC2_ASR_LARGE_LV60K_960H']
        env = {k: v for k, v in os.environ.items() if k != 'MPLBACKEND'}
        # WhisperX invokes ffmpeg by name; expose the existing bundled binary
        # only to this subprocess, without changing the system installation.
        bin_dir = Path(output_dir) / 'bin'
        bin_dir.mkdir()
        (bin_dir / 'ffmpeg').symlink_to(imageio_ffmpeg.get_ffmpeg_exe())
        env['PATH'] = str(bin_dir) + os.pathsep + env.get('PATH', '')
        subprocess.run(command, check=True, env=env, timeout=600)
        result = json.loads((Path(output_dir) / f'{Path(wav_filename).stem}.json').read_text())
    words = []
    for index, segment in enumerate(result['segments']):
        for word in segment.get('words', []):
            if 'start' not in word or 'end' not in word:
                continue
            words.append({'text': word['word'].replace('"', ''),
                          'start': word['start'], 'duration': word['end'] - word['start'],
                          'sequence_id': index, 'sentence': segment['text'].replace('"', '')})
    return pd.DataFrame(words, columns=['text', 'start', 'duration', 'sequence_id', 'sentence'])


if __name__ == '__main__':
    import truststore
    truststore.inject_into_ssl()
    from whisperx.__main__ import cli
    cli()

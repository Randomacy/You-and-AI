"""Isolated official-model inference. No fabricated fallback predictions."""
import argparse,json,time
from pathlib import Path
import numpy as np

def main():
 p=argparse.ArgumentParser();p.add_argument('video');p.add_argument('output');p.add_argument('--device',default='cpu');a=p.parse_args()
 import truststore
 truststore.inject_into_ssl()
 from tribev2 import TribeModel
 from tribev2.eventstransforms import ExtractWordsFromAudio
 from tribe_transcription import transcribe
 if a.device != "cuda":
  ExtractWordsFromAudio._get_transcript_from_audio = staticmethod(transcribe)
 began=time.monotonic();root=Path(__file__).resolve().parent
 config={'data.text_feature.device':a.device,'data.audio_feature.device':a.device,'data.video_feature.image.device':a.device}
 model=TribeModel.from_pretrained('facebook/tribev2',cache_folder=str(root/'.tribe/cache'),device=a.device,config_update=config)
 print('TRIBE checkpoint loaded; extracting media events', flush=True)
 events=model.get_events_dataframe(video_path=str(Path(a.video).resolve()))
 print(f'Media events ready: {len(events)}; extracting features and predicting', flush=True)
 preds,segments=model.predict(events=events)
 if preds.ndim!=2 or not np.isfinite(preds).all():raise ValueError('Invalid model output')
 np.savez_compressed(Path(a.output).with_suffix('.npz'),predictions=preds)
 metadata=[]
 for segment in segments:
  metadata.append({'start_seconds':float(segment.start),'duration_seconds':float(segment.duration),'timeline':str(segment.timeline)})
 result={'model':'facebook/tribev2','shape':list(preds.shape),'elapsed_seconds':time.monotonic()-began,'segments':metadata,'vertex_mean':preds.mean(axis=1).tolist(),'vertex_std':preds.std(axis=1).tolist(),'timing_verified':False,'note':'Raw segment metadata preserved. Hemodynamic offset and overlap alignment require validation before timeline painting.'}
 Path(a.output).write_text(json.dumps(result,allow_nan=False))
if __name__=='__main__':main()

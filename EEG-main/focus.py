"""Uncalibrated spectral engagement proxy; never a focus classifier."""
import numpy as np
from scipy.signal import welch

def estimate_focus(filtered, fs, warnings, synthetic=False):
    if synthetic:
        return {'status':'unclear','reason':'Synthetic signal: focus is not estimated.'}
    if warnings:
        return {'status':'unclear','reason':'Signal quality is too poor. This does not mean you are unfocused.'}
    x=np.asarray(filtered)
    if x.ndim!=2 or x.shape[0]!=8 or x.shape[1]<fs*3 or not np.isfinite(x).all():
        return {'status':'unclear','reason':'Collecting a fresh signal window.'}
    f,p=welch(x[[2,3,6]],fs=fs,nperseg=fs*2,axis=1)
    bands=[p[:,(f>=lo)&(f<hi)].sum(axis=1) for lo,hi in [(4,8),(8,13),(13,30)]]
    theta,alpha,beta=bands
    if np.any(theta+alpha<1e-12):
        return {'status':'unclear','reason':'Insufficient band power.'}
    ratio=float(np.median(beta/(theta+alpha)))
    return {'status':'experimental','ratio':round(ratio,3),'balance':round(ratio/(1+ratio),4),
            'reason':'Uncalibrated engagement proxy from Fz, Cz and Pz. Higher values are not proof of better focus.'}

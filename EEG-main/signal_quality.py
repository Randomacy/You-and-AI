"""Engineering diagnostics, not an impedance measurement or clinical assessment."""
import numpy as np
from scipy.signal import detrend, welch

CHANNELS = ['Fp1','Fp2','Fz','Cz','T7','T8','Pz','Oz']
# Verified against BrainFlow Knight parser at gain 12, signed 16-bit ADC.
ADC_LIMIT_UV = 4 / 12 * 1e6


def diagnose(raw, fs):
    raw = np.asarray(raw, dtype=float)
    if raw.ndim != 2 or raw.shape[0] != 8 or raw.shape[1] < fs or not np.isfinite(raw).all():
        raise ValueError('Diagnostics require at least one second of finite eight-channel samples')
    ac = detrend(raw, axis=1)
    f, psd = welch(ac, fs=fs, nperseg=min(fs*2, raw.shape[1]), axis=1)
    total = psd[:, (f>=1)&(f<=60)].sum(axis=1)
    line = psd[:, (f>=49)&(f<=51)].sum(axis=1) / np.maximum(total,1e-20)
    df=f[1]-f[0]
    absolute_line=psd[:,(f>=49)&(f<=51)].sum(axis=1)*df
    absolute_other=np.maximum(total*df-absolute_line,0)
    result=[]
    for i,name in enumerate(CHANNELS):
        row=raw[i]
        clipped=float(np.mean(np.abs(row)>=ADC_LIMIT_UV*.99))
        span=float(np.ptp(row))
        notes=[]
        if span < .1: notes.append('Flat: check channel activation/contact')
        if clipped > .01: notes.append('Clipping: check contact, reference and wiring')
        if line[i] > .5: notes.append('50 Hz dominates: check reference and nearby power sources')
        if not notes: notes.append('No clipping/flatline detected; contact not verified')
        band_psd=psd[i].copy();band_psd[f<1]=0
        result.append({'line_power_uv2':round(float(absolute_line[i]),2),'other_power_uv2':round(float(absolute_other[i]),2),'name':name,'raw_min_uv':round(float(row.min()),1),'raw_max_uv':round(float(row.max()),1),
            'dc_uv':round(float(np.median(row)),1),'peak_to_peak_uv':round(span,1),
            'clipping_percent':round(clipped*100,1),'line_noise_percent':round(float(line[i])*100,1),
            'dominant_hz':round(float(f[np.argmax(band_psd)]),1),'notes':notes})
    return result

"""Progress from upstream evidence only; never extrapolate elapsed-time percent."""
import re

STEPS=re.compile(r'Denoising:\s*(\d+)%[^\r\n]*?\|\s*(\d+)/(\d+)\s*\[')

def parse_progress(text:str):
    matches=list(STEPS.finditer(text))
    if matches:
        match=matches[-1];step,total=int(match[2]),int(match[3])
        if total>0 and 0<=step<=total:
            return {'phase':'generating' if step<total else 'encoding_output','step':step,'total_steps':total,'percent':round(step/total*100)}
    if 'Denoising completed in ' in text:
        return {'phase':'encoding_output'}
    # stdout may be buffered in running older workers. Do not infer exact loading
    # stage from process age or from warnings emitted before buffered messages.
    return {'phase':'preparing'}

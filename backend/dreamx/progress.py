"""Progress from upstream evidence only; never extrapolate elapsed-time percent."""
import re

STEPS=re.compile(r'Denoising:\s*(\d+)%[^\r\n]*?\|\s*(\d+)/(\d+)\s*\[')

def parse_progress(text:str):
    markers = re.findall(r'REFINER_PHASE (preparing|refining|muxing|validated)', text)
    if markers:
        phase = markers[-1]
        clean = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text).replace('\r', '\n')
        chunks = list(re.finditer(r'^\s*\d+%[^\n]*?\|\s*(\d+)/(\d+)\s*\[', clean, re.MULTILINE))
        result = {'phase': 'muxing' if phase in ('muxing', 'validated') else 'preparing'}
        if chunks:
            completed, total = map(int, chunks[-1].groups())
            if total > 0 and 0 <= completed <= total:
                result.update(completed_chunks=completed, total_chunks=total)
                if phase not in ('muxing', 'validated'):
                    result['phase'] = 'refining' if completed < total else 'decoding'
        return result
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

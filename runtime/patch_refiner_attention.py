"""Create a pinned, test-only upstream compatibility patch; never overwrite source."""
import argparse,hashlib
from pathlib import Path
ORIGINAL_SHA256='bf2ce7e5fbec950102322bb10c860ce2c26ea126fcdbec602ab7f0fdb5507709'
OLD="    if q.device.type != 'cuda' or q.size(-1) > 256:\n"
NEW="""    missing_flash = (q.device.type == 'cuda' and q.size(-1) <= 256
                     and not (FLASH_ATTN_2_AVAILABLE or FLASH_ATTN_3_AVAILABLE))
    if missing_flash and (q_lens is not None or k_lens is not None
                          or softmax_scale is not None or q_scale is not None
                          or causal or window_size != (-1, -1) or dropout_p != 0.
                          or deterministic or version is not None):
        raise RuntimeError('Unsupported options for missing-FlashAttention SDPA fallback')
    if missing_flash or q.device.type != 'cuda' or q.size(-1) > 256:
"""
def patched(source):
    assert hashlib.sha256(source).hexdigest()==ORIGINAL_SHA256,'Unexpected upstream source; no patch applied'
    text=source.decode();assert text.count(OLD)==1
    result=text.replace(OLD,NEW).encode();compile(result,'refiner_attention.py','exec');return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    result=patched(a.source.read_bytes())
    with a.output.open('xb') as f:f.write(result)
    print(hashlib.sha256(result).hexdigest())

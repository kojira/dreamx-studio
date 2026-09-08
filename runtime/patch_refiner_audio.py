"""Preserve all generated video frames when attaching slightly shorter audio."""
import argparse,hashlib
from pathlib import Path
SHA='17410e170dc6c42d098668478da226fa48a98678ab1e628202988cf204d2415d'
def patched(source):
    assert hashlib.sha256(source).hexdigest()==SHA,'Unexpected upstream source'
    old='"-c", "copy", "-shortest", tmp_path],'
    text=source.decode();assert text.count(old)==1
    result=text.replace(old,'"-c", "copy", tmp_path],').encode()
    compile(result,'inference_sr.py','exec');return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    result=patched(a.source.read_bytes())
    with a.output.open('xb') as f:f.write(result)
    print(hashlib.sha256(result).hexdigest())

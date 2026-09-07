"""Download only base-generator weights, never load them into RAM."""
import json
import shutil
from pathlib import Path
from huggingface_hub import HfApi, snapshot_download

root=Path('/weights')
api=HfApi()
info=api.model_info('GD-ML/DreamX-Creator',files_metadata=True)
prefixes=('creator/','audio_vae/','wan2.2_ti2v_5b/')
files=[f for f in info.siblings if f.rfilename.startswith(prefixes)]
assert files and all(f.size is not None for f in files), 'Missing size metadata'
total=sum(f.size for f in files)
free=shutil.disk_usage(root).free
assert free >= 2*total+150*1024**3, 'Insufficient disk budget'
manifest={'repo':info.id,'revision':info.sha,'bytes':total,'files':[{'name':f.rfilename,'size':f.size} for f in files]}
path=root/'download-manifest.json'
if path.exists():
    previous=json.loads(path.read_text())
    assert previous==manifest, 'Pinned download manifest differs; stop for review'
else:
    with path.open('x') as f: json.dump(manifest,f,indent=2)
print(json.dumps({'revision':info.sha,'files':len(files),'bytes':total,'free_bytes':free}),flush=True)
snapshot_download(repo_id=info.id,revision=info.sha,allow_patterns=[f.rfilename for f in files],local_dir=root,max_workers=2)
for f in files:
    assert (root/f.rfilename).stat().st_size==f.size, 'Downloaded size mismatch'
print('DOWNLOAD_VERIFIED',flush=True)

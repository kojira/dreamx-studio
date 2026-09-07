import io
import uuid
import warnings
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from .paths import id_path

MAX_BYTES=10*1024**2
MAX_PIXELS=16_000_000
Image.MAX_IMAGE_PIXELS=MAX_PIXELS

class InvalidImage(ValueError): pass


def ingest_image(data: bytes, root: Path):
    if not data or len(data)>MAX_BYTES: raise InvalidImage('Image must be between 1 byte and 10 MiB')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in ('JPEG','PNG','WEBP'): raise InvalidImage('Only JPEG, PNG and WebP are accepted')
                if getattr(image,'n_frames',1)!=1: raise InvalidImage('Animated images are not accepted')
                w,h=image.size
                if w*h>MAX_PIXELS or min(w,h)<1: raise InvalidImage('Image exceeds pixel budget')
                image.load()
                rgb=image.convert('RGB')
                image_id=str(uuid.uuid4())
                # Original filename and metadata are deliberately discarded.
                path=root/(image_id+'.png')
                with path.open('xb') as output:
                    rgb.save(output,format='PNG')
                return {'input_id':image_id,'width':w,'height':h}
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError,Image.DecompressionBombWarning) as exc:
        raise InvalidImage('Invalid image') from exc


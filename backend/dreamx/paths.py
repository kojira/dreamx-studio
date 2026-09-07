import uuid
from pathlib import Path

def id_path(root: Path, item_id: str, suffix=''):
    try:
        if str(uuid.UUID(item_id))!=item_id: raise ValueError()
    except (ValueError,AttributeError) as exc:
        raise ValueError('Invalid resource ID') from exc
    path=root/(item_id+suffix)
    if path.is_symlink() or path.resolve().parent!=root.resolve():
        raise ValueError('Invalid resource path')
    return path

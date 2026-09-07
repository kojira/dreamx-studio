import os
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from .api import create_app
from .runner_client import SocketRunner

root=Path(os.environ.get('DREAMX_DATA','/data'))
secret=Path(os.environ.get('DREAMX_SECRET_FILE','/config/access-secret')).read_text().strip()
app=create_app(root,secret,SocketRunner(Path('/control/runner.sock')))
app.mount('/',StaticFiles(directory='/opt/ui',html=True),name='ui')

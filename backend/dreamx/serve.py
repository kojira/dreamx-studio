import os
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from .api import create_app
from .runner_client import SocketRunner

root=Path(os.environ.get('DREAMX_DATA','/data'))
app=create_app(root,runner=SocketRunner(Path('/control/runner.sock')))
app.mount('/',StaticFiles(directory='/opt/ui',html=True),name='ui')

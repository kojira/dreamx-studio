"""Small same-origin trial API. Inference remains closed without a ready runner."""
import json
import secrets
from pathlib import Path
from typing import Protocol
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, ConfigDict
from .auth import Sessions, Unauthorized, RateLimited, check_origin
from .inputs import ingest_image, id_path, InvalidImage, MAX_BYTES
from .jobs import Jobs, Busy, Conflict

class Runner(Protocol):
    def status(self) -> dict: ...
    def submit(self, job: dict) -> None: ...
    def cancel(self, job_id: str) -> None: ...

class UnavailableRunner:
    def status(self): return {'runtime_ready':False,'reason':'RUNNER_NOT_READY','active_job_id':None}
    def submit(self,job): raise RuntimeError('Runner unavailable')
    def cancel(self,job_id): raise RuntimeError('Runner unavailable')

class JobRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    input_id: str
    prompt: str=Field(min_length=1,max_length=4000)
    seed: int|None=Field(default=None,ge=0,le=2147483647,strict=True)
    preset: str='trial'


def create_app(root: Path, secret: str, runner: Runner|None=None):
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    inputs=root/'inputs'; inputs.mkdir(mode=0o700,exist_ok=True)
    jobs=Jobs(root/'jobs.sqlite'); sessions=Sessions(secret); runner=runner or UnavailableRunner()
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    app.state.jobs=jobs

    @app.middleware('http')
    async def security(request: Request, call_next):
        modifying=request.method not in ('GET','HEAD','OPTIONS')
        try:
            check_origin(request.headers.get('host',''),request.headers.get('origin'),modifying=modifying)
            if request.url.path.startswith('/api/') and request.url.path!='/api/session':
                sessions.require(request.cookies.get('dreamx_session',''),request.headers.get('x-csrf-token'),modifying=modifying)
        except Unauthorized:
            return JSONResponse({'detail':'UNAUTHORIZED'},status_code=401)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Cache-Control']='no-store'
        response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' blob:; media-src 'self' blob:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response

    async def bounded_body(request, limit):
        parts=[]; size=0
        async for chunk in request.stream():
            size+=len(chunk)
            if size>limit: raise HTTPException(413,'REQUEST_TOO_LARGE')
            parts.append(chunk)
        return b''.join(parts)

    @app.post('/api/session')
    async def login(request:Request):
        try:
            data=json.loads(await bounded_body(request,4096))
            if not isinstance(data,dict) or not isinstance(data.get('secret'),str): raise ValueError()
            s=sessions.login(data['secret'])
        except RateLimited: raise HTTPException(429,'RATE_LIMITED')
        except Unauthorized: raise HTTPException(401,'UNAUTHORIZED')
        except (ValueError,TypeError): raise HTTPException(422,'INVALID_REQUEST')
        response=JSONResponse({'csrf':s.csrf})
        response.set_cookie('dreamx_session',s.token,max_age=28800,httponly=True,samesite='strict',secure=False)
        return response

    @app.delete('/api/session')
    async def logout(request:Request):
        try: sessions.require(request.cookies.get('dreamx_session',''),request.headers.get('x-csrf-token'),modifying=True)
        except Unauthorized: raise HTTPException(401,'UNAUTHORIZED')
        sessions.logout(request.cookies.get('dreamx_session',''))
        response=JSONResponse({'ok':True}); response.delete_cookie('dreamx_session'); return response

    @app.get('/api/status')
    def status(): return runner.status()

    @app.post('/api/inputs',status_code=201)
    async def upload(request:Request):
        # Bound the entire multipart body before parsing; do not trust Content-Length.
        raw=await bounded_body(request,MAX_BYTES+64*1024)
        sent=False
        async def receive():
            nonlocal sent
            if sent: return {'type':'http.request','body':b'','more_body':False}
            sent=True; return {'type':'http.request','body':raw,'more_body':False}
        parsed=Request(request.scope,receive)
        async with parsed.form(max_files=1,max_fields=0,max_part_size=MAX_BYTES) as form:
            if set(form.keys())!={'image'}: raise HTTPException(422,'EXPECTED_IMAGE')
            image=form['image']
            if not hasattr(image,'read'): raise HTTPException(422,'EXPECTED_IMAGE')
            data=await image.read(MAX_BYTES+1)
        try: return ingest_image(data,inputs)
        except InvalidImage as exc: raise HTTPException(422,str(exc))

    @app.post('/api/jobs',status_code=202)
    async def create_job(request:Request):
        try:
            body=JobRequest.model_validate_json(await bounded_body(request,32*1024))
            if not body.prompt.strip() or body.preset!='trial': raise ValueError('Invalid preset or prompt')
            if not id_path(inputs,body.input_id,'.png').is_file(): raise ValueError('Input missing')
        except ValueError: raise HTTPException(422,'INVALID_REQUEST')
        request_id=request.headers.get('idempotency-key','')
        if not 1<=len(request_id)<=128: raise HTTPException(422,'IDEMPOTENCY_KEY_REQUIRED')
        availability=runner.status()
        if not availability.get('runtime_ready'): raise HTTPException(503,availability.get('reason','RUNNER_NOT_READY'))
        payload=body.model_dump()
        # Store nullable seed for idempotency; runner resolves it once and persists evidence.
        try: job,created=jobs.create(request_id,payload)
        except Busy: raise HTTPException(409,'BUSY')
        except Conflict: raise HTTPException(409,'IDEMPOTENCY_CONFLICT')
        if created:
            try: runner.submit(job)
            except Exception:
                jobs.transition(job['id'],'failed','RUNNER_SUBMISSION_FAILED')
                raise HTTPException(503,'RUNNER_SUBMISSION_FAILED')
        return {'job_id':job['id'],'state':jobs.get(job['id'])['state']}

    @app.get('/api/jobs')
    def history(page:int=1):
        if page<1 or page>100000: raise HTTPException(422,'INVALID_PAGE')
        with jobs.connect() as db:
            return [dict(r) for r in db.execute('SELECT id,state,created_at,updated_at,error_code FROM jobs ORDER BY created_at DESC LIMIT 20 OFFSET ?',((page-1)*20,))]

    @app.get('/api/jobs/{job_id}')
    def detail(job_id:str):
        try: return jobs.get(job_id)
        except KeyError: raise HTTPException(404,'NOT_FOUND')

    @app.post('/api/jobs/{job_id}/cancel',status_code=202)
    def cancel(job_id:str):
        try: job=jobs.get(job_id)
        except KeyError: raise HTTPException(404,'NOT_FOUND')
        if job['state'] in ('succeeded','failed','cancelled','interrupted'):
            return JSONResponse({'state':job['state']},status_code=200)
        runner.cancel(job_id)
        return {'state':'cancelling'}

    @app.get('/api/jobs/{job_id}/artifacts/{kind}')
    def artifact(job_id:str,kind:str):
        allowed={'mp4':('output.mp4','video/mp4'),'wav':('output.wav','audio/wav'),'first_frame':('output_first_frame.png','image/png')}
        if kind not in allowed: raise HTTPException(404,'NOT_FOUND')
        try:
            job=jobs.get(job_id); directory=id_path(root/'jobs',job_id)
        except (KeyError,ValueError): raise HTTPException(404,'NOT_FOUND')
        if job['state']!='succeeded': raise HTTPException(409,'ARTIFACT_NOT_READY')
        filename,mime=allowed[kind]; path=directory/filename
        if path.is_symlink() or path.resolve().parent!=directory.resolve() or not path.is_file(): raise HTTPException(404,'NOT_FOUND')
        return FileResponse(path,media_type=mime)

    return app

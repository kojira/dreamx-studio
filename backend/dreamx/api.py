"""Small same-origin trial API. Inference remains closed without a ready runner."""
import asyncio
import contextlib
import json
import uuid
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, ConfigDict
from .auth import Sessions, Unauthorized, RateLimited, check_origin
from .inputs import ingest_image, id_path, InvalidImage, MAX_BYTES
from .jobs import Jobs, Busy, Conflict
from .video_contract import MAX_UPLOAD_BYTES
from .video_container import video_paths

class Runner(Protocol):
    def status(self) -> dict: ...
    def submit(self, job: dict) -> None: ...
    def cancel(self, job_id: str) -> None: ...
    def validate_video(self, input_id: str) -> dict: ...
    def cancel_validation(self, input_id: str) -> dict: ...

class UnavailableRunner:
    def status(self): return {'runtime_ready':False,'reason':'RUNNER_NOT_READY','active_job_id':None}
    def submit(self,job): raise RuntimeError('Runner unavailable')
    def cancel(self,job_id): raise RuntimeError('Runner unavailable')
    def validate_video(self,input_id): raise RuntimeError('RUNNER_NOT_READY')
    def cancel_validation(self,input_id): raise RuntimeError('RUNNER_NOT_READY')

class JobRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    input_id: str
    prompt: str=Field(min_length=1,max_length=4000)
    seed: int|None=Field(default=None,ge=0,le=2147483647,strict=True)
    preset: str='trial'
    spatial_tokens: int=Field(default=220,strict=True)


def create_app(root: Path, secret: str|None=None, runner: Runner|None=None):
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    inputs=root/'inputs'; inputs.mkdir(mode=0o700,exist_ok=True)
    jobs=Jobs(root/'jobs.sqlite'); local_session_secret=secret or secrets.token_urlsafe(32)
    sessions=Sessions(local_session_secret); runner=runner or UnavailableRunner()
    # Internal session tokens protect browser requests; no user-supplied access key.
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
            if data!={}: raise ValueError()
            s=sessions.login(local_session_secret)
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

    @app.post('/api/video-inputs', status_code=201)
    async def upload_video(request: Request):
        availability = await asyncio.to_thread(runner.status)
        if availability.get('reason') == 'BUSY' or jobs.operation():
            raise HTTPException(409, 'BUSY')
        if not availability.get('video_validation_ready'):
            raise HTTPException(503, 'RUNNER_NOT_READY')
        if request.headers.get('content-type', '').lower() != 'application/octet-stream':
            raise HTTPException(422, 'EXPECTED_VIDEO_BYTES')
        try:
            declared = int(request.headers.get('content-length', '0'))
            if declared < 0:
                raise ValueError()
        except ValueError:
            raise HTTPException(422, 'INVALID_REQUEST')
        if declared > MAX_UPLOAD_BYTES:
            raise HTTPException(413, 'UPLOAD_TOO_LARGE')
        identity = str(uuid.uuid4())
        directory = id_path(root / 'video-inputs', identity)
        directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        raw, work = video_paths(root, identity)
        work.mkdir(mode=0o700)
        jobs.reserve_upload(identity)
        started = False
        succeeded = False
        validation = None
        watcher = None
        try:
            size = 0
            async with asyncio.timeout(120):
                with raw.open('xb') as destination:
                    async for chunk in request.stream():
                        size += len(chunk)
                        if size > MAX_UPLOAD_BYTES:
                            raise HTTPException(413, 'UPLOAD_TOO_LARGE')
                        await asyncio.to_thread(destination.write, chunk)
            if not size:
                raise HTTPException(422, 'INVALID_VIDEO')
            started = True
            validation = asyncio.create_task(asyncio.to_thread(runner.validate_video, identity))
            # Observe errors even when the browser/server cancels this request.
            validation.add_done_callback(lambda task: task.exception() if not task.cancelled() else None)
            async def disconnected():
                while not await request.is_disconnected():
                    await asyncio.sleep(.1)
            watcher = asyncio.create_task(disconnected())
            done, _ = await asyncio.wait((validation, watcher), return_when=asyncio.FIRST_COMPLETED)
            if validation not in done:
                with contextlib.suppress(Exception):
                    await asyncio.to_thread(runner.cancel_validation, identity)
                with contextlib.suppress(Exception):
                    await asyncio.shield(validation)
                raise HTTPException(400, 'UPLOAD_CANCELLED')
            result = validation.result()
            succeeded = True
            return result
        except RuntimeError as error:
            code = str(error)
            status_code = 422
            if code == 'BUSY':
                status_code = 409
            elif code in ('RUNNER_NOT_READY', 'STOP_UNCONFIRMED'):
                status_code = 503
            elif code not in ('INVALID_VIDEO', 'UNSUPPORTED_VIDEO', 'INVALID_DURATION',
                              'UNSUPPORTED_AUDIO_TIMING', 'VALIDATION_TIMEOUT', 'VALIDATION_CANCELLED'):
                code, status_code = 'RUNNER_NOT_READY', 503
            raise HTTPException(status_code, code)
        except TimeoutError:
            raise HTTPException(503 if started else 408, 'RUNNER_NOT_READY' if started else 'UPLOAD_TIMEOUT')
        finally:
            if watcher is not None:
                watcher.cancel()
            if started and not succeeded:
                with contextlib.suppress(Exception, asyncio.CancelledError):
                    await asyncio.shield(asyncio.to_thread(runner.cancel_validation, identity))
                jobs.fail_video(identity)
            # Never delete files after handing them to a host-owned container.
            # Its lease survives this request until exact stop is confirmed.
            if not started:
                jobs.fail_video(identity)
                if raw.is_file() and not raw.is_symlink():
                    raw.unlink()  # Only this request's exclusive unfinished file.

    @app.get('/api/video-inputs/{input_id}/preview')
    def video_preview(input_id: str):
        try:
            row = jobs.video(input_id)
            _, work = video_paths(root, input_id)
        except (ValueError, KeyError):
            raise HTTPException(404, 'NOT_FOUND')
        if row['state'] != 'validated':
            raise HTTPException(409, 'INPUT_NOT_READY')
        path = work / 'normalized.mp4'
        if path.is_symlink() or not path.is_file():
            raise HTTPException(404, 'NOT_FOUND')
        return FileResponse(path, media_type='video/mp4')

    @app.post('/api/jobs',status_code=202)
    async def create_job(request:Request):
        try:
            body=JobRequest.model_validate_json(await bounded_body(request,32*1024))
            if not body.prompt.strip() or body.preset!='trial' or body.spatial_tokens not in (220,440,880): raise ValueError('Invalid preset or prompt')
            if not id_path(inputs,body.input_id,'.png').is_file(): raise ValueError('Input missing')
        except ValueError: raise HTTPException(422,'INVALID_REQUEST')
        request_id=request.headers.get('idempotency-key','')
        if not 1<=len(request_id)<=128: raise HTTPException(422,'IDEMPOTENCY_KEY_REQUIRED')
        payload=body.model_dump()
        # A retried admitted request must return its existing job even while busy.
        with jobs.connect() as db:
            prior=db.execute('SELECT * FROM jobs WHERE request_id=?',(request_id,)).fetchone()
        if prior:
            previous=json.loads(prior['payload']);previous.setdefault('spatial_tokens',220)
            if previous!=payload:raise HTTPException(409,'IDEMPOTENCY_CONFLICT')
            return {'job_id':prior['id'],'state':prior['state']}
        availability=runner.status()
        if availability.get('reason')=='BUSY':raise HTTPException(409,'BUSY')
        if not availability.get('runtime_ready'): raise HTTPException(503,availability.get('reason','RUNNER_NOT_READY'))
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
        try: job=jobs.get(job_id)
        except KeyError: raise HTTPException(404,'NOT_FOUND')
        job['spatial_tokens']=json.loads(job['payload']).get('spatial_tokens',220)
        terminal=job['state'] in ('succeeded','failed','cancelled','interrupted')
        end=datetime.fromisoformat(job['updated_at']) if terminal else datetime.now(timezone.utc)
        job['elapsed_seconds']=max(0,int((end-datetime.fromisoformat(job['created_at'])).total_seconds()))
        job['progress']={'phase':job['state'] if terminal else 'preparing'}
        if not terminal:
            try:
                path=id_path(root/'jobs',job_id)/'progress.json'
                if not path.is_symlink() and path.stat().st_size<8192:
                    progress=json.loads(path.read_text())
                    if 0<=time.time()-progress['at']<10:job['progress']=progress
                    else:job['progress']={'phase':'update_pending'}
            except (OSError,ValueError,KeyError):pass
        return job

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

"""Single-job executor and replaceable stage registry for the local pipeline.

Stage callbacks write only their supplied .part path. State ownership and cache
policy belong here, not in callbacks. Inject a registry in tests; no runtime fake mode.
"""
import errno
import json
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import artifacts, procs, store

log = logging.getLogger('quietclerk')


class StageFailure(Exception):
    """Stage-classified failure; C/E can forbid retry without text matching."""
    def __init__(self, reason, *, retryable=True, artifact=False):
        self.retryable = retryable
        self.artifact = artifact
        super().__init__(reason)


class NoSpeech(Exception):
    """Language-stage result that ends the job as a policy skip."""


class Excluded(Exception):
    pass


class Blocked(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class Stage:
    name: str
    output: str
    inputs: tuple
    params: object
    execute: object
    cache: bool = True


@dataclass
class Context:
    con: object
    job: object
    boot: str
    settings: dict
    run_id: str
    work: Path
    paths: dict = field(default_factory=dict)
    hashes: dict = field(default_factory=dict)
    stage_params: dict = field(default_factory=dict)
    note_path: object = None
    review_reasons: list = field(default_factory=list)
    current_stage: str = ''
    call_seq: int = 1

    def checkpoint(self):
        if not store.checkpoint(self.con, self.job['job_id'], self.run_id, self.boot):
            raise Excluded()

    def load(self, stage):
        return json.loads(self.paths[stage].read_text(encoding='utf-8'))

    def record(self, method, *args, **kwargs):
        return method(self.con, self.job['job_id'], self.run_id, self.boot, *args, **kwargs)


class Executor:
    def __init__(self, con, boot, settings, registry=None, *, free_space=None):
        self.con, self.boot = con, boot
        self.settings = settings
        self.registry = registry
        self.busy = False
        self.free_space = free_space or (lambda path: shutil.disk_usage(path).free)

    def run_one(self, now=None, paused=False):
        if self.busy:
            raise RuntimeError('executor already running')
        self.busy = True
        try:
            root = Path(self.settings.get('root'))
            if self.free_space(root) < 2 * 1024**3:
                store.set_engine_state(self.con, 'disk_low')
                return None
            if store.engine_state(self.con) == 'disk_low':
                store.set_engine_state(self.con, None)
            store.release_disk_low(self.con)
            claimed = store.claim(self.con, self.boot, self.settings, now=now, paused=paused)
            if claimed is None:
                return None
            started = time.time()
            log.info('start %s %s', claimed['job_id'], claimed['source_name'])
            self.execute(claimed)
            result = store.job(self.con, claimed['job_id'])
            stages = self.con.execute('''SELECT stage, status, finished_at - started_at AS sec FROM stage_runs
                WHERE run_id=? AND parent_seq IS NULL ORDER BY started_at''', (claimed['active_run_id'],)).fetchall()
            log.info('%s %s in %.0fs [%s]%s', result['status'], claimed['job_id'], time.time() - started,
                     ' '.join(f"{r['stage']}:{r['status']}:{r['sec'] or 0:.0f}s" for r in stages),
                     f" error={result['blocked_reason'] or result['last_error']}" if result['status'] != 'done' else '')
            return result
        finally:
            self.busy = False

    def execute(self, claimed):
        run_id = claimed['active_run_id']
        run = self.con.execute('SELECT * FROM runs WHERE run_id=?', (run_id,)).fetchone()
        snapshot = json.loads(run['settings_json'])
        work = Path(snapshot['root']) / 'work' / claimed['job_id'] / 'runs' / run_id
        retry_count = claimed['attempts'] + claimed['interrupt_count']
        cache_mode = 'resume' if retry_count else run['mode']
        retry_runs = {r['run_id'] for r in self.con.execute(
            'SELECT run_id FROM runs WHERE job_id=? AND run_id<>? ORDER BY started_at DESC,rowid DESC LIMIT ?',
            (claimed['job_id'], run_id, retry_count))} if retry_count else None
        ctx = Context(self.con, claimed, self.boot, snapshot, run_id, work)
        try:
            work.mkdir(parents=True, exist_ok=True)
            ctx.hashes.update(archive=claimed['sha256'],
                              source_name=artifacts.value_hash(claimed['source_name']))
            ctx.checkpoint()
            if self.registry is None:
                from .stages import default_registry
            registry = self.registry if self.registry is not None else default_registry()
            for stage in registry:
                ctx.current_stage, ctx.call_seq = stage.name, 1
                ctx.checkpoint()
                virtual_names = {'archive': 'source.m4a', 'source_name': 'source_name'}
                inputs = {ctx.paths[name].name if name in ctx.paths else virtual_names[name]: ctx.hashes[name]
                          for name in stage.inputs}
                path = work / stage.output
                allowed = stage.cache and artifacts.cache_allowed(stage.name, cache_mode)
                hit = None
                # Forced work may be reused only from this request's earlier attempts,
                # never from before the user's "redo" or "re-summarize" request.
                candidates = retry_runs if allowed and not artifacts.cache_allowed(stage.name, run['mode']) else None
                if allowed and run['mode'] == 'resummarize' and stage.name in artifacts.RESUMMARY_KEPT:
                    # Do not compute params here: that may need models or rules the old run never used.
                    hit = artifacts.find(work.parent, run_id, stage.output, stage.name, inputs, artifacts.ANY_PARAMS)
                if hit:
                    params = hit[1].get('params')
                else:
                    params = stage.params(ctx) if callable(stage.params) else stage.params
                    if allowed:
                        hit = artifacts.find(work.parent, run_id, stage.output, stage.name, inputs, params, run_ids=candidates)
                ctx.stage_params = params
                ctx.record(store.start_stage, stage.name, sent_fields=[])
                try:
                    part = Path(str(path) + '.part')
                    if hit:
                        source, meta = hit
                        artifacts.reuse(source, path)
                        status = 'reused'
                        if stage.name == 'detect_language' and json.loads(path.read_text())['status'] == 'not_run':
                            status = 'not_run'
                        ctx.record(store.finish_stage, stage.name, status=status,
                                   reused_from=f"{meta['producer']['run_id']}/{stage.name}")
                    else:
                        status = stage.execute(ctx, part)
                        artifacts.commit(path, part, stage=stage.name, run_id=run_id, inputs=inputs, params=params)
                        if stage.name == 'note' and store.publication_committed(self.con, run_id):
                            return  # Publication atomically closed the note stage and claim.
                        ctx.record(store.finish_stage, stage.name, status='not_run' if status == 'not_run' else 'done')
                except NoSpeech:
                    if part.exists():
                        artifacts.commit(path, part, stage=stage.name, run_id=run_id, inputs=inputs, params=params, ok=False)
                    ctx.record(store.finish_stage, stage.name)
                    raise
                except Excluded:
                    raise
                except Exception as exc:
                    if stage.name == 'note' and store.publication_committed(self.con, run_id):
                        return  # Never fail a publication after its final transaction.
                    if isinstance(exc, StageFailure) and exc.artifact and part.exists():
                        artifacts.commit(path, part, stage=stage.name, run_id=run_id, inputs=inputs,
                                         params=params, ok=False)
                    ctx.record(store.finish_stage, stage.name, status='timeout' if isinstance(exc, procs.StageTimeout) else 'failed',
                               error=str(exc))
                    raise
                ctx.paths[stage.name] = path
                ctx.hashes[stage.name] = artifacts.sha256(path)
                if stage.name == 'detect_language':
                    ctx.paths['language'] = path
                    ctx.hashes['language'] = ctx.hashes[stage.name]
            ctx.checkpoint()
            if ctx.note_path is None:
                raise RuntimeError('final stage did not publish a note')
            ctx.record(store.complete, ctx.note_path, review_reasons=ctx.review_reasons)
        except Excluded:
            pass
        except store.LostClaim:
            raise
        except NoSpeech:
            ctx.record(store.skip_no_speech)
        except StageFailure as exc:
            ctx.record(store.fail, str(exc), retryable=exc.retryable)
        except Blocked as exc:
            ctx.record(store.fail, str(exc), blocked_reason=exc.reason)
        except OSError as exc:
            if exc.errno == errno.ENOSPC:
                store.set_engine_state(self.con, 'disk_low')
                ctx.record(store.fail, 'disk_low', blocked_reason='disk_low')
            else:
                ctx.record(store.fail, str(exc)[-2000:])
        except Exception as exc:
            ctx.record(store.fail, str(exc)[-2000:])

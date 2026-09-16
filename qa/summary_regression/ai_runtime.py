"""Regression-only configuration and budgeted clients for injection into REAL FastAPI chains.

No evaluation prompts, replacement parser/summarizer or application settings loading.
"""
from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import re
import threading
import time

class ConfigurationError(ValueError):
    pass

class BudgetExceeded(RuntimeError):
    pass

@dataclass(frozen=True)
class AIConfig:
    api_key: str = field(repr=False)
    model: str = 'gpt-4o-mini'
    vision_model: str = 'gpt-4.1-mini'
    max_calls: int = 20
    max_output_tokens: int = 2048
    timeout_seconds: int = 45
    max_total_tokens: int = 100000


def load_config(env_file=None):
    """Only explicit QA file + REGRESSION_* overrides; never production .env/SSM/key."""
    values = {}
    allowed = {'REGRESSION_OPENAI_API_KEY', 'REGRESSION_OPENAI_MODEL',
               'REGRESSION_OPENAI_VISION_MODEL', 'REGRESSION_MAX_AI_CALLS',
               'REGRESSION_MAX_OUTPUT_TOKENS', 'REGRESSION_AI_TIMEOUT_SECONDS',
               'REGRESSION_MAX_TOTAL_TOKENS'}
    if env_file:
        path = Path(env_file)
        if not path.is_file():
            raise ConfigurationError('Regression environment file does not exist.')
        for number, line in enumerate(path.read_text().splitlines(), 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                raise ConfigurationError(f'Invalid regression configuration at line {number}.')
            name, value = (v.strip() for v in line.split('=', 1))
            if name not in allowed or name in values:
                raise ConfigurationError(f'Unknown or duplicate regression setting at line {number}.')
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            values[name] = value
    for name in allowed:
        if name in os.environ:
            values[name] = os.environ[name]
    key = values.get('REGRESSION_OPENAI_API_KEY', '').strip()
    if not key or key in {'replace-me', 'your-regression-key', 'sk-REPLACE_ME'}:
        raise ConfigurationError('Set REGRESSION_OPENAI_API_KEY; the application key is never used.')
    def integer(name, default, low, high):
        try:
            value = int(values.get(name, str(default)))
        except ValueError:
            raise ConfigurationError(f'{name} must be an integer.') from None
        if not low <= value <= high:
            raise ConfigurationError(f'{name} must be between {low} and {high}.')
        return value
    def model(name, default):
        value = values.get(name, default)
        if not re.fullmatch(r'gpt-(?:4o-mini|4o|4\.1-mini|4\.1)(?:-\d{4}-\d{2}-\d{2})?', value):
            raise ConfigurationError(f'{name} must name a supported GPT-4o/4.1 model or dated snapshot.')
        return value
    return AIConfig(key, model('REGRESSION_OPENAI_MODEL','gpt-4o-mini'),
                    model('REGRESSION_OPENAI_VISION_MODEL','gpt-4.1-mini'),
                    integer('REGRESSION_MAX_AI_CALLS',20,1,1000),
                    integer('REGRESSION_MAX_OUTPUT_TOKENS',2048,128,16000),
                    integer('REGRESSION_AI_TIMEOUT_SECONDS',45,1,300),
                    integer('REGRESSION_MAX_TOTAL_TOKENS',100000,1,10000000))


def redact(value, secret=''):
    if isinstance(value,str):
        if secret:
            value=value.replace(secret,'[REDACTED]')
        return re.sub(r'\bsk-[A-Za-z0-9_-]+','[REDACTED]',value)
    if isinstance(value,list):
        return [redact(x,secret) for x in value]
    if isinstance(value,dict):
        return {redact(str(k),secret):redact(v,secret) for k,v in value.items()}
    return value


class RegressionAI:
    """Build sync/async SDK clients for the application's model factory dependency.

    The adapter must inject these clients into the actual chains. SDK network requests
    retain production prompts, schemas, parsing and validators. QA adds transport limits.
    """
    def __init__(self, config):
        self.config=config
        self.calls=0
        self.total_tokens=0
        self.events=[]
        self.blocked_reason=None
        self._lock=threading.Lock()

    def _before(self, request):
        if request.url.scheme!='https' or request.url.host!='api.openai.com' or request.url.port not in (None,443):
            raise RuntimeError('Only the official OpenAI endpoint is permitted.')
        if request.method!='POST' or request.url.path not in ('/v1/chat/completions','/v1/responses'):
            raise RuntimeError('Only inference requests are permitted in regression.')
        if len(request.content)>32*1024*1024:
            self.blocked_reason='request_size'
            raise BudgetExceeded('Regression request size limit exceeded.')
        body=json.loads(request.content)
        if body.get('stream'):
            raise RuntimeError('Use nonstreaming inference for regression accounting.')
        if body.get('model') not in {self.config.model,self.config.vision_model}:
            raise RuntimeError('Model not in explicit regression configuration.')
        limit=body.get('max_completion_tokens',body.get('max_tokens',body.get('max_output_tokens')))
        if type(limit) is not int or not 1<=limit<=self.config.max_output_tokens:
            self.blocked_reason='output_token_limit'
            raise BudgetExceeded('Application request must set output limit within regression budget.')
        with self._lock:
            if self.calls>=self.config.max_calls or self.total_tokens>=self.config.max_total_tokens:
                self.blocked_reason='run_budget'
                raise BudgetExceeded('Regression AI budget exhausted.')
            self.calls+=1
            event={'attempt':self.calls,'requested_model':body['model'],'endpoint':request.url.path}
            self.events.append(event)
        return event,time.monotonic()

    def _after(self,event,response):
        event['http_status']=response.status_code
        if response.status_code>=400:
            return
        payload=response.json()
        usage=payload.get('usage') or {}
        with self._lock:
            self.total_tokens+=int(usage.get('total_tokens') or 0)
        event['usage']=usage
        event['returned_model']=payload.get('model')

    def _transport(self, asynchronous=False):
        import httpx
        owner=self
        if asynchronous:
            class Transport(httpx.AsyncBaseTransport):
                def __init__(self): self.inner=httpx.AsyncHTTPTransport(retries=0)
                async def handle_async_request(self,request):
                    event,started=owner._before(request)
                    try:
                        response=await self.inner.handle_async_request(request)
                        await response.aread()
                        owner._after(event,response)
                        return response
                    except Exception as exc:
                        event['exception_type']=type(exc).__name__
                        raise
                    finally: event['duration_seconds']=round(time.monotonic()-started,3)
                async def aclose(self): await self.inner.aclose()
        else:
            class Transport(httpx.BaseTransport):
                def __init__(self): self.inner=httpx.HTTPTransport(retries=0)
                def handle_request(self,request):
                    event,started=owner._before(request)
                    try:
                        response=self.inner.handle_request(request)
                        response.read()
                        owner._after(event,response)
                        return response
                    except Exception as exc:
                        event['exception_type']=type(exc).__name__
                        raise
                    finally: event['duration_seconds']=round(time.monotonic()-started,3)
                def close(self): self.inner.close()
        return Transport()

    def make_client(self):
        from openai import OpenAI
        import httpx
        self._quiet_logging()
        return OpenAI(api_key=self.config.api_key,base_url='https://api.openai.com/v1',
                      organization='',project='',max_retries=0,timeout=self.config.timeout_seconds,
                      http_client=httpx.Client(transport=self._transport(),trust_env=False,
                                               timeout=self.config.timeout_seconds))

    def make_async_client(self):
        from openai import AsyncOpenAI
        import httpx
        self._quiet_logging()
        return AsyncOpenAI(api_key=self.config.api_key,base_url='https://api.openai.com/v1',
                           organization='',project='',max_retries=0,timeout=self.config.timeout_seconds,
                           http_client=httpx.AsyncClient(transport=self._transport(True),trust_env=False,
                                                        timeout=self.config.timeout_seconds))

    @staticmethod
    def _quiet_logging():
        for name in ('openai','httpx','httpcore'):
            logging.getLogger(name).setLevel(logging.WARNING)

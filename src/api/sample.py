from __future__ import annotations
from typing import Callable, Optional
from fastapi import FastAPI, APIRouter, Body
from app.__internal import Function

from config import cfg


class SampleAPI(Function):

    def __init__(self, error: Callable):
        ...

    def Bootstrap(self, app: FastAPI):

        router = APIRouter(prefix="/api/sample")

        @router.get("/")
        def index():
            return {"hello": "world"}


        @router.get("/foo")
        def foo():
            return {
                "mnemonic": cfg.MY_CONFIGURATION,
                "remote": cfg.REMOTE_ID
            }

        app.include_router(router)


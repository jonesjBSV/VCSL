from fastapi import FastAPI
from kink import di

from misc.di_init import init_di
from misc.scheduler import Scheduler
from routers.rout_health import HealthCheckRouter
from routers.rout_bitarray import BitArrayRouter
from routers.rout_vcsl import VcslRouter

app = FastAPI()


@app.on_event("startup")
def startup_event():
    init_di()
    health_router = di[HealthCheckRouter]
    bit_array_router = di[BitArrayRouter]
    vcsl_router = di[VcslRouter]
    app.include_router(health_router.router)
    app.include_router(bit_array_router.router)
    app.include_router(vcsl_router.router)
    scheduler = di[Scheduler]
    scheduler.start()

import pkgutil
import importlib
from fastapi import FastAPI, APIRouter


def register_routers(app: FastAPI):
    package = importlib.import_module(__name__)

    for _, module_name, is_pkg in pkgutil.iter_modules(package.__path__):
        if is_pkg:
            continue

        module = importlib.import_module(f"{__name__}.{module_name}")
        router = getattr(module, "router", None)

        if not isinstance(router, APIRouter):
            continue

        app.include_router(router)

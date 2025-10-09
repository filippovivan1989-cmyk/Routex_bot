import asyncio
import inspect
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "asyncio: execute test function as an asyncio coroutine.")


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    if inspect.iscoroutinefunction(pyfuncitem.obj):
        kwargs = {arg: pyfuncitem.funcargs[arg] for arg in pyfuncitem._fixtureinfo.argnames}
        coroutine = pyfuncitem.obj(**kwargs)
        try:
            asyncio.run(coroutine)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(coroutine)
            finally:
                loop.close()
        return True
    return None

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any, Literal, TypeVar, overload

import pydantic_ai
from pydantic_ai import RunContext

from marvin.utilities.logging import get_logger

T = TypeVar("T")
logger = get_logger(__name__)


@overload
def update_fn(
    name_or_func: str,
    *,
    description: str | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]: ...


@overload
def update_fn(
    name_or_func: None = None,
    *,
    name: str,
    description: str | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]: ...


@overload
def update_fn(
    name_or_func: Callable[..., T],
    *,
    name: str,
    description: str | None = None,
) -> Callable[..., T]: ...


def update_fn(
    name_or_func: str | Callable[..., T] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]] | Callable[..., T]:
    """Rename a function and optionally set its docstring.

    Can be used as a decorator or called directly on a function.

    Args:
        name_or_func: Either the new name (when used as decorator) or the function to rename
        name: The new name (when used as a function)
        description: Optional docstring for the function

    Example:
        # As decorator with positional arg:
        @update_fn('hello_there', description='Says hello')
        def my_fn(x):
            return x

        # As decorator with keyword args:
        @update_fn(name='hello_there', description='Says hello')
        def my_fn(x):
            return x

        # As function:
        def add_stuff(x):
            return x + 1
        new_fn = update_fn(add_stuff, name='add_stuff_123', description='Adds stuff')

        # Works with async functions too:
        @update_fn('async_hello')
        async def my_async_fn(x):
            return x

    """

    def apply(func: Callable[..., T], new_name: str) -> Callable[..., T]:
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> T:  # type: ignore[reportRedeclaration]
                return await func(*args, **kwargs)
        else:

            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> T:
                return func(*args, **kwargs)

        wrapper.__name__ = new_name
        if description is not None:
            wrapper.__doc__ = description
        return wrapper

    if callable(name_or_func):
        # Used as function
        if name is None:
            raise ValueError("name must be provided when used as a function")
        return apply(name_or_func, name)
    # Used as decorator
    decorator_name = name_or_func if name_or_func is not None else name
    if decorator_name is None:
        raise ValueError("name must be provided either as argument or keyword")

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        return apply(func, decorator_name)

    return decorator


@dataclass
class ResultTool:
    type: Literal["result-tool"] = "result-tool"

    def run(self, ctx: RunContext) -> None:
        pass


def wrap_tool_errors(tool_fn: Callable[..., Any]):
    """
    Pydantic AI doesn't catch errors except for ModelRetry, so we need to make
    sure we catch them ourselves and raise a ModelRetry instead.
    """
    if inspect.iscoroutinefunction(tool_fn):

        @wraps(tool_fn)
        async def _fn(*args, **kwargs):
            try:
                return await tool_fn(*args, **kwargs)
            except pydantic_ai.ModelRetry as e:
                logger.debug(f"Tool failed: {e}")
                raise e
            except Exception as e:
                logger.debug(f"Tool failed: {e}")
                raise pydantic_ai.ModelRetry(message=f"Tool failed: {e}") from e

        return _fn

    else:

        @wraps(tool_fn)
        def _fn(*args: Any, **kwargs: Any):
            try:
                return tool_fn(*args, **kwargs)
            except pydantic_ai.ModelRetry as e:
                logger.debug(f"Tool failed: {e}")
                raise e
            except Exception as e:
                logger.debug(f"Tool failed: {e}")
                raise pydantic_ai.ModelRetry(message=f"Tool failed: {e}") from e

        return _fn

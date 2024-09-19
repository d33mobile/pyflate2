import typing as T
import logging

# basically log(*args), but debug
def log(*args: T.Any) -> None:
    logging.debug(" ".join(map(str, args)))

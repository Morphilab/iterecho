import logging
import os
import sys

_LOG_INITIALIZED = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"IterEcho.{name}")


def setup_logging(verbose: bool = False, quiet: bool = False) -> None:
    global _LOG_INITIALIZED

    if quiet:
        level = logging.WARNING
    elif verbose or os.environ.get("ITERECHO_DEBUG"):
        level = logging.DEBUG
    else:
        level = logging.INFO

    root = logging.getLogger()

    if not _LOG_INITIALIZED:
        root.setLevel(level)
        if not root.handlers:
            if verbose or os.environ.get("ITERECHO_DEBUG"):
                fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                datefmt = "%H:%M:%S"
            else:
                fmt = "%(levelname)s - %(message)s"
                datefmt = ""
            formatter = logging.Formatter(fmt, datefmt=datefmt)
            out_handler = logging.StreamHandler(sys.stdout)
            out_handler.setFormatter(formatter)
            out_handler.setLevel(level)
            out_handler.addFilter(lambda r: r.levelno < logging.WARNING)
            root.addHandler(out_handler)
            err_handler = logging.StreamHandler(sys.stderr)
            err_handler.setFormatter(formatter)
            err_handler.setLevel(logging.WARNING)
            root.addHandler(err_handler)
        _LOG_INITIALIZED = True
    else:
        root.setLevel(level)
        verbose_fmt = verbose or os.environ.get("ITERECHO_DEBUG")
        if verbose_fmt:
            fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            datefmt = "%H:%M:%S"
        else:
            fmt = "%(levelname)s - %(message)s"
            datefmt = ""
        formatter = logging.Formatter(fmt, datefmt=datefmt)
        for handler in root.handlers:
            handler.setFormatter(formatter)
            handler.setLevel(level)

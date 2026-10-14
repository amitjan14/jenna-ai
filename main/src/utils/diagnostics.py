"""Opt-in debug output. Default execution does not print prompts or passages."""
import logging

logger=logging.getLogger('jenna')


def debug(*items):
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(' '.join(str(item) for item in items))

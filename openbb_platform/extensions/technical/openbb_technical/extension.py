"""Technical extension entry point, including alert signal evaluation."""

from openbb_technical.signals import register_signals
from openbb_technical.technical_router import router

register_signals(router)

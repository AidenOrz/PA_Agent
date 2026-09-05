"""PA Agent utility package."""

from pa_agent.util.threading import CancelToken, OrchestratorEvent
from pa_agent.util.logging import configure_logging, update_api_key

__all__ = ["CancelToken", "OrchestratorEvent", "EventBus", "configure_logging", "update_api_key"]


def __getattr__(name: str):
    # Keep pure utility imports usable in headless workers and CLI tools.
    if name == "EventBus":
        from pa_agent.util.event_bus import EventBus

        return EventBus
    raise AttributeError(name)

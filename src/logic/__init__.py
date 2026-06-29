"""Logic handler registry. Map config names → handler classes."""
from src.logic.base import LogicHandler
from src.logic.desk_activity import DeskActivityHandler
from src.logic.headcount import HeadcountHandler
from src.logic.theft import TheftHandler

REGISTRY: dict[str, type[LogicHandler]] = {
    HeadcountHandler.name: HeadcountHandler,
    DeskActivityHandler.name: DeskActivityHandler,
    TheftHandler.name: TheftHandler,
}


def build_handlers(cam, zones) -> list[LogicHandler]:
    handlers: list[LogicHandler] = []
    for name in cam.logic:
        cls = REGISTRY.get(name)
        if cls is not None:
            handlers.append(cls(cam, zones))
    return handlers

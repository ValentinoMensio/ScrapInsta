from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol, Callable, Any, Dict, Tuple

from scrapinsta.application.dto.tasks import TaskEnvelope, ResultEnvelope

from scrapinsta.application.dto.profiles import AnalyzeProfileRequest
from scrapinsta.application.dto.messages import MessageRequest
from scrapinsta.application.dto.followings import FetchFollowingsRequest

from scrapinsta.application.use_cases.analyze_profile import AnalyzeProfileUseCase
from scrapinsta.application.use_cases.send_message import SendMessageUseCase
from scrapinsta.application.use_cases.fetch_followings import FetchFollowingsUseCase

logger = logging.getLogger(__name__)


# ----------------------------
# Fábrica de Use Cases (puertos ya inyectados)
# ----------------------------
class UseCaseFactory(Protocol):
    def create_analyze_profile(self) -> AnalyzeProfileUseCase: ...
    def create_send_message(self) -> SendMessageUseCase: ...
    def create_fetch_followings(self) -> FetchFollowingsUseCase: ...


@dataclass(frozen=True)
class _Route:
    parser: Callable[[Dict[str, Any]], Any]
    builder: Callable[[UseCaseFactory], Any]


def _parse_analyze(payload: Dict[str, Any]) -> AnalyzeProfileRequest:
    return AnalyzeProfileRequest(**payload)

def _parse_send_message(payload: Dict[str, Any]) -> MessageRequest:
    return MessageRequest(**payload)

def _parse_fetch_followings(payload: Dict[str, Any]) -> FetchFollowingsRequest:
    return FetchFollowingsRequest(**payload)


_ROUTES: Dict[str, _Route] = {
    "analyze_profile": _Route(parser=_parse_analyze, builder=lambda f: f.create_analyze_profile()),
    "send_message": _Route(parser=_parse_send_message, builder=lambda f: f.create_send_message()),
    "fetch_followings": _Route(parser=_parse_fetch_followings, builder=lambda f: f.create_fetch_followings()),
}


class TaskDispatcher:
    """
    Glue mínimo de aplicación:
    - Mapea task_name -> (DTO parser, use case)
    """

    def __init__(self, factory: UseCaseFactory) -> None:
        self._factory = factory

    def dispatch(self, env: TaskEnvelope) -> ResultEnvelope:
        route = _ROUTES.get(env.task)
        if not route:
            return ResultEnvelope(
                ok=False,
                error=f"unknown task '{env.task}'",
                attempts=1,
                task_id=env.id,
                correlation_id=env.correlation_id,
            )

        try:
            dto = route.parser(env.payload or {})
        except Exception as e:
            logger.exception("payload parse error: %s", e)
            return ResultEnvelope(
                ok=False,
                error=f"payload invalid: {e}",
                attempts=1,
                task_id=env.id,
                correlation_id=env.correlation_id,
            )

        try:
            use_case = route.builder(self._factory)
            result = use_case(dto)
            result_dict = result.model_dump() if hasattr(result, "model_dump") else dict(result or {})
            attempts = getattr(result, "attempts", 1)
            return ResultEnvelope(
                ok=True,
                result=result_dict,
                attempts=int(attempts) if isinstance(attempts, int) else 1,
                task_id=env.id,
                correlation_id=env.correlation_id,
            )
        except Exception as e:
            logger.exception("use case execution failed: %s", e)
            return ResultEnvelope(
                ok=False,
                error=str(e),
                attempts=1,
                task_id=env.id,
                correlation_id=env.correlation_id,
            )

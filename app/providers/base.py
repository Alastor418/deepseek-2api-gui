from abc import ABC, abstractmethod
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse


class BaseProvider(ABC):
    @abstractmethod
    async def chat_completion(
        self,
        request_data: dict[str, Any],
        original_request: Request,
    ) -> StreamingResponse | JSONResponse:
        ...

    @abstractmethod
    async def start(self) -> None:
        """Starts the provider."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stops the provider."""
        ...

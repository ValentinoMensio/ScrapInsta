from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class ClientRepo(ABC):
    @abstractmethod
    def get_by_id(self, client_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_by_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def create(self, client_id: str, name: str, email: Optional[str], api_key_hash: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        pass

    @abstractmethod
    def update_status(self, client_id: str, status: str) -> None:
        pass

    @abstractmethod
    def get_limits(self, client_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def update_limits(self, client_id: str, limits: Dict[str, int]) -> None:
        pass


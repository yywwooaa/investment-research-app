from __future__ import annotations

from abc import ABC, abstractmethod

from backend.app.models import CompanyRecord, RefreshResult


class DataProvider(ABC):
    @abstractmethod
    def list_companies(self) -> list[CompanyRecord]:
        raise NotImplementedError

    @abstractmethod
    def get_company(self, ticker: str) -> CompanyRecord:
        raise NotImplementedError

    @abstractmethod
    def refresh(self) -> RefreshResult:
        raise NotImplementedError

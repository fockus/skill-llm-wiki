"""Порт локального embedding provider; SQL и CLI не входят в контракт."""

from typing import Protocol


class Embedder(Protocol):
    @property
    def identity(self) -> str:
        """Идентификатор модели, весов, tokenizer и адаптера."""
        raise NotImplementedError

    def documents(self, texts: list[str]) -> list[list[float]]:
        """Конечные нормированные векторы одинаковой размерности."""
        raise NotImplementedError

    def question(self, text: str) -> list[float]:
        """Вектор запроса в том же пространстве."""
        raise NotImplementedError

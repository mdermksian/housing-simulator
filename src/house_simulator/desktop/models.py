"""Update presentation rows by identity without replacing their entire model."""

from collections.abc import Callable


class ModelBinding:
    def __init__(
        self, model_factory: Callable, row_factory: Callable, key: str
    ) -> None:
        self.model = model_factory([])
        self._row_factory = row_factory
        self._key = key
        self._rows: list[dict] = []

    def update(self, rows: list[dict]) -> None:
        wanted = {row[self._key] for row in rows}
        for index in range(len(self._rows) - 1, -1, -1):
            if self._rows[index][self._key] not in wanted:
                del self._rows[index]
                del self.model[index]
        for index, row in enumerate(rows):
            if index == len(self._rows):
                self._rows.append(row)
                self.model.append(self._row_factory(**row))
            elif self._rows[index][self._key] != row[self._key]:
                self._rows.insert(index, row)
                self.model.insert(index, self._row_factory(**row))
            elif self._rows[index] != row:
                self._rows[index] = row
                self.model[index] = self._row_factory(**row)
        while len(self._rows) > len(rows):
            del self._rows[-1]
            del self.model[len(self._rows)]

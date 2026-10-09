"""The store kept in DynamoDB - one table, an item per period and per answer - used
by the Lambda. Same interface as the JSON-file store the other builds use.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import boto3
from boto3.dynamodb.conditions import Key

from budget.store import Store

__all__ = ["DynamoStore"]


class DynamoStore(Store):
    def __init__(self, table) -> None:
        super().__init__(path=Path("/tmp/never-written"))
        self._table = table
        self._loaded_periods: set[str] = set()
        self._loaded_answers: set[str] = set()
        self._loaded_moves: set[str] = set()
        self._loaded_versions: set[int] = set()

    @classmethod
    def connect(cls, table_name: str) -> "DynamoStore":
        table = boto3.resource("dynamodb").Table(table_name)
        store = cls(table)
        for item in _all_items(table, "PERIOD"):
            store.periods[item["SK"]] = item["text"]
            if "year" in item:
                store.years[item["SK"]] = int(item["year"])
            if item.get("omitted"):
                store.omitted[item["SK"]] = list(item["omitted"])
            if item.get("adjusted"):
                store.adjusted[item["SK"]] = {
                    k: float(v) for k, v in item["adjusted"].items()
                }
        for item in _all_items(table, "ANSWER"):
            store.answers[item["SK"]] = item["group"]
        for item in _all_items(table, "MOVE"):
            store.moves[item["SK"]] = item["group"]
        for item in _all_items(table, "CONFIG"):
            if item["SK"] == "v1":
                store.config = json.loads(item["json"])
            elif item["SK"].startswith("ver#"):
                store.config_versions.append(json.loads(item["json"]))
        store.config_versions.sort(key=lambda v: v.get("id", 0))
        store._loaded_versions = {v.get("id") for v in store.config_versions}
        store._loaded_answers = set(store.answers)
        store._loaded_moves = set(store.moves)
        store._loaded_periods = set(store.periods)
        return store

    def save(self) -> None:
        with self._table.batch_writer() as batch:
            for identity, text in self.periods.items():
                item = {"PK": "PERIOD", "SK": identity, "text": text}
                if self.omitted.get(identity):
                    item["omitted"] = self.omitted[identity]
                if self.adjusted.get(identity):
                    item["adjusted"] = {
                        k: Decimal(str(v)) for k, v in self.adjusted[identity].items()
                    }
                if identity in self.years:
                    item["year"] = self.years[identity]
                batch.put_item(Item=item)
            for key, group in self.answers.items():
                batch.put_item(Item={"PK": "ANSWER", "SK": key, "group": group})
            for key, group in self.moves.items():
                batch.put_item(Item={"PK": "MOVE", "SK": key, "group": group})
            batch.put_item(
                Item={
                    "PK": "CONFIG",
                    "SK": "v1",
                    "json": json.dumps(self.config, ensure_ascii=False),
                }
            )
            for key in self._loaded_answers - set(self.answers):
                batch.delete_item(Key={"PK": "ANSWER", "SK": key})
            for key in self._loaded_moves - set(self.moves):
                batch.delete_item(Key={"PK": "MOVE", "SK": key})
            for identity in self._loaded_periods - set(self.periods):
                batch.delete_item(Key={"PK": "PERIOD", "SK": identity})
            for version in self.config_versions:
                batch.put_item(
                    Item={
                        "PK": "CONFIG",
                        "SK": f"ver#{version['id']:06d}",
                        "json": json.dumps(version, ensure_ascii=False),
                    }
                )
            for gone in self._loaded_versions - {v.get("id") for v in self.config_versions}:
                batch.delete_item(Key={"PK": "CONFIG", "SK": f"ver#{gone:06d}"})
        self._loaded_answers = set(self.answers)
        self._loaded_moves = set(self.moves)
        self._loaded_versions = {v.get("id") for v in self.config_versions}
        self._loaded_periods = set(self.periods)


def _all_items(table, pk: str):
    kwargs = {"KeyConditionExpression": Key("PK").eq(pk)}
    while True:
        page = table.query(**kwargs)
        yield from page["Items"]
        last = page.get("LastEvaluatedKey")
        if not last:
            return
        kwargs["ExclusiveStartKey"] = last

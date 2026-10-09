from __future__ import annotations

import sys
import types

try:
    import boto3
except ModuleNotFoundError:
    boto3 = types.ModuleType("boto3")
    dynamodb = types.ModuleType("boto3.dynamodb")
    conditions = types.ModuleType("boto3.dynamodb.conditions")

    class _Key:
        def __init__(self, name: str) -> None:
            self.name = name

        def eq(self, value):
            return (self.name, value)

    conditions.Key = _Key
    boto3.dynamodb = dynamodb
    dynamodb.conditions = conditions
    sys.modules["boto3"] = boto3
    sys.modules["boto3.dynamodb"] = dynamodb
    sys.modules["boto3.dynamodb.conditions"] = conditions
    _STUBBED = True
else:
    _STUBBED = False

from budget.dynamo import DynamoStore

if _STUBBED:
    for _name in ("boto3.dynamodb.conditions", "boto3.dynamodb", "boto3"):
        sys.modules.pop(_name, None)


class FakeBatch:
    def __init__(self, table: "FakeTable") -> None:
        self._table = table

    def __enter__(self) -> "FakeBatch":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def put_item(self, Item: dict) -> None:
        self._table.rows[(Item["PK"], Item["SK"])] = dict(Item)

    def delete_item(self, Key: dict) -> None:
        self._table.rows.pop((Key["PK"], Key["SK"]), None)


class FakeTable:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict] = {}

    def batch_writer(self) -> FakeBatch:
        return FakeBatch(self)


def test_unanswer_deletes_the_stored_item() -> None:
    table = FakeTable()

    first = DynamoStore(table)
    first.periods["salary:1"] = "notes text\n"
    first.answers = {"salary:1|1900 boat hire|0": "Hobbies", "salary:1|480 wine|0": "Celebrations"}
    first.save()
    assert ("ANSWER", "salary:1|1900 boat hire|0") in table.rows

    second = DynamoStore(table)
    second.answers = {k[1]: v["group"] for k, v in table.rows.items() if k[0] == "ANSWER"}
    second._loaded_answers = set(second.answers)
    del second.answers["salary:1|1900 boat hire|0"]
    second.save()

    assert ("ANSWER", "salary:1|1900 boat hire|0") not in table.rows
    assert table.rows[("ANSWER", "salary:1|480 wine|0")]["group"] == "Celebrations"
    assert table.rows[("PERIOD", "salary:1")]["text"] == "notes text\n"


def test_a_removed_period_is_deleted_from_the_table() -> None:
    table = FakeTable()

    first = DynamoStore(table)
    first.periods = {"salary:1": "March notes\n", "salary:2": "April notes\n"}
    first.years = {"salary:1": 2026, "salary:2": 2026}
    first.omitted = {"salary:1": ["Boat hire"]}
    first.save()
    assert ("PERIOD", "salary:1") in table.rows

    second = DynamoStore(table)
    second.periods = {k[1]: v["text"] for k, v in table.rows.items() if k[0] == "PERIOD"}
    second._loaded_periods = set(second.periods)
    del second.periods["salary:1"]
    second.omitted.pop("salary:1", None)
    second.save()

    assert ("PERIOD", "salary:1") not in table.rows
    assert table.rows[("PERIOD", "salary:2")]["text"] == "April notes\n"


def test_a_year_survives_the_round_trip() -> None:
    from decimal import Decimal

    table = FakeTable()
    store = DynamoStore(table)
    store.periods["salary:1"] = "text\n"
    store.years["salary:1"] = 2026
    store.save()
    assert table.rows[("PERIOD", "salary:1")]["year"] == 2026

    later = DynamoStore(table)
    item = dict(table.rows[("PERIOD", "salary:1")], year=Decimal(2026))
    later.periods[item["SK"]] = item["text"]
    if "year" in item:
        later.years[item["SK"]] = int(item["year"])
    assert later.years == {"salary:1": 2026}
    assert type(later.years["salary:1"]) is int


def test_config_survives_the_round_trip() -> None:
    import json as jsonlib

    table = FakeTable()
    store = DynamoStore(table)
    store.config = {"minors": {"Celebrations": {"renamed": "Parties"}}}
    store.save()
    row = table.rows[("CONFIG", "v1")]
    assert jsonlib.loads(row["json"]) == store.config

    later = DynamoStore(table)
    if row["SK"] == "v1":
        later.config = jsonlib.loads(row["json"])
    assert later.config == store.config

    store.config = {}
    store.save()
    assert jsonlib.loads(table.rows[("CONFIG", "v1")]["json"]) == {}


def test_save_refreshes_its_baseline() -> None:
    table = FakeTable()
    store = DynamoStore(table)
    store.answers = {"k": "Days out"}
    store._loaded_answers = {"k"}

    del store.answers["k"]
    store.save()
    assert ("ANSWER", "k") not in table.rows

    store.answers["k"] = "Hobbies"
    store.save()
    assert table.rows[("ANSWER", "k")]["group"] == "Hobbies"
    assert store._loaded_answers == {"k"}


def test_typed_left_figures_and_starting_figures_survive_the_round_trip(monkeypatch) -> None:
    from decimal import Decimal
    import budget.dynamo as dynamo

    class QueryTable(FakeTable):
        def query(self, **kwargs):
            cond = kwargs["KeyConditionExpression"]
            pk = cond[1] if isinstance(cond, tuple) else cond.get_expression()["values"][1]
            items = []
            for (key_pk, _), row in self.rows.items():
                if key_pk == pk:
                    items.append({k: ({kk: Decimal(str(vv)) for kk, vv in v.items()}
                                      if k in ("left_set", "adjusted") else v)
                                  for k, v in row.items()})
            return {"Items": items}

    table = QueryTable()
    store = DynamoStore(table)
    store.periods["salary:1"] = "text\n"
    store.left_set["salary:1"] = {"card": 41000.0}
    store.left_start = {"cash": 12.5}
    store.save()
    assert table.rows[("PERIOD", "salary:1")]["left_set"] == {"card": Decimal("41000.0")}
    assert table.rows[("CONFIG", "left_start")]["json"] == '{"cash": 12.5}'

    monkeypatch.setattr(dynamo, "boto3", types.SimpleNamespace(
        resource=lambda name: types.SimpleNamespace(Table=lambda table_name: table)))
    later = DynamoStore.connect("any")
    assert later.left_set == {"salary:1": {"card": 41000.0}}
    assert later.left_start == {"cash": 12.5}
    assert type(later.left_set["salary:1"]["card"]) is float

    later.left_set.clear()
    later.left_start = {}
    later.save()
    assert "left_set" not in table.rows[("PERIOD", "salary:1")]
    assert table.rows[("CONFIG", "left_start")]["json"] == "{}"
    again = DynamoStore.connect("any")
    assert again.left_set == {} and again.left_start == {}

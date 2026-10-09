"""The AWS Lambda entry point: an API Gateway HTTP API event in, `dispatch` on the
DynamoDB store, JSON out. Authentication happened before this runs - the route
carries a Cognito JWT authorizer.
"""

from __future__ import annotations

import json
import os

from budget.api import dispatch
from budget.dynamo import DynamoStore


def lambda_handler(event, context):
    if isinstance(event, dict) and isinstance(event.get("body"), str):
        try:
            event = json.loads(event["body"])
        except json.JSONDecodeError:
            return {"ok": False, "error": "body is not valid JSON"}
    if not isinstance(event, dict):
        return {"ok": False, "error": "event must be a JSON object"}

    store = DynamoStore.connect(os.environ["TABLE_NAME"])
    return dispatch(store, event)

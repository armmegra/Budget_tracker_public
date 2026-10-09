"""Reads a screenshot of notes into text. The AWS build calls the Textract service;
the Windows build puts its own reader in this module's place.
"""

from __future__ import annotations

import base64

import boto3

__all__ = ["extract"]


def extract(image_b64: str) -> str:
    blob = base64.b64decode(image_b64.split(",")[-1])
    reply = boto3.client("textract").detect_document_text(Document={"Bytes": blob})
    return "\n".join(
        block["Text"] for block in reply["Blocks"] if block["BlockType"] == "LINE"
    )

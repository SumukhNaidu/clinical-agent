"""Domain profiles: one JSON file per domain in ./domains controls the prompt,
answer format, safety rules, chunking and retrieval for that domain.

To add a domain, drop a new <key>.json into ./domains (copy general.json)."""

import json
import os
from functools import lru_cache
from typing import Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter


DOMAINS_DIR = os.path.join(os.path.dirname(__file__), "domains")
DEFAULT_DOMAIN = "general"

DEFAULTS = {
    "label": None,
    "description": "",
    "system": "You are a helpful document assistant. Answer using only the context below.",
    "answer_format": "",
    "rules": [],
    "glossary": {},
    "examples": [],
    "suggested_questions": [],
    "disclaimer": None,
    "chunking": {"chunk_size": 1000, "chunk_overlap": 200},
    "retrieval": {"k": 3, "max_distance": None},
    "not_found_message": "I couldn't find anything in this document that answers that question.",
}


def normalize_key(domain: Optional[str]) -> str:
    key = (domain or DEFAULT_DOMAIN).strip().lower()
    return key if os.path.exists(os.path.join(DOMAINS_DIR, f"{key}.json")) else DEFAULT_DOMAIN


@lru_cache(maxsize=None)
def load_domain(domain: Optional[str]) -> dict:
    key = normalize_key(domain)
    with open(os.path.join(DOMAINS_DIR, f"{key}.json"), "r", encoding="utf-8") as fh:
        config = {**DEFAULTS, **json.load(fh)}
    config["key"] = key
    config["label"] = config["label"] or key.title()
    config["chunking"] = {**DEFAULTS["chunking"], **config["chunking"]}
    config["retrieval"] = {**DEFAULTS["retrieval"], **config["retrieval"]}
    return config


def list_domains() -> list:
    keys = sorted(f[:-5] for f in os.listdir(DOMAINS_DIR) if f.endswith(".json"))
    # General first, the rest alphabetically
    keys.sort(key=lambda k: k != DEFAULT_DOMAIN)
    return [
        {
            "key": d["key"],
            "label": d["label"],
            "description": d["description"],
            "suggested_questions": d["suggested_questions"],
            "disclaimer": d["disclaimer"],
            "chunking": d["chunking"],
            "retrieval": d["retrieval"],
        }
        for d in (load_domain(k) for k in keys)
    ]


@lru_cache(maxsize=None)
def get_splitter(domain: Optional[str]) -> RecursiveCharacterTextSplitter:
    chunking = load_domain(domain)["chunking"]
    kwargs = {
        "chunk_size": chunking["chunk_size"],
        "chunk_overlap": chunking["chunk_overlap"],
        "length_function": len,
    }
    if chunking.get("separators"):
        kwargs["separators"] = chunking["separators"]
        kwargs["is_separator_regex"] = bool(chunking.get("separators_are_regex"))
    return RecursiveCharacterTextSplitter(**kwargs)


def build_system_prompt(domain: Optional[str]) -> str:
    """System prompt text for a domain, with literal braces escaped for ChatPromptTemplate.
    The caller appends the {context} placeholder."""
    d = load_domain(domain)
    parts = [d["system"]]

    parts.append(
        "The context is a list of excerpts from the document, each labelled like "
        "[Chunk 1 | page 3]. Cite excerpts using those labels, e.g. [Chunk 1]. "
        "Only cite chunk numbers that appear in the context."
    )

    if d["answer_format"]:
        parts.append("Answer format:\n" + d["answer_format"])

    if d["rules"]:
        parts.append("Rules:\n" + "\n".join(f"- {r}" for r in d["rules"]))

    if d["glossary"]:
        parts.append("Glossary (use these meanings when reading the document):\n" +
                     "\n".join(f"- {term}: {meaning}" for term, meaning in d["glossary"].items()))

    if d["examples"]:
        parts.append("Examples of good answers:\n" + "\n\n".join(
            f"Question: {ex['input']}\nAnswer: {ex['output']}" for ex in d["examples"]
        ))

    text = "\n\n".join(parts)
    return text.replace("{", "{{").replace("}", "}}")


def add_disclaimer(answer: str, domain: Optional[str]) -> str:
    disclaimer = load_domain(domain)["disclaimer"]
    return f"{answer}\n\n⚠️ {disclaimer}" if disclaimer else answer

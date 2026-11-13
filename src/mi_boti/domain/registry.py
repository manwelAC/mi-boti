"""Pure identity normalization. Supporting identifiers never claim a business."""

from dataclasses import dataclass
from datetime import datetime
import hashlib
import ipaddress
import json
import re
import unicodedata
from urllib.parse import urlsplit

from .errors import AppError


class RegistryError(AppError):
    code = "REGISTRY_INVALID"


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def normalized_text(value):
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join("".join(c if c.isalnum() else " " for c in value).split())


def domain(value):
    try:
        url = urlsplit(value)
        host = (url.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
        if url.scheme not in {"http", "https"} or url.username is not None or url.password is not None:
            return None
        if url.port not in {None, 80 if url.scheme == "http" else 443}:
            return None
        if not host or host == "localhost" or host.endswith(".localhost") or "." not in host:
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            if not re.fullmatch(r"[a-z0-9.-]+", host) or any(not label or label.startswith("-") or label.endswith("-") for label in host.split(".")):
                return None
        return host.removeprefix("www.")
    except (ValueError, UnicodeError):
        return None


def phone(value, country):
    digits = "".join(c for c in value if c in "0123456789")
    if value.strip().startswith("+") and 7 <= len(digits) <= 15:
        return ("e164", "+" + digits)
    if country == "PH" and len(digits) == 11 and digits.startswith("09"):
        return ("e164", "+63" + digits[1:])
    return ("published_digits", digits) if 7 <= len(digits) <= 15 else None


def name_similarity(left, right):
    a, b = set(left.split()), set(right.split())
    return len(a & b) / len(a | b) if a and b else 0.0


ADDRESS_FIELDS = frozenset({"country", "city", "street", "house_number", "unit", "postcode"})


@dataclass(frozen=True)
class Identity:
    name: str
    address: str | None
    country: str | None
    identifiers: tuple[tuple[str, str, str, str], ...]
    claims: tuple[str, ...]


def normalize(observation):
    if not isinstance(observation, dict) or len(encoded(observation).encode("utf-8")) > 65536:
        raise RegistryError("Observation must be a bounded JSON object.")
    for key in ("name", "source_namespace", "source_id", "source_url", "observed_at", "policy_version", "attribution"):
        if not isinstance(observation.get(key), str) or not 1 <= len(observation[key].strip()) <= 2048:
            raise RegistryError("Observation is missing valid name or source provenance.")
    name = normalized_text(observation["name"])
    if not name or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", observation["source_namespace"]):
        raise RegistryError("Observation name or source namespace is invalid.")
    if len(observation["source_id"]) > 256 or not domain(observation["source_url"]):
        raise RegistryError("Observation source identifier or URL is invalid.")
    try:
        stamp = datetime.strptime(observation["observed_at"], "%Y-%m-%dT%H:%M:%S.%fZ")
        if stamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != observation["observed_at"]:
            raise ValueError
    except ValueError:
        raise RegistryError("Observation timestamp must be canonical UTC.") from None
    address = observation.get("address", {})
    if not isinstance(address, dict) or set(address) - ADDRESS_FIELDS or any(not isinstance(v, str) or len(v) > 500 for v in address.values()):
        raise RegistryError("Observation address has unsupported fields or values.")
    address = {k: normalized_text(v) for k, v in address.items() if v.strip()}
    country = address.get("country", "").upper() or None
    if country is not None and not re.fullmatch("[A-Z]{2}", country):
        raise RegistryError("Country must be a two-letter code.")
    if observation.get("entity_kind", "BUSINESS") not in {"BUSINESS", "PARENT", "BRANCH"}:
        raise RegistryError("Business entity kind is invalid.")
    namespace, source = observation["source_namespace"], observation["source_id"]
    identifiers = [("SOURCE", namespace, source, "STRONG")]
    claims = ["source:" + encoded([namespace, source])]
    # A missing unit is weak; conservatively require every field for a second strong claim.
    if all(address.get(k) for k in ADDRESS_FIELDS):
        key = hashlib.sha256(encoded([name, address]).encode()).hexdigest()
        identifiers.append(("NAME_ADDRESS", "v1", key, "STRONG"))
        claims.append("name_address:v1:" + key)
    website = observation.get("website")
    if isinstance(website, str) and len(website) <= 2048 and (host := domain(website)):
        identifiers.append(("DOMAIN", "hostname", host, "SUPPORTING"))
    published_phone = observation.get("phone")
    if isinstance(published_phone, str) and len(published_phone) <= 100 and (number := phone(published_phone, country)):
        identifiers.append(("PHONE", number[0], number[1], "SUPPORTING"))
    email = observation.get("email")
    if isinstance(email, str) and len(email) <= 320 and re.fullmatch(r"[^@\s]+@[^@\s]+", email):
        local, mailhost = email.rsplit("@", 1)
        try:
            host = mailhost.encode("idna").decode("ascii").lower().rstrip(".")
        except UnicodeError:
            host = ""
        if re.fullmatch(r"[a-z0-9.-]+", host) and domain("https://" + host):
            identifiers.append(("EMAIL", "published", local + "@" + host, "SUPPORTING"))
    return Identity(name, encoded(address) if address else None, country, tuple(identifiers), tuple(claims))


def address_conflict(left, right):
    a, b = json.loads(left or "{}"), json.loads(right or "{}")
    return any(a[key] != b[key] for key in a.keys() & b.keys())

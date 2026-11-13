"""Bounded Overpass JSON translation; no live transport is enabled here."""

from dataclasses import dataclass
import math

from ..domain.registry import RegistryError, encoded

ATTRIBUTION = "© OpenStreetMap contributors — ODbL; https://www.openstreetmap.org/copyright"


@dataclass(frozen=True)
class DiscoveryBatch:
    observations: tuple[dict, ...]
    partial: bool
    limitations: tuple[str, ...]
    attribution: str = ATTRIBUTION


def parse_overpass(payload, *, observed_at, policy_version, max_elements=100):
    if type(max_elements) is not int or not 1 <= max_elements <= 100:
        raise RegistryError("Parser element limit must be between one and 100.")
    try:
        size = len(encoded(payload).encode("utf-8"))
    except (ValueError, TypeError):
        raise RegistryError("Source response is not valid JSON.") from None
    if not isinstance(payload, dict) or size > 5242880 or not isinstance(payload.get("elements"), list):
        raise RegistryError("Source response has an invalid or oversized envelope.")
    if len(payload["elements"]) > max_elements:
        raise RegistryError("Source response exceeds the reserved observation budget.")
    observations = []
    partial = bool(payload.get("remark")) or len(payload["elements"]) == max_elements
    for element in payload["elements"]:
        if not isinstance(element, dict):
            raise RegistryError("Source element must be an object.")
        kind, identifier, tags = element.get("type"), element.get("id"), element.get("tags", {})
        if kind not in {"node", "way", "relation"} or type(identifier) is not int or identifier < 1:
            raise RegistryError("Source element has no valid OSM identifier.")
        if not isinstance(tags, dict) or len(tags) > 256 or any(not isinstance(k, str) or not isinstance(v, str) or len(k)>256 or len(v)>2048 for k,v in tags.items()):
            raise RegistryError("Source element has invalid tags.")
        address = {field: tags['addr:'+tag] for field, tag in (
            ('country','country'),('city','city'),('street','street'),('house_number','housenumber'),('unit','unit'),('postcode','postcode'))
            if 'addr:'+tag in tags}
        limits = ["OSM tags are public observations, not independently verified business facts."]
        center = element if kind == "node" else element.get("center", {})
        coordinates = None
        if isinstance(center, dict):
            lat, lon = center.get("lat"), center.get("lon")
            if (type(lat) in {int,float} and type(lon) in {int,float} and math.isfinite(lat) and math.isfinite(lon)
                    and -90 <= lat <= 90 and -180 <= lon <= 180):
                coordinates = {"latitude": lat, "longitude": lon}
        if coordinates is None:
            limits.append("Source supplied no usable coordinates.")
        observations.append({"name": tags.get("name", ""), "source_namespace": "osm", "source_id": f"{kind}/{identifier}",
            "source_url": f"https://www.openstreetmap.org/{kind}/{identifier}", "observed_at": observed_at,
            "policy_version": policy_version, "attribution": ATTRIBUTION, "address": address,
            "website": tags.get("website", tags.get("contact:website")), "phone": tags.get("phone", tags.get("contact:phone")),
            "email": tags.get("email", tags.get("contact:email")), "coordinates": coordinates,
            "category": tags.get("amenity"), "limitations": limits})
    limitations = ("Source reported a remark or reached the output cap; completeness is not established.",) if partial else ()
    return DiscoveryBatch(tuple(observations), partial, limitations)

"""Fixed bounded Overpass query templates. Planning does not approve access."""

from dataclasses import dataclass
import hashlib
import math

from ..domain.registry import RegistryError, encoded


@dataclass(frozen=True)
class QuerySpec:
    bbox: tuple[float, float, float, float]
    categories: tuple[str, ...]
    limit: int
    target_version: int
    policy_version: str

    def __post_init__(self):
        if (not isinstance(self.bbox, tuple) or len(self.bbox) != 4
                or any(type(v) not in {int, float} or not math.isfinite(v) for v in self.bbox)):
            raise RegistryError("Query requires four finite geographic coordinates.")
        south, west, north, east = self.bbox
        if not (-90 <= south < north <= 90 and -180 <= west < east <= 180
                and north-south <= 1 and east-west <= 1):
            raise RegistryError("Query geographic bounds exceed the documented envelope.")
        rounded = tuple(round(float(v), 8) for v in self.bbox)
        if rounded[0] >= rounded[2] or rounded[1] >= rounded[3]:
            raise RegistryError("Query area is smaller than supported coordinate precision.")
        if not isinstance(self.categories, tuple) or not self.categories or any(c not in {"cafe", "restaurant"} for c in self.categories):
            raise RegistryError("This discovery fixture permits restaurants and cafes only.")
        if type(self.limit) is not int or not 1 <= self.limit <= 100 or type(self.target_version) is not int or self.target_version < 1:
            raise RegistryError("Query limits and target version must be positive bounded integers.")
        if not isinstance(self.policy_version, str) or not 1 <= len(self.policy_version) <= 128:
            raise RegistryError("Query requires a source policy version.")
        object.__setattr__(self, "bbox", rounded)
        object.__setattr__(self, "categories", tuple(sorted(set(self.categories))))

    def request(self):
        return {"schema_version": 1, "source_namespace": "osm", "template": "overpass-q1",
                "bbox": list(self.bbox), "categories": list(self.categories), "limit": self.limit,
                "target_version": self.target_version, "policy_version": self.policy_version}

    @property
    def fingerprint(self):
        return hashlib.sha256(encoded(self.request()).encode()).hexdigest()

    def overpass_query(self):
        bbox = ",".join(format(value, ".8f").rstrip("0").rstrip(".") for value in self.bbox)
        categories = "|".join(self.categories)
        return f'[out:json][timeout:10][maxsize:16777216];nwr["amenity"~"^({categories})$"]({bbox});out center tags {self.limit};'

from dataclasses import dataclass, asdict, field
from typing import Optional, Dict, Any, List
import json


@dataclass
class Lead:
    title: str
    category: Optional[str] = None
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    url: Optional[str] = None
    social_profiles: List[str] = field(default_factory=list)
    extra_details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

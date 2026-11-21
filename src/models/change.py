from dataclasses import dataclass, field
from datetime import datetime
from typing import List


@dataclass
class Change:
    revision: str
    author: str
    message: str
    timestamp: datetime
    files: List[str]
    repository: str = ""
    # [{"action": "ADD" | "MODIFY" | "DELETE" | ..., "path": "..."}]
    modifications: List[dict] = field(default_factory=list)

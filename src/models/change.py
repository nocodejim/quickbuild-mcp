from dataclasses import dataclass
from datetime import datetime
from typing import List

@dataclass
class Change:
    revision: str
    author: str
    message: str
    timestamp: datetime
    files: List[str]
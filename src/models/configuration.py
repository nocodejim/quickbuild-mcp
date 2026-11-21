from dataclasses import dataclass
from typing import Optional


@dataclass
class Configuration:
    id: str
    name: str
    description: str
    parent_id: Optional[str]
    enabled: bool
    # Full configuration path, e.g. "root/team/app" (QuickBuild "pathName")
    path: str = ""

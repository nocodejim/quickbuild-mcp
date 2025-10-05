from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class Build:
    id: str
    configuration_id: str
    version: str
    status: str
    start_time: datetime
    end_time: Optional[datetime]
    success: bool
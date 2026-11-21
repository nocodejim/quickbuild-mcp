from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional


@dataclass
class BuildRequest:
    """A queued or running QuickBuild build request (GET /rest/build_requests)."""

    id: str
    configuration_id: str
    # WAITING_PROCESS (queued) or RUNNING_BUILD, as reported by QuickBuild
    status: str
    requested_at: datetime
    requester_id: Optional[str] = None
    priority: Optional[int] = None
    scheduled: bool = False
    variables: Dict[str, str] = field(default_factory=dict)

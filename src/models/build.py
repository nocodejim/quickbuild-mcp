from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class Build:
    id: str
    configuration_id: str
    version: str
    status: str
    start_time: datetime
    end_time: Optional[datetime]
    success: bool
    # Details reported by GET /rest/builds/{id} (and build searches)
    requester_id: Optional[str] = None
    duration_ms: Optional[int] = None
    wait_duration_ms: Optional[int] = None
    scheduled: bool = False
    node: Optional[str] = None
    # [{"path": "master>checkout", "status": ..., "node": ..., "start_time": ..., "duration_ms": ...}]
    steps: List[dict] = field(default_factory=list)
    # repository name -> checked-out revision
    revisions: Dict[str, str] = field(default_factory=dict)
    # build request variables (secret values are reported masked, never in clear text)
    variables: Dict[str, Optional[str]] = field(default_factory=dict)

from dataclasses import dataclass
from datetime import datetime

@dataclass
class Agent:
    name: str
    status: str
    last_contact: datetime
    ip_address: str
    port: int
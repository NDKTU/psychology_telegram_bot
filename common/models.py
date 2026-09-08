from dataclasses import dataclass
from typing import Optional


@dataclass
class Client:
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    created_at: str
    status: str = "active"


@dataclass
class Worker:
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    is_active: bool = True
    registered_at: Optional[str] = None


@dataclass
class MessageMapping:
    id: Optional[int]
    worker_chat_id: int
    worker_message_id: int
    client_user_id: int
    client_message_id: int
    created_at: str


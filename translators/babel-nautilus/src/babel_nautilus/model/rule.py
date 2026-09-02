from dataclasses import dataclass
from enum import Enum


class RuleMode(Enum):
    regex = 'regex'
    rule = 'rule'

@dataclass
class Rule:
    name: str
    mode: RuleMode
    opts: str
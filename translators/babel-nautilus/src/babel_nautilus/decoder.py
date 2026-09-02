from abc import ABC
from dataclasses import dataclass
from enum import Enum

from babel_ir.model import BabelIr, BabelProduction, BabelBlockList, BabelBlock

def decode(babel_ir: BabelIr) -> str:
    pass


__all__ = ["decode"]

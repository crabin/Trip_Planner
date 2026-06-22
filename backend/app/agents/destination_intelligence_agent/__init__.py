"""
Destination Intelligence Agent
一个针对目的地旅游攻略的深度搜索AI代理实现
"""

from .agent import DestinationIntelligenceAgent, create_agent
from .utils.config import Settings

__version__ = "1.0.0"
__author__ = "Destination Intelligence Agent Team"

__all__ = ["DestinationIntelligenceAgent", "create_agent", "Settings"]

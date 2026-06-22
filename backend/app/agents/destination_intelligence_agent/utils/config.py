"""
destination_intelligence_agent 配置类

此模块使用 pydantic-settings 管理 destination_intelligence_agent 的配置，支持从环境变量和 .env 文件自动加载。
数据模型定义位置：
- 本文件 - 配置模型定义
"""


from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional

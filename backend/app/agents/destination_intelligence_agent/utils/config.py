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

# 计算 .env 优先级，优先当前目录下的 .env 文件，其次是根目录的 .env 文件
PROJECT_ROOT = Path(__file__).resolve().parents[4]
CWD_ENV = Path.cwd() / ".env"
ENV_FILE = CWD_ENV if CWD_ENV.exists() else PROJECT_ROOT / ".env"

class Settings(BaseSettings):
    """
    Destination Intelligence Agent 的配置类，使用 pydantic-settings 管理。
    支持 env和环境变量自动加载
    Args:
        BaseSettings (_type_): _description_
    """
    
    # ================== LLM 配置 ====================
    DESTINATION_INTELLIGENCE_AGENT_API_KEY: str = Field(...,  description="API key for the destination intelligence agent's LLM.")
    DESTINATION_INTELLIGENCE_AGENT_BASE_URL: Optional[str] = Field(None,  description="Base URL for the destination intelligence agent's LLM API.")
    DESTINATION_INTELLIGENCE_AGENT_MODEL_NAME: str = Field(..., description="Model name for the destination intelligence agent's LLM.")
    DESTINATION_INTELLIGENCE_AGENT_PROVIDER: Optional[str] = Field(None, description="LLM provider for the destination intelligence agent (e.g., 'openai', 'azure').")

    # ================== 网络工具配置 ====================
    TAVILY_API_KEY: str = Field(..., description="Tavily API（申请地址：https://www.tavily.com/）API密钥，用于Tavily网络搜索")

    # ================== 搜索参数配置 ====================
    SEARCH_TIMEOUT: int = Field(240, description="搜索超时（秒）")
    SEARCH_CONTENT_MAX_LENGTH: int = Field(20000, description="用于提示的最长内容长度")
    MAX_REFLECTIONS: int = Field(2, description="最大反思轮数")
    MAX_PARAGRAPHS: int = Field(5, description="最大段落数")
    MAX_SEARCH_RESULTS: int = Field(20, description="最大搜索结果数")
    
    # ================== 输出配置 ====================
    OUTPUT_DIR: str = Field("reports", description="输出目录")
    SAVE_INTERMEDIATE_STATES: bool = Field(True, description="是否保存中间状态")
    
    class Config:
        env_file = ENV_FILE
        env_prefix = ""
        case_sensitive = False
        extra = "allow"
        env_file_encoding = 'utf-8'
        
    
# 创建全局配置实例
settings = Settings()

def print_config(config: Settings):
    """
    打印配置信息
    
    Args:
        config: Settings配置对象
    """
    message = ""
    message += "=== Destination Intelligence Agent 配置 ===\n"
    message += f"LLM 模型: {config.DESTINATION_INTELLIGENCE_AGENT_MODEL_NAME}\n"
    message += f"LLM Base URL: {config.DESTINATION_INTELLIGENCE_AGENT_BASE_URL or '(默认)'}\n"
    message += f"Tavily API Key: {'已配置' if config.TAVILY_API_KEY else '未配置'}\n"
    message += f"搜索超时: {config.SEARCH_TIMEOUT} 秒\n"
    message += f"最长内容长度: {config.SEARCH_CONTENT_MAX_LENGTH}\n"
    message += f"最大反思次数: {config.MAX_REFLECTIONS}\n"
    message += f"最大段落数: {config.MAX_PARAGRAPHS}\n"
    message += f"最大搜索结果数: {config.MAX_SEARCH_RESULTS}\n"
    message += f"输出目录: {config.OUTPUT_DIR}\n"
    message += f"保存中间状态: {config.SAVE_INTERMEDIATE_STATES}\n"
    message += f"LLM API Key: {'已配置' if config.DESTINATION_INTELLIGENCE_AGENT_API_KEY else '未配置'}\n"
    message += "========================\n"
    print(message)

if __name__ == "__main__":
    # 直接运行此文件时，打印加载的配置以验证正确性
    print("Loading Destination Intelligence Agent configuration...")
    print(f"PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"ENV_FILE: {ENV_FILE}")
    print(f"CWD_ENV : {CWD_ENV}")
    print_config(settings)
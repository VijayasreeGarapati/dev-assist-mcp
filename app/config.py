import os
import json
from dataclasses import dataclass
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

@dataclass
class OllamaConfig:
    """Configuration for Ollama LLM integration"""
    base_url: str = "http://localhost:11434"
    models: List[str] = None
    timeout: int = 20
    temperature: float = 0.2
    top_p: float = 0.8
    max_tokens: int = 120
    
    def __post_init__(self):
        if self.models is None:
            self.models = ["llama3.2:3b", "qwen2.5-coder:1.5b", "tinyllama"]

@dataclass
class AnalysisConfig:
    """Configuration for PR analysis rules"""
    max_diff_size: int = 50000
    risk_keywords: Dict[str, float] = None
    file_type_weights: Dict[str, float] = None
    
    def __post_init__(self):
        if self.risk_keywords is None:
            self.risk_keywords = {
                "TODO": 0.2,
                "FIXME": 0.3,
                "HACK": 0.4,
                "XXX": 0.3,
                "password": 0.6,
                "secret": 0.6,
                "api_key": 0.6,
                "token": 0.4,
                "eval(": 0.7,
                "exec(": 0.7,
                "os.system": 0.8,
                "subprocess": 0.4,
                "shell=True": 0.6
            }
        
        if self.file_type_weights is None:
            self.file_type_weights = {
                ".py": 1.0,
                ".js": 1.0,
                ".ts": 1.0,
                ".java": 1.0,
                ".cpp": 1.0,
                ".sql": 1.3,
                ".sh": 1.3,
                ".yml": 0.8,
                ".yaml": 0.8,
                ".json": 0.8,
                ".md": 0.5,
                ".txt": 0.5
            }

@dataclass
class PRAnalyzerConfig:
    """Main configuration class"""
    ollama: OllamaConfig
    analysis: AnalysisConfig
    
    @classmethod
    def from_file(cls, config_path: str = "config.json") -> "PRAnalyzerConfig":
        """Load configuration from JSON file"""
        try:
            # Look for config in project root 
            if not os.path.isabs(config_path):
                project_root = os.path.dirname(os.path.dirname(__file__))
                config_path = os.path.join(project_root, config_path)
            
            if os.path.exists(config_path):
                logger.info(f"Loading configuration from {config_path}")
                with open(config_path, 'r') as f:
                    config_data = json.load(f)
                
                return cls(
                    ollama=OllamaConfig(**config_data.get("ollama", {})),
                    analysis=AnalysisConfig(**config_data.get("analysis", {}))
                )
            else:
                logger.info(f"No config file found at {config_path}, using defaults")
                return cls.default()
                
        except Exception as e:
            logger.warning(f"Failed to load config file: {e}. Using defaults.")
            return cls.default()
    
    @classmethod
    def default(cls) -> "PRAnalyzerConfig":
        """Create default configuration"""
        return cls(
            ollama=OllamaConfig(),
            analysis=AnalysisConfig()
        )

# Global config instance
_config: Optional[PRAnalyzerConfig] = None

def get_config() -> PRAnalyzerConfig:
    """Get the global configuration instance"""
    global _config
    if _config is None:
        _config = PRAnalyzerConfig.from_file()
    return _config
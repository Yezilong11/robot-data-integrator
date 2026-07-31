# src/rdi/config/settings.py
"""全局配置管理模块。

所有配置通过环境变量或 .env 文件注入，禁止在代码中硬编码
API key、路径或 URL。
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置，从环境变量或 .env 文件加载。

    优先级：环境变量 > .env 文件 > 默认值。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── LLM 配置（OpenAI 兼容） ───
    llm_api_key: str = Field(
        default="",
        description="LLM 服务 API Key（OpenAI 兼容）",
    )
    llm_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        description="LLM 服务 OpenAI 兼容端点，切换厂商改这一项",
    )
    llm_model: str = Field(
        default="qwen-plus",
        description="LLM 模型名称",
    )
    llm_embedding_model: str = Field(
        default="text-embedding-v3",
        description="Embedding 模型",
    )
    llm_max_retries: int = Field(
        default=3,
        description="LLM 调用最大重试次数",
    )
    llm_temperature: float = Field(
        default=0.3,
        description="LLM 生成温度，目标解析用低温度",
    )

    # ─── 数据源配置 ───
    github_token: str = Field(
        default="",
        description="GitHub API Token",
    )
    ieee_api_key: str = Field(
        default="",
        description="IEEE Xplore API Key",
    )
    adapter_timeout: float = Field(
        default=30.0,
        description="HTTP 请求超时秒数",
    )
    adapter_max_retry: int = Field(
        default=3,
        description="Adapter 最大重试次数",
    )
    adapter_rate_limit: int = Field(
        default=10,
        description="每秒最大并发请求数",
    )
    adapter_cache_ttl: int = Field(
        default=3600,
        description="缓存 TTL 秒数",
    )

    # ─── 数据源 URL 配置 ───
    huggingface_api_url: str = Field(
        default="https://huggingface.co/api",
        description="HuggingFace API 基础 URL",
    )
    zenodo_api_url: str = Field(
        default="https://zenodo.org/api",
        description="Zenodo API 基础 URL",
    )
    google_scanned_api_url: str = Field(
        default="https://fuel.gazebosim.org/1.0/GoogleResearch",
        description="Google Scanned Objects (Gazebo Fuel) API URL",
    )
    robotiq_base_url: str = Field(
        default="https://raw.githubusercontent.com/ros-industrial/robotiq/kinetic-devel",
        description="Robotiq URDF 模型仓库基础 URL",
    )
    allegro_base_url: str = Field(
        default="https://raw.githubusercontent.com/simlabor/allegro_hand_ros/main",
        description="Allegro 灵巧手 URDF 模型仓库基础 URL",
    )
    mujoco_base_url: str = Field(
        default="https://raw.githubusercontent.com/google-deepmind/mujoco_menagerie/main",
        description="MuJoCo MJCF 模型仓库基础 URL",
    )
    isaac_base_url: str = Field(
        default="https://raw.githubusercontent.com/NVIDIA-Omniverse/IsaacSim/main",
        description="Isaac Sim USD 模型仓库基础 URL",
    )

    # ─── 数据源 URL 配置（可通过环境变量覆盖） ───
    paperswithcode_base_url: str = Field(
        default="https://paperswithcode.com/api/v1",
        description="Papers with Code API 基础 URL",
    )
    semanticscholar_base_url: str = Field(
        default="https://api.semanticscholar.org/graph/v1",
        description="Semantic Scholar API 基础 URL",
    )
    ieee_base_url: str = Field(
        default="https://ieeexploreapi.ieee.org/api/v1/search",
        description="IEEE Xplore API 基础 URL",
    )
    graspnet_base_url: str = Field(
        default="https://huggingface.co",
        description="GraspNet 数据集镜像基础 URL（降级回退下载地址）",
    )
    ycb_base_url: str = Field(
        default="https://huggingface.co",
        description="YCB Objects 数据集镜像基础 URL（降级回退下载地址）",
    )
    franka_base_url: str = Field(
        default="https://raw.githubusercontent.com/frankaemika/franka_ros/develop",
        description="Franka 机器人模型仓库基础 URL（降级回退下载地址）",
    )

    # ─── 数据源网页 URL 配置（文档原始对接方式） ───
    paperswithcode_web_url: str = Field(
        default="https://paperswithcode.com",
        description="Papers with Code 网页地址（网页解析方式）",
    )
    graspnet_web_url: str = Field(
        default="https://graspnet.net",
        description="GraspNet 官方网页地址（官方下载方式）",
    )
    ycb_web_url: str = Field(
        default="https://rse-lab.cs.washington.edu/projects/3d-object-reconstruction/",
        description="YCB Objects 官方网页地址（官方下载方式）",
    )
    franka_web_url: str = Field(
        default="https://franka.de",
        description="Franka 官方网页地址（网页抓取方式）",
    )
    allegro_web_url: str = Field(
        default="https://www.wonikrobotics.com",
        description="Allegro 官方网页地址（网页抓取方式）",
    )
    robotiq_web_url: str = Field(
        default="https://robotiq.com",
        description="Robotiq 官方网页地址（网页抓取方式）",
    )
    mujoco_web_url: str = Field(
        default="https://mujoco.readthedocs.io",
        description="MuJoCo 文档地址（文档解析方式）",
    )
    isaac_web_url: str = Field(
        default="https://docs.isaacsim.omniverse.nvidia.com",
        description="Isaac Sim 文档地址（文档解析方式）",
    )

    # ─── ChromaDB 配置 ───
    chromadb_path: str = Field(
        default="./data/experience_db",
        description="ChromaDB 持久化路径",
    )

    # ─── 输出配置 ───
    output_dir: str = Field(
        default="./data/output_packages",
        description="数据包输出目录",
    )

    # ─── 日志配置 ───
    log_level: str = Field(
        default="INFO",
        description="日志级别",
    )
    log_format: str = Field(
        default="json",
        description="日志格式：json 或 console",
    )


# 全局单例
settings = Settings()

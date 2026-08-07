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
    max_fetch_bytes: int = Field(
        default=50_000_000,
        description=(
            "fetch 单文件下载体积阈值（字节）。"
            "超过此阈值的文件（如多 GB 数据集归档、大 PDF）"
            "改返回 metadata JSON（含 url/size/title 等），避免 30s 超时。"
            "默认 50MB，适配探活 30s 外部超时。"
        ),
    )
    arxiv_max_fetch_bytes: int = Field(
        default=2_000_000,
        description=(
            "arXiv PDF 下载体积阈值（字节），独立于全局 max_fetch_bytes。"
            "arXiv.org 在国内访问慢（5MB PDF 常 >30s），虽文件不大但下载超时；"
            "默认 2MB，超此阈值改返回 metadata JSON（含 url/title/abstract）。"
            "生产环境网络良好时可调大（如 ARXIV_MAX_FETCH_BYTES=100000000）下载全量 PDF。"
        ),
    )
    github_raw_mirror_base_url: str = Field(
        default="https://cdn.jsdelivr.net/gh",
        description=(
            "GitHub raw 镜像基础 URL（用于 _download_bytes 兜底）。"
            "raw.githubusercontent.com 在国内 CDN 不稳（E4，偶发 30s 超时），"
            "Franka/Allegro/Robotiq/MuJoCo/Isaac 等 Adapter 的 URDF/XML/Python "
            "配置文件均走 raw.githubusercontent.com。当主 URL 失败时自动改走"
            "jsdelivr 镜像（{base}/{owner}/{repo}@{ref}/{path}）。"
            "海外或 jsdelivr 不可达时可改为其他 GH raw 镜像或置空禁用。"
        ),
    )

    # ─── 数据源 URL 配置 ───
    huggingface_api_url: str = Field(
        default="https://huggingface.co/api",
        description="HuggingFace API 基础 URL（用于 search）",
    )
    huggingface_download_base_url: str = Field(
        default="https://hf-mirror.com",
        description=(
            "HuggingFace 文件下载基础 URL（用于 fetch/resolve）。"
            "国内默认走 hf-mirror.com，海外可改回 https://huggingface.co"
        ),
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
        default="https://raw.githubusercontent.com/ros-industrial-attic/robotiq/kinetic-devel",
        description="Robotiq URDF 模型仓库基础 URL（ros-industrial 已迁至 attic）",
    )
    allegro_base_url: str = Field(
        default="https://raw.githubusercontent.com/pal-robotics/allegro_hand/main",
        description="Allegro 灵巧手 URDF 模型仓库基础 URL（PAL Robotics 官方仓库）",
    )
    mujoco_base_url: str = Field(
        default="https://raw.githubusercontent.com/google-deepmind/mujoco_menagerie/main",
        description="MuJoCo MJCF 模型仓库基础 URL",
    )
    isaac_base_url: str = Field(
        default="https://raw.githubusercontent.com/isaac-sim/IsaacLab/release/3.0.0-beta2",
        description="Isaac Lab 资产配置仓库基础 URL（USD 资产通过 Python 配置引用）",
    )

    # ─── 数据源 URL 配置（可通过环境变量覆盖） ───
    paperswithcode_base_url: str = Field(
        default="https://paperswithcode.com/api/v1",
        description="Papers with Code API 基础 URL",
    )
    openalex_base_url: str = Field(
        default="https://api.openalex.org",
        description=(
            "OpenAlex API 基础 URL（PapersWithCode fallback 源）。"
            "paperswithcode.com 在国内受 Cloudflare 反爬 + 访问慢（E5），"
            "PwC search/fetch 失败时自动转 OpenAlex（免费、无需 key、国内可达）。"
            "OpenAlex 不提供 paper-code 关联，fallback 结果的 code_url 为空。"
            "海外或 OpenAlex 不可达时可改为其他 scholarly API 或置空禁用 fallback。"
        ),
    )
    ieee_base_url: str = Field(
        default="https://ieeexploreapi.ieee.org/api/v1/search",
        description="IEEE Xplore API 基础 URL",
    )
    graspnet_base_url: str = Field(
        default="https://hf-mirror.com",
        description="GraspNet 数据集镜像基础 URL（默认走 HF 镜像）",
    )
    ycb_base_url: str = Field(
        default="https://hf-mirror.com",
        description="YCB Objects 数据集镜像基础 URL（默认走 HF 镜像）",
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

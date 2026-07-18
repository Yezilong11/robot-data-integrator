"""
GitHub Token 验证脚本

功能：
- 检查 .env 文件中是否配置了 GITHUB_TOKEN
- 验证 Token 是否有效
- 显示用户信息和使用限制

作者：挑战杯团队
创建日期：2026-07-14
"""

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(__file__).rsplit("\\", 1)[0])
from config import config


def main() -> None:
    print("=" * 60)
    print("  GitHub Token 验证")
    print("=" * 60)

    # 检查 .env 文件
    env_file = config.PROJECT_ROOT / ".env"
    env_example = config.PROJECT_ROOT / ".env.example"

    if not env_file.exists():
        print(f"\n❌ .env 文件不存在: {env_file}")
        if env_example.exists():
            print(f"  提示: 复制 {env_example} 为 {env_file}")
        return

    # 检查 Token
    token = config.GITHUB_TOKEN
    if not token:
        print(f"\n❌ GITHUB_TOKEN 未配置")
        print(f"\n获取步骤:")
        print(f"  1. 访问 https://github.com/settings/tokens")
        print(f"  2. 点击 'Generate new token' -> 'Generate new token (classic)'")
        print(f"  3. Note: robot-data-integrator")
        print(f"  4. Expiration: 90 days")
        print(f"  5. Scopes: 勾选 'public_repo'")
        print(f"  6. 点击 'Generate token'")
        print(f"  7. 复制 Token 并添加到 .env 文件的 GITHUB_TOKEN 字段")
        return

    # 验证 Token
    print(f"\n✅ .env 中已配置 GITHUB_TOKEN (长度: {len(token)})")
    print(f"\n正在验证 Token 有效性...")

    try:
        response = httpx.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
            },
            timeout=15.0,
        )

        if response.status_code == 200:
            user = response.json()
            print(f"\n✅ Token 有效!")
            print(f"  用户名: {user.get('login')}")
            print(f"  姓名: {user.get('name', 'N/A')}")
            print(f"  邮箱: {user.get('email', 'N/A')}")
            print(f"  类型: {user.get('type', 'N/A')}")

            # 显示速率限制
            remaining = response.headers.get("X-RateLimit-Remaining", "N/A")
            limit = response.headers.get("X-RateLimit-Limit", "N/A")
            print(f"  速率限制: {remaining}/{limit}")

            print(f"\n你现在可以运行:")
            print(f"  python scripts\\download_github.py --test")
            print(f"  python scripts\\download_franka.py")
            print(f"  python scripts\\download_robotiq.py")
            print(f"  python scripts\\download_allegro_alt.py")

        elif response.status_code == 401:
            print(f"\n❌ Token 无效 (HTTP 401)")
            print(f"  请检查 .env 中的 GITHUB_TOKEN 是否正确")
            print(f"  重新生成: https://github.com/settings/tokens")
        else:
            print(f"\n❌ 验证失败: HTTP {response.status_code}")
            print(f"  响应: {response.text[:200]}")

    except httpx.TimeoutException:
        print(f"\n❌ 网络超时，请检查网络连接")
    except Exception as e:
        print(f"\n❌ 验证出错: {e}")


if __name__ == "__main__":
    main()

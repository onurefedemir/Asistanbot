"""Finans ajanını ve ortamını bir kez oluşturur (veya günceller).

Kullanım:
    python -m finance.setup_agent

ANTHROPIC_API_KEY ortam değişkeni (veya .env) gereklidir. Oluşan kimlikler
.env dosyasına FINANCE_AGENT_ID / FINANCE_ENVIRONMENT_ID olarak yazılır.
Sistem istemini ya da araçları değiştirdikten sonra tekrar çalıştırın: mevcut
ajan yeni sürüme güncellenir.
"""

from __future__ import annotations

import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv, set_key

from .agent import MODEL, SYSTEM_PROMPT
from .tools import TOOL_DEFS

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

# Yerleşik araçlar (bash, dosya, web) kapalı: ajan yalnızca bizim araçlarımızı kullanır.
TOOLS = [
    {
        "type": "agent_toolset_20260401",
        "default_config": {"enabled": False, "permission_policy": {"type": "auto"}},
    },
    *TOOL_DEFS,
]


def main() -> None:
    load_dotenv(ENV_FILE)
    ENV_FILE.touch(exist_ok=True)
    client = anthropic.Anthropic()

    env_id = os.environ.get("FINANCE_ENVIRONMENT_ID")
    if not env_id:
        env = client.beta.environments.create(
            name="asistanbot-finance",
            config={
                "type": "cloud",
                "networking": {"type": "limited", "allow_package_managers": False, "allow_mcp_servers": False},
            },
        )
        env_id = env.id
        set_key(str(ENV_FILE), "FINANCE_ENVIRONMENT_ID", env_id)
        print(f"Ortam oluşturuldu: {env_id}")

    agent_id = os.environ.get("FINANCE_AGENT_ID")
    if agent_id:
        current = client.beta.agents.retrieve(agent_id)
        agent = client.beta.agents.update(
            agent_id,
            version=current.version,
            model=MODEL,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
        )
        print(f"Ajan güncellendi: {agent.id} (sürüm {agent.version})")
    else:
        agent = client.beta.agents.create(
            name="Asistanbot Finans Ajanı",
            model=MODEL,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
        )
        set_key(str(ENV_FILE), "FINANCE_AGENT_ID", agent.id)
        print(f"Ajan oluşturuldu: {agent.id}")

    print("Hazır. Botu başlatmak için: python main.py")


if __name__ == "__main__":
    main()

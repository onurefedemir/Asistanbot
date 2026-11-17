"""Claude Managed Agents üzerinde çalışan finans ajanı.

- Ajan ve ortam bir kez `python -m finance.setup_agent` ile oluşturulur;
  kimlikleri .env dosyasına yazılır (FINANCE_AGENT_ID, FINANCE_ENVIRONMENT_ID).
- Her Telegram sohbeti için bir oturum (session) açılır ve tekrar kullanılır,
  böylece ajan konuşmanın geçmişini hatırlar.
- Ajanın araçları (fiyat, analiz, backtest, sanal al/sat) bu makinede çalışır.
"""

from __future__ import annotations

import os

import anthropic

from .portfolio import Portfolio
from .tools import run_tool

MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """Sen Asistanbot'un finans ajanısın. Kullanıcı Türkçe konuşur; Türkçe, kısa ve net yanıt ver (Telegram mesajı, en fazla ~15 satır, Markdown tablosu kullanma).

Görevlerin: fiyat sorgulama, teknik analiz, strateji backtest'i, sanal portföy yönetimi ve kullanıcının verdiği finans görevlerini araçlarla yerine getirmek.

Al/sat kararlarında:
- Önce analyze_symbol ve backtest_strategies ile veriye bak; tahmin yürütme, rakam uydurma.
- Bir sinyali, o sembolde geçmişte işe yarayan (toplam getirisi pozitif, al-tut ile kıyaslanabilir, yeterli işlem sayısı olan) stratejiyle destekle. Backtest güvenilir değilse bunu söyle.
- Her öneride giriş fiyatı, stop-loss ve hedef ver; pozisyon büyüklüğünü portföyün en fazla %10'u ile sınırla ve tek işlemde portföyün %2'sinden fazlasını riske atma.
- Kazanma oranı ya da getiri sözü verme. Geçmiş performans geleceği garanti etmez; belirsizliği açıkça belirt.
- Sinyaller zayıf veya çelişkiliyse "işlem yapma / bekle" de; bu da geçerli bir karardır.

İşlemler yalnızca SANAL portföyde yapılır. paper_buy / paper_sell araçlarını yalnızca kullanıcı açıkça işlem istediğinde ya da sana al/sat yetkisi verdiğinde kullan; yaptığın her işlemi gerekçesiyle bildir.
"""


class FinanceAgent:
    def __init__(self, portfolio: Portfolio):
        self.portfolio = portfolio
        self.agent_id = os.environ.get("FINANCE_AGENT_ID")
        self.environment_id = os.environ.get("FINANCE_ENVIRONMENT_ID")
        self.client = anthropic.Anthropic() if self.enabled else None

    @property
    def enabled(self) -> bool:
        return bool(self.agent_id and self.environment_id)

    def _session_for(self, chat_id: int) -> str:
        sid = self.portfolio.get_session(chat_id)
        if sid:
            return sid
        session = self.client.beta.sessions.create(
            agent=self.agent_id,
            environment_id=self.environment_id,
            title=f"Asistanbot sohbet {chat_id}",
        )
        self.portfolio.set_session(chat_id, session.id)
        return session.id

    def reset(self, chat_id: int) -> None:
        """Sohbeti unutur; bir sonraki mesajda yeni oturum açılır."""
        self.portfolio.set_session(chat_id, None)

    def ask(self, chat_id: int, text: str) -> str:
        """Kullanıcı mesajını ajana iletir, araç çağrılarını yürütür, yanıt metnini döndürür.
        Senkron çalışır; async koddan asyncio.to_thread ile çağırın."""
        if not self.enabled:
            return "Finans ajanı kurulmamış. Önce `python -m finance.setup_agent` çalıştırın."
        try:
            return self._ask(chat_id, text)
        except anthropic.NotFoundError:
            # Oturum silinmiş/arşivlenmiş olabilir: yenisini açıp bir kez daha dene.
            self.reset(chat_id)
            return self._ask(chat_id, text)

    def _ask(self, chat_id: int, text: str) -> str:
        session_id = self._session_for(chat_id)
        parts: list[str] = []
        sessions = self.client.beta.sessions

        # Önce akışı aç, sonra mesajı gönder (erken olaylar kaçmasın).
        with sessions.events.stream(session_id=session_id) as stream:
            sessions.events.send(
                session_id=session_id,
                events=[{"type": "user.message", "content": [{"type": "text", "text": text}]}],
            )
            for event in stream:
                if event.type == "agent.message":
                    for block in event.content:
                        if block.type == "text":
                            parts.append(block.text)
                elif event.type == "agent.custom_tool_use":
                    output = run_tool(event.name, event.input, chat_id, self.portfolio)
                    sessions.events.send(
                        session_id=session_id,
                        events=[{
                            "type": "user.custom_tool_result",
                            "custom_tool_use_id": event.id,
                            "content": [{"type": "text", "text": output}],
                        }],
                    )
                elif (
                    event.type in ("agent.tool_use", "agent.mcp_tool_use")
                    and getattr(event, "evaluated_permission", None) == "ask"
                ):
                    # Yerleşik araçlar kapalı; yine de onay isterse gözetimsiz olduğumuz için reddet.
                    sessions.events.send(
                        session_id=session_id,
                        events=[{"type": "user.tool_confirmation", "tool_use_id": event.id, "result": "deny"}],
                    )
                elif event.type == "session.status_idle":
                    if event.stop_reason.type != "requires_action":
                        break
                elif event.type == "session.status_terminated":
                    self.reset(chat_id)
                    break

        return "\n\n".join(p.strip() for p in parts if p.strip()) or "(Ajan yanıt üretmedi.)"

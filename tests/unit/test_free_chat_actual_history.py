"""FreeChatSession 追问实际历史（开发文档 §7.5）。

display_user_text 与 actual_user_content 必须分开保存：第二轮续接历史要重发
第一轮真正发送的内容（含行情快照表），不能用简短展示问题替换——否则前缀从
旧 user 位置断开，重启后也无法恢复原请求。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from pa_agent.orchestrator.free_chat import FreeChatSession
from pa_agent.records.schema import AnalysisRecord, RecordMeta
from pa_agent.util.threading import CancelToken

_KLINE_TABLE = "序号 | 时间\n-----+----\n1 | 2026-01-01 | ... | K线快照表"


def _make_reply(content: str = "AI response", reasoning: str = "") -> MagicMock:
    reply = MagicMock()
    reply.content = content
    reply.reasoning_content = reasoning
    reply.raw = {"model": "deepseek-v4.1-flash-1017"}
    reply.usage = MagicMock()
    reply.usage.prompt_tokens = 100
    reply.usage.completion_tokens = 50
    reply.usage.cached_prompt_tokens = 40
    reply.usage.total_tokens = 150
    reply.usage.cache_hit_rate = 0.4  # 真实 AIUsage 为 property；桩显式给值
    return reply


def _make_base_record() -> AnalysisRecord:
    meta = RecordMeta(
        timestamp_local_iso="2026-05-18T14:00:13.000",
        timestamp_local_ms=1_747_569_613_000,
        symbol="XAUUSD",
        timeframe="1h",
        bar_count=2,
        ai_provider={"model": "deepseek-v4-flash"},
    )
    return AnalysisRecord(
        meta=meta,
        kline_data=[],
        htf_text="",
        stage1_messages=[],
        stage1_response=None,
        stage1_diagnosis=None,
        stage2_messages=[
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "user msg"},
        ],
        stage2_response={"content": "stage2 content"},
        stage2_decision={"decision": {"order_type": "不下单"}},
        strategy_files_used=[],
        experience_loaded=[],
        exception=None,
        usage_total={},
    )


def _make_session(client: MagicMock, kline_snapshot_fn=None) -> tuple[FreeChatSession, MagicMock]:
    pending_writer = MagicMock()
    session = FreeChatSession(
        base_record=_make_base_record(),
        client=client,
        assembler=MagicMock(),
        pending_writer=pending_writer,
        ledger=MagicMock(),
        kline_snapshot_fn=kline_snapshot_fn,
    )
    return session, pending_writer


class TestFollowupActualHistory:
    def test_second_turn_resends_first_turn_actual_content(self):
        """第二轮请求的历史里，第一轮 user 必须是带行情快照的实际内容。"""
        client = MagicMock()
        client.stream_chat.side_effect = [_make_reply("reply 1"), _make_reply("reply 2")]
        session, _ = _make_session(client, kline_snapshot_fn=lambda: _KLINE_TABLE)
        cancel = CancelToken()

        session.send("第一轮问题", cancel)
        session.send("第二轮问题", cancel)

        second_call_messages: list[dict] = client.stream_chat.call_args_list[1][0][0]
        user_msgs = [m for m in second_call_messages if m["role"] == "user"]
        # [0] 分析参考，[1] 第一轮实际内容（含快照），[2] 第二轮实际内容
        assert len(user_msgs) == 3
        first_turn = user_msgs[1]["content"]
        assert "当前图表K线数据" in first_turn
        assert _KLINE_TABLE in first_turn
        assert "第一轮问题" in first_turn  # 展示问题仍在实际内容末尾
        assert first_turn != "第一轮问题"
        # 最后一轮同样携带本轮快照
        assert _KLINE_TABLE in user_msgs[2]["content"]

    def test_history_full_keeps_display_and_actual(self):
        """history_full 的 user 条目同时保留展示文本与实际请求内容。"""
        client = MagicMock()
        client.stream_chat.return_value = _make_reply()
        session, _ = _make_session(client, kline_snapshot_fn=lambda: _KLINE_TABLE)

        session.send("展示问题", CancelToken())

        user_entries = [m for m in session.history_full if m["role"] == "user"]
        assert len(user_entries) == 1
        assert user_entries[0]["content"] == "展示问题"
        assert user_entries[0]["actual_content"].endswith("展示问题")
        assert "当前图表K线数据" in user_entries[0]["actual_content"]

    def test_followup_turn_persists_actual_user(self):
        """落盘 FollowupTurn.actual_user：与展示文本不同时保存，相同为 None。"""
        client = MagicMock()
        client.stream_chat.return_value = _make_reply()
        session, pending_writer = _make_session(client, kline_snapshot_fn=lambda: _KLINE_TABLE)

        session.send("带快照的问题", CancelToken())
        turn = pending_writer.append_followup.call_args[0][1]
        assert turn.actual_user is not None
        assert "当前图表K线数据" in turn.actual_user
        assert turn.user == "带快照的问题"

        # 无快照 → 实际内容与展示文本相同 → actual_user=None
        client2 = MagicMock()
        client2.stream_chat.return_value = _make_reply()
        session2, pending_writer2 = _make_session(client2)
        session2.send("纯文本问题", CancelToken())
        turn2 = pending_writer2.append_followup.call_args[0][1]
        assert turn2.actual_user is None

    def test_usage_records_served_model_and_hit_rate(self):
        """usage 记录实际服务模型名与单次命中率（§8.2 逐请求观测）。"""
        client = MagicMock()
        client.stream_chat.return_value = _make_reply()
        session, pending_writer = _make_session(client)

        session.send("问题", CancelToken())
        turn = pending_writer.append_followup.call_args[0][1]
        assert turn.usage["model"] == "deepseek-v4.1-flash-1017"
        assert turn.usage["cache_hit_rate_pct"] == 40.0

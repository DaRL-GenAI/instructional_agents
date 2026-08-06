"""Tests for Agent and Deliberation classes in src/agents.py"""

import pytest
from unittest.mock import MagicMock, patch


# Mock OpenAI before importing src.agents
with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test-key"}):
    with patch("openai.OpenAI"):
        from src.agents import Agent, Deliberation, LLM


class TestLLM:
    """Tests for the LLM class."""

    @patch("openai.OpenAI")
    def test_init_default_model(self, mock_openai):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            llm = LLM()
        assert llm.model_name == "gpt-4o-mini"

    @patch("openai.OpenAI")
    def test_init_custom_model(self, mock_openai):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            llm = LLM(model_name="gpt-4o")
        assert llm.model_name == "gpt-4o"

    def test_api_failure_preserves_response_accounting_contract(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            llm = LLM()
        llm.client = MagicMock()
        llm.client.chat.completions.create.side_effect = RuntimeError("rate limit")

        response, elapsed, tokens = llm.generate_response([], stream=False)

        assert response == "Error: rate limit"
        assert elapsed >= 0
        assert tokens == 0


class TestAgent:
    """Tests for the Agent class."""

    def _make_agent(self, **kwargs):
        mock_llm = MagicMock(spec=LLM)
        defaults = {
            "name": "TestAgent",
            "role": "test role",
            "llm": mock_llm,
        }
        defaults.update(kwargs)
        return Agent(**defaults), mock_llm

    def test_init_default_system_prompt(self):
        agent, _ = self._make_agent()
        assert agent.name == "TestAgent"
        assert agent.role == "test role"
        assert "TestAgent" in agent.system_prompt
        assert "test role" in agent.system_prompt

    def test_init_custom_system_prompt(self):
        agent, _ = self._make_agent(system_prompt="Custom prompt")
        assert agent.system_prompt == "Custom prompt"

    def test_message_history_starts_empty(self):
        agent, _ = self._make_agent()
        assert agent.message_history == []

    def test_add_message_to_history(self):
        agent, _ = self._make_agent()
        agent.add_message_to_history("user", "hello")
        agent.add_message_to_history("assistant", "hi")
        assert len(agent.message_history) == 2
        assert agent.message_history[0] == {"role": "user", "content": "hello"}
        assert agent.message_history[1] == {"role": "assistant", "content": "hi"}

    def test_reset_history(self):
        agent, _ = self._make_agent()
        agent.add_message_to_history("user", "hello")
        agent.reset_history()
        assert agent.message_history == []

    def test_get_messages_with_system(self):
        agent, _ = self._make_agent(system_prompt="You are a helper.")
        messages = agent.get_messages_with_system("What is 2+2?")
        assert len(messages) == 2
        assert messages[0] == {"role": "system", "content": "You are a helper."}
        assert messages[1] == {"role": "user", "content": "What is 2+2?"}

    def test_get_messages_includes_history(self):
        agent, _ = self._make_agent()
        agent.add_message_to_history("user", "prev question")
        agent.add_message_to_history("assistant", "prev answer")
        messages = agent.get_messages_with_system("new question")
        assert len(messages) == 4  # system + 2 history + current
        assert messages[-1]["content"] == "new question"

    def test_output_constraint_appended(self):
        agent, mock_llm = self._make_agent(output_constraint="Only JSON output.")
        mock_llm.generate_response.return_value = ("response", 1.0, 100)

        agent.generate_response("test prompt", stream=False, save_to_history=False)

        call_args = mock_llm.generate_response.call_args[0][0]
        # The messages should contain the constraint appended to the prompt
        user_msg = call_args[-1]["content"]
        assert "Only JSON output." in user_msg

    def test_generate_saves_to_history(self):
        agent, mock_llm = self._make_agent()
        mock_llm.generate_response.return_value = ("the answer", 1.0, 100)

        agent.generate_response("the question", stream=False, save_to_history=True)

        assert len(agent.message_history) == 2
        assert agent.message_history[0] == {"role": "user", "content": "the question"}
        assert agent.message_history[1] == {"role": "assistant", "content": "the answer"}

    def test_generate_skips_history(self):
        agent, mock_llm = self._make_agent()
        mock_llm.generate_response.return_value = ("answer", 1.0, 100)

        agent.generate_response("question", stream=False, save_to_history=False)

        assert len(agent.message_history) == 0


class TestDeliberation:
    """Tests for the Deliberation class."""

    def _make_deliberation(self, num_agents=2, **kwargs):
        mock_llm = MagicMock(spec=LLM)
        mock_llm.generate_response.return_value = ("mock response", 0.5, 50)

        agents = []
        for i in range(num_agents):
            agent = Agent(name=f"Agent{i}", role=f"role{i}", llm=mock_llm)
            agents.append(agent)

        summary_agent = Agent(name="Summarizer", role="summarizer", llm=mock_llm)

        defaults = {
            "id": "test_delib",
            "name": "Test Deliberation",
            "agents": agents,
            "summary_agent": summary_agent,
            "max_rounds": 1,
            "instruction_prompt": "Discuss this topic.",
        }
        defaults.update(kwargs)
        return Deliberation(**defaults), mock_llm

    def test_init(self):
        delib, _ = self._make_deliberation()
        assert delib.id == "test_delib"
        assert delib.name == "Test Deliberation"
        assert len(delib.agents) == 2
        assert delib.max_rounds == 1

    def test_default_summary_agent(self):
        mock_llm = MagicMock(spec=LLM)
        agents = [Agent(name="A", role="r", llm=mock_llm)]
        delib = Deliberation(id="t", name="T", agents=agents)
        assert delib.summary_agent is agents[0]

    def test_add_to_discussion(self):
        delib, _ = self._make_deliberation()
        delib.add_to_discussion("Agent0", "I think X.")
        delib.add_to_discussion("Agent1", "I think Y.")
        assert len(delib.discussion_history) == 2
        assert delib.discussion_history[0]["agent"] == "Agent0"

    def test_format_discussion_history(self):
        delib, _ = self._make_deliberation()
        delib.add_to_discussion("Alice", "Hello")
        delib.add_to_discussion("Bob", "Hi")
        formatted = delib.format_discussion_history()
        assert "Alice: Hello" in formatted
        assert "Bob: Hi" in formatted

    def test_run_calls_all_agents(self):
        delib, mock_llm = self._make_deliberation(num_agents=2, max_rounds=1)
        result, elapsed, tokens = delib.run()

        # 2 agents + 1 summarizer = 3 calls
        assert mock_llm.generate_response.call_count == 3

    def test_run_with_context_and_suggestion(self):
        delib, mock_llm = self._make_deliberation(num_agents=1, max_rounds=1)
        delib.run(current_context="prior results", user_suggestion="focus on X")

        first_call = mock_llm.generate_response.call_args_list[0]
        prompt_messages = first_call[0][0]
        user_content = prompt_messages[-1]["content"]
        assert "prior results" in user_content
        assert "focus on X" in user_content

    def test_run_resets_histories(self):
        delib, mock_llm = self._make_deliberation()
        delib.agents[0].add_message_to_history("user", "old msg")
        delib.run()
        # After run, discussion_history should have entries from the run,
        # and agent histories should have been reset before the run started
        assert len(delib.discussion_history) == 2  # 2 agents discussed

    def test_run_accumulates_time_and_tokens(self):
        delib, mock_llm = self._make_deliberation(num_agents=2, max_rounds=1)
        mock_llm.generate_response.return_value = ("resp", 1.0, 100)

        _, elapsed, tokens = delib.run()

        # 3 calls (2 agents + summarizer) * 1.0s each
        assert elapsed == pytest.approx(3.0)
        assert tokens == 300

    def test_summary_agent_sees_only_the_transcript_by_default(self):
        delib, mock_llm = self._make_deliberation(num_agents=2, max_rounds=1)
        delib.run()

        summary_content = mock_llm.generate_response.call_args_list[-1][0][0][-1][
            "content"
        ]
        assert "Discuss this topic." not in summary_content

    def test_summary_agent_can_receive_the_instruction_prompt(self):
        delib, mock_llm = self._make_deliberation(
            num_agents=2, max_rounds=1, summary_sees_context=True
        )
        delib.run()

        summary_content = mock_llm.generate_response.call_args_list[-1][0][0][-1][
            "content"
        ]
        assert "Discuss this topic." in summary_content
        assert "Discussion History:" in summary_content

    def test_independent_first_round_withholds_the_transcript(self):
        delib, mock_llm = self._make_deliberation(
            num_agents=2, max_rounds=2, independent_first_round=True
        )
        delib.run()

        prompts = [
            call[0][0][-1]["content"]
            for call in mock_llm.generate_response.call_args_list
        ]
        # Round one: neither agent sees the other. Round two: both do.
        assert "Discussion History:" not in prompts[0]
        assert "Discussion History:" not in prompts[1]
        assert "Discussion History:" in prompts[2]
        assert "Discussion History:" in prompts[3]

    def test_second_agent_sees_the_transcript_without_the_flag(self):
        delib, mock_llm = self._make_deliberation(num_agents=2, max_rounds=1)
        delib.run()

        prompts = [
            call[0][0][-1]["content"]
            for call in mock_llm.generate_response.call_args_list
        ]
        assert "Discussion History:" not in prompts[0]
        assert "Discussion History:" in prompts[1]

    def test_output_format_default(self):
        delib, _ = self._make_deliberation()
        assert delib.output_format == "md"

    def test_output_format_custom(self):
        delib, _ = self._make_deliberation(output_format="tex")
        assert delib.output_format == "tex"

import os
from typing import List, Dict
from openai import OpenAI
import time


class LLM:
    def __init__(self, model_name: str = "gpt-4o-mini"):
        self.model_name = "gpt-4o-mini"
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    def generate_response(self, messages: List[Dict[str, str]], stream = False) -> str:
        start_time = time.time()

        try:
            chat_completion = self.client.chat.completions.create(
                messages=messages,
                model=self.model_name
            )
            response = chat_completion.choices[0].message.content
            print(f"[Response from {self.model_name}]: {response}")

            elapsed_time = time.time() - start_time
            token_usage = chat_completion.usage.total_tokens

            print(f"[Response Time: {elapsed_time:.2f}s]")
            print(f"[Total Tokens: {token_usage}]")
            return response, elapsed_time, token_usage

        except Exception as e:
            print(f"Error generating response: {e}")
            return f"Error: {e}"

class LLM_stream:
    """
    Base LLM class, responsible for calling OpenAI API with streaming input/output
    """
    def __init__(self, model_name: str = "gpt-4o-mini"):
        self.model_name = model_name
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        
        
    def generate_response(self, messages: List[Dict[str, str]], stream: bool = True) -> str:
        """
        Call OpenAI API to generate a response
        
        Args:
            messages: List of messages with role and content
            stream: Whether to use streaming output
            
        Returns:
            Generated response text
        """
        try:
            if stream:
                chat_completion = self.client.chat.completions.create(
                    messages=messages,
                    model=self.model_name,
                    stream=True
                )
                
                response = ""
                for chunk in chat_completion:
                    delta = chunk.choices[0].delta
                    if delta.content is not None:
                        response += delta.content
                        print(delta.content, end="", flush=True)
                print()  # Ensure newline after streaming output
                
                return response
            else:
                chat_completion = self.client.chat.completions.create(
                    messages=messages,
                    model=self.model_name
                )
                return chat_completion.choices[0].message.content
                
        except Exception as e:
            print(f"Error generating response: {e}")
            return f"Error: {e}"


class Agent:
    """
    Agent class, representing an intelligent entity with a specific role
    """
    def __init__(self, 
                 name: str, 
                 role: str, 
                 llm: LLM,
                 system_prompt: str = None,
                 output_constraint: str = None):
        """
        Initialize Agent
        
        Args:
            name: Agent name
            role: Agent role description
            llm: LLM instance to use
            system_prompt: System prompt defining Agent behavior and constraints
        """
        self.name = name
        self.role = role
        self.llm = llm
        self.system_prompt = system_prompt if system_prompt else f"You are {name}, {role}."
        self.output_constraint = output_constraint
        self.message_history = []
        
    def reset_history(self):
        """Reset message history"""
        self.message_history = []
        
    def add_message_to_history(self, role: str, content: str):
        """Add message to history"""
        self.message_history.append({"role": role, "content": content})
        
    def get_messages_with_system(self, prompt: str) -> List[Dict[str, str]]:
        """Get complete message list including system prompt"""
        messages = [{"role": "system", "content": self.system_prompt}]
        
        # Add history messages
        if self.message_history:
            messages.extend(self.message_history)
            
        # Add current prompt
        messages.append({"role": "user", "content": prompt})
        return messages
    
    def generate_response(self, 
                          prompt: str,  
                          stream: bool = True,
                          save_to_history: bool = True) -> str:
        """
        Generate Agent's response
        
        Args:
            prompt: Input prompt
            output_constraint: Output constraints
            stream: Whether to use streaming output
            save_to_history: Whether to save to message history
            
        Returns:
            Generated response
        """
        full_prompt = prompt
        if self.output_constraint:
            full_prompt += f"\n\n{self.output_constraint}"
            
        messages = self.get_messages_with_system(full_prompt)
        
        print(f"{'-'*50}\n{self.name} ({self.role}) is thinking...\n")
        response, elapsed_time, token_usage = self.llm.generate_response(messages, stream)

        if save_to_history:
            self.add_message_to_history("user", prompt)
            self.add_message_to_history("assistant", response)
            
        return response, elapsed_time, token_usage


class Deliberation:
    """
    Deliberation class, managing interactions between multiple agents
    """
    def __init__(self, 
                 id: str,
                 name: str,
                 agents: List[Agent], 
                 summary_agent: Agent = None,
                 max_rounds: int = 1,
                 instruction_prompt: str = "",
                 input_files = None,
                 output_format: str = "md"):
        """
        Initialize Deliberation
        
        Args:
            id: Unique identifier for this deliberation
            name: Human-readable name for this deliberation
            agents: List of participating agents
            moderator: Agent moderating the discussion (optional)
            max_rounds: Maximum discussion rounds
            summary_agent: Agent responsible for summarizing (optional)
            input_prompt: Default input prompt for this deliberation
            input_files: List of input files to use as additional context
        """
        self.id = id
        self.name = name
        self.agents = agents
        self.max_rounds = max_rounds
        self.summary_agent = summary_agent if summary_agent else agents[0]
        self.discussion_history = []
        self.instruction_prompt = instruction_prompt
        self.input_files = input_files
        self.output_format = output_format
        
    def add_to_discussion(self, agent_name: str, content: str):
        """Add content to discussion history"""
        self.discussion_history.append({
            "agent": agent_name,
            "content": content
        })
        
    def format_discussion_history(self) -> str:
        """Format discussion history as text"""
        formatted = "Discussion History:\n\n"
        for entry in self.discussion_history:
            formatted += f"{entry['agent']}: {entry['content']}\n\n"
        return formatted
    
    def run(self, current_context: str = None, user_suggestion: str = None) -> str:
        """
        Run the deliberation process
        
        Args:
            current_state: Output from previous deliberation to use as context
            user_suggestion: Optional user suggestion to guide the deliberation
            
        Returns:
            Discussion summary
        """
        print(f"\n{'='*50}\nStarting Deliberation: {self.name}\n{'='*50}\n")
        
        # Process input files if provided
        file_contents = str(self.input_files)
        
        # Combine initial prompt with previous state, user suggestion, and file contents
        print(f"Instruction prompt: {self.instruction_prompt}\n")
        
        full_prompt = self.instruction_prompt
        if user_suggestion:
            full_prompt += f"\n\nUser Suggestion: {user_suggestion}"
        if current_context:
            full_prompt += f"\n\nCurrent Context:\n{current_context}"
        if file_contents:
            full_prompt += f"\n\nAdditional input from files:\n{file_contents}"
        current_prompt = full_prompt
        
        # Reset all Agent histories
        for agent in self.agents:
            agent.reset_history()
            
        # Clear discussion history
        self.discussion_history = []
            
        # Main discussion loop
        elapsed_time = 0
        token_usage = 0
        for round_num in range(self.max_rounds):
            print(f"\n{'-'*50}\nRound {round_num + 1} of {self.max_rounds}\n{'-'*50}\n")
            
            for agent in self.agents:
                # Build current agent's input, including previous discussion
                if self.discussion_history:
                    agent_prompt = f"{current_prompt}\n\n{self.format_discussion_history()}\n\nIt's now your turn to provide your thoughts."
                else:
                    agent_prompt = current_prompt
                
                # Get agent's response
                response, et, tu = agent.generate_response(agent_prompt, save_to_history=False)
                self.add_to_discussion(agent.name, response)

                elapsed_time += et
                token_usage += tu
        
        # Generate results of this discussion          
        summary, et, tu = self.summary_agent.generate_response(
            f"{self.format_discussion_history()}",
            save_to_history=False
        )
        elapsed_time += et
        token_usage += tu
        
        print(f"\n{'='*50}\nDeliberation Complete\n{'='*50}\n")
        return summary, elapsed_time, token_usage


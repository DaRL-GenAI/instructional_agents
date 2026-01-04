"""
Slide Analysis Agent
分析现有幻灯片内容，提供改进建议
"""

from typing import Dict, List, Any, Optional
from src.agents import Agent, LLM


class SlideAnalysisAgent:
    """分析幻灯片并提供改进建议的Agent"""
    
    def __init__(self, llm: LLM):
        self.llm = llm
        
        # 创建分析Agent
        self.content_analyst = Agent(
            name="Content Analyst",
            role="Expert in analyzing educational content structure and quality",
            llm=llm,
            system_prompt=(
                "You are a Content Analyst specialized in reviewing educational slide decks. "
                "Your task is to analyze the structure, content quality, coverage, and organization "
                "of existing slide materials. Identify strengths, weaknesses, gaps, and areas for improvement."
            )
        )
        
        self.improvement_advisor = Agent(
            name="Improvement Advisor",
            role="Educational design consultant providing actionable improvement recommendations",
            llm=llm,
            system_prompt=(
                "You are an Improvement Advisor who provides specific, actionable recommendations "
                "for enhancing educational slide decks. Based on content analysis and user requirements, "
                "you suggest concrete improvements, additions, and modifications."
            )
        )
    
    def analyze_existing_content(
        self, 
        knowledge_base_summary: Dict[str, Any],
        user_requirements: str
    ) -> Dict[str, Any]:
        """
        分析现有幻灯片内容
        
        Args:
            knowledge_base_summary: 知识库内容摘要
            user_requirements: 用户的需求/想要改进的内容
            
        Returns:
            分析结果
        """
        # 构建分析提示
        analysis_prompt = f"""
Please analyze the following existing slide deck content and user requirements:

**Existing Content Summary:**
{self._format_knowledge_base_summary(knowledge_base_summary)}

**User Requirements:**
{user_requirements}

Please provide a comprehensive analysis covering:
1. Content Structure: How is the content organized? Is the flow logical?
2. Coverage Assessment: What topics are covered? What might be missing?
3. Quality Evaluation: Are the explanations clear? Are examples appropriate?
4. Strengths: What aspects are well-done?
5. Weaknesses: What areas need improvement?
6. Gap Analysis: What content is missing based on user requirements?

Format your response clearly with sections and bullet points.
"""
        
        analysis_response, _, _ = self.content_analyst.generate_response(
            analysis_prompt,
            stream=True,
            save_to_history=False
        )
        
        return {
            "analysis": analysis_response,
            "analyzer": "Content Analyst"
        }
    
    def generate_improvement_recommendations(
        self,
        analysis_result: Dict[str, Any],
        user_requirements: str,
        search_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        生成改进建议
        
        Args:
            analysis_result: 内容分析结果
            user_requirements: 用户需求
            search_results: 相关内容的搜索结果
            
        Returns:
            改进建议
        """
        # 格式化搜索结果
        relevant_content = "\n\n".join([
            f"**Slide {i+1}:** {result.get('content', '')[:500]}"
            for i, result in enumerate(search_results[:5])
        ])
        
        recommendation_prompt = f"""
Based on the following analysis and user requirements, provide specific improvement recommendations:

**Content Analysis:**
{analysis_result['analysis']}

**User Requirements:**
{user_requirements}

**Relevant Existing Content:**
{relevant_content}

Please provide:
1. **Specific Changes Needed**: What exactly should be modified?
2. **Content to Add**: What new content should be included?
3. **Content to Remove/Update**: What should be removed or updated?
4. **Structural Improvements**: How should the organization be improved?
5. **Prioritized Action Plan**: Step-by-step recommendations prioritized by importance
6. **Examples**: Specific examples of how to implement the changes

Format your response clearly with sections and bullet points.
"""
        
        recommendations, _, _ = self.improvement_advisor.generate_response(
            recommendation_prompt,
            stream=True,
            save_to_history=False
        )
        
        return {
            "recommendations": recommendations,
            "advisor": "Improvement Advisor",
            "based_on_analysis": True
        }
    
    def _format_knowledge_base_summary(self, summary: Dict[str, Any]) -> str:
        """格式化知识库摘要"""
        if summary.get("type") == "simple_storage":
            chunks = summary.get("chunks", [])
            content = f"Total slides: {summary['total_chunks']}\n\n"
            content += "Sample slides:\n"
            for chunk in chunks[:5]:
                content += f"- {chunk.get('title', 'Untitled')} (from {chunk.get('filename', 'unknown')})\n"
            return content
        else:
            return f"Knowledge base contains {summary.get('total_chunks', 0)} slide chunks."


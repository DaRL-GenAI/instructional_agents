"""
Slide Enhancer
基于原始PDF内容和改进建议，生成改进后的LaTeX幻灯片
"""

import os
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from src.agents import Agent, LLM
from src.slide_knowledge_base import SlideKnowledgeBase
from src.slides import SlideUtils  # 复用slides.py中的工具函数


class SlideEnhancer:
    """基于原始幻灯片和改进建议生成改进后的LaTeX"""
    
    def __init__(self, llm: LLM):
        self.llm = llm
        
        # 创建增强Agent
        self.content_enhancer = Agent(
            name="Content Enhancer",
            role="Expert in enhancing educational slides by applying improvement suggestions",
            llm=llm,
            system_prompt=(
                "You are a Content Enhancer specialized in improving educational slides. "
                "Your task is to take original slide content and enhancement recommendations, "
                "then create improved versions that incorporate the suggestions while maintaining "
                "the original structure and key concepts."
            )
        )
        
        self.latex_generator = Agent(
            name="LaTeX Generator",
            role="Expert in generating LaTeX beamer slides from enhanced content",
            llm=llm,
            system_prompt=(
                "You are a LaTeX Generator responsible for creating well-formatted beamer slides "
                "from enhanced educational content. Your goal is to generate clean, compilable "
                "LaTeX code that effectively presents the improved content."
            )
        )
    
    def enhance_and_generate_latex(
        self,
        knowledge_base_name: str,
        recommendations: Dict[str, Any],
        latex_template: Optional[str] = None,
        output_dir: str = "./enhanced_slides/",
        user_feedback: Optional[Dict[str, Any]] = None,
        kb_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        增强幻灯片并生成LaTeX文件
        
        Args:
            knowledge_base_name: 知识库名称（包含原始幻灯片内容）
            recommendations: 改进建议
            latex_template: LaTeX模板（可选）
            output_dir: 输出目录
            user_feedback: 用户反馈（可选），格式类似 {"slides": "...", "overall": "..."}
            kb_dir: 知识库目录路径（可选），如果提供，将从该目录读取knowledge base
            
        Returns:
            包含生成文件路径的字典
        """
        # 初始化user_feedback为默认值
        if user_feedback is None:
            user_feedback = {
                "slides": "",
                "overall": ""
            }
        print(f"\n{'='*60}\nStarting Slide Enhancement and LaTeX Generation\n{'='*60}\n")
        
        # 加载知识库获取原始内容
        if kb_dir:
            print(f"DEBUG: Loading knowledge base from exp directory: {kb_dir}")
            kb = SlideKnowledgeBase(knowledge_base_name, kb_dir=kb_dir)
        else:
            kb = SlideKnowledgeBase(knowledge_base_name)
        summary = kb.get_all_content_summary()
        
        # 获取所有原始幻灯片内容
        # 优先从chunks.json文件读取（包含完整的结构）
        chunks_file = kb.kb_dir / "chunks.json"
        if chunks_file.exists():
            with open(chunks_file, 'r', encoding='utf-8') as f:
                original_slides = json.load(f)
        elif summary.get("type") == "simple_storage":
            original_slides = kb.chunks if hasattr(kb, 'chunks') and kb.chunks else []
        else:
            # 从chromadb获取
            original_slides = self._get_all_chunks_from_kb(kb)
        
        if not original_slides:
            raise ValueError(f"No slides found in knowledge base: {knowledge_base_name}")
        
        # 确保幻灯片按照slide_number排序
        original_slides = sorted(
            original_slides,
            key=lambda x: x.get('slide_number', x.get('metadata', {}).get('slide_number', 0))
        )
        
        print(f"Found {len(original_slides)} slides to enhance")
        
        # 获取或创建LaTeX模板
        if latex_template is None:
            latex_template = SlideUtils.get_latex_template(catalog=False)
        
        # 解析LaTeX模板
        latex_prefix, latex_suffix = SlideUtils.parse_latex_template(latex_template)
        
        # 为每张幻灯片生成改进后的内容并转换为LaTeX
        enhanced_frames = []
        enhanced_content_list = []
        
        for idx, original_slide in enumerate(original_slides):
            print(f"\n{'-'*50}\nEnhancing Slide {idx + 1}/{len(original_slides)}: {original_slide.get('title', 'Untitled')}\n{'-'*50}\n")
            
            # 增强内容
            enhanced_content = self._enhance_slide_content(
                original_slide, 
                recommendations, 
                user_feedback=user_feedback
            )
            enhanced_content_list.append(enhanced_content)
            
            # 生成LaTeX
            latex_frames = self._generate_latex_frames(
                enhanced_content, 
                original_slide,
                user_feedback=user_feedback
            )
            enhanced_frames.extend(latex_frames)
        
        # 编译完整的LaTeX文档（使用工具函数）
        full_latex = SlideUtils.compile_latex_document(latex_prefix, enhanced_frames, latex_suffix)
        
        # 保存文件
        output_path = Path(output_dir).resolve()  # 使用resolve()获取绝对路径
        print(f"DEBUG: Creating output directory: {output_path.absolute()}")
        output_path.mkdir(parents=True, exist_ok=True)
        print(f"DEBUG: Directory created: {output_path.exists()}")
        
        latex_file = output_path / "enhanced_slides.tex"
        with open(latex_file, 'w', encoding='utf-8') as f:
            f.write(full_latex)
        
        # 保存增强后的内容（JSON格式，用于参考）
        enhanced_json = output_path / "enhanced_content.json"
        with open(enhanced_json, 'w', encoding='utf-8') as f:
            json.dump({
                "enhanced_at": datetime.now().isoformat(),
                "original_slides_count": len(original_slides),
                "enhanced_slides": enhanced_content_list
            }, f, indent=2, ensure_ascii=False)
        
        print(f"\n{'='*60}\nEnhancement Complete\n{'='*60}\n")
        print(f"✓ Enhanced LaTeX saved to: {latex_file}")
        print(f"✓ Enhanced content saved to: {enhanced_json}")
        
        return {
            "success": True,
            "latex_file": str(latex_file),
            "content_file": str(enhanced_json),
            "total_slides": len(original_slides),
            "total_frames": len(enhanced_frames)
        }
    
    def _get_all_chunks_from_kb(self, kb: SlideKnowledgeBase) -> List[Dict[str, Any]]:
        """从知识库获取所有chunks"""
        # 优先从chunks.json读取
        chunks_file = kb.kb_dir / "chunks.json"
        if chunks_file.exists():
            with open(chunks_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        if kb.use_chromadb:
            try:
                # 获取所有文档
                results = kb.collection.get()
                chunks = []
                if results.get("ids"):
                    for i, doc_id in enumerate(results["ids"]):
                        chunk = {
                            "id": doc_id,
                            "title": f"Slide {i+1}",  # 默认标题
                            "content": results["documents"][i] if results.get("documents") and i < len(results["documents"]) else "",
                            "metadata": results["metadatas"][i] if results.get("metadatas") and i < len(results["metadatas"]) else {}
                        }
                        # 尝试从metadata恢复title和其他信息
                        metadata = chunk.get("metadata", {})
                        if "file_path" in metadata:
                            chunk["filename"] = Path(metadata["file_path"]).name
                        chunks.append(chunk)
                return chunks
            except Exception as e:
                print(f"Warning: Could not get chunks from chromadb: {e}")
                return []
        else:
            return kb.chunks if hasattr(kb, 'chunks') and kb.chunks else []
    
    def _enhance_slide_content(
        self,
        original_slide: Dict[str, Any],
        recommendations: Dict[str, Any],
        user_feedback: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        基于原始内容和建议增强幻灯片
        
        Args:
            original_slide: 原始幻灯片内容
            recommendations: 改进建议
            user_feedback: 用户反馈（可选）
            
        Returns:
            增强后的内容
        """
        # 提取原始内容
        title = original_slide.get("title", "Untitled Slide")
        content = original_slide.get("content", "")
        if not content:
            # 尝试从其他字段获取
            content = original_slide.get("text", "") or str(original_slide)
        
        # 构建增强提示
        recommendations_text = recommendations.get("recommendations", "")
        if isinstance(recommendations_text, dict):
            recommendations_text = recommendations_text.get("recommendations", "")
        
        # 添加用户反馈（如果提供）
        feedback_text = ""
        if user_feedback:
            slides_feedback = user_feedback.get("slides", "")
            overall_feedback = user_feedback.get("overall", "")
            if slides_feedback:
                feedback_text += f"\n\n**User Feedback on Slides:**\n{slides_feedback}"
            if overall_feedback:
                feedback_text += f"\n\n**Overall User Feedback:**\n{overall_feedback}"
        
        enhancement_prompt = f"""
Please enhance the following slide by incorporating the improvement recommendations.{feedback_text}

**Original Slide:**
Title: {title}
Content:
{content[:2000]}

**Improvement Recommendations:**
{recommendations_text[:2000]}

Please create an enhanced version of this slide that:
1. Maintains the original structure and key concepts
2. Incorporates the improvement suggestions naturally
3. Adds examples, explanations, or content as recommended
4. Improves clarity and educational value
5. Keeps the content concise enough for a slide
{f"6. Addresses the user feedback provided above" if feedback_text else ""}

Format your response as:
**Enhanced Title:** [new or improved title]

**Enhanced Content:**
[enhanced content with improvements incorporated]

**Key Improvements Made:**
- [brief list of what was enhanced]
"""
        
        # 获取增强后的内容
        enhanced_response, _, _ = self.content_enhancer.generate_response(
            enhancement_prompt,
            stream=True,
            save_to_history=False
        )
        
        # 解析响应
        enhanced_title, enhanced_content = self._parse_enhanced_content(enhanced_response, title)
        
        return {
            "original_title": title,
            "enhanced_title": enhanced_title,
            "original_content": content,
            "enhanced_content": enhanced_content,
            "enhancement_summary": enhanced_response
        }
    
    def _parse_enhanced_content(self, response: str, fallback_title: str) -> tuple:
        """解析增强后的内容，提取标题和内容"""
        lines = response.split("\n")
        
        title = fallback_title
        content_start_idx = 0
        
        # 查找标题
        for i, line in enumerate(lines):
            if "Enhanced Title:" in line or "**Enhanced Title:**" in line:
                title = line.split(":", 1)[1].strip().strip("*").strip()
                content_start_idx = i + 1
                break
        
        # 提取内容
        in_content = False
        content_lines = []
        
        for i, line in enumerate(lines[content_start_idx:], start=content_start_idx):
            if "Enhanced Content:" in line or "**Enhanced Content:**" in line:
                in_content = True
                continue
            if in_content:
                if "Key Improvements" in line or "**Key Improvements" in line:
                    break
                content_lines.append(line)
        
        content = "\n".join(content_lines).strip()
        
        # 如果没有找到结构化内容，使用整个响应作为内容
        if not content:
            # 移除标题行
            content = "\n".join([l for l in lines if "Enhanced Title" not in l]).strip()
        
        return title, content
    
    def _generate_latex_frames(
        self,
        enhanced_content: Dict[str, Any],
        original_slide: Dict[str, Any],
        user_feedback: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """
        从增强后的内容生成LaTeX框架
        
        Args:
            enhanced_content: 增强后的内容
            original_slide: 原始幻灯片（用于参考）
            user_feedback: 用户反馈（可选）
            
        Returns:
            LaTeX框架列表
        """
        title = enhanced_content.get("enhanced_title", "Untitled")
        content = enhanced_content.get("enhanced_content", "")
        
        # 使用工具函数生成prompt（包含用户反馈）
        generation_prompt = SlideUtils.generate_latex_frame_prompt(
            title=title,
            content=content,
            user_feedback=user_feedback,
            max_frames=3
        )
        
        latex_response, _, _ = self.latex_generator.generate_response(
            generation_prompt,
            stream=True,
            save_to_history=False
        )
        
        # 使用工具函数提取frames
        frames = SlideUtils.extract_latex_frames(latex_response)
        
        if not frames:
            # 如果没有找到frame，创建一个简单的fallback
            frames = [f"""\\begin{{frame}}[fragile]
    \\frametitle{{{title}}}
    {content[:500]}
\\end{{frame}}"""]
        
        return frames
    


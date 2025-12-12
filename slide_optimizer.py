"""
Slide Optimizer
协调单章节和全课程优化
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

from slide_knowledge_base import SlideKnowledgeBase
from pdf_processor import PDFSlideProcessor
from slide_analysis_agent import SlideAnalysisAgent
from slide_enhancer import SlideEnhancer
from agents import LLM


class SlideOptimizer:
    """协调幻灯片优化流程"""
    
    def __init__(self):
        self.processor = PDFSlideProcessor()
        self.llm = LLM()
        self.analysis_agent = SlideAnalysisAgent(self.llm)
        self.enhancer = SlideEnhancer(self.llm)
    
    def optimize_chapter(
        self,
        storage_id: str,
        chapter_name: str,
        user_requirements: str,
        exp_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        优化指定章节
        
        Args:
            storage_id: PDF存储ID
            chapter_name: 章节名称（如"Chapter 3"）
            user_requirements: 用户需求
            exp_name: 实验名称，如果提供，knowledge base将保存到exp/{exp_name}/knowledge_base/
            
        Returns:
            优化结果
        """
        print(f"Optimizing chapter: {chapter_name}")
        
        # 1. 按需求提取相关内容
        extracted_data = self.processor.extract_by_requirement(
            storage_id=storage_id,
            user_requirements=user_requirements,
            target_chapters=[chapter_name]
        )
        
        if extracted_data["total_extracted_files"] == 0:
            return {
                "success": False,
                "error": f"No content found for {chapter_name}",
                "chapter": chapter_name
            }
        
        # 2. 创建知识库 - 如果提供了exp_name，保存到exp目录
        kb_name = f"{storage_id}_chapter_{chapter_name.replace(' ', '_').replace('Chapter', 'Ch')}"
        if exp_name:
            kb_dir = f"./exp/{exp_name}/knowledge_base"
            print(f"DEBUG: Creating knowledge base in exp directory: {kb_dir}")
        else:
            kb_dir = "knowledge_base"
        kb = SlideKnowledgeBase(kb_name, kb_dir=kb_dir)
        kb.create_from_extracted_data(extracted_data, chapter_filter=chapter_name)
        
        # 3. 分析内容
        summary = kb.get_all_content_summary()
        analysis_result = self.analysis_agent.analyze_existing_content(
            summary,
            user_requirements
        )
        
        # 4. 搜索相关内容
        search_results = kb.search(user_requirements, top_k=10)
        
        # 5. 生成建议
        recommendations = self.analysis_agent.generate_improvement_recommendations(
            analysis_result,
            user_requirements,
            search_results
        )
        
        return {
            "success": True,
            "chapter": chapter_name,
            "knowledge_base_name": kb_name,
            "extracted_slides": extracted_data["total_extracted_files"],
            "analysis": analysis_result,
            "recommendations": recommendations,
            "relevant_content": search_results[:5]
        }
    
    def optimize_all_chapters(
        self,
        storage_id: str,
        user_requirements: str,
        auto_detect_chapters: bool = True,
        exp_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        优化全部章节
        
        Args:
            storage_id: PDF存储ID
            user_requirements: 用户需求
            auto_detect_chapters: 是否自动检测章节
            exp_name: 实验名称，如果提供，knowledge base将保存到exp/{exp_name}/knowledge_base/
            
        Returns:
            所有章节的优化结果
        """
        results = {
            "success": True,
            "total_chapters": 0,
            "chapters": [],
            "overall_summary": None
        }
        
        if auto_detect_chapters:
            # 自动检测所有章节
            chapters = self._detect_all_chapters(storage_id)
        else:
            # 使用用户指定的章节列表
            chapters = []  # 可以从用户输入获取
        
        if not chapters:
            return {
                "success": False,
                "error": "No chapters detected. Please specify chapters manually.",
                "chapters": []
            }
        
        print(f"Found {len(chapters)} chapters to optimize")
        
        # 循环优化每个章节
        for chapter_name in chapters:
            try:
                print(f"\n{'='*60}")
                print(f"Processing chapter: {chapter_name}")
                print(f"{'='*60}\n")
                
                chapter_result = self.optimize_chapter(
                    storage_id,
                    chapter_name,
                    user_requirements,
                    exp_name=exp_name
                )
                results["chapters"].append(chapter_result)
                results["total_chapters"] += 1
            except Exception as e:
                print(f"Error optimizing chapter {chapter_name}: {e}")
                results["chapters"].append({
                    "success": False,
                    "chapter": chapter_name,
                    "error": str(e)
                })
        
        # 生成总体摘要
        results["overall_summary"] = self._generate_overall_summary(results["chapters"])
        
        return results
    
    def _detect_all_chapters(self, storage_id: str) -> List[str]:
        """自动检测所有章节"""
        storage_dir = self.processor.output_dir / "temp_storage" / storage_id
        
        if not storage_dir.exists():
            return []
        
        # 加载元数据
        metadata_file = storage_dir / "metadata.json"
        if not metadata_file.exists():
            return []
        
        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        chapters = set()
        
        # 从文件名提取章节
        for file_info in metadata["files"]:
            filename = file_info["filename"]
            chapter = self.processor._extract_chapter_from_filename(filename)
            if chapter:
                chapters.add(chapter)
        
        # 如果文件名中没有章节信息，尝试扫描PDF内容
        if not chapters:
            pdf_files = [Path(f["stored_path"]) for f in metadata["files"]]
            for pdf_file in pdf_files:
                if not pdf_file.exists():
                    continue
                    
                try:
                    # 快速扫描前几页提取章节信息
                    if PDFPLUMBER_AVAILABLE:
                        with pdfplumber.open(pdf_file) as pdf:
                            for page_num in range(min(5, len(pdf.pages))):
                                page = pdf.pages[page_num]
                                text = page.extract_text() or ""
                                
                                # 查找章节标题模式
                                chapter_patterns = [
                                    r'chapter\s*(\d+)',
                                    r'第\s*(\d+)\s*章',
                                ]
                                
                                for pattern in chapter_patterns:
                                    matches = re.findall(pattern, text, re.IGNORECASE)
                                    for match in matches:
                                        chapters.add(f"Chapter {match}")
                except Exception as e:
                    print(f"Warning: Could not scan {pdf_file.name}: {e}")
                    continue
        
        # 如果仍然没有找到，使用文件顺序作为章节
        if not chapters:
            pdf_files = sorted([Path(f["stored_path"]) for f in metadata["files"]])
            for i, pdf_file in enumerate(pdf_files, 1):
                chapters.add(f"Chapter {i}")
        
        # 按章节数字排序
        def extract_chapter_num(chapter_name: str) -> int:
            match = re.search(r'\d+', chapter_name)
            return int(match.group()) if match else 0
        
        return sorted(list(chapters), key=extract_chapter_num)
    
    def _generate_overall_summary(self, chapter_results: List[Dict]) -> Dict[str, Any]:
        """生成总体优化摘要"""
        successful = [r for r in chapter_results if r.get("success")]
        failed = [r for r in chapter_results if not r.get("success")]
        
        return {
            "total_chapters": len(chapter_results),
            "successful": len(successful),
            "failed": len(failed),
            "common_issues": self._identify_common_issues(successful),
            "overall_recommendations": self._aggregate_recommendations(successful)
        }
    
    def _identify_common_issues(self, results: List[Dict]) -> List[str]:
        """识别共同问题"""
        # 可以分析所有章节的分析结果，找出共同问题
        # 这里先返回空列表，后续可以扩展
        return []
    
    def _aggregate_recommendations(self, results: List[Dict]) -> str:
        """聚合所有章节的建议"""
        all_recommendations = []
        for result in results:
            if "recommendations" in result and result["recommendations"]:
                rec_text = result["recommendations"].get("recommendations", "")
                if rec_text:
                    all_recommendations.append(rec_text)
        
        # 汇总生成总体建议
        if all_recommendations:
            return "\n\n---\n\n".join(all_recommendations[:5])  # 返回前5个
        return "No specific recommendations generated."
    
    def generate_enhanced_latex(
        self,
        knowledge_base_name: str,
        recommendations: Dict[str, Any],
        output_dir: str = "./enhanced_slides/",
        latex_template: Optional[str] = None,
        user_feedback: Optional[Dict[str, Any]] = None,
        exp_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        基于改进建议生成改进后的LaTeX幻灯片
        
        Args:
            knowledge_base_name: 知识库名称（包含原始幻灯片）
            recommendations: 改进建议
            output_dir: 输出目录
            latex_template: LaTeX模板（可选）
            user_feedback: 用户反馈（可选），格式类似 {"slides": "...", "overall": "..."}
            exp_name: 实验名称，如果提供，将从exp/{exp_name}/knowledge_base/读取knowledge base
            
        Returns:
            包含生成文件路径的字典
        """
        print(f"Generating enhanced LaTeX slides from knowledge base: {knowledge_base_name}")
        
        # 如果提供了exp_name，从exp目录读取knowledge base
        kb_dir = None
        if exp_name:
            kb_dir = f"./exp/{exp_name}/knowledge_base"
            print(f"DEBUG: Using knowledge base from exp directory: {kb_dir}")
        
        result = self.enhancer.enhance_and_generate_latex(
            knowledge_base_name=knowledge_base_name,
            recommendations=recommendations,
            latex_template=latex_template,
            output_dir=output_dir,
            user_feedback=user_feedback,
            kb_dir=kb_dir
        )
        
        return result


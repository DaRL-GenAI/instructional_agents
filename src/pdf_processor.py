"""
PDF Slide Deck Processor
处理PDF格式的幻灯片文件，支持按章节/需求提取内容
"""

import os
import json
import re
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from datetime import datetime

try:
    import PyPDF2
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False
    print("Warning: PyPDF2 not available")

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    print("Warning: pdfplumber not available")


class PDFSlideProcessor:
    """处理PDF幻灯片文件，支持按需提取"""
    
    def __init__(self, output_dir: str = "knowledge_base"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
    
    def store_pdf_files(self, files: List[Path], storage_id: str) -> Dict[str, Any]:
        """
        存储PDF文件（不立即处理）
        
        Args:
            files: PDF文件列表
            storage_id: 存储标识符
            
        Returns:
            存储信息
        """
        storage_dir = self.output_dir / "temp_storage" / storage_id
        storage_dir.mkdir(parents=True, exist_ok=True)
        
        stored_files = []
        for pdf_file in files:
            if pdf_file.suffix.lower() == '.pdf':
                dest_path = storage_dir / pdf_file.name
                # 复制文件到存储目录
                shutil.copy2(pdf_file, dest_path)
                stored_files.append({
                    "filename": pdf_file.name,
                    "stored_path": str(dest_path),
                    "size": os.path.getsize(dest_path)
                })
        
        metadata = {
            "storage_id": storage_id,
            "stored_at": datetime.now().isoformat(),
            "total_files": len(stored_files),
            "files": stored_files
        }
        
        # 保存元数据
        metadata_file = storage_dir / "metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        return metadata
    
    def extract_by_requirement(
        self, 
        storage_id: str,
        user_requirements: str,
        target_chapters: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        根据用户需求提取相关PDF内容
        
        Args:
            storage_id: 存储标识符
            user_requirements: 用户需求描述
            target_chapters: 目标章节列表（如["Chapter 1", "第3章"]），如果为None则分析全部
            
        Returns:
            提取的内容数据
        """
        storage_dir = self.output_dir / "temp_storage" / storage_id
        
        if not storage_dir.exists():
            raise ValueError(f"Storage {storage_id} not found")
        
        # 加载元数据
        metadata_file = storage_dir / "metadata.json"
        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        # 获取所有PDF文件
        pdf_files = [Path(f["stored_path"]) for f in metadata["files"]]
        
        # 如果指定了章节，先识别相关文件
        if target_chapters:
            relevant_files = self._identify_relevant_files(pdf_files, target_chapters)
        else:
            # 如果用户要求优化全部课程，分析所有章节
            relevant_files = pdf_files
        
        # 提取相关内容
        extracted_slides = []
        for pdf_file in relevant_files:
            try:
                slide_data = self.process_single_pdf(
                    str(pdf_file),
                    user_requirements=user_requirements,
                    target_chapters=target_chapters
                )
                extracted_slides.append(slide_data)
            except Exception as e:
                print(f"Error processing {pdf_file.name}: {e}")
                extracted_slides.append({
                    "filename": pdf_file.name,
                    "error": str(e)
                })
        
        return {
            "storage_id": storage_id,
            "extracted_at": datetime.now().isoformat(),
            "user_requirements": user_requirements,
            "target_chapters": target_chapters,
            "total_extracted_files": len([s for s in extracted_slides if "error" not in s]),
            "slides": extracted_slides
        }
    
    def _identify_relevant_files(
        self, 
        pdf_files: List[Path], 
        target_chapters: List[str]
    ) -> List[Path]:
        """
        识别包含目标章节的PDF文件
        
        Args:
            pdf_files: PDF文件列表
            target_chapters: 目标章节列表
            
        Returns:
            相关的PDF文件列表
        """
        relevant_files = []
        
        for pdf_file in pdf_files:
            # 快速扫描PDF标题和第一页，看是否包含章节信息
            try:
                # 检查文件名
                filename_match = any(
                    self._match_chapter_in_text(pdf_file.stem, chapter) 
                    for chapter in target_chapters
                )
                
                if filename_match:
                    relevant_files.append(pdf_file)
                    continue
                
                # 检查前几页的标题
                if PDFPLUMBER_AVAILABLE:
                    with pdfplumber.open(pdf_file) as pdf:
                        for page_num in range(min(3, len(pdf.pages))):
                            page = pdf.pages[page_num]
                            text = page.extract_text() or ""
                            
                            # 检查是否包含章节关键词
                            if any(
                                self._match_chapter_in_text(text, chapter) 
                                for chapter in target_chapters
                            ):
                                relevant_files.append(pdf_file)
                                break
            except Exception as e:
                print(f"Warning: Could not scan {pdf_file.name}: {e}")
                # 如果无法扫描，默认包含该文件
                relevant_files.append(pdf_file)
        
        return relevant_files
    
    def _match_chapter_in_text(self, text: str, chapter_pattern: str) -> bool:
        """检查文本是否匹配章节模式"""
        # 支持的章节格式：
        # - "Chapter 1", "Chapter1", "Ch1"
        # - "第1章", "第 1 章"
        # - "Chapter One", "第一章"
        # - "1" (简单的数字)
        
        text_lower = text.lower()
        pattern_lower = chapter_pattern.lower()
        
        # 提取数字
        chapter_num_match = re.search(r'\d+', pattern_lower)
        if chapter_num_match:
            chapter_num = chapter_num_match.group()
            
            # 检查各种章节格式
            patterns = [
                rf'chapter\s*{chapter_num}\b',
                rf'ch\s*{chapter_num}\b',
                rf'第\s*{chapter_num}\s*章',
                rf'\b{chapter_num}\s*章',
            ]
            
            for pattern in patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    return True
        
        # 直接文本匹配
        if pattern_lower in text_lower:
            return True
        
        return False
    
    def _extract_chapter_from_filename(self, filename: str) -> Optional[str]:
        """从文件名提取章节信息"""
        # 匹配常见的章节格式
        patterns = [
            r'chapter\s*(\d+)',
            r'ch\s*(\d+)',
            r'第\s*(\d+)\s*章',
            r'(\d+)\s*章',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                return f"Chapter {match.group(1)}"
        
        return None
    
    def process_single_pdf(
        self, 
        pdf_path: str,
        user_requirements: Optional[str] = None,
        target_chapters: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        处理单个PDF文件，可以根据需求过滤内容
        
        Args:
            pdf_path: PDF文件路径
            user_requirements: 用户需求（用于内容过滤）
            target_chapters: 目标章节列表
            
        Returns:
            提取的幻灯片数据
        """
        pdf_file = Path(pdf_path)
        pdf_name = pdf_file.stem
        
        # 提取文本内容
        text_content = self.extract_text(pdf_path)
        
        # 识别幻灯片结构
        slide_structure = self.identify_slide_structure(pdf_path, text_content)
        
        # 如果指定了章节，过滤相关幻灯片
        if target_chapters:
            slide_structure = self._filter_slides_by_chapters(
                slide_structure, 
                target_chapters
            )
        
        # 如果提供了用户需求，进一步过滤相关内容
        if user_requirements:
            slide_structure = self._filter_slides_by_requirements(
                slide_structure,
                user_requirements
            )
        
        # 提取元数据
        metadata = self.extract_metadata(pdf_path)
        
        return {
            "filename": pdf_file.name,
            "file_path": str(pdf_file),
            "pdf_name": pdf_name,
            "metadata": metadata,
            "total_pages": metadata.get("num_pages", 0),
            "extracted_slides_count": len(slide_structure),
            "text_content": text_content,
            "slide_structure": slide_structure,
            "processed_at": datetime.now().isoformat()
        }
    
    def _filter_slides_by_chapters(
        self,
        slide_structure: List[Dict[str, Any]],
        target_chapters: List[str]
    ) -> List[Dict[str, Any]]:
        """根据章节过滤幻灯片"""
        filtered = []
        
        for slide in slide_structure:
            slide_text = f"{slide.get('title', '')} {slide.get('content', '')}"
            
            # 检查是否匹配任何目标章节
            if any(
                self._match_chapter_in_text(slide_text, chapter)
                for chapter in target_chapters
            ):
                filtered.append(slide)
        
        return filtered
    
    def _filter_slides_by_requirements(
        self,
        slide_structure: List[Dict[str, Any]],
        user_requirements: str
    ) -> List[Dict[str, Any]]:
        """根据用户需求过滤相关内容（可以扩展使用embedding相似度）"""
        # 这里可以使用简单的关键词匹配，或者使用embedding相似度
        # 为了简单，先使用关键词匹配
        requirements_lower = user_requirements.lower()
        keywords = requirements_lower.split()
        
        filtered = []
        for slide in slide_structure:
            slide_text = f"{slide.get('title', '')} {slide.get('content', '')}".lower()
            
            # 检查是否包含关键词
            if any(keyword in slide_text for keyword in keywords if len(keyword) > 2):
                filtered.append(slide)
        
        return filtered if filtered else slide_structure  # 如果没有匹配，返回全部
    
    def extract_text(self, pdf_path: str) -> Dict[str, Any]:
        """提取PDF中的文本内容"""
        text_by_page = []
        
        if PDFPLUMBER_AVAILABLE:
            try:
                # 使用pdfplumber提取文本（更准确）
                with pdfplumber.open(pdf_path) as pdf:
                    for page_num, page in enumerate(pdf.pages, 1):
                        text = page.extract_text()
                        if text:
                            text_by_page.append({
                                "page_number": page_num,
                                "text": text.strip(),
                                "char_count": len(text)
                            })
            except Exception as e:
                print(f"Warning: pdfplumber failed: {e}")
        
        if not text_by_page and PYPDF2_AVAILABLE:
            # 备用方案：使用PyPDF2
            try:
                with open(pdf_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    for page_num, page in enumerate(pdf_reader.pages, 1):
                        text = page.extract_text()
                        if text:
                            text_by_page.append({
                                "page_number": page_num,
                                "text": text.strip(),
                                "char_count": len(text)
                            })
            except Exception as e:
                print(f"Warning: PyPDF2 failed: {e}")
        
        if not text_by_page:
            raise ValueError(f"Could not extract text from {pdf_path}. Please install pdfplumber or PyPDF2.")
        
        full_text = "\n\n".join([page["text"] for page in text_by_page])
        
        return {
            "full_text": full_text,
            "pages": text_by_page,
            "total_characters": len(full_text)
        }
    
    def identify_slide_structure(self, pdf_path: str, text_content: Dict) -> List[Dict[str, Any]]:
        """识别幻灯片结构（标题、内容等）"""
        slides = []
        
        # 简单策略：每页作为一个幻灯片
        for page in text_content["pages"]:
            text = page["text"]
            
            # 尝试识别标题（通常是第一行或最大字体）
            lines = text.split("\n")
            title = lines[0].strip() if lines else "Untitled Slide"
            
            # 提取内容
            content = "\n".join(lines[1:]).strip() if len(lines) > 1 else text
            
            slides.append({
                "slide_number": page["page_number"],
                "title": title[:100],  # 限制标题长度
                "content": content,
                "bullet_points": self.extract_bullet_points(content)
            })
        
        return slides
    
    def extract_bullet_points(self, text: str) -> List[str]:
        """提取文本中的要点"""
        lines = text.split("\n")
        bullet_points = []
        
        for line in lines:
            line = line.strip()
            # 识别常见的要点标记
            if line and (line.startswith("•") or 
                        line.startswith("-") or 
                        line.startswith("*") or
                        any(line.startswith(f"{i}.") for i in range(1, 10))):
                bullet_points.append(line)
        
        return bullet_points
    
    def extract_metadata(self, pdf_path: str) -> Dict[str, Any]:
        """提取PDF元数据"""
        metadata = {
            "num_pages": 0,
            "file_size": os.path.getsize(pdf_path),
            "creation_date": None,
            "modification_date": None
        }
        
        if PYPDF2_AVAILABLE:
            try:
                with open(pdf_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    metadata["num_pages"] = len(pdf_reader.pages)
                    
                    if pdf_reader.metadata:
                        metadata.update({
                            "title": pdf_reader.metadata.get("/Title"),
                            "author": pdf_reader.metadata.get("/Author"),
                            "subject": pdf_reader.metadata.get("/Subject"),
                            "creation_date": str(pdf_reader.metadata.get("/CreationDate")),
                            "modification_date": str(pdf_reader.metadata.get("/ModDate"))
                        })
            except Exception as e:
                print(f"Warning: Could not extract metadata: {e}")
        
        return metadata


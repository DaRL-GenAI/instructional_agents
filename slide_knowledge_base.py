"""
Slide Knowledge Base
使用向量数据库存储PDF幻灯片内容，支持语义搜索
"""

import os
import json
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import numpy as np

# 可以选择使用chromadb或简单的embedding存储
try:
    import chromadb
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    print("Warning: chromadb not available, using simple storage")

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("Warning: OpenAI not available")


class SlideKnowledgeBase:
    """幻灯片知识库，存储和检索PDF内容"""
    
    def __init__(self, knowledge_base_name: str, kb_dir: str = "knowledge_base"):
        self.kb_name = knowledge_base_name
        self.kb_dir = Path(kb_dir) / knowledge_base_name
        self.kb_dir.mkdir(parents=True, exist_ok=True)
        
        if OPENAI_AVAILABLE:
            self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            self.embedding_model = "text-embedding-3-small"  # 或 "text-embedding-ada-002"
        else:
            self.client = None
            self.embedding_model = None
        
        # 初始化向量数据库
        if CHROMADB_AVAILABLE:
            self._init_chromadb()
        else:
            self._init_simple_storage()
    
    def _init_chromadb(self):
        """初始化ChromaDB向量数据库"""
        chroma_dir = self.kb_dir / "chroma_db"
        self.chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
        self.collection = self.chroma_client.get_or_create_collection(
            name=self.kb_name,
            metadata={"description": "Slide deck knowledge base"}
        )
        self.use_chromadb = True
    
    def _init_simple_storage(self):
        """使用简单的文件存储"""
        self.embeddings_file = self.kb_dir / "embeddings.pkl"
        self.data_file = self.kb_dir / "chunks.json"
        self.embeddings = {}
        self.chunks = []
        self.use_chromadb = False
        
        # 加载已有数据
        if self.data_file.exists():
            with open(self.data_file, 'r', encoding='utf-8') as f:
                self.chunks = json.load(f)
        if self.embeddings_file.exists():
            with open(self.embeddings_file, 'rb') as f:
                self.embeddings = pickle.load(f)
    
    def create_from_extracted_data(
        self, 
        extracted_data: Dict[str, Any],
        chapter_filter: Optional[str] = None
    ):
        """
        从按需提取的数据创建知识库
        
        Args:
            extracted_data: PDF处理器返回的提取数据
            chapter_filter: 章节过滤器（用于标记）
        """
        print(f"Creating knowledge base from {extracted_data['total_extracted_files']} extracted files...")
        
        chunks = []
        for slide_deck in extracted_data["slides"]:
            if "error" in slide_deck or not slide_deck.get("slide_structure"):
                continue
            
            # 只处理提取的幻灯片
            for slide in slide_deck["slide_structure"]:
                chunk = {
                    "id": f"{slide_deck['pdf_name']}_slide_{slide['slide_number']}",
                    "pdf_name": slide_deck["pdf_name"],
                    "filename": slide_deck["filename"],
                    "slide_number": slide["slide_number"],
                    "title": slide["title"],
                    "content": slide["content"],
                    "bullet_points": slide.get("bullet_points", []),
                    "chapter_filter": chapter_filter,
                    "user_requirements": extracted_data.get("user_requirements", ""),
                    "metadata": {
                        "file_path": slide_deck.get("file_path"),
                        "processed_at": slide_deck.get("processed_at"),
                        "extracted_at": extracted_data.get("extracted_at")
                    }
                }
                chunks.append(chunk)
        
        if not chunks:
            print("Warning: No chunks to process")
            return {
                "knowledge_base_name": self.kb_name,
                "created_at": datetime.now().isoformat(),
                "total_chunks": 0,
                "message": "No content extracted"
            }
        
        # 生成embeddings并存储
        print(f"Generating embeddings for {len(chunks)} chunks...")
        for i, chunk in enumerate(chunks):
            if (i + 1) % 10 == 0:
                print(f"  Progress: {i + 1}/{len(chunks)}")
            
            # 生成embedding
            text_to_embed = f"{chunk['title']}\n{chunk['content']}"
            embedding = self._generate_embedding(text_to_embed)
            
            if embedding is None:
                continue
            
            # 存储到向量数据库
            if self.use_chromadb:
                try:
                    self.collection.add(
                        ids=[chunk["id"]],
                        embeddings=[embedding],
                        documents=[text_to_embed],
                        metadatas=[chunk["metadata"]]
                    )
                except Exception as e:
                    print(f"Warning: Failed to add to chromadb: {e}")
            else:
                self.embeddings[chunk["id"]] = embedding
                self.chunks.append(chunk)
        
        # 保存数据
        if not self.use_chromadb:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.chunks, f, indent=2, ensure_ascii=False)
            with open(self.embeddings_file, 'wb') as f:
                pickle.dump(self.embeddings, f)
        
        # 无论使用哪种存储方式，都保存chunks.json以便后续使用
        chunks_json_file = self.kb_dir / "chunks.json"
        with open(chunks_json_file, 'w', encoding='utf-8') as f:
            json.dump(chunks, f, indent=2, ensure_ascii=False)
        
        # 保存元数据
        metadata = {
            "knowledge_base_name": self.kb_name,
            "created_at": datetime.now().isoformat(),
            "total_chunks": len(chunks),
            "source_storage_id": extracted_data.get("storage_id"),
            "user_requirements": extracted_data.get("user_requirements"),
            "target_chapters": extracted_data.get("target_chapters"),
            "chapter_filter": chapter_filter
        }
        
        metadata_file = self.kb_dir / "metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Knowledge base created with {len(chunks)} chunks")
        return metadata
    
    def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """生成文本的embedding"""
        if not self.client or not self.embedding_model:
            # 如果没有OpenAI客户端，返回None或使用简单的方法
            print("Warning: OpenAI client not available, skipping embedding generation")
            return None
        
        try:
            response = self.client.embeddings.create(
                model=self.embedding_model,
                input=text[:8000]  # 限制长度
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"Error generating embedding: {e}")
            return None
    
    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        语义搜索相关内容
        
        Args:
            query: 搜索查询
            top_k: 返回前k个结果
            
        Returns:
            相关内容的列表
        """
        if not self.client:
            # 如果没有embedding能力，返回空列表或使用关键词搜索
            return self._keyword_search(query, top_k)
        
        # 生成查询的embedding
        query_embedding = self._generate_embedding(query)
        
        if query_embedding is None:
            return self._keyword_search(query, top_k)
        
        if self.use_chromadb:
            try:
                results = self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=top_k
                )
                
                # 格式化结果
                formatted_results = []
                if results.get("ids") and len(results["ids"]) > 0:
                    for i in range(len(results["ids"][0])):
                        formatted_results.append({
                            "id": results["ids"][0][i],
                            "content": results["documents"][0][i] if results.get("documents") else "",
                            "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                            "distance": results["distances"][0][i] if results.get("distances") else None
                        })
                return formatted_results
            except Exception as e:
                print(f"Error searching chromadb: {e}")
                return self._keyword_search(query, top_k)
        else:
            # 简单的余弦相似度搜索
            similarities = []
            for chunk_id, embedding in self.embeddings.items():
                similarity = self._cosine_similarity(query_embedding, embedding)
                similarities.append((similarity, chunk_id))
            
            # 排序并返回top_k
            similarities.sort(reverse=True, key=lambda x: x[0])
            results = []
            
            chunk_dict = {chunk["id"]: chunk for chunk in self.chunks}
            for similarity, chunk_id in similarities[:top_k]:
                chunk = chunk_dict.get(chunk_id, {})
                results.append({
                    "id": chunk_id,
                    "content": f"{chunk.get('title', '')}\n{chunk.get('content', '')}",
                    "metadata": chunk.get("metadata", {}),
                    "similarity": float(similarity)
                })
            
            return results
    
    def _keyword_search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """使用关键词搜索（备用方案）"""
        query_lower = query.lower()
        keywords = [w for w in query_lower.split() if len(w) > 2]
        
        results = []
        for chunk in self.chunks[:100]:  # 限制搜索范围
            text = f"{chunk.get('title', '')} {chunk.get('content', '')}".lower()
            score = sum(1 for keyword in keywords if keyword in text)
            
            if score > 0:
                results.append({
                    "id": chunk.get("id", ""),
                    "content": f"{chunk.get('title', '')}\n{chunk.get('content', '')}",
                    "metadata": chunk.get("metadata", {}),
                    "similarity": score / len(keywords)
                })
        
        results.sort(reverse=True, key=lambda x: x["similarity"])
        return results[:top_k]
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        try:
            vec1 = np.array(vec1)
            vec2 = np.array(vec2)
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            return dot_product / (norm1 * norm2)
        except Exception as e:
            print(f"Error calculating cosine similarity: {e}")
            return 0.0
    
    def get_all_content_summary(self) -> Dict[str, Any]:
        """获取知识库内容的摘要"""
        if self.use_chromadb:
            try:
                count = self.collection.count()
                return {
                    "total_chunks": count,
                    "type": "chromadb"
                }
            except:
                return {
                    "total_chunks": 0,
                    "type": "chromadb",
                    "error": "Could not access collection"
                }
        else:
            return {
                "total_chunks": len(self.chunks),
                "type": "simple_storage",
                "chunks": self.chunks[:10]  # 返回前10个作为示例
            }


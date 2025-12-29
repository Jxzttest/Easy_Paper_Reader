import os
import uuid
import asyncio
import shutil
import re
import time
import hashlib
import fitz  # PyMuPDF
from typing import Dict, Any, List, Optional
from tqdm.asyncio import tqdm

# 假设你的 OCR 模型路径
from server.model.ocr_model.paddle_ocr import PaddleOCRPipeline 
from server.utils.logger import logger
from server.model.embedding_model.embedding import EmbeddingManager
from server.db.db_factory import DBFactory

class PDFParser:
    """PDF文档解析器：OCR -> Chunk -> Embedding -> DB"""
    _temp_files = []
    
    def __init__(
        self, 
        file_path: str,
        uploader_uuid: str, # 新增：需要知道是谁上传的
        **kwargs
    ):
        self.file_path = file_path
        self.uploader_uuid = uploader_uuid
        self.file_id = self._generate_file_id()
        self.file_uuid = uuid.uuid4().hex # 用于数据库的主键 UUID
        self.file_size = self._get_file_size()
        self.checksum = self._calculate_checksum()
        
        # 初始化 OCR 模型 (假设它支持异步或者我们用线程池跑)
        self.ocr_model = PaddleOCRPipeline()
        self.embedding_model = EmbeddingManager()
        
        # 设置输出目录
        self.output_folder = os.path.join(os.path.dirname(file_path), f'temp_{self.file_id}')
        self._temp_files = []

    # ... (保持原有的 register_temp_file, _calculate_checksum, _generate_file_id, _get_file_size) ...
    def register_temp_file(self, file_path: str):
        dir_path = os.path.dirname(file_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
        self._temp_files.append(file_path)

    def _calculate_checksum(self, chunk_size: int = 8192) -> str:
        hash_sha256 = hashlib.sha256()
        try:
            with open(self.file_path, "rb") as f:
                while chunk := f.read(chunk_size):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except OSError as e:
            logger.error(f"计算文件校验和失败: {str(e)}")
            return ""

    def _generate_file_id(self) -> str:
        file_name = os.path.basename(self.file_path)
        # 移除非法字符
        clean_name = re.sub(r'[\\/*?:"<>|]', "", file_name)
        return f"{int(time.time())}_{clean_name}"

    def _get_file_size(self) -> int:
        try:
            return os.path.getsize(self.file_path)
        except OSError:
            return 0

    def extract_metadata(self) -> Dict[str, Any]:
        """提取PDF元数据"""
        metadata = {"file_name": os.path.basename(self.file_path)}
        try:
            with fitz.open(self.file_path) as doc:
                meta = doc.metadata
                metadata.update({
                    "title": meta.get("title", "") or os.path.basename(self.file_path),
                    "author": meta.get("author", ""),
                    "page_count": len(doc),
                    "is_encrypted": doc.is_encrypted
                })
        except Exception as e:
            logger.error(f"提取PDF元数据失败: {str(e)}")
            metadata["title"] = os.path.basename(self.file_path)
        return metadata

    async def preprocess_to_images(self, dpi=300) -> List[str]:
        """
        第一步：将PDF转换为图片
        """
        if os.path.exists(self.output_folder) and os.listdir(self.output_folder):
            # 如果已有缓存，直接返回
            return sorted([
                os.path.join(self.output_folder, f) 
                for f in os.listdir(self.output_folder)
                if f.endswith('.png')
            ], key=lambda x: int(re.search(r'page_(\d+).png', x).group(1)))
        
        os.makedirs(self.output_folder, exist_ok=True)
        image_paths = []
        
        logger.info(f"开始PDF转图片: {self.file_path}")
        try:
            # 这是一个 CPU 密集型操作，建议在 executor 中运行，防止阻塞 asyncio 循环
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._convert_pdf_to_images_sync, dpi, image_paths)
        except Exception as e:
            logger.error(f"PDF转图片失败: {str(e)}")
            raise
        
        return image_paths

    def _convert_pdf_to_images_sync(self, dpi, image_paths):
        """同步的 PDF 转图片逻辑 (运行在线程池中)"""
        with fitz.open(self.file_path) as pdf_document:
            for page_num in range(len(pdf_document)):
                page = pdf_document.load_page(page_num)
                pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72))
                output_path = os.path.join(self.output_folder, f"page_{page_num + 1}.png")
                pix.save(output_path)
                image_paths.append(output_path)
                self.register_temp_file(output_path)

    async def ocr_process_images(self, image_paths: List[str]) -> List[Dict]:
        """
        第二步：对图片列表进行 OCR 识别
        返回结构: [{"page_num": 1, "text": "...", "raw_result": ...}, ...]
        """
        results = []
        logger.info(f"开始OCR处理，共 {len(image_paths)} 页")
        

        for idx, img_path in enumerate(image_paths):
            page_num = idx + 1
            try:
               

                loop = asyncio.get_running_loop()
                ocr_data = await loop.run_in_executor(None, self.ocr_model.invoke_single_img, img_path)
                
                # 这里做一个简单的清洗
                text_content = str(ocr_data) 
                
                if text_content.strip():
                    results.append({
                        "page_num": page_num,
                        "text": text_content
                    })
                logger.debug(f"Page {page_num} OCR 完成")
                
            except Exception as e:
                logger.error(f"OCR Page {page_num} 失败: {e}")
        
        return results

    def text_splitter(self, text: str, chunk_size=500, overlap=50) -> List[str]:
        """
        第三步：简单的文本切片
        生产环境建议使用 LangChain 的 RecursiveCharacterTextSplitter
        """
        if not text:
            return []
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            start += (chunk_size - overlap)
        return chunks

    async def parse_and_save(self):
        """
        主流程：解析并保存到数据库
        """
        logger.info(f"开始全流程解析文件: {self.file_path}")
        
        # 1. 获取数据库服务
        pg_store = DBFactory.get_pg_service()
        es_store = DBFactory.get_es_paper_service()
        
        # 2. 提取元数据并存入 PostgreSQL (标记为处理中)
        metadata = self.extract_metadata()
        paper_title = metadata.get('title', 'Untitled')
        
        try:
            # 存入 PG
            await pg_store.add_paper_metadata(
                paper_uuid=self.file_uuid,
                title=paper_title,
                uploader_uuid=self.uploader_uuid,
                file_path=self.file_path
            )
            logger.info("Metadata存入PG成功")

            # 3. PDF 转图片
            image_paths = await self.preprocess_to_images()
            
            # 4. OCR 识别
            ocr_results = await self.ocr_process_images(image_paths)
            
            # 5. 切片、向量化并存入 ES
            chunk_tasks = []
            
            logger.info("开始生成 Embedding 并存入 ES...")
            for page_data in ocr_results:
                page_text = page_data['text']
                page_num = page_data['page_num']
                
                # 切片
                chunks = self.text_splitter(page_text)
                
                for i, chunk in enumerate(chunks):
                    # 为每个 chunk 生成向量
                    vector = await self.embedding_model.get_embedding(chunk)
                    chunk_id = f"{self.file_uuid}_p{page_num}_c{i}"
                    
                    # 存入 ES
                    # 注意：metadata 可以包含更多信息
                    chunk_meta = {
                        "source": metadata['file_name'],
                        "author": metadata.get('author'),
                        "year": metadata.get('creationDate')
                    }
                    
                    # 构造 ES 任务
                    task = es_store.add_paper_chunk(
                        paper_id=self.file_uuid,
                        chunk_id=chunk_id,
                        content=chunk,
                        vector=vector,
                        title=paper_title,
                        page_num=page_num,
                        metadata=chunk_meta
                    )
                    chunk_tasks.append(task)
            
            # 并发执行 ES 写入 (控制并发量可以使用 asyncio.Semaphore)
            if chunk_tasks:
                await asyncio.gather(*chunk_tasks)
            
            # 6. 更新 PG 状态 (标记为已完成 - 如果你在 models.py 里加了 status 字段)
            await pg_store.mark_paper_processed(self.file_uuid)
            
            logger.info(f"文件处理完成: {self.file_uuid}")
            return {"status": "success", "file_uuid": self.file_uuid}

        except Exception as e:
            logger.error(f"文件处理流程发生严重错误: {e}")
            # 可以在这里更新 PG 状态为 FAILED
            raise
        finally:
            self.cleanup()

    def cleanup(self):
        """清理临时文件"""
        try:
            if os.path.exists(self.output_folder):
                shutil.rmtree(self.output_folder)
                logger.info(f"临时目录已清理: {self.output_folder}")
        except Exception as e:
            logger.warning(f"清理临时目录失败: {str(e)}")
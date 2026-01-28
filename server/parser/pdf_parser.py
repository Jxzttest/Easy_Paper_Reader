import os
import uuid
import asyncio
import shutil
import re
import time
import hashlib
import fitz  # PyMuPDF
from typing import Dict, Any, List
# 引入上面修改后的 OCR 类
from fastapi import HTTPException
from server.model.ocr_model.paddle_ocr import PaddleOCRPipeline 
from server.utils.logger import logger
from server.model.embedding_model.embedding import EmbeddingManager
from server.db.db_factory import DBFactory

class PDFParser:
    def __init__(self, file_path: str, uploader_uuid: str, **kwargs):
        self.file_path = file_path
        self.uploader_uuid = uploader_uuid
        self.file_id = self._generate_file_id()
        self.file_uuid = uuid.uuid4().hex
        
        # 实例化新的 OCR Pipeline
        self.ocr_model = PaddleOCRPipeline(use_gpu=False) # 如果有GPU改为True
        self.embedding_model = EmbeddingManager()
        
        # 临时目录
        self.temp_dir = os.path.join(os.path.dirname(file_path), f'temp_{self.file_id}')
        # 图片裁剪保存目录 (建议后续改为对象存储)
        self.assets_dir = os.path.join(self.temp_dir, "assets")
        os.makedirs(self.assets_dir, exist_ok=True)

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
        # 同你之前的代码，将 PDF 转为 PNG 图片
        os.makedirs(self.temp_dir, exist_ok=True)
        image_paths = []
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._convert_pdf_to_images_sync, dpi, image_paths)
        return image_paths

    def _convert_pdf_to_images_sync(self, dpi, image_paths):
        try:
            with fitz.open(self.file_path) as pdf_document:
                for page_num in range(len(pdf_document)):
                    page = pdf_document.load_page(page_num)
                    pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72))
                    output_path = os.path.join(self.temp_dir, f"page_{page_num + 1}.png")
                    pix.save(output_path)
                    image_paths.append(output_path)
        except Exception as e:
            logger.error(f"PDF转图片出错: {e}")
    
    async def parse_and_save(self):
        """
        主流程：解析 -> 结构化提取 -> 向量化 -> 入库
        """
        logger.info(f"开始解析文件: {self.file_path}")
        pg_store = DBFactory.get_pg_service()
        es_store = DBFactory.get_es_paper_service()
        
        metadata = self.extract_metadata()
        paper_title = metadata.get('title', 'Untitled')

        try:
            # 1. 存入 PG 元数据
            await pg_store.add_paper_metadata(
                paper_uuid=self.file_uuid,
                title=paper_title,
                uploader_uuid=self.uploader_uuid,
                file_path=self.file_path
            )

            # 2. PDF 转图片
            image_paths = await self.preprocess_to_images()
            
            # 3. 结构化 OCR 处理
            chunk_tasks = []
            
            for page_idx, img_path in enumerate(image_paths):
                page_num = page_idx + 1
                
                # 调用新的 PPStructure 逻辑，传入 assets_dir 用于存图
                # 结果是 List[Dict] (type, content, image_path, bbox)
                page_structure = await self.ocr_model.invoke_single_img(img_path, self.assets_dir)
                
                for i, item in enumerate(page_structure):
                    parsing_res = item['parsing_res_list']
                    for res in parsing_res:
                        chunk_id = f"{self.file_uuid}_p{page_num}_s{i}"
                        chunk_text = res['block_content']
                        c_type = res['block_label'] # text, table, figure...
                        if c_type not in ['text', 'formula', 'figure', 'table', 'image', 'figure_title']:
                            continue
                        # 表格 、 图片会做裁剪，保存路径在 res['image_path']
                        img_path_saved = res.get('image_path', '')
                        vector = await self.embedding_model.get_embedding(chunk_text)
                        
                        # 构造 ES 存入数据
                        task = es_store.add_paper_chunk(
                            paper_id=self.file_uuid,
                            chunk_id=chunk_id,
                            content=res['block_content'],
                            content_type=c_type,
                            image_path= img_path_saved,
                            vector=vector,
                            page_num=page_num,
                            metadata={
                                "original_bbox": item['block_bbox']
                            }
                        )
                        chunk_tasks.append(task)
            
            # 并发入库
            if chunk_tasks:
                await asyncio.gather(*chunk_tasks)

            # 更新 PG 状态
            await pg_store.mark_paper_processed(self.file_uuid)
            
            # 这里的 assets 文件夹里的图片不能删，因为 Agent 回答问题时可能需要发给用户看
            # 建议将 assets 移动到一个永久存储目录，或者上传到对象存储后删除本地
            self.finalize_assets() 

            return {"status": "success", "file_uuid": self.file_uuid}

        except Exception as e:
            logger.error(f"处理失败: {e}", exc_info=True)
            raise HTTPException(status_code=400, detail=str(e))
        finally:
            # 只清理 page_x.png 这种临时中间图，保留裁剪下来的 meaningful 图片
            self.cleanup_temp_images()
    
    def finalize_assets(self):
        """
        处理裁剪出来的图片：
        如果是本地部署，可以把 assets 里的图片移动到 web 静态资源目录。
        如果是云部署，这里应该遍历 assets 里的文件上传到 S3，然后更新 ES 里的 image_path 为 URL。
        这里简单起见，假设不做移动，assets 就在 output_folder 下
        """
        pass
    
    def cleanup_temp_images(self):
        """只删除 PDF 转出来的整页 PNG，保留 assets (包含裁剪图)"""
        try:
            for f in os.listdir(self.temp_dir):
                if f.endswith(".png") and f.startswith("page_"):
                    os.remove(os.path.join(self.temp_dir, f))
        except Exception as e:
            logger.warning(f"清理临时图片失败: {e}")

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
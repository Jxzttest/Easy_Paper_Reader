import os
import uuid
import numpy as np
import fitz
import asyncio
import shutil
import re
import time
import numpy as np
import hashlib
from tqdm import tqdm
from typing import Dict, Any, Union, List, Optional
from server.model.ocr_model.paddle_ocr import PaddleOCRPipeline
from server.utils.logger import logger


class PDFParser:
    """PDF文档解析器"""
    _temp_files = []
    
    def __init__(
        self, 
        file_path: str,
        **kwargs
    ):
        self.file_path = file_path
        self.file_id = self._generate_file_id()
        self.file_size = self._get_file_size()
        self.checksum = self._calculate_checksum()
        
        self.pdf_model: PaddleOCRPipeline  = PaddleOCRPipeline()
        # 设置输出目录
        self.output_folder = os.path.join(os.path.dirname(file_path), f'images_{self.file_id}')
    
    def register_temp_file(self, file_path: str):
        """注册临时文件（自动创建目录）"""
        dir_path = os.path.dirname(file_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
        self._temp_files.append(file_path)

    async def preprocess(self, dpi=300) -> str:
        """文档预处理（如格式转换）"""
        """分页提取PDF页面为图像，返回图像路径列表"""
        # 检查是否已提取
        if os.path.exists(self.output_folder) and os.listdir(self.output_folder):
            return sorted([
                os.path.join(self.output_folder, f) 
                for f in os.listdir(self.output_folder)
                if f.endswith('.png')
            ], key=lambda x: int(re.search(r'page_(\d+).png', x).group(1)))
        
        os.makedirs(self.output_folder, exist_ok=True)
        image_paths = []
        
        try:
            with fitz.open(self.file_path) as pdf_document:
                for page_num in range(len(pdf_document)):
                    page = pdf_document.load_page(page_num)
                    
                    # 设置缩放比例
                    zoom = dpi / 72
                    matrix = fitz.Matrix(zoom, zoom)
                    
                    # 渲染为图像
                    pix = page.get_pixmap(matrix=matrix)
                    
                    # 保存图像
                    output_path = os.path.join(self.output_folder, f"page_{page_num + 1}.png")
                    pix.save(output_path)
                    image_paths.append(output_path)
                    logger.debug(f"保存PDF页面图像: {output_path}")
                    
                    # 注册临时文件
                    self.register_temp_file(output_path)
        except Exception as e:
            logger.error(f"提取PDF页面失败: {str(e)}")
            raise
        return image_paths
    
    def _calculate_checksum(self, chunk_size: int = 8192) -> str:
        """计算文件校验和（优化大文件处理）"""
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
        """生成唯一文件ID（添加处理模式信息）"""
        file_name = os.path.basename(self.file_path)
        return f"{time.time_ns()}_{uuid.uuid4().hex[:8]}{file_name}"
    
    def _get_file_size(self) -> int:
        """获取文件大小（带错误处理）"""
        try:
            return os.path.getsize(self.file_path)
        except OSError as e:
            logger.error(f"获取文件大小失败: {str(e)}")
            return -1

    def extract_metadata(self) -> Dict[str, Any]:
        """提取PDF元数据"""
        metadata = {}
        try:
            with fitz.open(self.file_path) as doc:
                # 提取标准元数据
                metadata.update(doc.metadata)
                
                # 提取额外信息
                metadata['page_count'] = len(doc)
                metadata['is_encrypted'] = doc.is_encrypted
                
                # 尝试提取目录
                toc = doc.get_toc()
                if toc:
                    metadata['toc'] = toc
        except Exception as e:
            logger.error(f"提取PDF元数据失败: {str(e)}")
        return metadata
    
    
    async def extract_content(self):
        """异步提取文件内容"""
        logger.info(f"处理PDF: {self.file_path}")
        try:
            # 处理所有页面
            all_content = await self.pdf_model.invoke_file(self.file_path)
            
            return all_content
        except Exception as e:
            logger.error(f"处理PDF内容失败: {str(e)}")
            return []
    

    async def parser(self):
        file_metadata = self.extract_metadata()
        img_path = self.preprocess()
        file_content_data = self.extract_content(img_path)



    def cleanup(self):
        """清理PDF特定资源"""
        # 先调用父类清理临时文件
        super().cleanup()
        
        # 清理输出目录
        try:
            if os.path.exists(self.output_folder):
                shutil.rmtree(self.output_folder)
                logger.debug(f"清理PDF输出目录: {self.output_folder}")
        except Exception as e:
            logger.warning(f"清理PDF输出目录失败: {str(e)}")
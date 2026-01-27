import asyncio
import os
import cv2
import numpy as np
from typing import List, Dict, Any
from paddleocr import PPStructureV3
from server.utils.logger import logger

"""
from paddleocr import PPStructureV3

pipeline = PPStructureV3()
# pipeline = PPStructureV3(lang="en") # 将 lang 参数设置为使用英文文本识别模型。对于其他支持的语言，请参阅第5节：附录部分。默认配置为中英文模型。
# pipeline = PPStructureV3(use_doc_orientation_classify=True) # 通过 use_doc_orientation_classify 指定是否使用文档方向分类模型
# pipeline = PPStructureV3(use_doc_unwarping=True) # 通过 use_doc_unwarping 指定是否使用文本图像矫正模块
# pipeline = PPStructureV3(use_textline_orientation=True) # 通过 use_textline_orientation 指定是否使用文本行方向分类模型
# pipeline = PPStructureV3(device="gpu") # 通过 device 指定模型推理时使用 GPU
output = pipeline.predict("./pp_structure_v3_demo.png")
for res in output:
    res.print() ## 打印预测的结构化输出
    res.save_to_json(save_path="output") ## 保存当前图像的结构化json结果
    res.save_to_markdown(save_path="output") ## 保存当前图像的markdown格式的结果
"""


class PaddleOCRPipeline:
    """
    使用 PP-Structure 进行版面分析
    功能：
    1. 区分 文本、表格、图片、公式
    2. 提取表格为 HTML
    3. 返回结构化数据
    """

    def __init__(self, use_gpu: bool = False):
        self.use_gpu = use_gpu
        # 初始化 PP-Structure
        # table=False 表示不单独做复杂的表格结构还原(省资源)，如果需要精确表格数据设为 True
        # layout=True 开启版面分析
        self._engine = PPStructureV3(show_log=False, image_orientation=False, layout=True, table=True, use_gpu=use_gpu, lang='ch',
                                     use_doc_orientation_classify=True,
                                     use_doc_unwarping=True,
                                     use_textline_orientation=True)

    async def invoke_single_img(self, img_path: str, output_dir: str) -> List[Dict[str, Any]]:
        """
        处理单张图片，返回版面分析后的元素列表
        output_dir: 用于保存裁剪下来的图片（图表、表格截图）
        """
        loop = asyncio.get_running_loop()
        # 在线程池中运行 CPU 密集型任务
        return await loop.run_in_executor(None, self._predict_sync, img_path, output_dir)
    
    def _predict_sync(self, img_path: str, output_dir: str) -> List[Dict[str, Any]]:
        res = self._engine.predict(img_path)
        logger.info(f"结果存储至 {output_dir}")
        res.save_to_json(save_path=output_dir)
        

    # def _predict_sync(self, img_path: str, output_dir: str) -> List[Dict[str, Any]]:
    #     img = cv2.imread(img_path)
    #     if img is None:
    #         return []

    #     # 1. 执行推理
    #     # result 结构: [{'type': 'Text', 'bbox': [x1, y1, x2, y2], 'res': [{'text': '...', 'confidence': 0.9}]}, ...]
    #     result = self._engine(img)
        
    #     # 2. 排序版面（按照人类阅读习惯，从上到下，从左到右）
    #     h, w, _ = img.shape
    #     _, layout_res = sorted_layout_boxes(result, w)

    #     processed_chunks = []
        
    #     base_name = os.path.basename(img_path).split('.')[0]

    #     for idx, region in enumerate(layout_res):
    #         region_type = region.get('type', 'text').lower() # text, title, figure, table, equation
    #         bbox = region.get('bbox')
            
    #         content_text = ""
    #         img_storage_path = ""

    #         # --- 处理文本/标题/公式 ---
    #         if region_type in ['text', 'title', 'header', 'footer', 'reference']:
    #             # 将该区域内的所有行文本拼接
    #             lines = [line['text'] for line in region.get('res', [])]
    #             content_text = "\n".join(lines)
            
    #         # --- 处理表格 (Table) ---
    #         elif region_type == 'table':
    #             # PPStructure 会尝试生成 html
    #             content_text = region.get('res', {}).get('html', '')
    #             if not content_text:
    #                 # 如果没有html，降级为纯文本拼接
    #                  content_text = " ".join([x['text'] for x in region.get('res', []) if isinstance(x, dict)])
                
    #             # 保存表格截图，方便 Agent 展示给用户看
    #             img_storage_path = self._save_crop_img(img, bbox, output_dir, f"{base_name}_tbl_{idx}")

    #         # --- 处理图片 (Figure) ---
    #         elif region_type == 'figure':
    #             # 图片区域通常会有 OCR 结果（比如图里面的文字），作为图片的描述
    #             ocr_texts = [line['text'] for line in region.get('res', [])]
    #             content_text = " ".join(ocr_texts) # 这里通常是图例或图内文字
                
    #             # 核心：保存图片文件
    #             img_storage_path = self._save_crop_img(img, bbox, output_dir, f"{base_name}_fig_{idx}")

    #         # --- 处理公式 (Equation) ---
    #         elif region_type == 'equation':
    #             # 简单的 OCR 可能对复杂公式效果一般，理想情况是 LatexOCR，这里暂用文本代替
    #             lines = [line['text'] for line in region.get('res', [])]
    #             content_text = " ".join(lines)

    #         # 只有内容不为空，或者有图片路径时才保留
    #         if content_text.strip() or img_storage_path:
    #             processed_chunks.append({
    #                 "type": region_type,
    #                 "content": content_text,
    #                 "bbox": bbox,
    #                 "image_path": img_storage_path 
    #             })

    #     return processed_chunks

    # def _save_crop_img(self, original_img, bbox, output_dir, name_prefix):
    #     """裁剪并保存图片"""
    #     try:
    #         x1, y1, x2, y2 = [int(v) for v in bbox]
    #         # 边界检查
    #         h, w = original_img.shape[:2]
    #         x1, y1 = max(0, x1), max(0, y1)
    #         x2, y2 = min(w, x2), min(h, y2)
            
    #         crop_img = original_img[y1:y2, x1:x2]
    #         if crop_img.size == 0:
    #             return ""
                
    #         os.makedirs(output_dir, exist_ok=True)
    #         rel_path = f"{name_prefix}.jpg"
    #         full_path = os.path.join(output_dir, rel_path)
    #         cv2.imwrite(full_path, crop_img)
    #         return full_path # 实际生产中这里应该上传到 OSS/S3 并返回 URL
    #     except Exception:
    #         return ""
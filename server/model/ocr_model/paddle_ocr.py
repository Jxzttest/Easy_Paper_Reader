import asyncio
import os
import cv2
import numpy as np
import json
from httpx import AsyncClient
from typing import List, Dict, Any
from paddleocr import PPStructureV3
from server.model.base_model import BaseAIModel

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


class PaddleOCRPipeline(BaseAIModel):
    """
    使用 PP-Structure 进行版面分析
    功能：
    1. 区分 文本、表格、图片、公式
    2. 提取表格为 HTML
    3. 返回结构化数据
    """

    def _setup(self) -> None:
        self.model_name = self.kwargs.get("model_name")
        self.temperature = self.kwargs.get("temperature", 0.7)
        
        if self.mode == "api":
            self._engine = AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=60)
        else:
            self.use_gpu = self.kwargs.get('use_gpu')
            ocr_version = self.kwargs.get('ocr_version', "PP-OCRv5")
            lang = self.kwargs.get('lang', 'ch')
            # 初始化 PP-Structure
            self._engine = PPStructureV3(lang=lang,ocr_version=ocr_version,
                                        use_doc_orientation_classify=True,
                                        use_table_recognition=True,
                                        use_doc_unwarping=True,
                                        use_textline_orientation=True,
                                        use_region_detection=True,
                                        device="gpu" if self.use_gpu else "cpu")
    

    async def async_invoke(self, img_path: str, output_dir: str = "", paper_index: int = 1) -> List[Dict[str, Any]]:
        """
        处理单张图片，返回版面分析后的元素列表
        output_dir: 用于保存裁剪下来的图片（图表、表格截图）
        """
        loop = asyncio.get_running_loop()
        # 在线程池中运行 CPU 密集型任务
        return await loop.run_in_executor(None, self._predict_sync, img_path, output_dir, paper_index)
        
    
    def _predict_sync(self, img_path: str, output_dir: str = "", paper_index: int = 1) -> List[Dict[str, Any]]:
        res = self._engine.predict(img_path)
        # logger.info(f"结果存储至 {output_dir}")

        # for r in res:
        #     ocr_result = r.json
        #     print(r.markdown)
        #     logger.info(f"第 {paper_index} 页 OCR 结果: {ocr_result}")
            # self.save_json(paper_index, ocr_result, output_dir)
        result_list = []
        for r in res:
            result_dict = r.json.get("res", {})
            for index, parsing_result in enumerate(result_dict["parsing_res_list"]):
                if parsing_result['block_label'] in ['image', 'table']:
                    # 裁剪图片保存路径
                    img_path_saved = self._save_crop_img(img_path, parsing_result['block_bbox'], output_dir, f"paper{paper_index}_block_{index}")
                    parsing_result['image_path'] = img_path_saved
            result_list.append(result_dict)
        return result_list
    
    def _save_crop_img(self, img_path: str, bbox: List[int], output_dir: str, name_prefix: str) -> str:
        """裁剪并保存图片"""
        try:
            img = cv2.imread(img_path)
            if img is None:
                return ""
            x1, y1, x2, y2 = [int(v) for v in bbox]
            # 边界检查
            h, w = img.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            
            crop_img = img[y1:y2, x1:x2]
            if crop_img.size == 0:
                return ""
                
            os.makedirs(output_dir, exist_ok=True)
            rel_path = f"{name_prefix}.jpg"
            full_path = os.path.join(output_dir, rel_path)
            cv2.imwrite(full_path, crop_img)
            return full_path # 实际生产中这里应该上传到 OSS/S3 并返回 URL
        except Exception as e:
            self.logger.error(f"保存裁剪图片失败: {str(e)}")
            return ""

    def save_json(self, idx, ocr_result, output_dir: str):
        os.makedirs(output_dir, exist_ok=True)
        json_path = os.path.join(output_dir, f"page_{idx+1}_structure.json")
        json.dump(ocr_result, open(json_path, "w", encoding="utf-8"), ensure_ascii=False, indent=4)
        self.logger.info(f"结构化结果已保存至 {json_path}")
        return output_dir

    async def async_stream(self, *args, **kwargs) -> AsyncGenerator[Any, None]:
        "无调用"
        pass
import asyncio
from pathlib import Path
from typing import List, Dict, Any

from paddlex import create_pipeline

class PaddleOCRPipeline:
    """
    异步 OCR 封装
    1. 内部持有一个 OCR 产线实例，避免每次重复加载模型
    2. 支持批量 / 单张两种入口
    3. 返回结构化结果：{"img_path": str, "texts": List[str], "boxes": List[List[List[int]]]}
    """

    def __init__(self, device: str = "cpu", config_path: str = None):
        """
        device: cpu / gpu:0 / gpu:1 ...
        config_path: 如果要用自己导出的高精度模型，可传入 *.yaml 路径；None 则走默认轻量模型
        """
        # 关键：这里填 "OCR" 即可启动官方 OCR 产线
        self._pipe = create_pipeline(
            pipeline=config_path or "OCR",
            device=device
        )

    async def invoke_single_img(self, img_path: str) -> Dict[str, Any]:
        """单张图片 OCR"""
        return await self._predict_one(img_path)

    async def invoke_file(self, img_paths: List[str]) -> List[Dict[str, Any]]:
        """批量图片 OCR"""
        # asyncio.create_task 并发推理，I/O 不阻塞
        tasks = [asyncio.create_task(self._predict_one(p)) for p in img_paths]
        return await asyncio.gather(*tasks)

    async def _predict_one(self, img_path: str) -> Dict[str, Any]:
        """
        同步模型 predict + 异步线程池，防止事件循环被阻塞
        """
        loop = asyncio.get_running_loop()
        output = await loop.run_in_executor(None, self._pipe.predict, str(img_path))

        texts, boxes = [], []
        for res in output:
            texts.append(res["text"])
            boxes.append(res["box"].tolist())  # ndarray -> list

        return {"img_path": str(img_path), "texts": texts, "boxes": boxes}


# ----------------- 使用示例 -----------------
async def main():
    ocr = PaddleOCRPipeline(device="cpu")          # 也可 device="gpu:0"
    single = await ocr.invoke_single_img("1.jpg")
    print("单张结果 >>>", single)

    batch = await ocr.invoke_file(["1.jpg", "2.jpg"])
    print("批量结果 >>>", batch)


if __name__ == "__main__":
    asyncio.run(main())
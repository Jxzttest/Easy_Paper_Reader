import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
import fitz  # PyMuPDF
from typing import Dict, Any
from server.model.ocr_model.paddle_ocr import PaddleOCRPipeline

output_folder = os.path.join(os.path.dirname(__file__), "output_images")
os.makedirs(output_folder, exist_ok=True)
image_paths = []

def extract_metadata(file_path, dpi=300) -> Dict[str, Any]:
    try:
        with fitz.open(file_path) as pdf_document:
            for page_num in range(len(pdf_document)):
                page = pdf_document.load_page(page_num)
                
                # 设置缩放比例
                zoom = dpi / 72
                matrix = fitz.Matrix(zoom, zoom)
                
                # 渲染为图像
                pix = page.get_pixmap(matrix=matrix)
                
                # 保存图像
                output_path = os.path.join(output_folder, f"page_{page_num + 1}.png")
                pix.save(output_path)
                image_paths.append(output_path)
    except Exception as e:
        raise Exception(f"Failed to extract metadata from {file_path}: {str(e)}")


async def main():
    pdf_path = "/DATA/llm_xuzhentao/Easy_Paper_Reader/A Survey of Context Engineering for Large.pdf"
    extract_metadata(pdf_path)
    parser = PaddleOCRPipeline()
    for img_path in image_paths:
        await parser.invoke_single_img(img_path, output_dir=output_folder)

if main() == "__main__":
    import asyncio
    asyncio.run(main())
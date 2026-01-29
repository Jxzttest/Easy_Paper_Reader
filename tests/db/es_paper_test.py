import os
import json
import sys
sys.path.append("/data/code/Easy_Paper_Reader/")
from server.db.elasticsearch_function.es_paper import ESPaperStore
import asyncio
import numpy as np

def get_embedding():
    return np.random.rand(1024).tolist()

def test_paper_function():
    test_paper_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ocr_test/output_images")
    result_list = []

    pages = []
    for p in os.listdir(test_paper_path):
        if p.startswith("page_") and p.endswith("_structure.json"):
            # 把 "page_123_structure.json" 里的 123 取出来
            num = int(p.split("_")[1])
            pages.append((num, p))

    # 2. 按页码升序
    pages.sort(key=lambda t: t[0])
    for file_tuple in pages:
        file_name = file_tuple[1]
        with open(os.path.join(test_paper_path, file_name), 'r', encoding='utf-8') as file:
            result_dict = json.loads(file.read())
            result_list.append(result_dict["res"])
    return result_list

async def main():
    file_uuid = "test_123"
    es_paper_store = ESPaperStore()
    await es_paper_store.initialize()
    # result_list = test_paper_function()

    # chunk_tasks = []
    # for i, item in enumerate(result_list):
    #     parsing_res = item['parsing_res_list']
    #     for res in parsing_res:
    #         chunk_id = f"{file_uuid}_p{i}_s{i}"
    #         chunk_text = res['block_content']
    #         c_type = res['block_label'] # text, table, figure...
    #         if c_type not in ['text', 'formula', 'figure', 'table', 'image', 'figure_title']:
    #             continue
    #         # 表格 、 图片会做裁剪，保存路径在 res['image_path']
    #         img_path_saved = res.get('image_path', '')
    #         vector = get_embedding()
            
    #         # 构造 ES 存入数据
    #         task = es_paper_store.add_paper_chunk(
    #             paper_id=file_uuid,
    #             chunk_id=chunk_id,
    #             content=chunk_text,
    #             content_type=c_type,
    #             image_path= img_path_saved,
    #             vector=vector,
    #             page_num=i,
    #             metadata={
    #                 "original_bbox": res['block_bbox']
    #             }
    #         )
    #         chunk_tasks.append(task)
    
    # # 并发入库
    # if chunk_tasks:
    #     await asyncio.gather(*chunk_tasks)
    
    # 查询是否入库成功
    await es_paper_store.search_paper_chunks(file_uuid)


if __name__ == "__main__":
    asyncio.run(main())
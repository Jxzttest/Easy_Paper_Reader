import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
from server.parser.pdf_parser import PDFParser

async def main():
    pdf_path = "/DATA/llm_xuzhentao/Easy_Paper_Reader/A Survey of Context Engineering for Large.pdf"
    parser = PDFParser(pdf_path, uploader_uuid="test-uuid-1234")
    parser.parse_and_save()

if main() == "__main__":
    import asyncio
    asyncio.run(main())
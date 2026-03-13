from fastapi import APIRouter, Depends, HTTPException, UploadFile
from server.parser.pdf_parser import PDFParser
from starlette import status
from starlette.responses import JSONResponse
from server.utils.logger import logger

router = APIRouter(prefix="/pdf_parser")

@router.post('/')
async def pdf_parser_api(pdf_file: UploadFile, uploader_uuid: str):
    """
    Docstring for pdf_parser_api
    
    :param pdf_file: 上传文件
    :param uploader_uuid: 上传文件uuid
    """
    logger.info(f"开始上传pdf文件: {pdf_file.filename}")
    pdf_parser = PDFParser(pdf_file, uploader_uuid)
    try:
        pdf_parser.parse_and_save()
    except Exception as e:
        logger.error(str(e))
        return JSONResponse(status_code=400, content=str(e))



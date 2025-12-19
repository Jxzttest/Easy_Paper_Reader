#! /usr/bin/python3
# -*- coding: utf-8 -*-


from fastapi import APIRouter, Depends, HTTPException
from starlette import status
from starlette.responses import JSONResponse
# from server.chat_manager.depends import get_session_manager, get_message_manager
from server.chat_manager.depends import get_es_chat_service
from server.db.elasticsearch_function.es_chat import ESChatStore
from server.db.elasticsearch_function.talkItem import TalkItem
from server.db.elasticsearch_function.queryItem import QueryItem
from server.utils.logger import logger

router = APIRouter(prefix="/chat_history")


@router.post('/delete_select_messages')
async def delete_select_messages(request: TalkItem,
                                 es_chat_store: ESChatStore = Depends(get_es_chat_service)):
    user_id = request.user_id
    session_id = request.session_id
    
    await es_chat_store.delete_session(user_id, session_id)
    logger.info("session delete success")
    await es_chat_store.delete_message(user_id, session_id)
    logger.info("message delete success")
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"response": "success", "result": "delete success"},
    )


@router.post("/get_conversation_files")
async def get_conversation_files(talk_item: TalkItem, es_chat_store: ESChatStore = Depends(get_es_chat_service)):
    files_retriever = await es_chat_store.get_user_files(talk_item.user_id, talk_item.session_id)
    logger.info("get conversation files success")
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"response": "success", "files": files_retriever})


@router.post("/get_session_title")
async def get_session_title(request: TalkItem, es_chat_store: ESChatStore = Depends(get_es_chat_service)):
    user_id = request.user_id
    session_id = request.session_id
    chat_session = f"chat_history_{user_id}_{session_id}"
    if not await es_chat_store.check_session_exist(chat_session):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"chat_history_{user_id}_{session_id} not in db",
        )
    session_title = await es_chat_store.get_session_title(user_id, session_id)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"response": "success", "result": session_title},
    )


@router.post('/change_session_title')
async def change_session_title(request: TalkItem, es_chat_store: ESChatStore = Depends(get_es_chat_service)):
    user_id = request.user_id
    session_id = request.session_id
    new_title = request.new_title
    chat_session = f"chat_history_{user_id}_{session_id}"
    if not await es_chat_store.check_session_exist(chat_session):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"chat_history_{user_id}_{session_id} not in db",
        )
    await es_chat_store.add_session_title(user_id, session_id, new_title)
    logger.info("change session success")
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"response": "success", "result": {"id": session_id, "title": new_title}})


@router.post('/add_dialogue')
async def add_dialogue(query_item: QueryItem, chat_content: str,
                               es_chat_store: ESChatStore = Depends(get_es_chat_service)):
    es_chat_store.add_dialogue_result(query_item, chat_content)
    logger.info("add chat_content success")
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"response": "success", "result": "add chat_content success"})


@router.post('/add_new_talk')
async def add_new_talk(request: TalkItem,
                       es_chat_store: ESChatStore = Depends(get_es_chat_service)):
    user_id = request.user_id
    session_id = request.session_id
    chat_session = f"chat_history_{user_id}_{session_id}"
    # if await session_manager.check_session_exist(chat_session):
    #     raise HTTPException(
    #         status_code=status.HTTP_400_BAD_REQUEST,
    #         detail=f"chat_history_{user_id}_{session_id} has in db",
    #     )
    await es_chat_store.add_session(user_id, session_id)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"response": "success", "result": "add new talk success"},
    )


@router.post('/get_user_chat_history')
async def get_user_chat_history(request: TalkItem, es_chat_store: ESChatStore = Depends(get_es_chat_service)):
    # 获得用户对话框下的对话记录
    user_id = request.user_id
    session_id = request.session_id
    if not await es_chat_store.check_session_exist(f"chat_history_{user_id}_{session_id}"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"response": "failed", "result": f"chat_history_{user_id}_{session_id} not in db"},
        )
    chat_message_list = await es_chat_store.get_all_messages(user_id, session_id)
    chat_history_list = [hits['_source'] for hits in chat_message_list]
    return_chat_history_list = []
    for chat_history in chat_history_list:
        temp = {}
        temp["sender"] = chat_history["sender"]
        temp["text"] = chat_history["chat_message"]
        temp["timestamp"] = chat_history["timestamp"]
        temp['id'] = chat_history["message_id"]
        temp['files'] = chat_history["files_info"]
        temp['isTemp'] = False
        return_chat_history_list.append(temp)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"response": "success", "result": return_chat_history_list},
    )

@router.post('/get_user_session_chat_history')
async def get_user_chat_history(request: TalkItem, es_chat_store: ESChatStore = Depends(get_es_chat_service)):
    # 获得用户的对话框记录
    user_id = request.user_id
    chat_session_list = await es_chat_store.get_user_sessions(user_id)
    return_chat_history_list = []
    
    for chat_history in chat_session_list:
        temp = chat_history["_source"]
        session_id = chat_history["_source"]["session_id"]
        temp["created_at"] = temp["create_time"]
        chat_message_list = await es_chat_store.get_all_messages(user_id, session_id)
        chat_history_list = [hits['_source'] for hits in chat_message_list]
        if len(chat_history_list) != 0:
            temp["last_message"] = chat_history_list[-1]["chat_message"]
        return_chat_history_list.append(temp)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"response": "success", "result": return_chat_history_list},
    )


async def delete_user_all_chat(user_uuid, es_chat_store: ESChatStore = Depends(get_es_chat_service)):

    chat_session_list = await es_chat_store.get_user_sessions(user_uuid)

    for chat_history in chat_session_list:
        session_id = chat_history["_source"]["session_id"]
        await es_chat_store.delete_session(user_uuid, session_id)
        logger.info("session delete success")
        await es_chat_store.delete_message(user_uuid, session_id)
        logger.info("message delete success")
    return {"response": "success", "result": "delete success"}


if __name__ == "__main__":
    import asyncio
    talk_item = TalkItem()
    result = asyncio.run(add_new_talk(talk_item))
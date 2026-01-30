import sys
sys.path.append("/data/code/Easy_Paper_Reader/")
import time
from server.db.elasticsearch_function.es_chat import ESChatStore
from server.db.postgresql_function.postgresql_function import PostgresStore
from langchain.messages import AIMessage, HumanMessage, SystemMessage
import asyncio


async def main():
    postgresdb = PostgresStore()
    es_chat_store = ESChatStore()
    human_message = HumanMessage(content="1+1=2?")
    ai_message = AIMessage(content="yes")
    await postgresdb.add_new_chat(user_uuid="user-uuid-5678", session_id="chat_1234", start_time=time.time())
    message_id = await es_chat_store.add_message(user_uuid="user-uuid-5678", session_id="chat_1234", role="Human", content=human_message.content, parent_message_id="")
    await es_chat_store.add_message(user_uuid="user-uuid-5678", session_id="chat_1234", role="AI", content=ai_message.content, parent_message_id=message_id)
    await es_chat_store.delete_message(user_uuid="user-uuid-5678", session_id="chat_1234")
    await postgresdb.delete_chat(user_uuid="user-uuid-5678", session_id="chat_1234")



if __name__ == "__main__":
    asyncio.run(main())
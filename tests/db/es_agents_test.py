import sys
sys.path.append("/data/code/Easy_Paper_Reader/")
import time
from server.db.elasticsearch_function.es_agent import ESAgentStore
from server.db.postgresql_function.postgresql_function import PostgresStore
from langchain.messages import AIMessage, HumanMessage, SystemMessage
import asyncio


async def main():
    es_agent_store = ESAgentStore()
    es_agent_store.add_tool_call_result

if __name__ == "__main__":
    asyncio.run(main())
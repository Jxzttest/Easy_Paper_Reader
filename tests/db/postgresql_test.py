import sys
sys.path.append("/data/code/Easy_Paper_Reader/")
from server.db.postgresql_function.postgresql_function import PostgresStore
import asyncio

async def main():
    postgresdb = PostgresStore()
    await postgresdb.initialize()
    await postgresdb.create_user(user_uuid="user-uuid-5678", username="testuser")
    await postgresdb.add_paper_metadata(paper_uuid="test-uuid-1234", title="Test Paper", uploader_uuid="user-uuid-5678", file_path="/path/to/test_paper.pdf")

if __name__ == "__main__":
    asyncio.run(main())
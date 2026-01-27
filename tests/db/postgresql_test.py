import sys
sys.path.append("/DATA/llm_xuzhentao/Easy_Paper_Reader/")
from server.db.postgresql_function.postgresql_function import PostgresStore
import asyncio

postgresdb = PostgresStore()
asyncio.run(postgresdb.initialize(db_name="users"))
asyncio.run(postgresdb.create_user(user_uuid="user-uuid-5678", username="test_user"))
asyncio.run(postgresdb.add_paper_metadata(paper_uuid="test-uuid-1234", title="Test Paper", uploader_uuid="user-uuid-5678", file_path="/path/to/test_paper.pdf"))
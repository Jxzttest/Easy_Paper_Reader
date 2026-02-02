import yaml
import os
from openai import AsyncOpenAI
from langchain.messages import SystemMessage


with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "/config/model_config.yaml")) as file:
    model_config = yaml.load(file.read())


client = AsyncOpenAI(api_key=model_config.get("api_key", ""), base_url=model_config.get("url", ""))

async def _internal_llm_process(messages: list = []) -> str:
    messages.insert(0, SystemMessage("你是一位根据用户问题回答对应答案的机器人，你要严格遵守用户的要求进行作答"))
    response = await client.chat.completions.create(
        model=model_config.get("model_name", "gpt-4-turbo"), messages=messages, temperature=0.3
    )
    return response.choices[0].message.content
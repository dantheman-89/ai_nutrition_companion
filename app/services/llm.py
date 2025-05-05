import asyncio
from openai import AsyncOpenAI
from config import OPENAI_API_KEY, SYSTEM_PROMPT, LINKAI_API_KEY

# Instantiate a client with API key.
client = AsyncOpenAI(
    api_key=OPENAI_API_KEY
)

# async streaming function to get text response from OpenAI
async def stream_text_response(messages, systemprompt):
    # Streaming text response from OpenAI
    response = await client.responses.create(
       model="gpt-4.1-nano",
       instructions=systemprompt,
       input=messages,
       stream=True,
    )

    async for event in response:
       if event.type == 'response.output_text.delta':
            # Extract the text from the response
            text = event.delta
            if text:
                yield text

# # 使用代理API创建客户端
# client = AsyncOpenAI(
#     api_key=LINKAI_API_KEY,
#     base_url="https://api.link-ai.chat/v1"  # 替换为你的代理API URL
# )

# # 异步流式响应函数
# async def stream_text_response(messages, systemprompt):
#     # 转换消息格式
#     formatted_messages = []
#     for msg in messages:
#         formatted_messages.append({
#             "role": msg["role"],
#             "content": msg["content"]
#         })
    
#     # 添加系统提示
#     if formatted_messages and formatted_messages[0]["role"] != "system":
#         formatted_messages.insert(0, {"role": "system", "content": systemprompt})
    
#     # 使用代理API流式调用
#     response = await client.chat.completions.create(
#         model="gpt-4.1-nano",
#         messages=formatted_messages,
#         stream=True,
#     )

#     async for chunk in response:
#         if chunk.choices[0].delta.content is not None:
#             yield chunk.choices[0].delta.content


# ─── Example usage ─────────────────────────────────────────────────────────────

async def main():
    # initiative messages with system prompt
    import time
    
    # pre-determined user messages
    messages_user = ["Okay, I want you to help me being healthy",
                     "Okay, hi, so I'm looking at nutrition needs some advice on getting healthier losing weight",
                     "Okay, hi, so I'm looking at nutrition needs some advice on getting healthier losing weight"
                     ]

    # Append a user message to initiate a conversation.
    history = []
    for user_says in messages_user:
        history.append({"role": "user", "content": user_says})
        print("User:", user_says)    
    
        # time LLM response time
        start_time = time.perf_counter()
        first = True

        # stream reponse and print it out
        full_response = ""
        async for token in stream_text_response(history, SYSTEM_PROMPT):
            # record the first response time
            if first:
                response_duration = time.perf_counter() - start_time
                print("LLM:", end="")
                first = False
            
            # Immediately process the token (e.g. forward to TTS) if desired.
            full_response += token
            print(token, end="", flush=True)

        # print time taken for the LLM to respond
        print(f"\nLLM first responded in {response_duration:.3f} seconds")
        response_duration = time.perf_counter() - start_time
        print(f"LLM completely responded in {response_duration:.3f} seconds")
        
        # update messages history.
        history.append({"role": "assistant", "content": full_response})

if __name__ == "__main__":
    asyncio.run(main())
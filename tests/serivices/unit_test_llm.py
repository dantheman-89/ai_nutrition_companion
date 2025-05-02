# import asyncio
# import time
# from app.core.llm import stream_chat_completion, system_prompt

# # Example usage:
# async def main():
#     # initiative messages with system prompt
#     messages = [{"role": "system", "content": system_prompt}]
    
#     # pre-determined user messages
#     messages_user = ["hello", 
#                      "Okay, hi, so I'm looking at nutrition needs some advice on getting healthier losing weight"
#                      ]

#     # Append a user message to initiate a conversation.
#     for user_says in messages_user:
#         messages.append({"role": "user", "content": user_says})
#         print("User:", user_says)    
    
#         # time LLM response time
#         start_load = time.perf_counter()

#         full_response = ""
#         print("LLM:", end="")
#         async for token in stream_chat_completion(messages):
#             full_response += token
#             # Immediately process the token (e.g. forward to TTS) if desired.
#             print(token, end="", flush=True)

#         response_duration = time.perf_counter() - start_load
#         print(f"\nLLM responded in {response_duration:.3f} seconds\n")

#         # update messages history.
#         messages.append({"role": "assistant", "content": full_response})

# if __name__ == "__main__":
    
#     asyncio.run(main())



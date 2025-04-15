import time
import openai
from app.llm import messages 

user_says = "Okay, hi, so I'm looking at nutrition needs some advice on getting healthier losing weight"

messages.append({"role": "user", "content": user_says})
print("User:", user_says)    

# time LLM response time
start_load = time.perf_counter()

first_token_time = None

full_response = ""

response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.8,
        max_tokens=150,
        stream=True
    )

for chunk in response:
    # Extract token from the delta, if available.
    if first_token_time is None:
        first_token_time = time.perf_counter()
        print(f"Time to first token: {first_token_time - start_load:.3f} seconds")

    token = chunk["choices"][0]["delta"].get("content", "")
    full_response += token


print("\nLLM:", full_response)

response_duration = time.perf_counter() - start_load
print(f"LLM responded in {response_duration:.3f} seconds")


import requests
import json
import config
from transformers import  AutoTokenizer
from ollama import Client
from openai import AzureOpenAI, BadRequestError
from openai import OpenAI
import tiktoken
import anthropic

llm_model = config.LLM

local_port = 11434  # Default port for Qwen model


def run_llm_model(prompt):
    """
    Run the LLM model with the given prompt.
    """
    if prompt is None or prompt.strip() == "":
        return "Prompt is empty. Please provide a valid prompt."
    if "qwen" in llm_model:
        return interact_with_qwen(prompt)
    elif "gpt" in llm_model:
        return interact_with_gpt(prompt)
    elif "codex" in llm_model:
        return interact_with_codex(prompt)
    elif "deepseek" in llm_model or "codellama" in llm_model:
        return interact_with_deepseek(prompt)
    elif "claude" in llm_model:
        return interact_with_claude(prompt)


def interact_with_codex(prompt):
    # 1. Initialize the client for Poe's OpenAI-compatible endpoint
    client = OpenAI(api_key=config.codex_api_key)

    # 2. Call the Codex model (gpt-5.3-codex is the latest available)
    response = client.chat.completions.create(
        model="gpt-5.1-codex-mini",
        messages=[{"role": "user", "content": prompt}],
        max_completion_tokens=1024,
        n=1
    )
    
    output = response.choices[0].message.content.strip()

    # codex-mini doesn't use tiktoken the same way, so approximate:
    num_prompt_tokens = response.usage.prompt_tokens
    num_response_tokens = response.usage.completion_tokens
    
    return output, num_prompt_tokens, num_response_tokens

def interact_with_claude(prompt):
    bot_name = "claude-sonnet-4-6"
    client = anthropic.Anthropic(
        api_key=config.claude_api_key 
    )
    
    try:
        response = client.messages.create(
            model=bot_name,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        
        output = response.content[0].text.strip()
        num_prompt_tokens = response.usage.input_tokens
        num_response_tokens = response.usage.output_tokens
        
        print(f"Response: {output}")
        print(f" tokens in prompt: {num_prompt_tokens}")
        print(f" tokens in response: {num_response_tokens}")
        
        return output, num_prompt_tokens, num_response_tokens

    except Exception as e:
        print(f"An unexpected error occurred with Claude: {e}")
        return "", 0, 0

def set_local_port(port):
    global local_port
    local_port = port


def interact_with_gpt(prompt):
    encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")  # Replace with the correct model name , for gpt 4o is gpt-3.5-turbo
    input = [
            {"role": "user", "content": prompt},
            ]

    client = AzureOpenAI(
        api_key=config.global_openai_key,
        api_version='2024-06-01', # gpt-4o-mini 2024-06-01 , 2025-02-01-preview for o3 mini
        azure_endpoint='https://hkust.azure-api.net'
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=input,
        max_completion_tokens=1024, # max_tokens renamed to max_completion_tokens for o3-mini
        n=1,
        stop=None
    )
    token_prompt = encoding.encode(prompt)
    token_response = encoding.encode(response.choices[0].message.content.strip()) # change to content for chat models o3-mini , before for gpt it was response.choices[0].text.strip()
    print(f"Response: {response.choices[0].message.content.strip()}")
    print(f" tokens in prompt: {len(token_prompt)}")
    print(f" tokens in response: {len(token_response)}")
    return str(response.choices[0].message.content.strip()), token_prompt, token_response

def interact_with_qwen(prompt):
    base_url = f"http://localhost:{local_port}/api/generate"
    data = {"model": "qwen2.5-coder:32b-instruct-q4_K_M", "prompt": prompt, "stream": False}
    combined_response = ""

    try:
        response = requests.post(base_url, json=data)
        if response.status_code != 200:
            print(f"Error: {response.status_code} when connecting to Qwen model.")
            print(f"Response text: {response.text}")
            return "", 0, 0

        # Parse the single JSON object from the non-streaming response
        json_obj = response.json()
        
        # Extract the relevant data
        combined_response = json_obj.get('response', '')
        num_prompt_tokens = json_obj.get('prompt_eval_count', 0)
        num_response_tokens = json_obj.get('eval_count', 0)

        return combined_response.strip(), num_prompt_tokens, num_response_tokens

    except requests.exceptions.ConnectionError as e:
        print(f"Connection error: Could not connect to {base_url}.")
        print("Ensure Ollama is running and configured for remote access (OLLAMA_HOST=0.0.0.0).")
        return "", 0, 0
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return "", 0, 0



def interact_with_deepseek(prompt):
    base_url = f"http://localhost:{local_port}/api/chat"
    model_name = llm_model
    data = {"model": model_name, "prompt": prompt}
    # Define the messages in the correct chat format

    messages = [
        {"role": "user", "content": prompt}
    ]

    data = {
        "model": model_name,
        "messages": messages,
        "stream": False,  # Use non-streaming for a single response
         "options": {
            "think": False
        }
    }

    try:
        response = requests.post(base_url, json=data)

        if response.status_code != 200:
            print(f"Error: {response.status_code} when connecting to DeepSeek model.")
            print(f"Response text: {response.text}")
            return "", 0, 0

        # Parse the single JSON object from the response
        json_obj = response.json()
        full_response = json_obj.get('message', {}).get('content', '')

        # Process the full response to get only the last line
        lines = full_response.strip().splitlines()
        last_line = lines[-1].strip() if lines else ""
        
        # Extract the content and token counts
        combined_response = json_obj.get('message', {}).get('content', '')
        num_prompt_tokens = json_obj.get('prompt_eval_count', 0)
        num_response_tokens = json_obj.get('eval_count', 0)

        return last_line.strip(), num_prompt_tokens, num_response_tokens

    except requests.exceptions.ConnectionError as e:
        print(f"Connection error: Could not connect to {base_url}.")
        print("Ensure Ollama is running and the deepseek-r1:32b model is pulled.")
        return "", 0, 0
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return "", 0, 0

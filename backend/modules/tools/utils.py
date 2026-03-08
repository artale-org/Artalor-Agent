# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

from IPython.display import Image, display
import os
from langchain.chat_models import init_chat_model
from dotenv import load_dotenv
import os
from datetime import datetime

def load_env():
    # parent path
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

def get_llm_client(model_name="openai:gpt-4o", temperature=0.7):
    chat_model = init_chat_model(model_name, temperature=temperature)
    return chat_model


def draw_graph(graph):
    return graph.get_graph().draw_mermaid_png(output_file_path='graph.png')

# task_path = os.path.join('task_data', f"task_20250504022920")
def create_task(task_path=None):
    if task_path is None:
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        task_path = os.path.join('task_data', f"task_{ts}")
        if not os.path.exists(task_path):
            os.makedirs(task_path, exist_ok=True)
    return task_path

def filter_description(text):
    # Keywords mapping for sensitive content replacement
    key_words_mapping = {
        'black man': 'African American',
        '黑人': '非裔美国人'
    }

    # Sort by length to avoid partial replacement issues
    sorted_mappings = sorted(key_words_mapping.items(), key=lambda x: len(x[0]), reverse=True)
    
    for k, v in sorted_mappings:
        text = text.replace(k, v)
        text = text.replace(k.upper(), v.upper())
        text = text.replace(k.capitalize(), v.capitalize())
        text = text.replace(k.title(), v.title())
    
    # # Limit description length to avoid overly long prompts
    # if len(text) > 500:
    #     text = text[:500] + "..."
    
    # Remove potentially problematic special characters
    text = text.replace('\n', ' ').replace('\r', ' ')
    
    return text


class ProgressIndicator:
    def __init__(self, prefix='', show_mode=0):
        self.prefix = prefix
        self.ind = 0
        self.ind_show = [['.', '..', '...'], ['-', '\\', '|', '/']][show_mode]

    def next_print(self, comment=''):
        data = ' '.join([self.prefix, comment])
        print(f'\r{data}{self.ind_show[self.ind]}', end='')
        self.ind = (self.ind + 1) % len(self.ind_show)
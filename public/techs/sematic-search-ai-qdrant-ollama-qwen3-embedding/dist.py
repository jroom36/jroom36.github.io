import numpy as np
import json
import sys
import requests

def get_embedding(text, model="qwen3-embedding:4b"):
    response = requests.post(
        "http://localhost:11434/api/embeddings",
        json={"model": model, "prompt": text}
    )
    return np.array(response.json()["embedding"])

def cosine_similarity(v1, v2):
    return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

def euclidean_distance(v1, v2):
    return np.linalg.norm(v1 - v2)

def manhattan_distance(v1, v2):
    return np.sum(np.abs(v1 - v2))

words = ['king', 'queen', 'ping']
target = 'king'
vectors = {word: get_embedding(word) for word in words}

for word in words:
    v1 = vectors[target]
    v2 = vectors[word]
    
    print(f"\n{target} vs {word}:")
    print(f"  cosine:  {cosine_similarity(v1, v2):.4f}")
    print(f"  euclid:  {euclidean_distance(v1, v2):.4f}")
    print(f"  manhat:  {manhattan_distance(v1, v2):.4f}")
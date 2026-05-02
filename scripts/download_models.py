import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import HF_EMBED_MODEL, HF_RERANKER_MODEL, HF_TOKEN

def download():
    print(f"\n{'='*60}")
    print("  ActInsight — Pre-downloading HuggingFace Models")
    print(f"{'='*60}\n")

    if HF_TOKEN:
        os.environ["HF_TOKEN"] = HF_TOKEN
        print("Using HF_TOKEN from .env\n")

    from sentence_transformers import SentenceTransformer, CrossEncoder

    print(f"1. Downloading Embedding Model: {HF_EMBED_MODEL} (~2.4 GB)...")
    try:
        SentenceTransformer(HF_EMBED_MODEL)
        print("   ✓ Embedding model ready.\n")
    except Exception as e:
        print(f"   X Error downloading embedding model: {e}\n")

    print(f"2. Downloading Reranker Model: {HF_RERANKER_MODEL} (~1.3 GB)...")
    try:
        CrossEncoder(HF_RERANKER_MODEL)
        print("   ✓ Reranker model ready.\n")
    except Exception as e:
        print(f"   X Error downloading reranker model: {e}\n")

    print(f"{'='*60}")
    print("  All models downloaded and cached in ~/.cache/huggingface")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    download()

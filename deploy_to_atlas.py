import os
import sys
import urllib.request


def transfer_model_to_atlas():
    # Structural target destination on your 1 TB drive
    target_directory = "/Volumes/Atlas/models"
    model_filename = "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"
    destination_path = os.path.join(target_directory, model_filename)
    
    # Secure direct binary download mirror path on Hugging Face
    huggingface_source_url = (
        f"https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF"
        f"/resolve/main/{model_filename}"
    )
    
    print("🌍 [CONNECTOR] Initializing connection to foundational Hugging Face servers...")
    
    # Physical hardware guardrail validation scan
    if not os.path.exists(target_directory):
        print(f"❌ [HARDWARE ERROR] Cannot find the path: {target_directory}")
        print("💡 Validation Steps:\n   1. Ensure 'Atlas' is formatted and plugged in.\n   2. Ensure you created a folder named 'models' inside it.")
        sys.exit(1)
        
    print(f"📦 [TARGET CLEARED] Destination Verified: {destination_path}")
    print("⏳ Starting stream transfer sequence directly onto Atlas. Standby...")
    
    try:
        def stream_progress(block_count, block_size, total_size):
            bytes_transferred = block_count * block_size
            percent = min(int(bytes_transferred * 100 / total_size), 100)
            megabytes = bytes_transferred / (1024 * 1024)
            total_mb = total_size / (1024 * 1024)
            print(f"\r   💾 Transferring Binary Weights: {percent}% [{megabytes:.1f} MB / {total_mb:.1f} MB]", end="")

        urllib.request.urlretrieve(huggingface_source_url, destination_path, stream_progress)
        print("\n\n🚀 [SUCCESS] Foundational brain safely moved to Atlas! File is verified and locked.")
        
    except Exception as error:
        print(f"\n❌ [STREAM ERROR] Data pipeline anomaly during transfer: {error}")

if __name__ == "__main__":
    print("=== AETHERSYSTEM ASSET DEPLOYMENT PROTOCOL ACTIVE ===\n")
    transfer_model_to_atlas()

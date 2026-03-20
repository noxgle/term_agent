#!/usr/bin/env python3
"""
Hugging Face Model Downloader for all-MiniLM-L6-v2
Downloads the model to the hf_cache directory using HF_TOKEN from .env
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from huggingface_hub import snapshot_download
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, DownloadColumn, TransferSpeedColumn

console = Console()

def load_hf_token():
    """Load HF_TOKEN from .env file"""
    load_dotenv()
    token = os.getenv('HF_TOKEN')
    if not token:
        console.print("[red]ERROR: HF_TOKEN not found in .env file[/red]")
        sys.exit(1)
    return token

def download_model(model_id: str, cache_dir: str, token: str):
    """
    Download a Hugging Face model to the specified cache directory
    
    Args:
        model_id: The Hugging Face model identifier
        cache_dir: Directory to save the model
        token: Hugging Face API token
    """
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    
    console.print(f"[cyan]Downloading model: {model_id}[/cyan]")
    console.print(f"[cyan]Cache directory: {cache_path.absolute()}[/cyan]")
    console.print()
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            console=console,
        ) as progress:
            # Download the model
            local_dir = snapshot_download(
                repo_id=model_id,
                cache_dir=str(cache_path),
                token=token,
            )
            
        console.print()
        console.print(f"[green]✓ Model downloaded successfully![/green]")
        console.print(f"[green]Location: {local_dir}[/green]")
        
        # List downloaded files
        local_path = Path(local_dir)
        if local_path.exists():
            files = list(local_path.rglob("*"))
            file_count = sum(1 for f in files if f.is_file())
            total_size = sum(f.stat().st_size for f in files if f.is_file())
            
            console.print(f"[cyan]Downloaded {file_count} files ({total_size / (1024*1024):.2f} MB)[/cyan]")
        
        return local_dir
        
    except Exception as e:
        console.print(f"[red]ERROR: Failed to download model: {e}[/red]")
        sys.exit(1)

def main():
    """Main entry point"""
    console.print("[bold cyan]═══════════════════════════════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]  Vault-Tec Hugging Face Model Downloader[/bold cyan]")
    console.print("[bold cyan]═══════════════════════════════════════════════════════════════[/bold cyan]")
    console.print()
    
    # Configuration
    MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
    CACHE_DIR = "hf_cache"
    
    # Load token
    console.print("[yellow]Loading HF_TOKEN from .env...[/yellow]")
    token = load_hf_token()
    console.print("[green]✓ Token loaded successfully[/green]")
    console.print()
    
    # Download model
    download_model(MODEL_ID, CACHE_DIR, token)
    
    console.print()
    console.print("[bold green]Download complete! Vault-Tec reminds you: Always back up your data![/bold green]")

if __name__ == "__main__":
    main()
# Private local RAG system – Complete step-by-step guide

The instructions, scripts, and tools needed to build your own private, local, and offline RAG.

Built with help from Grok (xAI), ChatGPT, Claude AI – November 2025/January 2026

## Table of Contents
- [Private local RAG system – Complete step-by-step guide](#private-local-rag-system--complete-step-by-step-guide)
  - [Table of Contents](#table-of-contents)
  - [Important assumptions](#important-assumptions)
  - [Final Architecture](#final-architecture)
  - [Prerequisites](#prerequisites)
    - [a. Install Python with pip](#a-install-python-with-pip)
    - [Step 3 – Drop the resulting .md files into your existing Markdown folder](#step-3--drop-the-resulting-md-files-into-your-existing-markdown-folder)
    - [Recommended folder structure (completely optional but nice)](#recommended-folder-structure-completely-optional-but-nice)
  - [Adding images](#adding-images)
    - [During conversion → extract images + add captions](#during-conversion--extract-images--add-captions)
      - [a. PowerPoint (.pptx) → pptx2md already does this automatically!](#a-powerpoint-pptx--pptx2md-already-does-this-automatically)
      - [b. DITA](#b-dita)
      - [c. Word (.docx)](#c-word-docx)
      - [d. PDF → extract images + add descriptive caption](#d-pdf--extract-images--add-descriptive-caption)
      - [e. Results](#e-results)
  - [Backup and Restore](#backup-and-restore)
    - [Backup DB:](#backup-db)
    - [Restore:](#restore)
  - [Troubleshooting Common Issues](#troubleshooting-common-issues)
  - [Optional enhancements](#optional-enhancements)
  - [Reference information](#reference-information)
    - [Example folder structure for model](#example-folder-structure-for-model)
    - [Scripts](#scripts)

## Important assumptions  

* This guide assumes you already have **Ollama** and **Open WebUI** running in Docker (via Docker Desktop or any other Docker engine).  
If you do **not** have them yet, run the two containers in section 5 first — they are required before anything else will work.
* mcpo is used to proxy your MCP (Model Context Protocol) servers, allowing Open WebUI to integrate custom tools like RAG search via HTTP.
* Everything else (LLM download, WebUI login, model selection, etc.) is already covered by the official Ollama/Open-WebUI docs.

The rest of this guide focuses only on:
- Setting up the permanent, high-performance vector database (TimescaleDB + pgvector)
- The incremental ingestion script
- Day-to-day workflow for growing your private knowledge base
- Integrating querying via MCP/mcpo for seamless RAG in Open WebUI

All components run locally in containers and are completely private and offline-capable.

---

## Final Architecture

![Private Local RAG Architecture](./rag_architecture4.jpg)

Architecural components:
| Component                              | Role                                                                                           | How it is used in this guide                                      |
|----------------------------------------|------------------------------------------------------------------------------------------------|--------------------------------------------------------------------|
| **Ollama**                             | Runs the LLM + embedding model (`nomic-embed-text`)                                            | Generates embeddings during ingestion + completions during queries         |
| **Open WebUI**                         | Chat UI + RAG orchestration + Knowledge/Collections management        | Front-end + queries TimescaleDB via mcpo       |
| **TimescaleDB + pgvector** (Docker)    | PostgreSQL + official pgvector extension| Stores all documents, chunks, embeddings, and metadata            |
| **HNSW index**                         | Fast approximate nearest-neighbour search inside PostgreSQL                                   | Created automatically by `rag_processor.py`                        |
| **rag_processor.py** (our script)      | Incremental ingestion tool | Chunks markdown, calls mcpo for embeddings, and upserts to DB  |
| **mcpo** | MCP-to-OpenAPI proxy | Wraps MCP servers (like mcp_rag_server.py) for HTTP access


All containers run on your laptop/desktop → **completely private**. No cloud dependencies.

## Prerequisites 

**Note: one-time only**

### a. Install Python with pip
1. Download Python 3.12+ from https://python.org/downloads/
2. During installation → **check  “Add Python to PATH”**
3. Re-open PowerShell → verify:
   ```powershell
   python --version
   pip --version
### b. Install required Python packages

 `pip install psycopg2-binary requests tqdm argparse ollama mcp mcpo`

* psycopg2-binary: For PostgreSQL connections.
* requests: For API calls (e.g., to Ollama).
* tqdm: Progress bars during ingestion.
* argparse: Command-line argument parsing.
* ollama: Python client for Ollama.
* mcp and mcpo: For MCP servers and proxying.

## Install TimescaleDB + pgvector

* Use the official TimescaleDB Docker image, which includes pgvector by default as of 2025+ releases.
* if pgai is ever needed in the future, run this command: `docker exec -it timescale-vector psql -U rag_user -d knowledge_db -c "CREATE EXTENSION IF NOT EXISTS ai CASCADE;"`

Verify:
* run command: `docker exec -it timescale-vector psql -U rag_user -d knowledge_db -c "\dx"`
  \dx should list vector and timescaledb.

## Launch All Containers

You have two equally valid options — pick **one**:

### Option A – Recommended: Single docker-compose.yml

docker-compose.yml can be found here: `\Mondi-Tech\Everyone - BSS\HPE MPC Common\AI_tools\*`

Commands:
* Navigate to the folder: `cd D:\ollama-docker`
* Start:`docker compose up -d`
  
  → All three containers start in the correct order.

* Access Open WebUI: `http://localhost:3000`

### Option B – Manual docker run commands (for debugging)

`docker run -d --name ollama -p 11434:11434 -v ollama:/root/.ollama ollama/ollama`

`docker run -d --name timescale-vector -p 5432:5432 -e POSTGRES_PASSWORD=mysecretpassword -e POSTGRES_USER=rag_user -e POSTGRES_DB=knowledge_db -v timescale-data:/var/lib/postgresql/data timescale/timescale/timescaledb:latest-pg17`

`docker run -d --name open-webui --add-host=host.docker.internal:host-gateway -p 3000:8080 -v open-webui:/app/backend/data -e OLLAMA_BASE_URL=http://host.docker.internal:11434 -e VECTOR_DB=pgvector -e PGVECTOR_URL=postgresql://rag_user:mysecretpassword@host.docker.internal:5432/knowledge_db -e RAG_EMBEDDING_MODEL=nomic-embed-text -e RAG_EMBEDDING_ENGINE=ollama ghcr.io/open-webui/open-webui:main`

→ Open `http://localhost:3000` 

→ You have a fully working private AI assistant.

## Increase Context Length 

**Note: Do this once. It is critical**

The default 2048-token context in Ollama limits retrieved context. Increase to 8192+ for better results.

Steps to fix:
Step 1: Check Your CPU Cores
1. Press Ctrl + Shift + Esc to open Task Manager
2. Click "Performance" tab
3. Click "CPU" on the left
4. Look for "Cores" - let's say you have 8 cores

Step 2: Create the Modelfile
1. Open Notepad (press `Win + R`, type `notepad`, press Enter)
2. Copy and paste this content (adjust `num_thread` based on your cores):
```
FROM llama3.1:8b

PARAMETER num_ctx 8192
PARAMETER num_thread 6 #adjust to your cores (e.g., 6 for 8-core CPU)
PARAMETER temperature 0.7
PARAMETER top_p 0.9
```
Where:
- **num_ctx 8192**: Context window size (how much text the model can "remember")
- **num_thread 6**: How many CPU threads to use for processing
- **temperature 0.7**: Controls randomness (0.7 is balanced for RAG)
- **top_p 0.9**: Nucleus sampling parameter (helps with coherence)

3. Click File → Save As
4. In the "Save as type" dropdown, select All Files (.)
5. Name it exactly: Modelfile (no extension like .txt)
6. Choose a location you can easily find (like your Desktop or Documents)
7. Click Save
8. Copy the Modelfile into the Container
`docker cp Modelfile ollama:/tmp/Modelfile`
9. Create the custom model inside the container
`docker exec ollama ollama create llama3.1-rag -f /tmp/Modelfile`
10. Verify the model was created
`docker exec ollama ollama list`


## Pull the embedding model 

**Note: Do this once.**

Run the following command:

`docker exec -it ollama ollama pull nomic-embed-text`

## RAG DB creation and ingestion script

**rag_processor.py** (for ingestion only)

**File location:**
`D:\ollama-docker\scripts\rag_processor.py`

For a full list of options for script use this command:
`python rag_processor.py --help`

**Features**

* Incremental: Upserts without deleting old documents
* Only overwrites when same file appears again (new version)
 *Smart chunking: Respects Markdown header
* HNSW indexing (for fast queries)
* Collection support (group documents logically)

**Examples:

 – **From script folder**

`python3 rag_processor.py --dsn "postgresql://rag_user:mysecretpassword@localhost:5432/knowledge_db" --folder "D:\documents" --collection "documents" --version "v1"`

 – **Full path**

`python "CD_\ollama-docker\scripts\rag_processor.py --dsn "postgresql://rag_user:mysecretpassword@localhost:5432/knowledge_db" --folder "D:\documents" --collection "documents" --version "v1"`

 – **If added to PATH**

`rag_processor.py --folder "D:\documents" --collection "documents" --version "v1"`

First run creates tables/indexes automatically.

## Document Folder Structure (Recommended)

**Note: You can name the folder anything you like (documents, telecom-docs, knowledge-base, etc.).
Just use the exact same path every time you run the script.**

Root: D:\documents\

**Example:**

```
D:\documents\
├── NWDAF\
│   ├── Document 1\index.md
│   ├── Document 2\index.md
│   └── ...
├── CHF\
│   ├── Document 1\index.md
│   └── ...
└── FutureProduct\
    └── ...
```

**Rule:** One subfolder per document set -> one index.md per set -> one collection

* Subfolder per topic/product.
* Processes all .md files recursively.
* Metadata includes "product": "NWDAF" for filtering in Open WebUI.

## Daily Workflow - adding new documents (append only)

### a. Copy new files/folders:
`robocopy "C:\Path\To\Latest\Export" "D:\documents\NewTopic" /MIR /J`

### b. Run ingestion
`python3 rag_processor.py --dsn "postgresql://rag_user:mysecretpassword@localhost:5432/knowledge_db" --folder "D:\documents" --collection "documents" --version "v1"`

* New content is available in Open WebUI immediately.
* All previous knowledge remains intact.
* Repeat for every new document.

## Update an Existing Document (replace old version)
### a. Delete old version (safe)
`Remove-Item -Recurse -Force "D:\documents\OldTopic\"`

### b. Copy new version
`robocopy "C:\Downloads\New_doc_v2" "D:\documents\OldTopice" /MIR /J`

### c. Re-run script
`python rag_processor.py --dsn "postgresql://rag_user:mysecretpassword@localhost:5432/knowledge_db" --folder "D:\documents\OldTopic" --collection "documents" --version "v1"`

Upserts replace matching chunks.

## mcpo servers
* Query server (mcp_rag_server.py): 
  - Use this tool for knowledge base context.

  - Location: `D:\ollama-docker\scripts\mcp_rag_server.py`

  - Run: `mcpo --port 8001 --host 0.0.0.0 -- python mcp_rag_server.py`

* Vale server (style/policy tool):
   - Use this to check text for style, formatting, spelling, or policy violations.

   - Run: `mcpo --port 8002 -- vale-cli`

mcpo exposes MCP stdio as OpenAPI HTTP for Open WebUI integraion.

Add API keys for security: `api-key "yoursecret"`.
## Using the system

* Open WebUI -> Go to http://localhost:3000
* register tools in Open WebUI: Admin Panel -> Settings -> External Tools
  - MCP_RAG_SERVER
    URL: http://host.docker.internal:8001
  - Vale-MCP Server Tool
    URL: http://host.docker.internal:8002
* Create a model → configure it as in this example:
![Open WebUI Model config example](./open_webui_model_config_example.png)
* Chat: Enable tools via + integrations icon

  → remember to use best practice in prompting
  - example prompt: “Quote the exact passages from the knowledge base that describe UE Location prediction for targeted paging, and summarize them. Cite the document.”
  - example usage:
    Query 1 — Document search
    Question: What does the knowledge base say about UE location prediction for targeted paging?

   Model calls search_documents tool automatically

   Query 2 — Style check
   Check this paragraph for style and policy violations:
   "The network operator must configure UTRA cells optimally..."

   The model will call mcp_vale → returns Vale rule violations

## Useful Docker commands (maintenance & troubleshooting)

For docker-compose (in D\ollama-docker):

| Goal                                          | Command                                                        |
|-----------------------------------------------|----------------------------------------------------------------|
| Start everything                              | `docker compose up -d`                                         |
| Stop everything (data stays safe)             | `docker compose down`                                          |
| Restart everything                            | `docker compose restart`                                       |
| View live logs                                | `docker compose logs -f`                                       |
| **Full nuclear reset** (deletes models + knowledge base + WebUI data) | `docker compose down -v` |
| **Delete only the vector database** (keep models & WebUI) | `docker compose down && docker volume rm <project>_timescale-data` |

### Legacy way → manual `docker run` commands

| Goal                                          | Command                                                                 |
|-----------------------------------------------|-------------------------------------------------------------------------|
| Stop the database container                   | `docker stop timescale-vector`                                          |
| Start it again                                | `docker start timescale-vector`                                         |
| Restart it                                    | `docker restart timescale-vector`                                       |
| Remove container (data stays)                 | `docker rm timescale-vector`                                            |
| **Delete the entire knowledge base forever** | `docker volume rm timescale-data`                                       |
| Full wipe (container + data)                  | `docker stop timescale-vector; docker rm timescale-vector; docker volume rm timescale-data` |

### General useful commands

| Action                                      | Command                            |
|---------------------------------------------|------------------------------------|
| Show running containers                     | `docker ps`                        |
| Show all containers (running + stopped)     | `docker ps -a`                     |
| List all volumes                            | `docker volume ls`                 |
| Inspect the knowledge base volume           | `docker volume inspect timescale-data` |

### Persistent volumes

| docker-compose volume name pattern | Manual-run volume name | What it stores                                      |
|------------------------------------|------------------------|-----------------------------------------------------|
| `<foldername>_ollama-data`         | `ollama`               | All LLMs + `nomic-embed-text` model                 |
| `<foldername>_timescale-data`      | `timescale-data`       | **Your entire RAG knowledge base** (never delete unless you really mean it) |
| `<foldername>_open-webui-data`     | `open-webui`           | WebUI users, settings, chat history, themes, etc.   |

**Golden rule**  
- `docker compose down` → everything stops, **all data stays**  
- `docker compose down -v` → **everything disappears** → perfect clean slate

**Key point:**  
Your entire vector database (all documents, embeddings, collections) lives safely inside the Docker volume `timescale-data`.  
→ You can stop, remove, or even recreate the container as many times as you want — **your data stays 100 % intact** until you deliberately run `docker volume rm timescale-data`.

## Useful psql commands

* To enter psql in PowerShell enter: `psql -h localhost -U rag_user -d knowledge_db`
* Commands:

List extensions: `\dx`
List tables: `\dt`
Describe table: `\d document_chunk`
Query chunks: `SELECT * FROM document_chunk LIMIT 5;`
Count chunks: `SELECT COUNT(*) FROM document_chunk;`
Collections: `SELECT DISTINCT collection_name FROM document_chunk;`
Drop table (careful!): `DROP TABLE document_chunk;`
Exit: `\q` or Ctrl+D

## Ingesting Word, PowerPoint, Excel, DITA, and PDF

Convert to Markdown first; rag_processor.py handles .md.

### Step 1 –One-time installs:
`pip install pandoc pptx2md python-docx docx2md pymupdf pandas openpyxl`

### Step 2 –Conversions:

```powershell
# Word → Markdown
pandoc "Spec 123.docx" -t markdown -o "Spec_123.md"

# PowerPoint → Markdown
pptx2md "Slides.pptx" -o processed/

# Excel → Markdown tables
python -c "import pandas as pd; df = pd.read_excel('Data.xlsx'); print(df.to_markdown(index=False))" > Data.md

# PDF → beautiful Markdown (2025 quality)
python -c "import fitz; doc=fitz.open('spec.pdf'); text=''; [text:=text+block[4]+'\n\n' for page in doc for block in page.get_text('blocks')]; open('spec.md','w',encoding='utf-8').write(text)"

# DITA → Markdown (simple)
dita --input=source.dita --format=markdown --output=processed/
```
### Step 3 – Drop the resulting .md files into your existing Markdown folder

Run your ingestion script: `rag_processor.py`.

Result: Word, PPT, Excel, DITA, and PDF all become first-class citizens in your private knowledge base with zero changes to the rest of the system.

### Recommended folder structure (completely optional but nice)

```
D:\documents\          ← one single root folder
├── 00-inbox\                         ← drop new .docx/.pptx/.xlsx/.pdf here
├── 10-telecom-specs\
   ├── image_001.png
   └── document_001.md
├── 20-product-guides\
├── 30-standards\
└── 99-archive\
```

**Workflow:**
* Convert files from 00-inbox
* Move the resulting .md files anywhere inside the tree
* Re-run rag_processor.py -> everything is automatically added/updated

You can drop converted Word, Excel, DITA, PDF → Markdown files anywhere inside the documents folder (or subfolders). The ingestion script processes everything recursively. No index.md or special folders required.

Leave all original PDF/Word/Excel/PowerPoint/DITA files in the 00-inbox folder. The ingestion script automatically ignores them and only processes the .md files.

## Adding images

The current text-only RAG already handles images perfectly. The images need to be saved next to the Markdown files with correct relative links.

### During conversion → extract images + add captions

#### a. PowerPoint (.pptx) → pptx2md already does this automatically!
In PowerShell: `pptx2md "Slides.pptx" -o processed/`
* creates Slides.md
* all images in a subfolder with image links

#### b. DITA  
* Convert DITA to Markdown with DITA-OT or any modern plugin or tool such as Oxygen Author XML
* DITA → Markdown tools create a folder like `_images/Document-Name/`.  
*→* Contains correct relative links like ![…](../_images/5G-Core-Standard/figure-01-network.png)
*→* Just drop the .md file + its _images folder into your documents\ tree — Open WebUI displays everything perfectly.

**DITA folder structure**

```
D:\my-private-rag\documents\
├── 00-inbox\
│   ├── 5G-Core-Standard.dita
│   └── 5G-Core-Standard.md          ← generated by DITA-OT
│       └── _images/
│           └── 5G-Core-Standard/
│               ├── figure-01.png
│               └── figure-02.png
├── 10-telecom-specs\
│   └── Requirements-v18.md
│       └── _images/
│           └── Requirements-v18/
└── ...
```

#### c. Word (.docx)
* Run below command `python - <<'PY' "Requirements v45.docx"`

```powershell
# Extract ALL images from a .docx + print ready-to-paste Markdown links
python - <<'PY' "Your File.docx"
import zipfile, sys, pathlib, re
from pathlib import Path

if len(sys.argv) != 2:
    print("Usage: python extract_docx_images.py \"My Document.docx\"")
    sys.exit(1)

docx_path = Path(sys.argv[1])
out = docx_path.parent / "extracted_images"
out.mkdir(exist_ok=True)

with zipfile.ZipFile(docx_path) as z:
    i = 0
    for name in z.namelist():
        if name.startswith("word/media/") and not name.endswith('/'):
            i += 1
            ext = Path(name).suffix or ".png"
            img_data = z.read(name)
            img_file = out / f"image_{i:03d}{ext}"
            img_file.write_bytes(img_data)
            rel = img_file.name
            print(f"![Figure {i}: replace with real caption]({rel})")
PY
```
* Creates a folder extracted_images/ next to the .docx
* Prints perfectly formatted Markdown image links you can copy-paste into your converted .md file

#### d. PDF → extract images + add descriptive caption
In PowerShell: `python extract_pdf_images.py "spec.pdf" "processed/"`
**(script can be found here: d:\ollama-docker\dockerfile\extract_pdf_images.py)**

#### e. Results

* The script rag_processor.py ingests the Markdown + the rich captions
* Users ask: “Show me the network diagram”, Open WebUI displays the actual image automatically because the Markdown contains the valid image

## Backup and Restore

### Backup DB:

* `docker exec -t timescale-vector pg_dump -U rag_user knowledge_db > backup.sql`
* Or volume: `docker cp timescale-vector:/var/lib/postgresql/data`. (stop container first).

### Restore:

* Create new DB/container.
* `docker exec -i timescale-vector psql -U rag_user -d knowledge_db < backup.sql`

Automate: Add cron/PS script for daily backups.

## Troubleshooting Common Issues

* Embedding errors: Check Ollama logs (docker logs ollama); ensure nomic-embed-text pulled.
* DB connection: Verify DSN; test with psql.
* Tool not calling: Use Native function calling in Open WebUI; add system prompt: "Use search_documents for DB queries."
* Slow queries: Increase HNSW ef_search (edit rag_processor.py); limit results.
* Container crashes: Check docker logs <name>; increase RAM in Docker Desktop.
* mcpo fails: Ensure ports free; add --host 0.0.0.0.
* Outdated tools: Update images: docker compose pull.

## Optional enhancements

* Keep multiple versions side-by-side:
Use different collection names: --collection "Specs April 2025"
* Global search: Model with all collections selected.
* Faster DB: Tune HNSW (m=16, ef_construction=64).
* Security: Add API keys to mcpo; use HTTPS proxy.
* Monitoring: Add Prometheus to TimescaleDB.
* Multi-modal: Extend for images via CLIP embeddings (future script).

## Reference information

### Example folder structure for model
  
```
D:\ollama-docker
├── docker-compose.yml          # Essential – starts/stops all containers
├── Modelfile                   # Essential – for recreating custom llama3.1-rag model (8192 context). It is needed if you ever recreate the model.
├── ollama-data\                # Docker volume (LLM models)
├── open-webui-data\            # Docker volume (WebUI settings, chats)
├── timescale-data\             # Docker volume (your entire knowledge base – never delete!)
└── scripts
├── check_db.py             # Useful diagnostic tool
├── cleanup_postgres.ps1    # Useful maintenance script
├── extract_pdf_images.py   # Useful for extracting images from PDFs.
├── mcp_rag_server.py       # Critical – RAG query server (used with mcpo)
└── rag_processor.py        # Critical – document ingestion script
```

### Scripts

| Script name | Description | 
|----------------------------------------|------------------------------------------------------------------------------------------------|
| check_db.py | Quick diagnostic script to verify table structure, counts, collections, etc. Very useful for troubleshooting. | 
| cleanup_postgres.ps1 | Handy for cleaning up old test data or resetting the DB without losing the volume. Nice to have for maintenance. | 
| extract_pdf_images.py | Useful helper script for extracting images from PDFs (mentioned in your guide under "Adding images"). Keep if you ever process PDFs with figures/diagrams. | 
| mcp_rag_server.py | This is your current MCP RAG query server – the one you run with mcpo --port 8001 -- python mcp_rag_server.py. This is how Open WebUI searches your knowledge base. Critical – do not delete! | 
| rag_processor.py | Your current ingestion script – chunks Markdown, generates embeddings via Ollama, upserts to TimescaleDB, creates HNSW index. You use this daily/weekly to add or update documents. Critical – keep! | 


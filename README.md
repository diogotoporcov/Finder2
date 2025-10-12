# Finder v2

[![Python](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-ready-336791.svg)](https://www.postgresql.org/)
[![CUDA](https://img.shields.io/badge/CUDA-12.8-76b900.svg)](https://developer.nvidia.com/cuda-toolkit)
[![NVIDIA Triton Server](https://img.shields.io/badge/NVIDIA%20Triton%20Server-ready-76b900.svg)](https://developer.nvidia.com/nvidia-triton-inference-server)


Finder v2 is a highly efficient image management system designed for organizing, storing, and preventing duplicate images in large databases. It leverages advanced techniques like visual feature extraction and semantic search using deep learning models to identify and prevent duplicates across multiple layers: SHA-256, pHash, and embedding cosine similarity. The system offers seamless image upload, storage, and retrieval with a strong focus on performance and scalability.

---

## Sumary

1. [Core Features](#core-features)
2. [Dependencies and Versions](#dependencies-and-versions)
3. [Installation Guide](#finder-v2-installation-guide)
4. [Running NVIDIA Triton Server](#running-nvidia-triton-server)
5. [Running Finder v2](#running-finder-v2)
6. [Endpoints](#rest-api-endpoints)
7. [Future Plans](#future-plans)
8. [License](#license)

---

## Core Features

* User-scoped image collections.
* Automatic duplicate image detection and prevention using a three-layer check system:
  * **SHA-256** for exact binary matches.
  * **pHash** for visually similar images within a small Hamming distance.
  * **Embedding cosine similarity** for semantic duplicates.\
    The system can be toggled per upload with the `detect_duplicates` parameter, letting users choose whether to enforce duplicate blocking or allow similar images intentionally.
* Fully asynchronous upload, storage, embedding extraction and database operations.
* Triton-based CLIP embeddings for semantic similarity search, capable of batching and parallelizing multiple image embeddings efficiently across requests.
* Smart embedding pipeline that automatically handles both single-image and multi-image uploads using dynamic batching on the Triton Inference Server.
* Hierarchical storage layout `/storage/collections/{user_id}/{collection_id}/{filename}`.
* Security enforced through JWT-based authentication with short-lived access tokens and hashed refresh tokens.
* Passwords protected with Argon2id hashing and unique per-user salt.
* Each user can only access their own collections and images.



---

## Dependencies and Versions

| Component                 | Version / Type | Notes                                                                                      |
|---------------------------|----------------|--------------------------------------------------------------------------------------------|
| **Python**                | 3.11.x         | Required                                                                                   |
| **PostgreSQL**            | ≥14            | Tested in version 17.6                                                                     |
| **pgvector**              | Latest         | [Installation guide](https://github.com/pgvector/pgvector?tab=readme-ov-file#installation) |
| **Docker**                | Latest         | Needed for Triton container                                                                |
| **CUDA Toolkit**          | 12.8           | Required only if using GPU.                                                                |
| **PyTorch / TorchVision** | CUDA-matched   | See compatibility below                                                                    |
| **NVIDIA Triton Server**  | 25.05          | See compatibility below                                                                    |


If your device does not support CUDA 12.8, select a CUDA version compatible with your hardware and pick PyTorch / TorchVision builds matching that CUDA version.

[1]: https://developer.nvidia.com/cuda-12-8-0-download-archive "CUDA Toolkit 12.8 Downloads - NVIDIA Developer"

---

### Picking Correct PyTorch and TorchVision Versions

> **Note:** Project was tested with CUDA 12.8 using the following packages.

Official wheel indices:

* [PyTorch wheels](https://download.pytorch.org/whl/torch)
* [TorchVision wheels](https://download.pytorch.org/whl/torchvision)

**GPU (CUDA 12.8)**

```txt
torch==2.8.0+cu128
torchvision==0.23.0+cu128
```

**CPU-only**

```txt
torch==2.8.0+cpu
torchvision==0.23.0+cpu
```

---

### Picking Correct NVIDIA Triton Version

Use an image that matches your PyTorch CUDA build:

| System Type     | Recommended Image                           | CUDA Compatibility | Notes                          |
|-----------------|:--------------------------------------------|:-------------------|--------------------------------|
| **GPU-enabled** | `nvcr.io/nvidia/tritonserver:25.05-py3`     | CUDA 12.8          | Includes CUDA, cuDNN, TensorRT |
| **CPU-only**    | `nvcr.io/nvidia/tritonserver:25.05-py3-cpu` | N/A                | For systems without NVIDIA GPU |

Keep PyTorch and Triton on the same CUDA minor version (e.g., `cu128` ↔ Triton CUDA 12.8).

> **Note:** The official Triton image is large and includes many backends. For lighter setups, you can build a custom Triton Server with only the needed components from the [Triton source](https://github.com/triton-inference-server/server).


---

## Finder v2 Installation Guide

### 1. Clone repository

```bash
git clone https://github.com/diogotoporcov/Finder2.git
cd finder2
```

### 2. Configure environment

Duplicate or rename [`.env.example`](.env.example) to `.env`:

Then edit `.env` to match your setup:

* Database settings:

  ```dotenv
  DB_HOST=localhost
  POSTGRES_DB=finder2
  POSTGRES_USER=finder2
  POSTGRES_PASSWORD=finder2
  POSTGRES_PORT=5432
  ```
  
* Security:
  ```dotenv
  JWT_SECRET=
  JWT_ALG=HS512
  ACCESS_TTL_MIN=15
  REFRESH_TTL_DAYS=30
  ```
  
  > **Note:** You can generate a secure JWT secret with:
  > ```bash
  > python -c "import secrets; print(secrets.token_urlsafe(64))"
  > ```


* Upload configuration:

  ```dotenv
  ALLOWED_MIME_TYPES=image/jpeg,image/png,image/webp,image/bmp,image/tiff
  MAX_FILE_SIZE=20MB
  MAX_UPLOAD_FILES=10
  STORAGE_PATH=/storage
  ```

  > **Note:** The listed MIME types in [`.env.example`](.env.example) have been tested and verified. Other formats may have unknown compatibility and could cause upload or embedding errors.

---

### 3. Create and activate virtual environment

**Linux / macOS**

```bash
python -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell)**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

---

### 4. Install dependencies

> **Note:** Ensure the correct `torch` and `torchvision` versions are set in `requirements.txt`. \
> Refer to **[Picking Correct PyTorch and TorchVision Versions](#picking-correct-pytorch-and-torchvision-versions)** for guidance on selecting the right build for your system.

Then install all dependencies:

```bash
pip install -r requirements.txt
```


---

### 5. Export clip model to ONNX

After installing dependencies, run the following command from the root directory to export the model as an ONNX file:

```bash
python ./models/embedder/export.py
```

This will export the model as an ONNX file, which is necessary for running the image embedding process through the Triton server.

---

### 6. Run database migrations

> **Note:** Ensure PostgreSQL and `pgvector` are installed.

```bash
alembic upgrade head
```

---

## Running NVIDIA Triton Server

> **Note:** Ensure Docker is running and the correct `tritonserver` version is used for your setup. \
Refer to **[Picking Correct NVIDIA Triton Version](#picking-correct-nvidia-triton-version)** for guidance on selecting the right build for your system.

> For CPU-only systems, replace `-py3` with `-py3-cpu`.

**Linux / macOS**

```bash
docker run --rm -it -p8000:8000 -p8001:8001 -p8002:8002 \
  -v "$(pwd)/models:/models" \
  nvcr.io/nvidia/tritonserver:25.05-py3 \
  tritonserver --model-repository=/models
```

**Windows (PowerShell)**

```powershell
docker run --rm -it -p8000:8000 -p8001:8001 -p8002:8002 `
  -v ${PWD}\models:/models `
  nvcr.io/nvidia/tritonserver:25.05-py3 `
  tritonserver --model-repository=/models
```

> **Note:** Triton exposes:
> * **HTTP API** on port 8000
> * **GRPC API** on port 8001
> * **Metrics** on port 8002

---

## Running Finder v2

Start the application with:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8080
```

> **Note:** Access at: [http://localhost:8080](http://localhost:8080)

---

## REST API Endpoints

### Authentication (`/auth`)

| Method | Path             | Description           | Input                                                         |
|--------|:-----------------|-----------------------|---------------------------------------------------------------|
| `POST` | `/auth/register` | Register a new user   | **Body**: `username: str`, `email: EmailStr`, `password: str` |
| `POST` | `/auth/login`    | Login to get tokens   | **Body**: `username: str`, `password: str`                    |
| `POST` | `/auth/refresh`  | Refresh the JWT token | **Body**: `refresh_token: str`                                |

---

### Users (`/users`)

| Method   | Path               | Description             | Input                                                            |
|----------|--------------------|-------------------------|------------------------------------------------------------------|
| `PATCH`  | `/users/{user_id}` | Update user details     | **Body**: `username: Optional[str]`, `email: Optional[EmailStr]` |
| `DELETE` | `/users/{user_id}` | Delete the user account |                                                                  |

---

### Collections (`/collections`)

| `Method` | Path                           | Description                   | Input                                                        |
|----------|--------------------------------|-------------------------------|--------------------------------------------------------------|
| `POST`   | `/collections/`                | Create a new collection       | **Body**: `name: str`, `tags: Optional[List[str]]`           |
| `PATCH`  | `/collections/{collection_id}` | Update an existing collection | **Body**: `name: Optional[str]`, `tags: Optional[List[str]]` |
| `DELETE` | `/collections/{collection_id}` | Delete a collection           |                                                              |

---

### Images (`/images`)

| Method   | Path                 | Description                           | Input                                                                                                                                    |
|----------|----------------------|---------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------|
| `GET`    | `/images/{image_id}` | Retrieve an image                     |                                                                                                                                          |
| `GET`    | `/images/`           | List all images in user's collections |                                                                                                                                          |
| `POST`   | `/images/`           | Upload new images                     | **Body**: `files: List[UploadFile]` <br> **Query**: `target_collection: Union[uuid.UUID, Literal['DEFAULT']]`, `detect_duplicates: bool` |
| `PATCH`  | `/images/{image_id}` | Update image metadata (tags)          | **Body**: `tags: Optional[List[str]]`                                                                                                    |
| `DELETE` | `/images/{image_id}` | Delete an image                       |                                                                                                                                          |


---

# Future Plans

* Implement permissions to allow users to access collections belonging to other users.
* Develop a user interface (web-based) for improved accessibility and interaction.
* Integrate Docker and Kubernetes to streamline project management across multiple devices and environments.
* Enhance function documentation to improve code maintainability and clarity.
* Establish automated testing using pytest, with CI/CD integration via GitHub Actions to trigger tests after each commit.
* Develop a system to automatically detect and handle duplicate entries within the platform.

---

## License

This project is licensed under the MIT License - See [LICENSE](LICENSE) for more information.
